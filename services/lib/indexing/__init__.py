"""Semantic indexing layer.

Mirrors graph nodes that carry prose (Sections, Paragraphs, Statements,
ContractClauses, ...) into a vector database so the retriever can reach them
when structural seeds are weak. Everything here is gracefully no-op when the
underlying services (Qdrant, embedding model) are unavailable, so the rest of
the pipeline keeps working.
"""

from __future__ import annotations

from .embedder import Embedder, get_embedder
from .payload import INDEXABLE_NODE_TYPES, IndexPayload, payload_to_dict
from .qdrant_indexer import QdrantIndexer, get_indexer

__all__ = [
    "Embedder",
    "INDEXABLE_NODE_TYPES",
    "IndexPayload",
    "QdrantIndexer",
    "get_embedder",
    "get_indexer",
    "payload_to_dict",
]
