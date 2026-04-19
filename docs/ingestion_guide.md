# Ingestion guide

## 1. Public source adapters

Public ingestion is adapter-driven. Each adapter lives under
`services/lib/ingestion/adapters/<name>.py` and implements:

```python
class PublicSourceAdapter(Protocol):
    name: str
    source_tier: int           # 1..5 per authority tiers
    def discover(...) -> Iterable[SourceRef]: ...
    def fetch(ref: SourceRef) -> RawDocument: ...
```

The adapter's **only** job is: "produce `RawDocument`s with provenance."
All parsing, segmentation, enrichment, and graph writing happens downstream in
the agent pipeline.

### 1.1 Built-in adapters (stubs shipped; wiring in Phase 2)

| Adapter | Source | License | Notes |
|---|---|---|---|
| `india_code` | https://www.indiacode.nic.in | Govt. of India | Acts / rules / amendments |
| `sci_opendata` | `s3://indian-supreme-court-judgments` | CC-BY-4.0 | SC judgments + metadata |
| `hc_ecourts` | eCourts HC portals | varies | scraping where permitted |
| `nyaya_anumana` | HF dataset | check card | case corpus |
| `ildc` | HF / Zenodo | check card | Indian legal doc corpus |
| `opennyai` | OpenNyAI | Apache-2.0 | NER / rhetorical role labels |

Attribution for each public source is persisted on every `SourceEpisode` and
surfaced in the answer JSON.

## 2. Private sources

Private ingestion is driven by `POST /ingest/private` (single file) or
`services.lib.ingestion.private.bulk_import(matter_id, directory)`.

Each file is:

1. persisted to `MINIO_BUCKET_PRIVATE` with a content hash
2. registered as a `File` node scoped to `matter_id`
3. tagged with confidentiality (default `private`, overridable)
4. OCR'd if it is a scanned PDF (threshold: text coverage < 20%)
5. segmented with the legal-structure-aware segmenter appropriate for its kind
6. enriched (NER, citation extraction, ingredient/fact extraction)
7. written to the graph in the matter-scoped partition

### 2.1 Supported kinds (auto-detected, overridable)

`plaint`, `written_statement`, `rejoinder`, `affidavit`, `witness_statement`,
`fir`, `complaint`, `chargesheet`, `remand_paper`, `order`, `judgment`,
`exhibit`, `contract`, `notice`, `correspondence`, `email`, `timeline`,
`note`, `memo`, `medical_record`, `forensic_record`.

### 2.2 Matter scoping

All private nodes carry `matter_id`. Retrieval enforces this at query time via
graph-side filters. No private node can be returned for a public query.

## 3. Provenance contract

Every ingested document produces:

- exactly one `File` node (raw bytes reference in MinIO)
- exactly one `SourceEpisode` (the ingestion event itself)
- one or more `SourceSpan` nodes (exact char ranges + page numbers)
- downstream nodes linked via `NODE_DERIVED_FROM_SOURCE` → `SourceSpan`

No span, no node. If an enrichment cannot anchor to a span, it is dropped.

## 4. OCR

`services/ocr/` runs Tesseract via `pytesseract` with `eng+hin` by default.
Bounding-box output is persisted so quotes can be highlighted in the UI. OCR
confidence below `OCR_MIN_CONF` (default 60) is flagged on the span.

## 5. Replay & audit

Every ingestion run emits events with a stable `trace_id`. `scripts/replay.py
--trace-id <id>` re-runs a trace deterministically against a new commit to
validate pipeline changes.
