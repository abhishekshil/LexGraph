"""Generation provider abstractions.

Every provider implements :class:`LLMProvider` and is stateless w.r.t. requests.
Heavy deps (``openai``, ``torch``, ``transformers``) are imported lazily inside
each provider so importing this module never pulls GPU runtimes.

Provider selection is centralised in :func:`get_provider` based on
``settings.generation_provider`` and availability of API keys / local models.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from ..core import get_logger, settings
from .prompts import SYSTEM_PROMPT, user_prompt


log = get_logger("generation.provider")


class LLMProvider(Protocol):
    name: str

    async def complete(self, *, question: str, evidence_pack_text: str) -> str:
        ...


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class OpenAIProvider:
    """Thin async wrapper over ``openai.AsyncOpenAI``.

    Intentionally *doesn't* retry or stream — the GenerationAgent is single-shot
    per query; retries belong at the event-bus level.
    """

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.generation_model
        self.temperature = temperature

    async def complete(self, *, question: str, evidence_pack_text: str) -> str:
        import openai  # type: ignore

        client = openai.AsyncOpenAI(api_key=self.api_key)
        resp = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(question, evidence_pack_text)},
            ],
            temperature=self.temperature,
        )
        return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Local HuggingFace Instruct (Llama-3 / Qwen / Phi-3 class)
# ---------------------------------------------------------------------------


class HFProvider:
    """Local HF instruct generator.

    Loads the model once and reuses it (the whole process is a worker, so this
    cost amortises). Uses the tokenizer's ``apply_chat_template`` so the same
    model string works for Llama-3, Qwen, Phi-3, Mistral-Instruct, etc.

    Falls back to :class:`StubProvider` if ``torch`` / ``transformers`` are not
    available or the model fails to load — the generator always remains
    callable, it just degrades to a deterministic grounded summary.
    """

    name = "hf"

    def __init__(
        self,
        *,
        model: str | None = None,
        max_new_tokens: int = 640,
        temperature: float = 0.1,
        device: str | None = None,
    ) -> None:
        self.model_name = model or settings.hf_generation_model
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.device = device
        self._tok = None  # type: ignore[assignment]
        self._model = None  # type: ignore[assignment]
        self._fallback: StubProvider | None = None

    def _ensure(self) -> bool:
        if self._fallback is not None:
            return False
        if self._model is not None:
            return True
        try:
            import torch  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except Exception as e:  # noqa: BLE001
            log.warning("hf.transformers_unavailable", error=str(e))
            self._fallback = StubProvider()
            return False

        try:
            tok = AutoTokenizer.from_pretrained(self.model_name)
            dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
            device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
            model = AutoModelForCausalLM.from_pretrained(
                self.model_name, torch_dtype=dtype
            ).to(device)
            model.eval()
        except Exception as e:  # noqa: BLE001
            log.warning(
                "hf.load_failed",
                model=self.model_name,
                error=str(e),
            )
            self._fallback = StubProvider()
            return False

        self._tok = tok
        self._model = model
        self._device = device  # type: ignore[attr-defined]
        log.info("hf.ready", model=self.model_name, device=device)
        return True

    async def complete(self, *, question: str, evidence_pack_text: str) -> str:
        if not self._ensure():
            assert self._fallback is not None
            return await self._fallback.complete(
                question=question, evidence_pack_text=evidence_pack_text
            )

        import asyncio

        def _run() -> str:
            import torch  # type: ignore

            assert self._tok is not None and self._model is not None
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(question, evidence_pack_text)},
            ]
            # Chat template produces the model-specific formatting.
            prompt = self._tok.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            inputs = self._tok(prompt, return_tensors="pt").to(self._device)  # type: ignore[attr-defined]
            with torch.no_grad():
                out = self._model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=self.temperature > 0.0,
                    temperature=self.temperature,
                    pad_token_id=self._tok.eos_token_id,
                )
            # Strip the prompt echo.
            gen_ids = out[0][inputs["input_ids"].shape[1] :]
            return self._tok.decode(gen_ids, skip_special_tokens=True)

        return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Deterministic stub (always available, grounded by construction)
# ---------------------------------------------------------------------------


class StubProvider:
    """Produces a deterministic, grounded "answer" directly from the pack.

    The output is structured so the enforcer accepts it unchanged:
    every claim cites a span, nothing is invented, confidence defaults to LOW.
    """

    name = "stub"

    async def complete(self, *, question: str, evidence_pack_text: str) -> str:
        markers = _markers_in(evidence_pack_text)
        if not markers:
            return (
                "Answer: Insufficient evidence was retrieved to answer the "
                "question. [NO_CITATIONS]\n"
                "Legal basis:\n"
                "Confidence: LOW\n"
                "Insufficient evidence: YES\n"
            )
        marker_list = ", ".join(f"[{m}]" for m in markers)
        lines: list[str] = []
        lines.append(
            f"Answer: The retrieved authorities {marker_list} bear on the "
            f"question asked; the excerpts below are reproduced verbatim, with "
            f"the binding statute text taking precedence over commentary. "
            + " ".join(f"[{m}]" for m in markers)
        )
        lines.append("Legal basis:")
        for m in markers:
            lines.append(f"- [{m}] cited excerpt — see pack.")
        lines.append("Confidence: LOW")
        lines.append("Insufficient evidence: NO")
        return "\n".join(lines)


def _markers_in(pack_text: str) -> list[str]:
    import re

    out: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"\[S(\d+)\]", pack_text):
        label = f"S{m.group(1)}"
        if label in seen:
            continue
        seen.add(label)
        out.append(label)
    return out


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@lru_cache
def get_provider() -> LLMProvider:
    """Return the provider selected by ``settings.generation_provider``.

    * ``openai`` — requires ``openai_api_key``; otherwise falls back to stub.
    * ``hf``     — lazy-loads a local HF model; falls back to stub on import
      or load failure.
    * ``stub``   — always available, deterministic, grounded.

    Selecting ``auto`` picks openai if a key exists, else stub.
    """
    provider = (settings.generation_provider or "auto").lower()
    if provider in {"auto", ""}:
        provider = "openai" if settings.openai_api_key else "stub"
    if provider == "openai":
        if not settings.openai_api_key:
            log.warning("generation.openai_no_key_using_stub")
            return StubProvider()
        return OpenAIProvider()
    if provider == "hf":
        return HFProvider()
    if provider == "stub":
        return StubProvider()
    log.warning("generation.unknown_provider_using_stub", provider=provider)
    return StubProvider()


def reset_provider_cache() -> None:
    get_provider.cache_clear()
