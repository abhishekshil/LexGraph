# LexGraph Architecture

## 1. Design principles

1. **Graph is primary, vectors are fallback.** All reasoning hops through typed
   graph relations. Vectors only rescue recall when graph seeds miss.
2. **Every claim is grounded.** The final answer is assembled from
   `SourceSpan`s. A sentence without at least one linked span is suppressed.
3. **Authority is ranked explicitly.** 8-tier authority ordering drives
   retrieval ranking, evidence selection, and conflict surfacing.
4. **Provenance is immutable.** Once a `SourceEpisode` is written, it is
   append-only; corrections introduce a new episode with a superseding edge.
5. **Private ≠ public.** Private case material lives in a matter-scoped
   partition and cannot leak to public-query answers unless the query is
   explicitly matter-bound.
6. **Each agent is an independent worker.** Agents communicate only via the
   event bus. Any agent can be killed and restarted without losing state.
7. **Token-efficient by construction.** We ship compact evidence packs (exact
   spans + node summaries) to the generator, not raw chunks.

## 2. Layered view

```
   ┌──────────────────────────────────────────────────────────────────┐
L12│  API + UI                         (FastAPI, Next.js)             │
   ├──────────────────────────────────────────────────────────────────┤
L11│  Evaluation                       (metrics + datasets)           │
   ├──────────────────────────────────────────────────────────────────┤
L10│  Grounded Generation              (evidence-locked LLM)          │
   ├──────────────────────────────────────────────────────────────────┤
L9 │  Evidence Pack Assembly           (spans + graph path + summary) │
   ├──────────────────────────────────────────────────────────────────┤
L8 │  Reranking                        (authority + semantic)         │
   ├──────────────────────────────────────────────────────────────────┤
L7 │  Semantic Recall (fallback)       (InLegalBERT / BGE)            │
   ├──────────────────────────────────────────────────────────────────┤
L6 │  Graph Retrieval                  (Graphiti traversal + rules)   │
   ├──────────────────────────────────────────────────────────────────┤
L5 │  Provenance Layer                 (SourceEpisode, SourceSpan)    │
   ├──────────────────────────────────────────────────────────────────┤
L4 │  Ontology / Graph Construction    (node types, edges, crosswalk) │
   ├──────────────────────────────────────────────────────────────────┤
L3 │  Normalization                    (section numbering, dates)     │
   ├──────────────────────────────────────────────────────────────────┤
L2 │  Parsing                          (PDF/HTML/DOCX/XML + OCR)      │
   ├──────────────────────────────────────────────────────────────────┤
L1 │  Ingestion Adapters               (India Code, SC opendata, …)   │
   └──────────────────────────────────────────────────────────────────┘
```

Lower layers never call upward. Upper layers may call any layer beneath them,
mediated by the agents that own that layer.

## 3. Multi-agent topology

Each agent is:

- an implementation module under `services/svc_<role>/agent.py`
- a runnable microservice entry `services.svc_<role>` (`python -m services.svc_<role>`); ids are listed in `configs/product_services.yml`
- packaged in its own docker service in `ops/docker-compose.yml`
- subscribed to one or more named streams on the event bus
- idempotent: replaying an event must be safe

| Agent | Listens on | Produces | Purpose |
|---|---|---|---|
| `IngestAgent` | `ingest.request` | `ingest.completed` | download / receive file, persist raw bytes, create `File` + `SourceEpisode` root |
| `SegmentAgent` | `ingest.completed` | `segment.completed` | parse + legal-structure-aware segmentation into `SourceSpan`s |
| `EnrichAgent` | `segment.completed` | `enrich.completed` | legal NER, citation extraction, issue/holding extraction, crosswalk tagging |
| `GraphWriterAgent` | `enrich.completed` | `graph.written` | create / upsert typed nodes + edges in Graphiti / Neo4j |
| `IndexAgent` | `graph.written` | `index.completed` | optional semantic indexing in Qdrant for fallback recall |
| `RetrievalAgent` | `query.request` | `query.evidence_pack` | classify query, traverse graph, assemble evidence pack |
| `GenerationAgent` | `query.evidence_pack` | `query.answer` | grounded generation with citations |
| `EvalAgent` | `eval.request` | `eval.report` | run evaluation suite and write report |

Every event carries a `trace_id`, `tenant_id`, and optional `matter_id`. The
event bus abstraction (`services/lib/bus/`) is backed by Redis Streams by default,
swappable for Kafka.

## 4. Query-time flow (graph-first)

```
UI → /query
  → RetrievalAgent:
      1. classify intent (statute | precedent | offence | procedure |
                         evidence_rule | crosswalk | private_evidence_cross
                         | contradiction | timeline | authority_conflict)
      2. identify seed nodes (by entity linking, section-ref, case cite,
                              crosswalk table, matter scope)
      3. bounded neighborhood expansion on Graphiti
         (max_hops, max_nodes, authority-weighted BFS)
      4. if recall gap: semantic fallback via Qdrant
      5. rerank candidates by authority tier + semantic score
      6. collect exact SourceSpans from top-ranked nodes
      7. assemble EvidencePack (spans + graph paths + conflicts + confidence)
  → GenerationAgent:
      8. prompt LLM with EvidencePack ONLY
      9. require inline [S1]…[Sn] markers
     10. parse markers back to citations[]
     11. if any sentence lacks a marker: drop or flag
     12. return Answer JSON + human-readable memo
```

## 5. Authority tiers

Defined in `configs/authority/tiers.yml` and enforced in
`services/lib/ontology/authority.py`.

| Tier | Kind |
|---|---|
| 1 | Constitution, official statutes, amendments, gazette, notifications |
| 2 | Supreme Court of India |
| 3 | High Courts |
| 4 | Tribunals (NCLAT, NGT, ITAT, CAT, …) |
| 5 | Lower courts, procedural records |
| 6 | User's private case documents |
| 7 | User's private notes / memos |
| 8 | AI-generated summaries / abstractions |

Rule: `tier(source) ≤ tier(claim_supported_by)`; summaries can never outrank a
source. Old/repealed tier-1 provisions remain in the graph but carry a
`ValidityPeriod` node and are filtered by default for current-law queries.

## 6. Old ↔ new law crosswalks

Crosswalk tables live in `configs/crosswalks/*.yml` (IPC↔BNS, CrPC↔BNSS,
IEA↔BSA). They are loaded at graph-build time and materialized as
`SECTION_CROSSWALK_TO` edges between the corresponding `Section` nodes. Each
edge carries:

- `mapping_type`: `one_to_one | one_to_many | many_to_one | partial | none`
- `notes`: human-readable note, often the government concordance text
- `source`: citation for the crosswalk itself (so it, too, is provable)

## 7. Storage

| Store | Role |
|---|---|
| **Graphiti on Neo4j** | Primary memory graph (nodes, edges, temporal episodes) |
| **PostgreSQL** | Audit log, jobs, users, matters, evaluation runs |
| **MinIO / S3** | Raw files for every ingested source (public + private) |
| **Qdrant** | Optional vector index for semantic fallback only |

## 8. Security / privacy

- `matter_id` is enforced at every retrieval query; spans outside the matter
  scope are excluded unless `authority.tier <= 5` (public authority).
- Private buckets in MinIO are per tenant; public corpora are in a separate
  bucket.
- Every answer logs the evidence pack it used; replays are deterministic given
  the same pack.
