from __future__ import annotations

from services.lib.normalization.statute_segmenter import segment_statute


def test_statute_hierarchy():
    text = (
        "CHAPTER XVII Offences Against Property\n"
        "378. Theft.—Whoever, intending to take dishonestly...\n\n"
        "(1) first subsection text.\n\n"
        "Provided that no provision shall apply in the following cases.\n\n"
        "Explanation.— a thing attached to earth is not movable.\n\n"
        "Illustration.— A cuts a tree.\n\n"
        "379. Punishment for theft.—Whoever commits theft shall be punished...\n"
    )
    segs = segment_statute(text, [(0, len(text))])
    labels = [s.label for s in segs]
    assert "Chapter XVII" in labels
    assert "Section 378" in labels
    assert "Section 379" in labels
    assert any("(1)" in s.label for s in segs)
    assert any(s.node_type == "Proviso" for s in segs)
    assert any(s.node_type == "Explanation" for s in segs)
    assert any(s.node_type == "Illustration" for s in segs)
