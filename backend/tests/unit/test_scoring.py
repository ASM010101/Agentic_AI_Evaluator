from __future__ import annotations

from app.schemas import NormalizedCriterion, NormalizedTest
from app.scoring.engine import EvidenceLike, calculate_score


def test_scoring_is_deterministic_and_weighted():
    criteria = [
        NormalizedCriterion(
            id="correctness",
            name="Correctness",
            analyzer="io_tests",
            weight=0.75,
            description="",
            scoring_mode="test_ratio",
        ),
        NormalizedCriterion(
            id="style",
            name="Style",
            analyzer="static_analysis",
            weight=0.25,
            description="",
            scoring_mode="evidence_score",
        ),
    ]
    tests = [
        NormalizedTest(
            id="a",
            input="a",
            expected_output="a",
            comparator="exact",
            rationale="explicit",
            provenance="problem_statement",
            status="validated",
        ),
        NormalizedTest(
            id="b",
            input="b",
            expected_output="b",
            comparator="exact",
            rationale="explicit",
            provenance="problem_statement",
            status="validated",
        ),
    ]
    evidence = [
        EvidenceLike("e1", "correctness", "a", "pass", {"normalized_score": 1}),
        EvidenceLike("e2", "correctness", "b", "fail", {"normalized_score": 0}),
        EvidenceLike("e3", "style", None, "pass", {"normalized_score": 0.8}),
    ]
    result = calculate_score(criteria, tests, evidence)
    assert result.finalized is True
    assert result.total_score == 57.5
    assert result.criteria[0].contribution == 37.5
    assert result.criteria[1].contribution == 20.0


def test_missing_evidence_never_silently_becomes_a_final_zero():
    criterion = NormalizedCriterion(
        id="correctness",
        name="Correctness",
        analyzer="io_tests",
        weight=1.0,
        description="",
        scoring_mode="test_ratio",
    )
    test = NormalizedTest(
        id="a",
        input="a",
        expected_output="a",
        comparator="exact",
        rationale="explicit",
        provenance="problem_statement",
        status="validated",
    )
    result = calculate_score([criterion], [test], [])
    assert result.finalized is False
    assert result.total_score is None
    assert result.criteria[0].status == "unavailable"
