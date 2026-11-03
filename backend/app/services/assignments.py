from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.agents.assignment_agent import AssignmentUnderstandingAgent
from app.db.models import (
    Assignment,
    AssignmentVersion,
    AuditEvent,
    Evidence,
    EvaluationRun,
    SimilarityFinding,
    Submission,
    SubmissionBatch,
    TestCase,
)
from app.rules import NormalizedRules, can_activate, normalize_rules
from app.schemas import AssignmentSpec, CreateAssignmentRequest


def _audit(
    db: Session, entity_type: str, entity_id: str, event_type: str, details: dict[str, Any]
) -> None:
    db.add(
        AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            details_json=details,
        )
    )


def create_assignment(db: Session, request: CreateAssignmentRequest) -> Assignment:
    # Validate at creation time so invalid JSON rules never become a durable
    # assignment draft that the UI cannot explain.
    normalized = normalize_rules(request.rules, request.problem_statement)
    assignment = Assignment(
        name=request.name.strip(),
        problem_statement=request.problem_statement,
        rules_json=normalized.raw,
    )
    db.add(assignment)
    db.flush()
    _audit(db, "assignment", assignment.id, "created", {"name": assignment.name})
    db.commit()
    db.refresh(assignment)
    return assignment


def get_assignment(db: Session, assignment_id: str) -> Assignment | None:
    return db.get(Assignment, assignment_id)


def get_version(db: Session, assignment_id: str, version_number: int) -> AssignmentVersion | None:
    return db.scalar(
        select(AssignmentVersion).where(
            AssignmentVersion.assignment_id == assignment_id,
            AssignmentVersion.version_number == version_number,
        )
    )


def prepare_assignment(
    db: Session, assignment: Assignment, request: CreateAssignmentRequest | None = None
) -> tuple[AssignmentVersion, list[str]]:
    if request is None:
        request = CreateAssignmentRequest(
            name=assignment.name,
            problem_statement=assignment.problem_statement,
            rules=assignment.rules_json,
        )
    normalized: NormalizedRules = normalize_rules(request.rules, request.problem_statement)
    latest = db.scalar(
        select(func.max(AssignmentVersion.version_number)).where(
            AssignmentVersion.assignment_id == assignment.id
        )
    )
    version_number = int(latest or 0) + 1
    version = AssignmentVersion(
        assignment_id=assignment.id,
        version_number=version_number,
        problem_statement=request.problem_statement,
        rules_json=normalized.raw,
        spec_json=normalized.spec.model_dump(mode="json"),
        version_hash=normalized.rules_hash,
        status="needs_review" if normalized.spec.ambiguities else "prepared",
    )
    db.add(version)
    db.flush()
    agent = AssignmentUnderstandingAgent()
    spec = agent.prepare(normalized)
    for test in spec.tests:
        db.add(
            TestCase(
                # Test IDs are stable within an assignment version. The
                # database primary key is scoped so two assignments can both
                # use common IDs such as "sample" or "zero".
                id=f"{version.id}:{test.id}",
                assignment_version_id=version.id,
                input_data=test.input,
                expected_output=test.expected_output,
                expected_behavior=test.expected_behavior,
                comparator_json={"mode": test.comparator},
                rationale=test.rationale,
                provenance=test.provenance,
                status=test.status,
                requirement_id=test.requirement_id,
                metadata_json={**test.metadata, "test_id": test.id},
                score_affecting=test.score_affecting,
                validation_note=test.validation_note,
            )
        )
    _audit(
        db,
        "assignment_version",
        version.id,
        "prepared",
        {"version_number": version_number, "rules_hash": normalized.rules_hash},
    )
    db.commit()
    db.refresh(version)
    return version, [item["message"] for item in spec.ambiguities]


def activate_version(db: Session, version: AssignmentVersion) -> AssignmentVersion:
    spec = AssignmentSpec.model_validate(version.spec_json)
    allowed, warnings = can_activate(spec)
    if not allowed:
        raise ValueError("cannot activate assignment version: " + "; ".join(warnings))
    active_versions = db.scalars(
        select(AssignmentVersion).where(
            AssignmentVersion.assignment_id == version.assignment_id,
            AssignmentVersion.status == "active",
        )
    ).all()
    for item in active_versions:
        item.status = "superseded"
    version.status = "active"
    version.activated_at = datetime.now(timezone.utc)
    _audit(
        db,
        "assignment_version",
        version.id,
        "activated",
        {"version_number": version.version_number},
    )
    db.commit()
    db.refresh(version)
    return version


def delete_version(db: Session, version: AssignmentVersion) -> None:
    if version.status == "active":
        raise ValueError("cannot delete the active version; activate another version first")

    references = (
        (SubmissionBatch, "submission batches"),
        (Submission, "submissions"),
        (EvaluationRun, "evaluation runs"),
        (Evidence, "evidence records"),
        (SimilarityFinding, "similarity findings"),
    )
    for model, label in references:
        reference = db.scalar(
            select(model.id).where(model.assignment_version_id == version.id).limit(1)
        )
        if reference is not None:
            raise ValueError(f"cannot delete this version; it has {label} attached")

    version_id = version.id
    version_number = version.version_number
    db.execute(delete(TestCase).where(TestCase.assignment_version_id == version_id))
    db.delete(version)
    _audit(
        db,
        "assignment_version",
        version_id,
        "deleted",
        {"version_number": version_number},
    )
    db.commit()
