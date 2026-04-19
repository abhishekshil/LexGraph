# Evaluation guide

LexGraph is evaluated on *grounded* legal research, not on generic QA.

## 1. Metric set

| Metric | Defined in | Goal |
|---|---|---|
| `citation_faithfulness` | `evaluation/metrics/citation.py` | every sentence maps to at least one retrieved span verbatim or near-verbatim |
| `grounding_rate` | `evaluation/metrics/grounding.py` | fraction of claim sentences with ≥1 `SourceSpan` |
| `unsupported_claim_rate` | `evaluation/metrics/grounding.py` | 1 - grounding_rate |
| `statute_retrieval_acc@k` | `evaluation/metrics/retrieval.py` | correct section(s) in top-k |
| `judgment_retrieval_rel@k` | idem | correct judgment(s) in top-k |
| `graph_path_correctness` | `evaluation/metrics/paths.py` | gold path matches returned path |
| `span_citation_correctness` | `evaluation/metrics/citation.py` | cited span actually contains the quoted text |
| `authority_ranking_correctness` | `evaluation/metrics/authority.py` | higher-tier sources ranked above lower-tier when both match |
| `crosswalk_mapping_acc` | `evaluation/metrics/crosswalk.py` | IPC↔BNS, CrPC↔BNSS, IEA↔BSA mapping |
| `contradiction_detection_f1` | `evaluation/metrics/contradiction.py` | witness / exhibit contradiction detection |
| `private_evidence_linking_acc` | `evaluation/metrics/private.py` | correct fact→ingredient/issue linkage |
| `latency_ms` | `evaluation/metrics/perf.py` | p50 / p95 per query |
| `token_usage` | `evaluation/metrics/perf.py` | prompt + completion tokens |
| `evidence_recall@k` | `evaluation/metrics/retrieval.py` | gold spans present in evidence pack |

## 2. Dataset cards

Each dataset under `evaluation/datasets/<name>/` contains:

- `DATASET.md` — provenance, license, splits
- `items.jsonl` — test items
- `gold.jsonl` — expected retrievals / spans / answers
- `loader.py` — load + normalize

Starter datasets (shipped as stubs, to be populated in Phase 5):

- `offence_ingredients_ipc_bns` — ingredients per offence, old↔new mapping
- `punishment_lookup` — section → punishment
- `procedure_crpc_bnss` — procedural step → governing section
- `evidence_rule_iea_bsa` — rule → section
- `precedent_search` — question → relevant judgments
- `statute_interpretation` — section → leading interpretations
- `private_fact_to_ingredient` — synthetic matter + fact→ingredient gold
- `witness_contradiction` — synthetic statements + expected contradictions
- `timeline_reconstruction` — case files → expected timeline

## 3. Running evaluations

```bash
# one dataset (see scripts/run_eval.py for flags)
python -m scripts.run_eval --datasets offence_ingredients_ipc_bns --no-gate

# Makefile shortcuts
make eval          # report only
make eval-gate     # CI-style thresholds
```

Reports are written to `data/processed/eval/<run_id>/report.json` and a Markdown
summary is produced for PR reviews.

## 4. Regression gates

Before a release:

- `grounding_rate ≥ 0.98`
- `unsupported_claim_rate ≤ 0.02`
- `span_citation_correctness ≥ 0.95`
- `authority_ranking_correctness ≥ 0.95`
- `crosswalk_mapping_acc ≥ 0.90`

Fail the build if any gate regresses by more than 2 points vs the prior
release.
