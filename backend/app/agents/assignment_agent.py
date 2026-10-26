from __future__ import annotations

from app.rules import NormalizedRules
from app.schemas import AssignmentSpec


class AssignmentUnderstandingAgent:
    """Deterministic role-1 implementation.

    Explicit instructor tests are authoritative. In the absence of explicit
    tests this role records a material ambiguity instead of inventing an oracle.
    A future Ollama-backed variant can propose candidates, but candidates remain
    unvalidated until an operator approves them.
    """

    name = "assignment_understanding_and_test_design"
    version = "deterministic-v1"

    def prepare(self, normalized: NormalizedRules) -> AssignmentSpec:
        return normalized.spec
