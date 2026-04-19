"""Central configuration, sourced from environment (.env aware)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # runtime
    app_env: str = "local"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_prefix: str = "/api"

    # auth
    auth_secret_key: str = "change-me"
    auth_token_expires_min: int = 60

    # graphiti
    graphiti_llm_provider: str = "openai"
    graphiti_embed_model: str = "text-embedding-3-small"
    graphiti_embed_dim: int = 1536

    # neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"
    neo4j_database: str = "neo4j"

    # postgres
    database_url: str = "postgresql+psycopg://lexgraph:lexgraph@localhost:5432/lexgraph"

    # redis / event bus
    redis_url: str = "redis://localhost:6379/0"
    event_bus_backend: str = "redis-streams"

    # minio
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "lexgraph"
    minio_secret_key: str = "lexgraph"
    minio_secure: bool = False
    minio_bucket_public: str = "lexgraph-public"
    minio_bucket_private: str = "lexgraph-private"

    # qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_public: str = "lex_public"
    qdrant_collection_private: str = "lex_private"

    # models
    openai_api_key: str | None = None
    generation_model: str = "gpt-4.1-mini"
    generation_provider: str = "openai"
    hf_generation_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    legal_embedding_model: str = "law-ai/InLegalBERT"
    general_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model: str = "BAAI/bge-reranker-base"

    # enrichment (NER)
    # When ``enrich_ner_enabled`` is True AND ``enrich_ner_model`` is set, the
    # EnrichAgent loads a HuggingFace token-classification model on first use
    # and layers it on top of the regex NER baseline. The wrapper degrades
    # gracefully to regex-only if the model cannot be loaded.
    enrich_ner_enabled: bool = False
    enrich_ner_model: str | None = None
    enrich_ner_device: str = "auto"  # auto | cpu | cuda | mps

    # retrieval
    retrieval_mode: str = "graph_plus_semantic"
    graph_max_hops: int = 3
    graph_max_nodes: int = 400
    graph_frontier_fanout: int = 40
    seed_min_before_semantic: int = 1
    semantic_seed_topk: int = 8
    semantic_fallback_topk: int = 20
    rerank_topk: int = 10
    evidence_max_spans: int = 12
    evidence_max_tokens: int = 3500
    evidence_tier_cap: int = 6   # max spans per tier to avoid domination
    evidence_force_tier1_for_statute: bool = True

    # ocr
    ocr_enabled: bool = True
    ocr_langs: str = "eng+hin"
    ocr_min_conf: int = 60

    # ingestion
    ingest_tmp_dir: str = "/tmp/lexgraph-ingest"
    ingest_max_file_mb: int = 200

    # adapters
    adapter_india_code: bool = True
    adapter_supreme_court_opendata: bool = True
    adapter_high_court: bool = False
    adapter_nyaya_anumana: bool = False
    adapter_ildc: bool = False
    adapter_opennyai: bool = False

    # paths
    repo_root: Path = Field(default=REPO_ROOT)
    configs_dir: Path = Field(default=REPO_ROOT / "configs")
    data_dir: Path = Field(default=REPO_ROOT / "data")


@lru_cache
def _load() -> Settings:
    return Settings()


settings: Settings = _load()
