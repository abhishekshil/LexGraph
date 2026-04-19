# LexGraph

A **graph-first, citation-first, provenance-first** Indian legal research system.

LexGraph is designed around three non-negotiable ideas:

1. **The graph is the memory.** Statutes, judgments, rules, and your own case
   material are decomposed into nodes with typed relations and temporal validity.
   Answers come from graph traversal, not from model recall.
2. **Every claim must cite.** Every sentence in a generated answer is traced
   back to a `SourceSpan` - an exact range in an exact file. If nothing is
   retrieved, the system refuses to generate.
3. **Authority is ranked.** An 8-tier authority hierarchy (Constitution →
   statutes → SC → HC → tribunals → lower courts → private docs → private notes
   → AI summaries) is enforced at retrieval and at ranking time.

This is an **open-source, production-grade research assistant** for Indian law,
covering IPC / CrPC / Indian Evidence Act **and** the new BNS / BNSS /
Bharatiya Sakshya Adhiniyam with explicit crosswalks. It also ingests your own
private matter materials (FIRs, chargesheets, witness statements, exhibits,
contracts, notices, etc.) as first-class sources.

## Why not "just another RAG chatbot"

| Generic legal RAG | LexGraph |
|---|---|
| Chunks + cosine similarity | Ontology-typed graph + legal-structure-aware segmentation |
| Single-pass vector retrieval | Graph-first → semantic-fallback → rerank → evidence-pack |
| "Here is what the model thinks" | "Here are 4 sections + 2 SC rulings supporting this, and 1 conflicting HC ruling" |
| Flat source list | 8 authority tiers; binding vs persuasive; historical validity |
| Model may hallucinate cites | If no evidence is retrieved, the system says so and refuses |
| One monolithic service | Each agent is an independent worker, separately runnable and debuggable |

## System at a glance

```
┌───────────── UI (Next.js) ─────────────┐
│ ask, upload, filter, memo, provenance  │
└───────────────────┬────────────────────┘
                    │ REST
┌───────────────────▼────────────────────┐
│            FastAPI API gateway         │
│ /ingest/public  /ingest/private        │
│ /query  /evidence  /graph/subgraph     │
│ /evaluate  /export/memo                │
└───────────┬──────────────┬─────────────┘
            │              │
      event bus (Redis streams / Kafka)
            │              │
   ┌────────┴─┬────────┬───┴────┬─────────┬────────┐
   ▼          ▼        ▼        ▼         ▼        ▼
 Ingest  Segment  Enrich    Graph     Retrieve  Generate
 Agent   Agent    Agent     Writer    Agent     Agent
 worker  worker   worker    Agent     worker    worker
                            worker
                              │
                              ▼
                     ┌──────────────────┐
                     │   Graphiti +     │
                     │   Neo4j (opt.)   │
                     │  PostgreSQL      │
                     │  (audit/meta)    │
                     │  MinIO (files)   │
                     │  Qdrant (vec)    │
                     └──────────────────┘
```

Every arrow between workers is an event on the bus, so an individual agent can
be restarted, replayed, or debugged in isolation (for example `python -m services.svc_enrich`).

## Repository layout

| Path | What lives there |
|------|------------------|
| `services/` | **`lib/`** = shared domain code (`services.lib.*`); **`svc_*`** = gateway + workers. Map: `configs/product_services.yml`, discovery: `GET /api/system/services`. Layout: `services/README.md`. |
| `configs/` | Crosswalks, authority tiers, adapter flags |
| `docs/` | Architecture and design notes |
| `ops/` | Docker Compose, Dockerfiles |
| `scripts/` | Seeds, eval, **project graph** (`build_project_graph.sh`) |
| `ui/` | Next.js app |
| `tests/` | Pytest |

**Codebase graph (for contributors):** `pip install -e ".[graphify]"` (or `.[dev,graphify]`), then `make project-graph`. That uses the open-source [graphify](https://github.com/safishamsi/graphify) stack (`graphifyy` on PyPI) to emit `graphify-out/graph.json`, `graph.html`, and `GRAPH_REPORT.md` (AST pass; no LLM required). Ignore bulky paths in `.graphifyignore`.

## Quick start (local)

```bash
cp .env.example .env
docker compose up --build
# API:   http://localhost:8080/docs
# UI:    http://localhost:3000
# Neo4j: http://localhost:7474
```

Seed a tiny corpus and ask a question:

```bash
make seed-example     # ingests a few statute sections + 2 judgments + 1 private matter
make query Q="What are the ingredients of theft under BNS, and which judgments interpret them?"
```

## Phases

The build is strictly phased. See `docs/architecture.md` for the full plan.

- **Phase 1** (this scaffold): repo skeleton, ontology, provenance, metadata
  models, answer schema, Graphiti integration, multi-agent worker scaffold,
  crosswalk configs, base API.
- **Phase 2**: production ingestion for statutes / judgments / private files.
- **Phase 3**: graph construction + authority ranking + graph-first retrieval + semantic fallback.
- **Phase 4**: evidence-pack assembly + grounded generation.
- **Phase 5**: evaluation suite + tests + demo UI + ops.

## License & disclaimers

Code: MIT. Ingested public corpora retain their original licenses (see
`docs/ingestion_guide.md`). LexGraph provides **legal information**, not legal
advice.
