# Graph Report - /Users/abhishek/Desktop/PERSONAL/LexGraph  (2026-04-19)

## Corpus Check
- 176 files · ~57,425 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1108 nodes · 3004 edges · 37 communities detected
- Extraction: 52% EXTRACTED · 48% INFERRED · 0% AMBIGUOUS · INFERRED: 1438 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]

## God Nodes (most connected - your core abstractions)
1. `Event` - 50 edges
2. `RawDocument` - 47 edges
3. `EvidencePack` - 39 edges
4. `DocumentKind` - 34 edges
5. `DocumentMetadata` - 34 edges
6. `Streams` - 34 edges
7. `InMemoryBus` - 32 edges
8. `IngestRequestEvent` - 31 edges
9. `SourceRef` - 30 edges
10. `IngestAgent` - 30 edges

## Surprising Connections (you probably didn't know these)
- `test_storage_key_is_deterministic()` --calls--> `storage_key_for()`  [INFERRED]
  /Users/abhishek/Desktop/PERSONAL/LexGraph/tests/unit/test_storage.py → /Users/abhishek/Desktop/PERSONAL/LexGraph/lexgraph/storage/base.py
- `test_storage_key_sanitises_prefix_and_filename()` --calls--> `storage_key_for()`  [INFERRED]
  /Users/abhishek/Desktop/PERSONAL/LexGraph/tests/unit/test_storage.py → /Users/abhishek/Desktop/PERSONAL/LexGraph/lexgraph/storage/base.py
- `graph_store()` --calls--> `InMemoryGraphStore`  [INFERRED]
  /Users/abhishek/Desktop/PERSONAL/LexGraph/tests/integration/test_generation_pipeline.py → /Users/abhishek/Desktop/PERSONAL/LexGraph/lexgraph/graph/memory_store.py
- `object_store()` --calls--> `get_object_store()`  [INFERRED]
  /Users/abhishek/Desktop/PERSONAL/LexGraph/tests/integration/test_retrieval_pipeline.py → /Users/abhishek/Desktop/PERSONAL/LexGraph/lexgraph/storage/factory.py
- `graph_store()` --calls--> `InMemoryGraphStore`  [INFERRED]
  /Users/abhishek/Desktop/PERSONAL/LexGraph/tests/integration/test_retrieval_pipeline.py → /Users/abhishek/Desktop/PERSONAL/LexGraph/lexgraph/graph/memory_store.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (106): ABC, Agent, Answer, Agent, EventBus, Publish `event` to `stream`. Returns backend-specific message id., Subscribe to every listen stream and dispatch to self.handle., Route a poisoned event to a DLQ stream named `<stream>.dlq`. (+98 more)

### Community 1 - "Community 1"
Cohesion: 0.04
Nodes (69): Crosswalk, CrosswalkEntry, load_all_crosswalks(), load_crosswalk(), _norm(), Loader for old ↔ new law crosswalks declared in configs/crosswalks/*.yml., _approx_tokens(), _confidence_from() (+61 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (80): AnswerCitation, AnswerConflict, GraphPath, Answer schema - the machine-readable + human-readable shape of every reply., One cited source, resolved from an [S#] marker in the generated text., Human-readable path explaining how the system reached an authority., Final, grounded answer. This is the API response shape., AuthorityTier (+72 more)

### Community 3 - "Community 3"
Cohesion: 0.04
Nodes (38): _json_safe(), ProvenanceAudit, Append-only provenance audit log.  Every ingestion, segmentation, enrichment and, handle(), PublicSourceAdapter, Object-store interface shared by MinIO and local backends., Every public-source adapter satisfies this shape., _infer_kind() (+30 more)

### Community 4 - "Community 4"
Cohesion: 0.04
Nodes (65): citation_faithfulness(), pack_utilisation(), Citation-level metrics., Fraction of ``[S#]`` tokens in the answer whose marker exists in the pack., Fraction of emitted citations that carry both ``excerpt`` and     ``source_span_, Mean fraction of pack spans that were actually cited in the answer.      Low uti, span_citation_correctness(), crosswalk_mapping_accuracy() (+57 more)

### Community 5 - "Community 5"
Cohesion: 0.04
Nodes (42): authority_tier_for(), Authority tiers per docs/architecture.md §5.  Tiers drive ranking, evidence sele, Return the tier for a node.      For judicial nodes (Case/Holding/Paragraph/Rati, EdgeSchema, EdgeType, Canonical edge types. Every edge stored in the graph MUST be one of these., Allowed endpoints + whether the edge is temporally validated., subgraph() (+34 more)

### Community 6 - "Community 6"
Cohesion: 0.04
Nodes (44): _go(), CLI shortcut: python -m scripts.ask "what are the ingredients of theft?", BaseSettings, ask(), eval_dataset(), Operator CLI. `lexgraph --help` for commands., _load(), Central configuration, sourced from environment (.env aware). (+36 more)

### Community 7 - "Community 7"
Cohesion: 0.07
Nodes (58): Citation, CitationExtractor, _dedupe(), extract_citations(), _from_air(), _from_case_title(), _from_crilj(), _from_hc_neutral() (+50 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (45): ObjectStore, Narrow async interface. Any backend implementing this works everywhere., run_eval(), check_thresholds(), DatasetReport, EvaluationReport, EvaluationSummary, ItemResult (+37 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (35): dim(), Embedder, get_embedder(), _hash_embed(), Lazy-loaded text embedder.  Primary model: InLegalBERT (or any configured legal, Feature-hashing embedding: signed token hashes normalised to unit norm.      Det, Wraps a sentence-transformer with graceful degradation.      Thread-safe for laz, _payload_from_raw() (+27 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (14): ObjectKey, Replace unsafe chars with ``_`` and collapse '..' runs to defeat path     traver, Bucket + key pair. ``uri`` renders as ``s3://bucket/key``., _safe_filename(), _sanitise(), get_object_store(), Factory picking the right object store backend based on config., LocalObjectStore (+6 more)

### Community 11 - "Community 11"
Cohesion: 0.1
Nodes (30): Entity, LegalNER, _merge(), _NERBackend, Legal NER.  The regex + list layer is the *baseline* — it is cheap, offline, and, Merge overlapping entities; regex wins on exact-span collisions.      Two entiti, Protocol satisfied by any NER layer that returns :class:`Entity`., Combined regex + optional transformer NER.      Parameters     ----------     tr (+22 more)

### Community 12 - "Community 12"
Cohesion: 0.13
Nodes (26): _attach_roles(), Judgment segmenter.  Produces Paragraph segments keyed by paragraph numbers with, segment_judgment(), _extras_for_block(), _label_for_block(), _node_type_for_block(), Private-document segmenter.  Private case materials don't follow statutory struc, _segment_chargesheet() (+18 more)

### Community 13 - "Community 13"
Cohesion: 0.14
Nodes (17): parse_docx_bytes(), parse_html_bytes(), HTML parser with boilerplate stripping.  Preserves only document body text and d, parse_bytes(), parse_raw_document(), ParsedDocument, Dispatcher: RawDocument -> (text, per-page offsets).  Parsers accept either byte, Parse in-memory bytes into a :class:`ParsedDocument`. (+9 more)

### Community 14 - "Community 14"
Cohesion: 0.14
Nodes (12): AuthorityReranker, Re-rank candidates by authority tier, with tie-break on recency + score.  Scorin, Crude recency bonus. Newer judgments get up to +1., _recency_bonus(), CompositeReranker, Compose semantic + authority reranking., _lexical_score(), Cross-encoder reranker with a lexical fallback.  When the BGE / reranker model i (+4 more)

### Community 15 - "Community 15"
Cohesion: 0.67
Nodes (1): ask()

### Community 16 - "Community 16"
Cohesion: 0.67
Nodes (1): Seed a tiny example corpus so the system is runnable end-to-end on a laptop.  Dr

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (0): 

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (0): 

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (0): 

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (0): 

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (0): 

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (0): 

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (0): 

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (0): 

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (0): 

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (0): 

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (0): 

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (0): 

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (0): 

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **95 isolated node(s):** `Append-only provenance audit log.  Every ingestion, segmentation, enrichment and`, `Operator CLI. `lexgraph --help` for commands.`, `Typed metadata for different kinds of ingested documents.`, `Baseline metadata for every ingested document.`, `Extra fields when we know this is a statute / amendment / rule.` (+90 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 17`** (2 nodes): `RootLayout()`, `layout.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 18`** (1 nodes): `next.config.mjs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 19`** (1 nodes): `next-env.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 20`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `EvidencePack` connect `Community 2` to `Community 0`, `Community 1`, `Community 6`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `RawDocument` connect `Community 0` to `Community 3`, `Community 13`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `main()` connect `Community 0` to `Community 5`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Are the 38 inferred relationships involving `Event` (e.g. with `Answer` and `EvidencePack`) actually correct?**
  _`Event` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 44 inferred relationships involving `RawDocument` (e.g. with `Event` and `IngestRequestEvent`) actually correct?**
  _`RawDocument` has 44 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `EvidencePack` (e.g. with `Unit tests for Phase 3 retrieval components.` and `Unit tests for lexgraph.generation.  Covers the enforcement pass, provider selec`) actually correct?**
  _`EvidencePack` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 32 inferred relationships involving `DocumentKind` (e.g. with `End-to-end retrieval → generation integration test.  Ingests a small IPC snippet` and `A nonsense query should produce a refusal answer, not a hallucination.`) actually correct?**
  _`DocumentKind` has 32 INFERRED edges - model-reasoned connections that need verification._