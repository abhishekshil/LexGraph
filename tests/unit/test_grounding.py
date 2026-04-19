from __future__ import annotations

from services.lib.evaluation.metrics.grounding import grounding_rate


def test_grounding_rate_counts_markers():
    results = [
        {"answer": "Answer: Section 378 IPC defines theft [S1]. It requires dishonest intent [S2]."},
        {"answer": "Answer: This is an unsupported sentence. A second one too."},
    ]
    rate = grounding_rate(results)
    # 2 cited out of 4 claim sentences (headers excluded for first because sentence starts 'Section...')
    assert 0.4 <= rate <= 0.6
