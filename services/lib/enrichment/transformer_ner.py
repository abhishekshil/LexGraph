"""Pluggable transformer-based legal NER.

Wraps a HuggingFace ``token-classification`` model (any checkpoint fine-tuned
for NER is supported) behind the same interface as the regex-based
:class:`~services.lib.enrichment.legal_ner.LegalNER`. When the model fails to
load, or when the feature flag is off, the extractor returns an empty list
and the caller falls back to the regex baseline — so the whole pipeline
keeps working in air-gapped / CI environments.

Recommended models (configure with ``ENRICH_NER_MODEL``):

* ``opennyaiorg/en_legal_ner_trf`` — OpenNyAI's Indian legal NER (spaCy
  transformer pipeline). Not directly loadable with ``AutoModel``; use a
  community HF fine-tune of InLegalBERT instead, or swap in a custom class.
* ``dslim/bert-base-NER`` — generic English NER, good fallback.
* ``Jean-Baptiste/roberta-large-ner-english`` — stronger generic NER.
* any InLegalBERT fine-tune for token classification.

Label mapping. The wrapper maps a small universe of upstream NER labels onto
the node-type taxonomy used by the graph writer. Unknown labels are passed
through unchanged so custom checkpoints can introduce their own types
without a code change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Any

from ..core import get_logger
from .legal_ner import Entity

if TYPE_CHECKING:  # pragma: no cover - only for type checkers
    from transformers import Pipeline


log = get_logger(__name__)


# Label translation. Keys are upper-cased labels from the upstream model;
# values are node types used by the LexGraph ontology. Unknown labels pass
# through verbatim.
_LABEL_MAP: dict[str, str] = {
    # Generic BERT-NER / CoNLL
    "PER": "Person",
    "PERSON": "Person",
    "ORG": "Organisation",
    "ORGANIZATION": "Organisation",
    "ORGANISATION": "Organisation",
    "LOC": "Location",
    "LOCATION": "Location",
    "GPE": "Location",
    "MISC": "Misc",
    "DATE": "Date",
    # Legal-domain (OpenNyAI / InLegal-NER-like)
    "COURT": "Court",
    "JUDGE": "Judge",
    "LAWYER": "Lawyer",
    "PETITIONER": "Party",
    "RESPONDENT": "Party",
    "APPELLANT": "Party",
    "DEFENDANT": "Party",
    "WITNESS": "Witness",
    "STATUTE": "Act",
    "ACT": "Act",
    "PROVISION": "Section",
    "SECTION": "Section",
    "PRECEDENT": "Case",
    "CASE": "Case",
    "CASE_NUMBER": "CaseNumber",
    "CRIME": "Offence",
    "OFFENCE": "Offence",
    "OTHER_PERSON": "Person",
}


# Some models put the petitioner/respondent distinction in the label itself.
# Preserve it as an ``extra`` attribute on the entity.
_ROLE_MAP: dict[str, str] = {
    "PETITIONER": "petitioner",
    "APPELLANT": "petitioner",
    "RESPONDENT": "respondent",
    "DEFENDANT": "respondent",
}


@dataclass
class _LoadedPipeline:
    pipe: Any            # transformers.Pipeline
    aggregation: str     # aggregation strategy actually used
    model_name: str


class TransformerLegalNER:
    """Lazy-loading NER. Safe to import even without ``transformers`` installed.

    Parameters
    ----------
    model_name:
        HuggingFace model id or local path. If ``None``, reads
        ``ENRICH_NER_MODEL`` from the environment; if that is unset, the
        extractor stays disabled and :meth:`extract` returns ``[]``.
    enabled:
        When ``False`` (default taken from ``ENRICH_NER_ENABLED`` env var),
        :meth:`extract` is a no-op. This lets CI and unit tests run without
        downloading model weights.
    aggregation_strategy:
        HuggingFace aggregation strategy; ``"simple"`` merges sub-words into
        whole-entity spans with start/end offsets into the original text.
    device:
        ``"cpu"`` | ``"cuda"`` | ``"mps"``. ``None`` auto-detects.
    """

    def __init__(
        self,
        model_name: str | None = None,
        enabled: bool | None = None,
        aggregation_strategy: str = "simple",
        device: str | None = None,
    ) -> None:
        self.model_name = model_name or os.getenv("ENRICH_NER_MODEL") or ""
        if enabled is None:
            enabled = _env_bool("ENRICH_NER_ENABLED", default=False)
        self.enabled = bool(enabled) and bool(self.model_name)
        self.aggregation = aggregation_strategy
        self.device = device
        self._pipeline: _LoadedPipeline | None = None
        self._load_failed = False
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, text: str) -> list[Entity]:
        """Run NER over ``text``. Returns ``[]`` if disabled or load failed.

        The wrapper never raises — a model-load or inference failure is logged
        at WARN and the caller continues with an empty result, so the regex
        NER baseline remains authoritative.
        """
        if not self.enabled or self._load_failed:
            return []
        if not text or not text.strip():
            return []

        loaded = self._ensure_loaded()
        if loaded is None:
            return []

        try:
            raw = loaded.pipe(text)
        except Exception as exc:  # noqa: BLE001 - runtime inference errors
            log.warning(
                "transformer_ner.inference_failed",
                model=loaded.model_name,
                error=str(exc),
            )
            return []

        return _to_entities(raw, text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> _LoadedPipeline | None:
        if self._pipeline is not None:
            return self._pipeline
        with self._lock:
            if self._pipeline is not None:
                return self._pipeline
            if self._load_failed:
                return None
            try:
                from transformers import (  # type: ignore[import-not-found]
                    AutoModelForTokenClassification,
                    AutoTokenizer,
                    pipeline,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "transformer_ner.transformers_unavailable",
                    error=str(exc),
                )
                self._load_failed = True
                return None

            try:
                tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                model = AutoModelForTokenClassification.from_pretrained(
                    self.model_name
                )
                pipe = pipeline(
                    "token-classification",
                    model=model,
                    tokenizer=tokenizer,
                    aggregation_strategy=self.aggregation,
                    device=_resolve_device(self.device),
                )
            except Exception as exc:  # noqa: BLE001 - network / cache errors
                log.warning(
                    "transformer_ner.load_failed",
                    model=self.model_name,
                    error=str(exc),
                )
                self._load_failed = True
                return None

            self._pipeline = _LoadedPipeline(
                pipe=pipe,
                aggregation=self.aggregation,
                model_name=self.model_name,
            )
            log.info(
                "transformer_ner.loaded",
                model=self.model_name,
                aggregation=self.aggregation,
            )
            return self._pipeline


def _to_entities(raw: list[dict[str, Any]], text: str) -> list[Entity]:
    """Convert HF pipeline output to LexGraph :class:`Entity` records."""
    out: list[Entity] = []
    for item in raw or []:
        label_raw = str(
            item.get("entity_group")
            or item.get("entity")
            or item.get("label")
            or ""
        ).upper().lstrip("BIOE-")
        entity_text = str(item.get("word") or item.get("text") or "").strip()
        if not entity_text or not label_raw:
            continue

        start_raw = item.get("start")
        end_raw = item.get("end")
        if isinstance(start_raw, int) and isinstance(end_raw, int):
            start, end = start_raw, end_raw
        else:
            idx = text.find(entity_text)
            if idx < 0:
                continue
            start, end = idx, idx + len(entity_text)

        node_type = _LABEL_MAP.get(label_raw, label_raw.capitalize())
        extra: dict[str, str] = {"source": "transformer"}
        if role := _ROLE_MAP.get(label_raw):
            extra["role"] = role
        if score := item.get("score"):
            try:
                extra["score"] = f"{float(score):.4f}"
            except (TypeError, ValueError):
                pass

        out.append(
            Entity(
                type=node_type,
                text=entity_text,
                start=start,
                end=end,
                extra=extra,
            )
        )
    return out


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_device(explicit: str | None) -> int | str:
    """Return a device argument acceptable to ``transformers.pipeline``.

    The HF pipeline accepts an integer GPU index or ``-1`` for CPU, and (on
    newer versions) a string such as ``"mps"`` or ``"cuda"``. We keep the
    mapping small and safe for CPU-only environments.
    """
    if explicit in (None, "", "auto"):
        return -1
    return explicit  # type: ignore[return-value]


__all__ = ["TransformerLegalNER"]
