from __future__ import annotations

import pytest

from app.orchestration.state_machine import InvalidTransition, RunState, transition
from app.similarity.fingerprints import compare_sources, normalize_tokens
from app.testing.comparators import compare


def test_state_machine_rejects_illegal_transition():
    assert transition(RunState.QUEUED, RunState.PREPARING) == RunState.PREPARING
    with pytest.raises(InvalidTransition):
        transition(RunState.COMPLETED, RunState.QUEUED)


def test_output_comparison_has_explicit_whitespace_policy():
    assert compare("12\r\n", "12\n", "trim_trailing_whitespace").passed
    assert not compare("12 3", "123", "exact").passed


def test_similarity_normalizes_comments_and_identifiers():
    left = "// comment\nint add(int lhs, int rhs) { return lhs + rhs; }"
    right = "int sum(int a, int b) { return a + b; }"
    assert "IDENT" in normalize_tokens(left)
    result = compare_sources(left, right)
    assert result.score > 0.8
    assert "not proof" in " ".join(result.caveats)
