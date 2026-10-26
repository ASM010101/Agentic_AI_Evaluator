from __future__ import annotations

from enum import StrEnum


class RunState(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    COMPILING = "compiling"
    TESTING = "testing"
    ANALYZING = "analyzing"
    VALIDATING_EVIDENCE = "validating_evidence"
    SCORING = "scoring"
    REPORTING = "reporting"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    CANCELLED = "cancelled"


VALID_TRANSITIONS: dict[str, set[str]] = {
    RunState.QUEUED: {RunState.PREPARING, RunState.CANCELLED},
    RunState.PREPARING: {RunState.COMPILING, RunState.FAILED, RunState.CANCELLED},
    RunState.COMPILING: {RunState.TESTING, RunState.ANALYZING, RunState.FAILED, RunState.CANCELLED},
    RunState.TESTING: {RunState.ANALYZING, RunState.FAILED, RunState.CANCELLED},
    RunState.ANALYZING: {RunState.VALIDATING_EVIDENCE, RunState.FAILED, RunState.CANCELLED},
    RunState.VALIDATING_EVIDENCE: {RunState.SCORING, RunState.NEEDS_REVIEW, RunState.FAILED},
    RunState.SCORING: {RunState.REPORTING, RunState.NEEDS_REVIEW, RunState.FAILED},
    RunState.REPORTING: {RunState.COMPLETED, RunState.NEEDS_REVIEW, RunState.FAILED},
    RunState.NEEDS_REVIEW: {RunState.QUEUED, RunState.CANCELLED},
    RunState.FAILED: {RunState.QUEUED, RunState.CANCELLED},
    RunState.COMPLETED: set(),
    RunState.CANCELLED: set(),
}


class InvalidTransition(ValueError):
    pass


RUN_STAGE_ORDER: tuple[str, ...] = (
    "preparing",
    "compiling",
    "validated_tests",
    "source_and_safety_analysis",
    "evidence_validation",
    "scoring",
    "reporting",
    "completed",
)

RUN_STAGE_LABELS: dict[str, str] = {
    "queued": "Queued",
    "preparing": "Preparing run",
    "compiling": "Compiling C source",
    "validated_tests": "Running validated tests",
    "source_and_safety_analysis": "Analyzing source and safety",
    "evidence_validation": "Validating evidence",
    "scoring": "Calculating score",
    "reporting": "Writing report",
    "completed": "Completed",
    "needs_review": "Needs instructor review",
    "failed": "Failed",
    "cancelled": "Cancelled",
    "compile_failed": "Compilation failed",
    "sandbox_unavailable": "Sandbox unavailable",
    "scoring_incomplete": "Scoring needs review",
}

RUN_NEXT_STAGE: dict[str, str | None] = {
    "queued": "preparing",
    "preparing": "compiling",
    "compiling": "validated_tests",
    "validated_tests": "source_and_safety_analysis",
    "source_and_safety_analysis": "evidence_validation",
    "evidence_validation": "scoring",
    "scoring": "reporting",
    "reporting": "completed",
    "completed": None,
    "needs_review": None,
    "failed": None,
    "cancelled": None,
}


def stage_label(stage: str | None) -> str:
    if not stage:
        return RUN_STAGE_LABELS["queued"]
    return RUN_STAGE_LABELS.get(stage, stage.replace("_", " ").capitalize())


def next_stage(stage: str | None, state: str | None = None) -> str | None:
    key = state if state in RUN_NEXT_STAGE else stage
    return RUN_NEXT_STAGE.get(key or "queued")


def transition(current: str, target: str) -> str:
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransition(f"illegal evaluation transition: {current} -> {target}")
    return target
