"""Populate public-adapter caches from HuggingFace-hosted legal corpora.

This script is the bridge between the ``PublicSourceAdapter`` contract and the
legal datasets the Indian NLP community has already published on HuggingFace.
It streams N records from each configured dataset, writes one ``.txt`` file
per record into the adapter's cache (``data/raw/<adapter>/``), and appends a
matching entry to ``configs/adapters/<adapter>_seeds.yml``.

Why streaming, and why ``.txt`` per record?

* Streaming avoids pulling a multi-GB parquet shard just to sample 10 cases.
* Writing one file per record means the existing ``discover()`` fallback
  (``for p in sorted(self._cache.glob('*'))``) picks them up with **zero
  adapter code changes** — no HTTP round-trip, no URL schemes to invent.
* Seed entries are still written so operators can filter by court/year and so
  the provenance chain (``SourceEpisode`` → dataset id) stays auditable.

Usage (inside the api container, which already mounts ../data + ../configs):

    pip install datasets huggingface_hub        # if not baked into the image
    python scripts/fetch_hf_corpora.py --adapters nyaya_anumana,ildc --samples 10

Gated datasets (e.g. opennyai/InJudgements_dataset) require::

    HF_TOKEN=hf_xxx python scripts/fetch_hf_corpora.py --adapters opennyai

and the HF account must have accepted the dataset's terms on the dataset page.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("LEXGRAPH_DATA_DIR", REPO_ROOT / "data"))
CONFIGS_DIR = Path(os.environ.get("LEXGRAPH_CONFIGS_DIR", REPO_ROOT / "configs"))
HF_SOURCES = CONFIGS_DIR / "adapters" / "hf_sources.yml"

# Documents longer than this get truncated before being written. HF judgments
# routinely run into hundreds of thousands of tokens; keeping the ingestion
# payload compact keeps graph writes cheap and prevents one bad record from
# monopolising a batch.
DEFAULT_MAX_CHARS = 60_000


def _slugify(raw: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_").lower()
    return s[:64] or "doc"


def _pick_text(record: dict[str, Any], candidates: Iterable[str]) -> str | None:
    """Return the first candidate field that looks like a judgment body.

    Falls back to the longest string value in the record so we still produce
    output for datasets whose column names we did not anticipate.
    """
    for key in candidates:
        val = record.get(key)
        if isinstance(val, str) and len(val.strip()) >= 200:
            return val
    best = ""
    for val in record.values():
        if isinstance(val, str) and len(val) > len(best):
            best = val
    return best if len(best) >= 200 else None


def _pick_scalar(record: dict[str, Any], key: str | None, default: str) -> str:
    if not key:
        return default
    val = record.get(key)
    if val is None or val == "":
        return default
    return str(val)


def _load_existing_seeds(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"seeds": []}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("seeds", [])
    return data


def _already_seeded(seeds: list[dict], external_id: str) -> bool:
    return any(s.get("external_id") == external_id for s in seeds)


def _fetch_adapter(
    adapter: str,
    cfg: dict[str, Any],
    *,
    samples: int,
    max_chars: int,
    hf_token: str | None,
) -> int:
    # Imported lazily so the script remains useful for --help / --list even in
    # environments where `datasets` is not (yet) installed.
    from datasets import load_dataset

    dataset_id = cfg["dataset"]
    split = cfg.get("split", "train")
    config_name = cfg.get("config")
    gated = bool(cfg.get("gated", False))
    text_fields = cfg.get("text_fields") or ["text"]

    if gated and not hf_token:
        print(
            f"  [skip] {adapter}: dataset {dataset_id} is gated and HF_TOKEN is not set.\n"
            f"         Create a token at https://huggingface.co/settings/tokens,\n"
            f"         accept the dataset's terms on its HF page, then re-run with\n"
            f"         HF_TOKEN=hf_xxx",
            file=sys.stderr,
        )
        return 0

    cache_dir = DATA_DIR / "raw" / adapter
    cache_dir.mkdir(parents=True, exist_ok=True)
    seeds_path = CONFIGS_DIR / "adapters" / f"{adapter}_seeds.yml"
    seeds_doc = _load_existing_seeds(seeds_path)
    seeds: list[dict] = seeds_doc["seeds"]

    print(f"  [{adapter}] streaming {dataset_id} (split={split}, samples={samples})…")

    load_kwargs: dict[str, Any] = {"split": split, "streaming": True}
    if config_name:
        load_kwargs["name"] = config_name
    if hf_token:
        load_kwargs["token"] = hf_token

    try:
        ds = load_dataset(dataset_id, **load_kwargs)
    except Exception as e:
        print(f"  [error] {adapter}: failed to load {dataset_id}: {e}", file=sys.stderr)
        return 0

    written = 0
    for idx, record in enumerate(ds):
        if written >= samples:
            break
        text = _pick_text(record, text_fields)
        if not text:
            continue
        text = text.strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[... truncated by fetch_hf_corpora ...]"

        base_id = _pick_scalar(record, cfg.get("id_field"), "")
        if not base_id:
            # Stable-ish id derived from the text prefix so reruns are
            # idempotent and we do not re-ingest the same record twice.
            digest = hashlib.sha256(text[:2048].encode("utf-8")).hexdigest()[:12]
            base_id = f"{adapter}_{idx:05d}_{digest}"
        external_id = _slugify(base_id)

        out_path = cache_dir / f"{external_id}.txt"
        if out_path.exists():
            continue
        out_path.write_text(text, encoding="utf-8")

        if not _already_seeded(seeds, external_id):
            seeds.append(
                {
                    "external_id": external_id,
                    "title": text.splitlines()[0][:120] if text else external_id,
                    "url": f"hf://{dataset_id}#{idx}",
                    "court": _pick_scalar(
                        record, cfg.get("court_field"), cfg.get("court_default", "")
                    ),
                    "year": _pick_scalar(
                        record, cfg.get("year_field"), cfg.get("year_default", "")
                    ),
                    "mime": "text/plain",
                    "source_tier": cfg.get("source_tier_default", 3),
                    "provenance": {
                        "hf_dataset": dataset_id,
                        "hf_split": split,
                        "hf_row": idx,
                    },
                }
            )
        written += 1

    if written:
        # Preserve top-level keys (e.g. schema comments) by rewriting with
        # the merged document.
        with seeds_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                seeds_doc, f, sort_keys=False, allow_unicode=True, default_flow_style=False
            )
    print(f"  [{adapter}] wrote {written} new records to {cache_dir}")
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--adapters",
        default="all",
        help="Comma-separated adapter names (default: all configured).",
    )
    ap.add_argument("--samples", type=int, default=10, help="Records per adapter.")
    ap.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help="Truncate each document to at most this many characters.",
    )
    ap.add_argument(
        "--list", action="store_true", help="List configured adapters and exit."
    )
    args = ap.parse_args()

    if not HF_SOURCES.exists():
        print(f"missing {HF_SOURCES}", file=sys.stderr)
        return 2
    with HF_SOURCES.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    adapters_cfg: dict[str, dict] = doc.get("adapters", {}) or {}

    if args.list:
        for name, cfg in adapters_cfg.items():
            gated = " [gated]" if cfg.get("gated") else ""
            print(f"  {name:18s} -> {cfg['dataset']}{gated}")
        return 0

    want = (
        list(adapters_cfg.keys())
        if args.adapters == "all"
        else [a.strip() for a in args.adapters.split(",") if a.strip()]
    )
    unknown = [a for a in want if a not in adapters_cfg]
    if unknown:
        print(f"unknown adapters: {unknown}", file=sys.stderr)
        return 2

    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    total = 0
    for name in want:
        total += _fetch_adapter(
            name,
            adapters_cfg[name],
            samples=args.samples,
            max_chars=args.max_chars,
            hf_token=hf_token,
        )

    print(f"\nDone. {total} new records written across {len(want)} adapter(s).")
    print("Restart api + worker-ingest so adapter registry picks up the new seeds:")
    print("  docker compose -f LexGraph/ops/docker-compose.yml restart api worker-ingest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
