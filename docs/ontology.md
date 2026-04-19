# LexGraph Ontology

This document is the single source of truth for node types, edge types, and
extension rules. The machine-readable counterparts live in
`services/lib/ontology/`.

## 1. Design rules

1. **Every node is provenance-linked.** Every non-system node has at least one
   `NODE_DERIVED_FROM_SOURCE` edge to a `SourceEpisode` or `SourceSpan`.
2. **Every node carries an authority tier.** See `docs/architecture.md` §5.
3. **Every temporal claim has a `ValidityPeriod`.** Statute sections,
   amendments, repeals, and judgments use start/end dates.
4. **Summaries are typed.** `SummaryNode` is distinct from primary nodes and
   can never be a citation target at tier ≤ 5.
5. **Edges are typed and directional.** No generic `RELATED_TO`.

## 2. Node types

### 2.1 Public law

| Type | Key fields |
|---|---|
| `Constitution` | name, language, provenance |
| `Act` | short_title, long_title, act_number, year, jurisdiction, current_version_id |
| `Amendment` | amending_act_ref, target_act_ref, date_enforced |
| `Part`, `Chapter` | number, heading, act_ref |
| `Section` | number, heading, act_ref, chapter_ref, validity_period |
| `Subsection`, `Proviso`, `Explanation`, `Illustration` | number/label, parent_section_ref |
| `Rule`, `Regulation` | number, parent_rule_set_ref |
| `Notification`, `Circular` | number, date, issuing_authority |
| `Schedule` | number, title, act_ref |

### 2.2 Judicial

| Type | Key fields |
|---|---|
| `Case` | title, citation, court_ref, bench_ref, decision_date |
| `Court` | name, level (SC / HC / Tribunal / …), jurisdiction |
| `Bench` | judge_refs[], coram_type (single / division / constitution) |
| `Judge` | name, aliases |
| `Party` | name, role (petitioner / respondent / appellant …) |
| `Citation` | neutral_citation, reported_citations[] |
| `Paragraph` | number, case_ref, text_span_ref |
| `Holding`, `Ratio`, `Obiter` | text_span_ref, case_ref |
| `Issue`, `LegalTest`, `Doctrine`, `Precedent` | name, description |
| `ProceduralStage`, `Relief`, `Outcome` | name, description |

### 2.3 Offence / procedure / evidence

| Type | Key fields |
|---|---|
| `Offence` | name, governing_section_ref |
| `Ingredient` | description, offence_ref |
| `Punishment` | kind, min, max, section_ref |
| `Procedure` | name, governing_section_ref |
| `Requirement` | description, context_ref |
| `StandardOfProof` | name (preponderance / balance / beyond reasonable doubt) |
| `EvidenceRule` | name, governing_section_ref |
| `EvidentiaryIssue` | description |

### 2.4 Private case material

| Type | Key fields |
|---|---|
| `Matter` | matter_id, title, client_ref, confidentiality |
| `Document` | matter_ref, filename, kind (plaint / affidavit / FIR / …) |
| `Witness` | name, matter_ref |
| `Statement` | witness_ref, document_ref, date |
| `Exhibit` | label (Ex. P-1), document_ref |
| `Fact` | description, matter_ref |
| `TimelineEvent` | at, description, matter_ref |
| `Allegation`, `Defense`, `Argument` | description |
| `Contradiction` | between_nodes[], description |
| `MedicalRecord`, `ForensicRecord` | kind, findings |
| `Notice` | date, sender, receiver |
| `ContractClause` | contract_ref, clause_number, text |
| `Communication` | kind (email / letter / …), at, from, to |

### 2.5 System / provenance

| Type | Key fields |
|---|---|
| `SourceEpisode` | kind (public / private), origin, ingested_at, raw_file_ref, hash |
| `SourceSpan` | episode_ref, file_ref, page, char_start, char_end, text |
| `File` | storage_uri, mime, sha256, size |
| `Chunk` | file_ref, idx, text, embedding_id |
| `ExtractedClaim` | text, from_span_ref, confidence |
| `SummaryNode` | neighborhood_hash, text, tier=8 |
| `Crosswalk` | name, source_act, target_act, version |
| `Jurisdiction` | name, kind (central / state / court-specific) |
| `ValidityPeriod` | start, end (nullable means "ongoing") |

## 3. Edge types

### 3.1 Structural (statute)

- `ACT_CONTAINS_PART`, `ACT_CONTAINS_CHAPTER`, `CHAPTER_CONTAINS_SECTION`
- `SECTION_CONTAINS_SUBSECTION`, `SECTION_HAS_PROVISO`, `SECTION_HAS_EXPLANATION`, `SECTION_HAS_ILLUSTRATION`

### 3.2 Temporal / amendment

- `SECTION_AMENDED_BY` (→ `Amendment`)
- `SECTION_REPEALED_BY` (→ `Amendment` or `Act`)
- `SECTION_CROSSWALK_TO` (→ `Section`, with `mapping_type`)
- `NODE_HAS_VALIDITY` (→ `ValidityPeriod`)

### 3.3 Judicial

- `CASE_CITES_CASE`, `CASE_DISTINGUISHES_CASE`, `CASE_FOLLOWS_CASE`, `CASE_OVERRULES_CASE`
- `CASE_INTERPRETS_SECTION`, `CASE_APPLIES_STATUTE`, `CASE_REFERENCES_DOCTRINE`
- `PARAGRAPH_SUPPORTS_HOLDING`, `HOLDING_RESOLVES_ISSUE`, `ISSUE_INVOLVES_DOCTRINE`

### 3.4 Offence / procedure / evidence

- `OFFENCE_HAS_INGREDIENT`, `SECTION_PRESCRIBES_PUNISHMENT`
- `PROCEDURE_GOVERNED_BY_SECTION`, `EVIDENCE_RULE_GOVERNED_BY_SECTION`

### 3.5 Private case material

- `DOCUMENT_BELONGS_TO_MATTER`, `DOCUMENT_HAS_CONFIDENTIALITY`
- `DOCUMENT_CONTAINS_FACT`, `WITNESS_STATES_FACT`
- `EXHIBIT_SUPPORTS_FACT`, `EXHIBIT_CONTRADICTS_FACT`
- `FACT_RELEVANT_TO_ISSUE`, `FACT_LINKED_TO_OFFENCE`, `FACT_LINKED_TO_INGREDIENT`
- `FACT_OCCURS_AT_TIME`, `ARGUMENT_SUPPORTS_POSITION`, `ARGUMENT_CONTRADICTS_ARGUMENT`

### 3.6 Provenance / derived

- `SOURCE_SPAN_SUPPORTS_CLAIM`
- `CLAIM_TRACED_TO_EPISODE`
- `NODE_DERIVED_FROM_SOURCE`
- `NODE_SUMMARIZES_NEIGHBORHOOD`

## 4. Extending the ontology

1. Add node/edge type to `services/lib/ontology/node_types.py` /
   `edge_types.py`.
2. Add authority + validity expectations to `ontology/rules.py`.
3. Add an extractor in `services/enrichment/` that produces the new type.
4. Add a test fixture in `tests/unit/ontology/` with at least one example.
5. If public-facing, document here.

Every new edge type must answer: "what question does this edge let a query
agent skip a hop for?" If none, it probably shouldn't exist.
