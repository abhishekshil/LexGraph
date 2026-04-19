from __future__ import annotations

from services.lib.enrichment import extract_section_refs


def test_section_variants():
    text = "See Section 378 IPC and S.173(2) CrPC as well as Article 21."
    refs = extract_section_refs(text)
    assert any(r.section == "378" and "Indian Penal Code" in r.act for r in refs)
    assert any(r.section == "173" and r.subsection == "2" for r in refs)
    assert any(r.is_article and r.section == "21" for r in refs)
