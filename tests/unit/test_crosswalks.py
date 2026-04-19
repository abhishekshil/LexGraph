from __future__ import annotations

from services.lib.enrichment.crosswalk_loader import load_all_crosswalks


def test_all_crosswalks_load():
    cws = load_all_crosswalks()
    assert {"ipc_bns", "crpc_bnss", "iea_bsa"}.issubset(cws)
    ipc_bns = cws["ipc_bns"]
    assert ipc_bns.lookup_source("378")[0].target_section == "303"
    assert ipc_bns.lookup_target("101")[0].source_section == "300"
