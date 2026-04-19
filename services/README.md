# LexGraph `services` package

## Layout

```
services/
├── lib/                    # Shared library (import-only; not a separate process)
│   ├── core/               # Config, logging, security
│   ├── bus/                # Event bus
│   ├── data_models/        # Events, provenance, answers
│   ├── observability/      # Tracing helpers
│   ├── audit.py
│   ├── ontology/           # Types, authority
│   ├── graph/              # Graphiti / Neo4j
│   ├── storage/            # Object store
│   ├── ingestion/          # Adapters
│   ├── parsers/            # PDF/HTML/…
│   ├── normalization/      # Segmenters
│   ├── ocr/
│   ├── enrichment/         # NER, citations
│   ├── indexing/           # Qdrant
│   ├── retrieval/          # Orchestrator, graph recall
│   ├── reranking/
│   ├── generation/         # Grounded LLM
│   └── evaluation/         # Metrics, datasets, runner
├── svc_http/               # HTTP gateway (FastAPI)
├── svc_ingest/ … svc_eval/ # Pipeline workers (bus consumers)
├── catalog.py              # Loads configs/product_services.yml
├── agent_base.py / runner.py
└── cli.py                  # Operator CLI
```

Import shared code as **`services.lib.<package>`** (e.g. `services.lib.core.settings`).
Run deployables as **`python -m services.svc_*`**.

## Product service IDs

Canonical map: **`configs/product_services.yml`**. HTTP discovery: **`GET /api/system/services`**.

| Service ID | Module |
|------------|--------|
| `svc_http` | `services.svc_http` |
| `svc_ingest` … `svc_eval` | `services.svc_*` |

Docker Compose sets **`com.lexgraph.service.id`** on each container.
