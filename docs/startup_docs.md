# LexGraph Startup Architecture

## v1 Alignment Note

This document is the startup-facing architecture note for **what LexGraph
actually ships in version 1**.

The previous draft described a broader destination product:

- Research engine
- Drafting engine
- Shared legal platform
- Workflow orchestration layer
- Full matter workspace

That direction is still valid, but it was **ahead of the implemented system**.
The current repository is a **research-first legal intelligence platform** with
ingestion, graph construction, retrieval, grounded generation, evaluation, and a
working operator UI. Drafting should be treated as **v2**, not presented as an
existing engine in v1.

## 1. Product Boundary for v1

LexGraph v1 is a **verification-first legal research product** for Indian law.

It currently supports:

- public and private document ingestion
- provenance-first segmentation into exact source spans
- enrichment and graph construction
- graph-first retrieval with semantic fallback
- evidence-pack assembly
- grounded answer generation with inline source markers
- evaluation runs and operator observability
- a Next.js workspace for research, ingestion, and runtime inspection

It does **not** yet ship:

- a separate drafting engine
- drafting templates or court-ready document generation
- approval checkpoints between research and drafting
- collaborative matter workflows
- a full matter workspace with chronology, drafts, and team review

## 2. Direction Check

### Are we moving in the right architectural direction?

Yes, with one correction:

- the **shared legal platform** is the right foundation
- the **research engine** is the correct first product surface
- the **workflow layer** exists today as API orchestration plus trace streaming
- the **drafting engine should remain explicitly future scope**

The mistake in the earlier draft was not the target state. The mistake was
describing planned drafting capabilities as though they were already part of the
current production boundary.

## 3. Correct v1 Architecture

```text
                 ┌────────────────────────────┐
                 │      Data Sources          │
                 │ statutes · judgments ·     │
                 │ private matter documents   │
                 └─────────────┬──────────────┘
                               ↓
                 ┌────────────────────────────┐
                 │     Ingestion Pipeline     │
                 │ fetch · parse · OCR ·      │
                 │ segment · enrich           │
                 └─────────────┬──────────────┘
                               ↓
       ┌─────────────────────────────────────────────────┐
       │ Shared Legal Platform                           │
       │ provenance · graph · authority tiers · storage │
       │ vector fallback · evidence packs               │
       └─────────────┬───────────────────────┬──────────┘
                     ↓                       ↓
          ┌───────────────────┐   ┌────────────────────┐
          │ Research Engine   │   │ Evaluation Layer   │
          │ retrieve · rerank │   │ metrics · datasets │
          │ ground answers    │   │ regression checks  │
          └─────────┬─────────┘   └─────────┬──────────┘
                    ↓                       ↓
              ┌────────────────────────────────────┐
              │ FastAPI Gateway + Next.js UI       │
              │ query · ingest · evidence · graph  │
              │ trace stream · runtime visibility  │
              └────────────────────────────────────┘
```

## 4. Architecture Alignment Table

| Capability | v1 status | Notes |
| --- | --- | --- |
| Shared legal platform | implemented | object storage, provenance, graph, vector fallback, authority tiers |
| Research engine | implemented | retrieval, evidence packs, grounded generation |
| Workflow orchestration | partial | API-driven orchestration plus event/trace streaming |
| Matter workspace | partial | query + ingest + diagnostics surface exists; full matter operations do not |
| Drafting engine | not implemented | reserve for v2 after research reliability is stable |
| Verification layer | implemented in research path | answer generation is evidence-locked; unsupported claims are suppressed |
| Team collaboration | not implemented | future scope |

## 5. Shared Legal Platform Responsibilities

The platform layer remains the foundation of the product.

### Data sources

- Supreme Court and High Court material
- statutes, rules, notifications, and crosswalks
- user-uploaded private matter files
- future optional firm knowledge sources

### Pipeline outputs

- `File`
- `SourceEpisode`
- `SourceSpan`
- typed legal nodes such as `Act`, `Section`, `Case`, and `Paragraph`
- provenance edges linking every derived node back to exact source material

### Storage model

| Layer | Current stack |
| --- | --- |
| Object storage | MinIO or local disk fallback |
| Graph store | Neo4j / Graphiti adapter |
| Audit and metadata | PostgreSQL |
| Event transport | Redis Streams, swappable later |
| Semantic fallback | Qdrant |

### Platform rules

- graph traversal is primary
- vectors are fallback for recall gaps
- every answerable claim must map to a source span
- private matter data must stay matter-scoped
- authority ranking affects retrieval and presentation

## 6. Research Engine in v1

### Inputs

- legal question
- optional matter scope
- optional private matter documents already ingested

### Pipeline

```text
Question
 → Intent classify
 → Seed discovery
 → Graph retrieval
 → Semantic fallback
 → Rerank
 → Evidence pack assembly
 → Grounded generation
 → Citation enforcement
```

### Outputs

- grounded answer with `[S#]` markers
- public and private citations
- graph paths
- conflict hints
- confidence and refusal state
- live trace of the pipeline for debugging and trust

## 7. Workflow Layer in v1

There is no separate Temporal-style workflow engine in the current shipped
system. Instead, v1 uses:

- FastAPI request orchestration
- agent-specific workers
- an event bus for ingestion and background processing
- a trace bus for live query observability in the UI

This is sufficient for a production v1 research product. A stronger workflow
orchestration layer can be introduced when drafting, approvals, retries, and
multi-step matter flows become first-class product requirements.

## 8. UI Scope for v1

The UI should present LexGraph as an **operator workspace**, not as a generic
landing page.

Required v1 surfaces:

- research console
- ingest panel for private matter documents
- answer view with citation drill-down
- live agent trace
- runtime/service visibility
- architecture status that is honest about implemented versus planned scope

Not required in v1:

- full drafting studio
- collaboration inbox
- timeline and chronology editor
- document assembly workflows

## 9. Production-Grade Refactor Rules

To keep the codebase credible for v1:

- keep the frontend modular and contract-driven
- keep API routes aligned with the current service topology
- avoid placeholder claims about unsupported product features
- preserve citation-first refusal behavior
- make lint, build, and tests run cleanly
- expose runtime and trace information so failures are debuggable

## 10. V2 Expansion Path

The next major layer should be a **Drafting Engine**, but only after the
research stack is stable and measurable.

### V2 should add

- document templates
- matter facts intake
- proposition injection from verified research output
- structured draft assembly
- document verification and unsupported-claim detection
- user approval checkpoints between research and draft generation

### V2 architecture target

```text
Shared Legal Platform
  → Research Engine
  → Drafting Engine
  → Workflow Orchestrator
  → Full Matter Workspace
```

That remains the correct long-term product direction. It is just **not the v1
claim**.

## 11. Final Statement

LexGraph v1 should be described as:

> A production-oriented, graph-first, citation-first legal research platform
> for Indian law, with provenance-backed ingestion, evidence-locked answers,
> matter-scoped private documents, evaluation tooling, and an operator
> workspace for research and system visibility.

And not as:

> a complete research-and-drafting platform already shipping both engines.
