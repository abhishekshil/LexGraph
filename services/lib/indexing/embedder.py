"""Lazy-loaded text embedder.

Primary model: InLegalBERT (or any configured legal model); fallback: MiniLM.
If no sentence-transformers / torch is installed (e.g. CI sandbox) we fall back
to a deterministic hash-bucketed vector so the rest of the pipeline still runs
without a live embedding service. The hash embedder is obviously *not*
useful for real retrieval but keeps tests green and the system debuggable.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from functools import lru_cache
from typing import Iterable

from ..core import get_logger, settings


log = get_logger("indexing.embedder")

_HASH_DIM = 256  # only used when the real model isn't available


class Embedder:
    """Wraps a sentence-transformer with graceful degradation.

    Thread-safe for lazy init. ``dim`` is only known after the first encode.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._primary = model_name or settings.legal_embedding_model
        self._fallback = settings.general_embedding_model
        self._model = None  # sentence-transformers model, or None on degrade
        self._degraded = False
        self._lock = threading.Lock()
        self._dim: int | None = None

    # ---- public API ----------------------------------------------------

    @property
    def dim(self) -> int:
        if self._dim is None:
            # force load by running a tiny encode
            self.encode(["dim probe"])
        assert self._dim is not None
        return self._dim

    def encode(self, texts: Iterable[str], *, batch_size: int = 16) -> list[list[float]]:
        chunks = [t if isinstance(t, str) else str(t) for t in texts]
        if not chunks:
            return []
        model = self._load()
        if model is None:
            vecs = [_hash_embed(t) for t in chunks]
            self._dim = _HASH_DIM
            return vecs
        try:
            raw = model.encode(
                chunks,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("embed.runtime_failed_fallback_to_hash", error=str(e))
            self._degraded = True
            vecs = [_hash_embed(t) for t in chunks]
            self._dim = _HASH_DIM
            return vecs
        out = [list(map(float, row)) for row in raw]
        self._dim = len(out[0]) if out else self._dim
        return out

    def encode_one(self, text: str) -> list[float]:
        res = self.encode([text])
        return res[0] if res else []

    @property
    def model_name(self) -> str:
        if self._degraded or self._model is None:
            return "hash-fallback"
        return getattr(self._model, "_model_name", self._primary)

    # ---- internal ------------------------------------------------------

    def _load(self):
        if self._degraded:
            return None
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            for name in (self._primary, self._fallback):
                try:
                    from sentence_transformers import SentenceTransformer  # type: ignore

                    m = SentenceTransformer(name)
                    m._model_name = name  # stash for logging
                    log.info("embed.loaded", model=name)
                    self._model = m
                    return self._model
                except Exception as e:  # noqa: BLE001
                    log.warning("embed.load_failed", model=name, error=str(e))
                    continue
            log.warning("embed.no_model_available", primary=self._primary, fallback=self._fallback)
            self._degraded = True
            return None


@lru_cache
def get_embedder() -> Embedder:
    return Embedder()


# -- hash-bucket fallback (deterministic, low-quality but non-zero signal) ---

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+", re.UNICODE)


def _hash_embed(text: str, dim: int = _HASH_DIM) -> list[float]:
    """Feature-hashing embedding: signed token hashes normalised to unit norm.

    Deterministic and cheap; good enough to make the in-memory tests exercise
    the full retrieval path without downloading ~1 GB of model weights.
    """
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall(text.lower())
    if not tokens:
        return vec
    for tok in tokens:
        h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:8], "little")
        idx = h % dim
        sign = 1.0 if (h >> 63) & 1 == 0 else -1.0
        vec[idx] += sign
    # L2 normalise
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
