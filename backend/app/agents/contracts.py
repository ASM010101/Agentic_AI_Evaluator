from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRequirement(BaseModel):
    """A requirement extracted from the assignment by Agent 1.

    Requirements are advisory metadata.  The authoritative problem statement
    and instructor rubric remain the source of grading rules.
    """

    id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2_000)
    mandatory: bool = False
    rationale: str = Field(default="", max_length=2_000)


class AgentCandidateTest(BaseModel):
    """A test proposal that still needs instructor/oracle validation."""

    id: str = Field(min_length=1, max_length=120)
    input: str = Field(default="", max_length=20_000)
    expected_output: str | None = Field(default=None, max_length=20_000)
    expected_behavior: str | None = Field(default=None, max_length=2_000)
    rationale: str = Field(default="", max_length=2_000)
    requirement_id: str | None = Field(default=None, max_length=120)
    oracle_basis: str = Field(default="", max_length=2_000)


class AgentAmbiguity(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2_000)
    severity: Literal["info", "minor", "material"] = "material"


class AssignmentAgentOutput(BaseModel):
    summary: str = Field(default="", max_length=4_000)
    requirements: list[AgentRequirement] = Field(default_factory=list, max_length=100)
    candidate_tests: list[AgentCandidateTest] = Field(default_factory=list, max_length=100)
    ambiguities: list[AgentAmbiguity] = Field(default_factory=list, max_length=100)


class SolutionAgentFinding(BaseModel):
    requirement_id: str | None = Field(default=None, max_length=120)
    status: Literal["supported", "violated", "inconclusive", "not_applicable"]
    summary: str = Field(min_length=1, max_length=4_000)
    severity: Literal["info", "warning", "error"] = "info"
    confidence: Literal["low", "medium", "high"] = "medium"
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    source_location: dict[str, Any] | None = None


class SolutionAgentOutput(BaseModel):
    algorithm_summary: str = Field(default="", max_length=4_000)
    estimated_time_complexity: str = Field(default="unknown", max_length=500)
    estimated_space_complexity: str = Field(default="unknown", max_length=500)
    findings: list[SolutionAgentFinding] = Field(default_factory=list, max_length=100)


class SimilarityAgentOutput(BaseModel):
    classification: Literal[
        "common_solution",
        "distinctive_overlap",
        "needs_manual_review",
    ] = "needs_manual_review"
    explanation: str = Field(min_length=1, max_length=4_000)
    caveats: list[str] = Field(default_factory=list, max_length=20)


class FeedbackIssue(BaseModel):
    summary: str = Field(min_length=1, max_length=2_000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    suggested_fix: str = Field(default="", max_length=2_000)


class FeedbackAgentOutput(BaseModel):
    summary: str = Field(default="", max_length=4_000)
    strengths: list[str] = Field(default_factory=list, max_length=20)
    issues: list[FeedbackIssue] = Field(default_factory=list, max_length=50)
    next_steps: list[str] = Field(default_factory=list, max_length=20)
