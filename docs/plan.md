## LexGraph — Phased Execution Plan

Phase 1 (complete): architecture, ontology, provenance + metadata + answer
schemas, repo skeleton, agent scaffolding, Graphiti/Neo4j facades, event bus,
parsers, segmenters, enrichment, retrieval scaffolding, generation scaffolding,
workers, API, evaluation scaffold, UI skeleton.

### Phase 2 — Ingestion & provenance (current)

Goal: raw bytes in → structural nodes & spans in the graph, with complete
provenance and durable storage. No query-side work is blocked on graph data
shape after this phase.

Deliverables:

1. `services/storage/minio_store.py` — async MinIO client with:
   - `ensure_bucket()`, `put_object()` (content-addressed by sha256 prefix),
     `get_object()`, `presign_get()`, `exists()`.
   - Matter-scoped key schema `matter_id/sha256_prefix/filename`.
   - Fallback local-disk implementation used when `MINIO_ENDPOINT` is unset.
2. `services/api/routes/ingest.py` + `IngestAgent` rewired to MinIO:
   - `/ingest/private` streams the upload into MinIO and publishes a
     `storage_uri = s3://bucket/key` in the `IngestRequestEvent`.
   - `IngestAgent` reads bytes back from MinIO, computes SHA, constructs `File`.
3. Real HTTP fetching in adapters (`india_code`, `sci_opendata`):
   - `httpx.AsyncClient` with connect/read timeouts.
   - Token-bucket rate-limit + `robots.txt` policy check.
   - Cache-first: persists a copy to `data/raw/<adapter>/<external_id>.*` so
     re-runs are offline-safe.
4. New `hc_ecourts` adapter (rate-limited, cache-first, stub-ready for CAPTCHA).
5. Parser hardening:
   - PDF: detects encrypted docs, skips with a clear error; triggers OCR when
     text density < threshold.
   - HTML: readability-lite boilerplate stripping.
6. Private segmenter: FIR / chargesheet / contract patterns (clause numbering).
7. Judgment segmenter: rhetorical-role tagging pass.
8. Graphiti episode creation verified for `Section`, `Paragraph`, `Exhibit`,
   `Statement` — carries node metadata + provenance pointer.
9. Append-only NDJSON provenance log at `data/audit/<yyyy-mm-dd>.log`.
10. `tests/integration/` with an in-memory event bus exercising
    ingest → segment → enrich → graph_written end-to-end.

### Phase 3 — Graph-first retrieval
- Neo4j-backed seed finder (section / citation / entity lookup).
- Authority-weighted typed-BFS with temporal-validity filter.
- Qdrant indexer agent — mirrors text spans into `lex_public` / `lex_private`.
- Semantic-fallback wired to Qdrant.
- BGE cross-encoder reranker loaded on demand.
- Evidence-pack token budgeter + conflict detection across tiers.

### Phase 4 — Generation & UI
- Local HF Instruct path behind the same interface as OpenAI.
- Strict citation enforcement: drop sentences without a resolvable `[S#]`.
- Refusal path when evidence is insufficient.
- UI renders citations, conflicts, authority tiers, and provenance links.

### Phase 5 — Evaluation
- Datasets: offence ingredients IPC↔BNS (7 items), procedure CrPC↔BNSS
  (5 items), evidence IEA↔BSA (3 items), private-matter Q&A (5 items). Each
  dataset ships a corpus the runner ingests before answering.
- Metrics: grounding rate, unsupported-claim rate, fabricated-marker rate,
  citation faithfulness, span citation correctness, pack utilisation, tier-1
  anchor rate, retrieval hit rate, retrieval coverage, refusal / false-refusal
  / true-refusal rates, crosswalk-mapping accuracy, latency p50/p95/max.
- `EvaluationRunner` accepts DI (store / object_store / orchestrator /
  generator) and bootstraps the corpus into an in-memory graph so runs are
  reproducible without Neo4j / MinIO.
- CI regression gate: thresholds YAML (`configs/eval_thresholds.yaml`) +
  `scripts/run_eval.py` + `make eval-gate`. The gate fails CI on any metric
  violation; `null` lets a dataset opt out of a default threshold.

### Phase cadence
One phase at a time. After each phase, show diff, run tests, stop and wait
before proceeding.
