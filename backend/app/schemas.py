from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RuleTestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    input: str = ""
    expected_output: str | None = None
    expected_behavior: str | None = None
    comparator: Literal["exact", "trim_trailing_whitespace", "whitespace"] = (
        "trim_trailing_whitespace"
    )
    rationale: str = Field(min_length=1)
    provenance: Literal[
        "problem_statement", "explicit_rule", "derived_property", "manual_review", "llm_candidate"
    ] = "explicit_rule"
    status: Literal["candidate", "validated", "requires_review", "rejected", "disabled"] = (
        "candidate"
    )
    requirement_id: str | None = None
    score_affecting: bool = True
    validation_note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def expected_value_is_present(self) -> "RuleTestInput":
        if self.expected_output is None and not self.expected_behavior:
            raise ValueError("a test needs expected_output or expected_behavior")
        return self


class ScoringRuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["test_ratio", "evidence_score", "evidence_status", "fixed"] | None = None
    missing_evidence: Literal["needs_review", "not_applicable", "zero"] = "needs_review"
    max_points: float = Field(default=100.0, gt=0)


class MetricRuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    analyzer: str = Field(min_length=1, max_length=120)
    weight: float = Field(gt=0, le=1)
    params: dict[str, Any] = Field(default_factory=dict)
    scoring: ScoringRuleInput | None = None


class CriterionRuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    name: str | None = None
    description: str = ""
    max_points: float = Field(gt=0)
    analyzer: str = "evidence"
    params: dict[str, Any] = Field(default_factory=dict)
    scoring: ScoringRuleInput | None = None


class RulesDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem: str | None = None
    time_limit_s: float = Field(default=2.0, gt=0, le=300)
    memory_limit_mb: int = Field(default=128, gt=0, le=4096)
    metrics: list[MetricRuleInput] | None = None
    criteria: list[CriterionRuleInput] | None = None
    tests: list[RuleTestInput] = Field(default_factory=list)
    comparison: dict[str, Any] = Field(default_factory=lambda: {"mode": "trim_trailing_whitespace"})
    execution: dict[str, Any] = Field(default_factory=dict)
    scoring: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def has_rubric(self) -> "RulesDocument":
        if not self.metrics and not self.criteria:
            raise ValueError("rules must define either metrics or criteria")
        if self.metrics and self.criteria:
            raise ValueError("define metrics or criteria, not both")
        return self

    @field_validator("comparison")
    @classmethod
    def supported_comparison(cls, value: dict[str, Any]) -> dict[str, Any]:
        mode = value.get("mode", "trim_trailing_whitespace")
        if mode not in {"exact", "trim_trailing_whitespace", "whitespace"}:
            raise ValueError(f"unsupported comparison mode: {mode}")
        return value


class NormalizedCriterion(ApiModel):
    id: str
    name: str
    analyzer: str
    weight: float
    description: str
    params: dict[str, Any] = Field(default_factory=dict)
    scoring_mode: Literal["test_ratio", "evidence_score", "evidence_status", "fixed"]
    missing_evidence: Literal["needs_review", "not_applicable", "zero"] = "needs_review"
    max_points: float = 100.0


class NormalizedTest(ApiModel):
    id: str
    input: str
    expected_output: str | None = None
    expected_behavior: str | None = None
    comparator: str
    rationale: str
    provenance: str
    status: str
    requirement_id: str | None = None
    score_affecting: bool = True
    validation_note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssignmentSpec(ApiModel):
    schema_version: str = "1.0"
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    criteria: list[NormalizedCriterion] = Field(default_factory=list)
    tests: list[NormalizedTest] = Field(default_factory=list)
    ambiguities: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)


class CreateAssignmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    problem_statement: str = Field(min_length=1, max_length=500_000)
    rules: dict[str, Any]


class AssignmentSummary(ApiModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class AssignmentVersionSummary(ApiModel):
    id: str
    assignment_id: str
    version_number: int
    status: str
    version_hash: str
    created_at: datetime
    activated_at: datetime | None = None
    spec: AssignmentSpec | None = None


class AssignmentDetail(AssignmentSummary):
    problem_statement: str
    rules: dict[str, Any]
    versions: list[AssignmentVersionSummary] = Field(default_factory=list)


class PrepareResponse(ApiModel):
    version: AssignmentVersionSummary
    warnings: list[str] = Field(default_factory=list)


class BatchSummary(ApiModel):
    id: str
    assignment_version_id: str
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class LiveStageEvent(ApiModel):
    id: str
    event_type: str
    state: str | None = None
    stage: str | None = None
    stage_label: str | None = None
    detail: str | None = None
    progress: int | None = None
    created_at: datetime


class LiveEvaluation(ApiModel):
    id: str
    submission_id: str
    submission_label: str
    state: str
    progress: int
    current_stage: str | None = None
    current_stage_label: str
    current_detail: str | None = None
    next_stage: str | None = None
    next_stage_label: str | None = None
    attempt: int
    error_summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime
    stage_history: list[LiveStageEvent] = Field(default_factory=list)


class BatchLiveResponse(ApiModel):
    batch: BatchSummary
    total_submissions: int
    queued: int
    running: int
    completed: int
    needs_review: int
    failed: int
    cancelled: int
    overall_progress: int
    last_updated_at: datetime
    runs: list[LiveEvaluation] = Field(default_factory=list)
    active_runs: list[LiveEvaluation] = Field(default_factory=list)
    recent_events: list[LiveStageEvent] = Field(default_factory=list)


class SubmissionSummary(ApiModel):
    id: str
    batch_id: str
    assignment_version_id: str
    label: str
    original_filename: str
    content_hash: str
    source_size: int
    status: str
    created_at: datetime


class EvaluationSummary(ApiModel):
    id: str
    submission_id: str
    assignment_version_id: str
    state: str
    progress: int
    current_stage: str | None = None
    attempt: int
    error_summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EvidenceResponse(ApiModel):
    id: str
    assignment_version_id: str
    submission_id: str
    run_id: str
    source_type: str
    requirement_id: str | None = None
    rubric_criterion_id: str | None = None
    test_id: str | None = None
    status: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    source_location: dict[str, Any] | None = None
    input: str | None = None
    expected_output: str | None = None
    actual_output: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CriterionScore(ApiModel):
    criterion_id: str
    name: str
    weight: float
    points: float | None
    contribution: float | None
    status: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class ScoreResponse(ApiModel):
    total_score: float | None
    finalized: bool
    scoring_rule_version: str
    criteria: list[CriterionScore] = Field(default_factory=list)
    calculation_trace: dict[str, Any] = Field(default_factory=dict)


class ReportResponse(ApiModel):
    id: str
    run_id: str
    report: dict[str, Any]
    created_at: datetime


class SubmissionResult(ApiModel):
    submission: SubmissionSummary
    evaluation: EvaluationSummary | None = None
    score: ScoreResponse | None = None
    report: ReportResponse | None = None
    source_content: str | None = None


class SimilarityFindingResponse(ApiModel):
    id: str
    assignment_version_id: str
    left_submission_id: str
    right_submission_id: str
    score: float
    method: str
    details: dict[str, Any] = Field(default_factory=dict)
    review_status: str
    disposition: str | None = None
    created_at: datetime


class DispositionRequest(BaseModel):
    disposition: Literal["confirmed_overlap", "benign_similarity", "needs_manual_review"]


class HealthResponse(ApiModel):
    status: str
    service: str
    version: str


class DependencyHealth(ApiModel):
    name: str
    available: bool
    detail: str
    version: str | None = None


class DependenciesResponse(ApiModel):
    dependencies: list[DependencyHealth]
    configured_runner: str = "bubblewrap"
