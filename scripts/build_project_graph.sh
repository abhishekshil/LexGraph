#!/usr/bin/env bash
# Build a queryable codebase graph under graphify-out/ using graphify
# (PyPI: graphifyy). AST extraction only — no LLM keys required.
#
# Uses the repo venv when present: .venv/bin/python -m graphify …
# Docs: https://github.com/safishamsi/graphify
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ -n "${LEXGRAPH_PYTHON:-}" ]]; then
  PY="${LEXGRAPH_PYTHON}"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
else
  PY="python3"
fi

if ! "${PY}" -c "import graphify" 2>/dev/null; then
  echo "graphify is not installed for ${PY}. Run: pip install -e \".[graphify]\"" >&2
  exit 1
fi

echo ">> ${PY} -m graphify update . (writes graphify-out/, respects .graphifyignore)"
"${PY}" -m graphify update .

echo ">> done: open graphify-out/graph.html or read graphify-out/GRAPH_REPORT.md"
