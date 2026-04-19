# LexGraph — Solution Design & Architecture Flow

> Audience: engineers, SREs, and architects onboarding to LexGraph.
> Scope: end-to-end solution design — components, data flow, contracts,
> storage, runtime topology, and failure/observability model.
>
> For domain-level design rules see `docs/architecture.md` and for the
> graph schema see `docs/ontology.md`. This document focuses on the
> *engineering* view: how bytes flow, what each service owns, and what
> you can operate independently.

---

## 1. Problem statement (one paragraph)

LexGraph is a graph-first, citation-first legal research system for
Indian law (IPC/CrPC/IEA + BNS/BNSS/BSA + judgments + private matter
files). It must answer legal questions with **exact source spans**,
**ranked by authority**, **never hallucinate citations**, and support
**private case material** without leaking it into public-query answers.
The solution is a multi-agent pipeline over an event bus, backed by a
typed knowledge graph (Graphiti on Neo4j) with vector fallback
(Qdrant), object storage (MinIO/S3), and a relational audit store
(PostgreSQL).

---

## 2. High-level solution architecture

```
                         ┌──────────────────────────────┐
                         │   Next.js UI  (port 3000)    │
                         │  ask · upload · filter ·     │
                         │  memo · provenance viewer    │
                         └──────────────┬───────────────┘
                                        │ HTTPS / REST
                         ┌──────────────▼───────────────┐
                         │  FastAPI Gateway (port 8080) │
                         │  /ingest/*  /query  /evidence│
                         │  /graph/*   /evaluate  /export│
                         └───┬─────────┬─────────┬──────┘
             publishes       │         │         │  reads
             events ───────► │         │         │ ◄──── Postgres (audit)
                             ▼         ▼         ▼
                     ┌────────────────────────────────┐
                     │   Event Bus (Redis Streams)    │
                     │   swappable → Kafka            │
                     └───┬────┬────┬────┬────┬────┬───┘
                         │    │    │    │    │    │
         ┌───────────────┘    │    │    │    │    └──────────────┐
         ▼                    ▼    ▼    ▼    ▼                   ▼
    ┌─────────┐         ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ Ingest  │         │ Segment │ │ Enrich  │ │ Graph   │ │ Index   │
    │ Worker  │────────▶│ Worker  │▶│ Worker  │▶│ Writer  │▶│ Worker  │
    └────┬────┘         └─────────┘ └─────────┘ └────┬────┘ └────┬────┘
         │                                           │           │
         │ raw bytes                                  │ upsert    │ embed
         ▼                                           ▼           ▼
    ┌─────────┐                               ┌──────────┐  ┌──────────┐
    │ MinIO/  │                               │ Graphiti │  │  Qdrant  │
    │   S3    │                               │ + Neo4j  │  │ (vectors)│
    └─────────┘                               └──────────┘  └──────────┘

                  Query path (separate stream)
    ┌──────────┐  query.request   ┌──────────┐  evidence_pack   ┌──────────┐
    │ Retrieve │◄──────────────── │  API     │ ────────────────▶│ Generate │
    │  Worker  │ ────────────────▶│ Gateway  │ ◄────────────────│  Worker  │
    └──────────┘  query.answer    └──────────┘                  └──────────┘
```

All arrows crossing the bus are **idempotent, replayable events** carrying
`trace_id`, `tenant_id`, optional `matter_id`, and a `schema_version`.

---

## 3. Component responsibility matrix

| # | Component | Kind | Owns | Does NOT own |
|---|---|---|---|---|
| 1 | `ui` (Next.js) | Frontend | Query UX, upload, memo rendering, provenance drill-down | Any business logic |
| 2 | `api` (FastAPI) | Gateway | Auth, request validation, event publish, audit, response shaping | Parsing, ranking, graph writes |
| 3 | `IngestAgent` | Worker | Download/receive files, persist raw bytes, create `File` + `SourceEpisode` | Parsing, enrichment |
| 4 | `SegmentAgent` | Worker | Parse (PDF/HTML/DOCX/XML/OCR), legal-structure-aware segmentation into `SourceSpan`s | Entity extraction |
| 5 | `EnrichAgent` | Worker | Legal NER, citation extraction, issue/holding extraction, crosswalk tagging | Graph writes |
| 6 | `GraphWriterAgent` | Worker | Upsert typed nodes/edges in Graphiti/Neo4j with provenance edges | Retrieval |
| 7 | `IndexAgent` | Worker | Optional semantic embeddings into Qdrant for fallback recall | Primary retrieval |
| 8 | `RetrievalAgent` | Worker | Intent classify, seed, bounded graph BFS, semantic fallback, rerank, evidence-pack assembly | Generation |
| 9 | `GenerationAgent` | Worker | Evidence-locked LLM call, citation marker parsing, answer JSON + memo | Retrieval |
| 10 | `EvalAgent` | Worker | Run evaluation suite against fixed datasets, emit report | Production queries |
| 11 | `Neo4j + Graphiti` | Store | Typed memory graph, temporal episodes | Raw files, vectors |
| 12 | `PostgreSQL` | Store | Users, tenants, matters, jobs, audit log, eval runs | Graph, vectors |
| 13 | `MinIO/S3` | Store | Raw ingested files (public + private buckets) | Derived data |
| 14 | `Qdrant` | Store | Chunk embeddings for fallback recall only | Primary truth |
| 15 | `Redis Streams` | Bus | Event transport, consumer groups, per-agent DLQs | Durable archive |

---

## 4. End-to-end flows

### 4.1 Ingestion flow (public statute or private document)

```
Client ──POST /ingest/{public|private}──▶ API
   │                                       │
   │                                       ├── validate payload (tenant, matter, kind)
   │                                       ├── write job row (Postgres)
   │                                       └── publish event: ingest.request
   │                                                             │
   ▼                                                             ▼
                                                          IngestAgent
                                                          ├── fetch / receive bytes
                                                          ├── store in MinIO (tenant-scoped bucket)
                                                          ├── compute sha256, create File node
                                                          ├── create SourceEpisode (append-only)
                                                          └── emit: ingest.completed
                                                                          │
                                                                          ▼
                                                                   SegmentAgent
                                                                   ├── pick parser by mime
                                                                   ├── OCR fallback if scanned
                                                                   ├── structure-aware split
                                                                   │   (Act→Chapter→Section→…)
                                                                   ├── create SourceSpan nodes
                                                                   └── emit: segment.completed
                                                                                  │
                                                                                  ▼
                                                                           EnrichAgent
                                                                           ├── legal NER
                                                                           ├── citation extractor
                                                                           ├── issue/holding extractor
                                                                           ├── crosswalk tagger
                                                                           └── emit: enrich.completed
                                                                                         │
                                                                                         ▼
                                                                                  GraphWriterAgent
                                                                                  ├── upsert typed nodes
                                                                                  ├── typed edges
                                                                                  │   (incl. provenance)
                                                                                  ├── authority tier tag
                                                                                  ├── validity period
                                                                                  └── emit: graph.written
                                                                                                  │
                                                                                                  ▼
                                                                                           IndexAgent
                                                                                           ├── embed chunks
                                                                                           ├── upsert to Qdrant
                                                                                           └── emit: index.completed
```

**Contract highlights**

- `File.sha256` is the idempotency key — re-ingesting the same bytes is a
  no-op after the `File` node.
- Every derived node has a `NODE_DERIVED_FROM_SOURCE` edge to a
  `SourceSpan` or `SourceEpisode`.
- Private ingests carry `matter_id`; storage is written to a
  tenant-scoped private MinIO bucket and tagged with
  `DOCUMENT_HAS_CONFIDENTIALITY`.

### 4.2 Query flow (graph-first, evidence-locked)

```
Client ──POST /query {question, filters, matter_id?}──▶ API
   │                                                     │
   │                                                     ├── auth + matter scope check
   │                                                     └── publish: query.request
   │                                                                       │
   ▼                                                                       ▼
                                                                   RetrievalAgent
                                                                   1. classify intent
                                                                      (statute|precedent|offence|
                                                                       procedure|evidence_rule|
                                                                       crosswalk|private_cross|
                                                                       contradiction|timeline|
                                                                       authority_conflict)
                                                                   2. seed nodes
                                                                      (entity link, section ref,
                                                                       case cite, crosswalk map,
                                                                       matter scope)
                                                                   3. bounded BFS on Graphiti
                                                                      (max_hops, max_nodes,
                                                                       authority-weighted)
                                                                   4. if recall gap → Qdrant ANN
                                                                   5. rerank
                                                                      (authority tier + semantic)
                                                                   6. collect exact SourceSpans
                                                                   7. assemble EvidencePack
                                                                      {spans, graph_paths,
                                                                       conflicts, confidence}
                                                                   └── emit: query.evidence_pack
                                                                                      │
                                                                                      ▼
                                                                             GenerationAgent
                                                                             8. LLM prompted with
                                                                                EvidencePack ONLY
                                                                             9. require [S1]…[Sn]
                                                                                inline markers
                                                                            10. parse markers →
                                                                                citations[]
                                                                            11. drop/flag any
                                                                                sentence lacking
                                                                                a marker
                                                                            12. emit query.answer
                                                                                      │
                                                                                      ▼
                                                                                    API
                                                                                    ├── persist answer
                                                                                    │   + pack (audit)
                                                                                    └── respond to client
```

**Evidence-pack contract (simplified)**

```json
{
  "trace_id": "…",
  "intent": "offence",
  "spans": [
    { "id": "S1", "node_id": "Section:BNS:303", "span": {"file":"…","page":12,"char_start":410,"char_end":820}, "tier": 1 },
    { "id": "S2", "node_id": "Case:SC:2019:…",  "span": {"file":"…","page":4, "char_start":0,  "char_end":612}, "tier": 2 }
  ],
  "graph_paths": [["Offence:Theft","OFFENCE_HAS_INGREDIENT","Ingredient:Dishonestly"], "…"],
  "conflicts": [],
  "confidence": 0.82
}
```

If `spans == []` the generator **refuses to answer**.

---

## 5. Runtime topology

- One Docker service per agent (`ops/docker-compose.yml`). Each is
  horizontally scalable via Redis consumer groups.
- One CLI entrypoint per worker under ``services/svc_*`` so any worker can run
  standalone for local debugging:

  ```bash
  python -m services.svc_enrich
  ```

- API and UI are independent services; UI only talks to API.
- Graphiti/Neo4j, Postgres, MinIO, Qdrant, and Redis run as stateful
  services with their own volumes.

### Scaling knobs

| Axis | Lever |
|---|---|
| Ingestion throughput | more `IngestAgent` + `SegmentAgent` replicas |
| Extraction quality/cost | swap model in `EnrichAgent` config |
| Graph write contention | batch upserts in `GraphWriterAgent`, partition by `tenant_id` |
| Query latency | cache hot subgraphs, tune BFS `max_hops`/`max_nodes` |
| Recall | enable/disable Qdrant fallback per intent |

---

## 6. Data & storage model

| Store | What lives there | Why not elsewhere |
|---|---|---|
| **Neo4j (Graphiti)** | All typed nodes/edges, temporal episodes, authority tier, validity | Only store with cheap multi-hop traversal + temporal edges |
| **PostgreSQL** | Users, tenants, matters, jobs, audit log, eval runs, rate limits | Relational invariants + transactions |
| **MinIO/S3** | Raw ingested bytes (public bucket + per-tenant private buckets) | Cheap, immutable, content-addressed |
| **Qdrant** | Chunk embeddings, metadata filter on tier/matter | ANN fallback only; never the source of truth |
| **Redis Streams** | Inter-agent events, DLQs | Low-latency, replayable, consumer-group semantics |

### Provenance invariants

1. `SourceEpisode` is append-only. Corrections insert a new episode
   linked by a `SUPERSEDES` edge.
2. Every derived node carries `NODE_DERIVED_FROM_SOURCE`.
3. Every answer persists the exact `EvidencePack` it was generated from,
   so replays are deterministic.

---

## 7. Authority & matter-scope enforcement

- **Authority tiers** (1=Constitution/statute … 8=AI summary) are set at
  graph-write time in `GraphWriterAgent` and enforced in
  `RetrievalAgent` ranking and `GenerationAgent` citation checks.
  Invariant: `tier(source) ≤ tier(claim_supported_by)`.
- **Matter scope**: every query that includes `matter_id` restricts the
  retrieval frontier to `matter_id`-tagged nodes **plus** public
  authority (tier ≤ 5). Queries without `matter_id` cannot return
  private (tier 6–7) nodes.
- **Old ↔ new law**: crosswalks (`configs/crosswalks/*.yml`) become
  `SECTION_CROSSWALK_TO` edges with `mapping_type` and their own
  citation, so even the crosswalk itself is provable.

---

## 8. API surface (gateway)

| Method | Path | Purpose |
|---|---|---|
| POST | `/ingest/public` | Ingest public statute/judgment (by URL or upload) |
| POST | `/ingest/private` | Ingest private matter file (requires `matter_id`) |
| POST | `/query` | Ask a question → returns grounded answer + citations |
| GET | `/evidence/{trace_id}` | Fetch evidence pack used for an answer |
| GET | `/graph/subgraph` | Return bounded subgraph around seed nodes |
| POST | `/evaluate` | Trigger an evaluation run on a dataset |
| GET | `/export/memo/{trace_id}` | Export a human-readable legal memo |

Every response includes `trace_id` (correlates to bus events + audit
log) so any answer is replayable from the stored `EvidencePack`.

---

## 9. Event contract (bus)

All events share this envelope:

```json
{
  "trace_id": "uuid",
  "tenant_id": "…",
  "matter_id": "… | null",
  "schema_version": "1",
  "event_type": "ingest.completed",
  "occurred_at": "ISO-8601",
  "payload": { }
}
```

| Stream | Produced by | Consumed by |
|---|---|---|
| `ingest.request` | API | IngestAgent |
| `ingest.completed` | IngestAgent | SegmentAgent |
| `segment.completed` | SegmentAgent | EnrichAgent |
| `enrich.completed` | EnrichAgent | GraphWriterAgent |
| `graph.written` | GraphWriterAgent | IndexAgent |
| `index.completed` | IndexAgent | (terminal) |
| `query.request` | API | RetrievalAgent |
| `query.evidence_pack` | RetrievalAgent | GenerationAgent |
| `query.answer` | GenerationAgent | API |
| `eval.request` / `eval.report` | API / EvalAgent | EvalAgent / API |

Idempotency: every handler keys on
`(event_type, trace_id, payload.hash)` before performing side effects.

---

## 10. Failure & recovery model

| Failure | Detection | Recovery |
|---|---|---|
| Agent crash mid-event | consumer-group PEL / visibility timeout | event redelivered; idempotent handler re-executes safely |
| Poison message | N retries exceeded | moved to per-stream DLQ; alerts fire; replayable after fix |
| Neo4j outage | write failures on `GraphWriterAgent` | events back up on bus; agent retries with exponential backoff |
| Qdrant outage | retrieval fallback disabled | RetrievalAgent skips semantic recall, graph-only mode |
| LLM provider outage | generation fails | answer endpoint returns 503 with evidence pack preserved for later retry |
| Bad extractor regression | eval report regression | `EvalAgent` gates deploys; roll back extractor image |

Every agent exposes `/healthz` and `/metrics`. Answers cannot be
generated without an evidence pack, so an outage degrades to "no
answer" rather than "hallucinated answer".

---

## 11. Observability

- **Tracing**: `trace_id` on every event + request; OpenTelemetry spans
  across API → bus → agents.
- **Metrics**: per-agent lag (stream depth), processing latency,
  extraction success rates, retrieval recall/precision proxies,
  generation refusal rate.
- **Audit log**: Postgres table of every query, evidence pack id, model
  version, and returned answer — replayable end-to-end.

---

## 12. Security & privacy

- `matter_id` boundary enforced at API, retrieval, and storage layers.
- Per-tenant MinIO buckets; public corpora in a distinct bucket.
- Secrets via env (`.env`); no PII in logs; PII redaction hooks live in
  `EnrichAgent`.
- ACLs in Neo4j/Graphiti at the tenant level; read-replica pattern for
  heavy public-query workloads.
- LLM calls are evidence-locked: the model only sees the
  `EvidencePack`, never raw case files outside it.

---

## 13. Build & deployment

- `ops/Dockerfile.python` — one image, multiple entrypoints, one per
  worker / API.
- `ops/Dockerfile.ui` — Next.js UI.
- `ops/docker-compose.yml` — full local stack (API, UI, agents, Neo4j,
  Postgres, MinIO, Qdrant, Redis).
- Shared Python image is built by the `api` service and reused by every
  worker: `docker compose -f ops/docker-compose.yml build api`.
- CI runs `tests/unit`, `tests/integration`, and a smoke slice of
  `tests/eval` (datasets under `services/lib/evaluation/datasets/`) on every
  PR.

---

## 14. Local quick start (engineer)

```bash
cp .env.example .env
docker compose -f ops/docker-compose.yml up --build

# API:   http://localhost:8080/docs
# UI:    http://localhost:3000
# Neo4j: http://localhost:7474

make seed-example
make query Q="What are the ingredients of theft under BNS, and which judgments interpret them?"
```

Run a single agent in isolation:

```bash
python -m services.svc_retrieve
```

Replay a past answer from its `trace_id`:

```bash
curl localhost:8080/evidence/$TRACE_ID | jq
```

---

## 15. Extension points

| You want to… | Touch |
|---|---|
| Support a new legal source (e.g., a new HC portal) | `services/lib/ingestion/adapters/` + `configs/adapters/` |
| Add a new node/edge type | `services/lib/ontology/*` + `docs/ontology.md` + extractor in `lib/enrichment/` |
| Add a new query intent | `services/lib/retrieval/query_classifier.py` + new traversal recipe |
| Swap the LLM | `services/generation/` + `configs/agents/generation.yaml` |
| Swap the bus (Redis → Kafka) | implement `services/lib/bus/` driver; no agent code changes |
| Add a new crosswalk (e.g., IT Act ↔ DPDP) | `configs/crosswalks/*.yml` |

---

## 16. Phased rollout

1. **Phase 1 (scaffold)** — repo skeleton, ontology, provenance, answer
   schema, Graphiti integration, multi-agent worker scaffold, base API.
2. **Phase 2** — production ingestion for statutes, judgments, private
   files.
3. **Phase 3** — graph construction + authority ranking + graph-first
   retrieval + semantic fallback.
4. **Phase 4** — evidence-pack assembly + grounded generation.
5. **Phase 5** — evaluation suite + tests + demo UI + ops hardening.

See `docs/plan.md` for detailed milestones.
