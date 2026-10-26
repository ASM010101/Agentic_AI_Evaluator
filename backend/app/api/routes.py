from __future__ import annotations

import csv
import io
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.db.models import (
    Assignment,
    AssignmentVersion,
    AuditEvent,
    Evidence,
    EvaluationRun,
    Report,
    ScoreBreakdown,
    SimilarityFinding,
    Submission,
    SubmissionBatch,
)
from app.llm.client import OllamaClient
from app.rules import RulesError
from app.schemas import (
    AssignmentDetail,
    AssignmentSpec,
    AssignmentSummary,
    AssignmentVersionSummary,
    BatchLiveResponse,
    BatchSummary,
    CreateAssignmentRequest,
    DependenciesResponse,
    DependencyHealth,
    DispositionRequest,
    EvaluationSummary,
    EvidenceResponse,
    HealthResponse,
    LiveEvaluation,
    LiveStageEvent,
    PrepareResponse,
    ReportResponse,
    ScoreResponse,
    SimilarityFindingResponse,
    SubmissionResult,
    SubmissionSummary,
)
from app.orchestration.state_machine import next_stage, stage_label
from app.sandbox.runner import BubblewrapSandboxRunner, DockerSandboxRunner
from app.services.assignments import (
    activate_version,
    create_assignment,
    get_assignment,
    get_version,
    prepare_assignment,
)
from app.services.evaluation import EvaluationCoordinator
from app.services.uploads import UploadValidationError, create_batch


router = APIRouter(prefix="/api")


def _http_error(exc: Exception, status_code: int = 422) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": "validation_error", "message": str(exc)}
    )


def _version_summary(version: AssignmentVersion) -> AssignmentVersionSummary:
    return AssignmentVersionSummary(
        id=version.id,
        assignment_id=version.assignment_id,
        version_number=version.version_number,
        status=version.status,
        version_hash=version.version_hash,
        created_at=version.created_at,
        activated_at=version.activated_at,
        spec=AssignmentSpec.model_validate(version.spec_json),
    )


def _assignment_summary(assignment: Assignment) -> AssignmentSummary:
    return AssignmentSummary.model_validate(assignment)


def _batch_summary(batch: SubmissionBatch) -> BatchSummary:
    return BatchSummary(
        id=batch.id,
        assignment_version_id=batch.assignment_version_id,
        status=batch.status,
        summary=batch.summary_json,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )


_RUNNING_STATES = {
    "queued",
    "preparing",
    "compiling",
    "testing",
    "analyzing",
    "validating_evidence",
    "scoring",
    "reporting",
}
_TERMINAL_STATES = {"completed", "needs_review", "failed", "cancelled"}


def _live_event(event: AuditEvent) -> LiveStageEvent:
    details = event.details_json or {}
    state = details.get("state")
    stage = details.get("stage")
    return LiveStageEvent(
        id=event.id,
        event_type=event.event_type,
        state=state,
        stage=stage,
        stage_label=stage_label(stage or state),
        detail=details.get("detail"),
        progress=details.get("progress"),
        created_at=event.created_at,
    )


def _live_evaluation(
    run: EvaluationRun, submission: Submission, history: list[LiveStageEvent]
) -> LiveEvaluation:
    current = run.current_stage or run.state
    upcoming = next_stage(current, run.state)
    current_detail = next(
        (event.detail for event in history if event.stage == current and event.detail), None
    )
    return LiveEvaluation(
        id=run.id,
        submission_id=submission.id,
        submission_label=submission.label,
        state=run.state,
        progress=run.progress,
        current_stage=run.current_stage,
        current_stage_label=stage_label(current),
        current_detail=current_detail,
        next_stage=upcoming,
        next_stage_label=stage_label(upcoming) if upcoming else None,
        attempt=run.attempt,
        error_summary=run.error_summary,
        started_at=run.started_at,
        completed_at=run.completed_at,
        updated_at=run.updated_at,
        stage_history=history,
    )


def _submission_summary(submission: Submission) -> SubmissionSummary:
    return SubmissionSummary.model_validate(submission)


def _evaluation_summary(run: EvaluationRun) -> EvaluationSummary:
    return EvaluationSummary.model_validate(run)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="autograder-api", version="0.1.0")


@router.get("/health/dependencies", response_model=DependenciesResponse)
def dependency_health(settings: Settings = Depends(get_settings)) -> DependenciesResponse:
    gcc = shutil.which("gcc")
    bubblewrap = BubblewrapSandboxRunner(settings)
    bubblewrap_available, bubblewrap_detail = bubblewrap.availability()
    dependencies = [
        DependencyHealth(
            name="gcc",
            available=bool(gcc),
            detail="GCC is installed" if gcc else "GCC is missing",
        ),
        DependencyHealth(
            name="bubblewrap",
            available=bubblewrap_available,
            detail=bubblewrap_detail,
            version="configured runner" if settings.runner == "bubblewrap" else "optional runner",
        ),
    ]
    if settings.runner == "docker":
        docker = DockerSandboxRunner(settings)
        docker_available, docker_detail = docker.availability()
        dependencies.append(
            DependencyHealth(name="docker", available=docker_available, detail=docker_detail)
        )
    ollama_available, ollama_detail, model = OllamaClient(settings).health_sync()
    dependencies.append(
        DependencyHealth(
            name="ollama", available=ollama_available, detail=ollama_detail, version=model
        )
    )
    return DependenciesResponse(
        configured_runner=settings.runner,
        dependencies=dependencies,
    )


@router.get("/settings/model-status", response_model=DependencyHealth)
def model_status(settings: Settings = Depends(get_settings)) -> DependencyHealth:
    available, detail, model = OllamaClient(settings).health_sync()
    return DependencyHealth(name="ollama", available=available, detail=detail, version=model)


@router.get("/assignments", response_model=list[AssignmentSummary])
def list_assignments(db: Session = Depends(get_db)) -> list[AssignmentSummary]:
    assignments = db.scalars(select(Assignment).order_by(Assignment.created_at.desc())).all()
    return [_assignment_summary(item) for item in assignments]


@router.post("/assignments", response_model=AssignmentSummary, status_code=201)
def create_assignment_route(
    request: CreateAssignmentRequest, db: Session = Depends(get_db)
) -> AssignmentSummary:
    try:
        return _assignment_summary(create_assignment(db, request))
    except RulesError as exc:
        raise _http_error(exc) from exc


@router.get("/assignments/{assignment_id}", response_model=AssignmentDetail)
def assignment_detail(assignment_id: str, db: Session = Depends(get_db)) -> AssignmentDetail:
    assignment = get_assignment(db, assignment_id)
    if not assignment:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "assignment not found"}
        )
    versions = db.scalars(
        select(AssignmentVersion)
        .where(AssignmentVersion.assignment_id == assignment.id)
        .order_by(AssignmentVersion.version_number.desc())
    ).all()
    return AssignmentDetail(
        **_assignment_summary(assignment).model_dump(),
        problem_statement=assignment.problem_statement,
        rules=assignment.rules_json,
        versions=[_version_summary(version) for version in versions],
    )


@router.get("/assignments/{assignment_id}/versions", response_model=list[AssignmentVersionSummary])
def assignment_versions(
    assignment_id: str, db: Session = Depends(get_db)
) -> list[AssignmentVersionSummary]:
    if not get_assignment(db, assignment_id):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "assignment not found"}
        )
    versions = db.scalars(
        select(AssignmentVersion)
        .where(AssignmentVersion.assignment_id == assignment_id)
        .order_by(AssignmentVersion.version_number.desc())
    ).all()
    return [_version_summary(version) for version in versions]


@router.post("/assignments/{assignment_id}/prepare", response_model=PrepareResponse)
def prepare_route(
    assignment_id: str,
    request: CreateAssignmentRequest | None = None,
    db: Session = Depends(get_db),
) -> PrepareResponse:
    assignment = get_assignment(db, assignment_id)
    if not assignment:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "assignment not found"}
        )
    try:
        version, warnings = prepare_assignment(db, assignment, request)
    except (RulesError, ValueError) as exc:
        raise _http_error(exc) from exc
    return PrepareResponse(version=_version_summary(version), warnings=warnings)


@router.post(
    "/assignments/{assignment_id}/versions/{version_number}/activate",
    response_model=AssignmentVersionSummary,
)
def activate_route(
    assignment_id: str, version_number: int, db: Session = Depends(get_db)
) -> AssignmentVersionSummary:
    version = get_version(db, assignment_id, version_number)
    if not version:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "assignment version not found"}
        )
    try:
        return _version_summary(activate_version(db, version))
    except ValueError as exc:
        raise _http_error(exc, 409) from exc


@router.post("/assignments/{assignment_id}/batches", response_model=BatchSummary, status_code=201)
async def create_batch_route(
    assignment_id: str,
    version_number: int = Form(...),
    labels_json: str | None = Form(None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BatchSummary:
    version = get_version(db, assignment_id, version_number)
    if not version:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "assignment version not found"}
        )
    try:
        batch, _submissions = await create_batch(db, version, files, settings, labels_json)
    except UploadValidationError as exc:
        db.rollback()
        raise _http_error(exc) from exc
    return _batch_summary(batch)


@router.get("/batches/{batch_id}", response_model=BatchSummary)
def batch_detail(batch_id: str, db: Session = Depends(get_db)) -> BatchSummary:
    batch = db.get(SubmissionBatch, batch_id)
    if not batch:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "batch not found"}
        )
    return _batch_summary(batch)


@router.get("/batches/{batch_id}/live", response_model=BatchLiveResponse)
def batch_live(batch_id: str, db: Session = Depends(get_db)) -> BatchLiveResponse:
    """Return the operator-facing live monitor for a submission batch.

    The dashboard polls this single endpoint while work is active. It exposes
    the latest run for each submission, the current/next pipeline stage and
    the audit-backed stage history without requiring the UI to guess from a
    batch status alone.
    """

    batch = db.get(SubmissionBatch, batch_id)
    if not batch:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "batch not found"}
        )
    submissions = db.scalars(
        select(Submission).where(Submission.batch_id == batch_id).order_by(Submission.created_at)
    ).all()
    submission_by_id = {submission.id: submission for submission in submissions}
    if not submissions:
        return BatchLiveResponse(
            batch=_batch_summary(batch),
            total_submissions=0,
            queued=0,
            running=0,
            completed=0,
            needs_review=0,
            failed=0,
            cancelled=0,
            overall_progress=0,
            last_updated_at=batch.updated_at,
        )

    runs = db.scalars(
        select(EvaluationRun)
        .where(EvaluationRun.submission_id.in_(list(submission_by_id)))
        .order_by(EvaluationRun.created_at.desc())
    ).all()
    latest_runs: dict[str, EvaluationRun] = {}
    for run in runs:
        latest_runs.setdefault(run.submission_id, run)

    run_ids = list(latest_runs.values())
    history_by_run: dict[str, list[LiveStageEvent]] = {run.id: [] for run in run_ids}
    if run_ids:
        events = db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == "evaluation_run",
                AuditEvent.entity_id.in_([run.id for run in run_ids]),
            )
            .order_by(AuditEvent.created_at.desc())
        ).all()
        for event in events:
            history_by_run.setdefault(event.entity_id, []).append(_live_event(event))

    live_runs = [
        _live_evaluation(latest_runs[submission.id], submission, history_by_run[run.id])
        for submission in submissions
        if (run := latest_runs.get(submission.id)) is not None
    ]
    active_runs = [run for run in live_runs if run.state not in _TERMINAL_STATES]
    missing_runs = len(submissions) - len(live_runs)
    queued = sum(run.state == "queued" for run in live_runs)
    if batch.status in {"queued", "evaluating"}:
        queued += missing_runs
    counts = {
        "queued": queued,
        "running": sum(run.state in _RUNNING_STATES - {"queued"} for run in live_runs),
        "completed": sum(run.state == "completed" for run in live_runs),
        "needs_review": sum(run.state == "needs_review" for run in live_runs),
        "failed": sum(run.state == "failed" for run in live_runs),
        "cancelled": sum(run.state == "cancelled" for run in live_runs),
    }
    progress_total = sum(run.progress for run in live_runs)
    overall_progress = round(progress_total / len(submissions)) if submissions else 0
    recent_events = sorted(
        (event for history in history_by_run.values() for event in history),
        key=lambda event: event.created_at,
        reverse=True,
    )[:20]
    timestamps = [batch.updated_at, *[run.updated_at for run in live_runs]]
    if recent_events:
        timestamps.append(recent_events[0].created_at)
    last_updated_at = max(timestamps)
    return BatchLiveResponse(
        batch=_batch_summary(batch),
        total_submissions=len(submissions),
        **counts,
        overall_progress=overall_progress,
        last_updated_at=last_updated_at,
        runs=live_runs,
        active_runs=active_runs,
        recent_events=recent_events,
    )


@router.get("/batches/{batch_id}/submissions", response_model=list[SubmissionSummary])
def batch_submissions(batch_id: str, db: Session = Depends(get_db)) -> list[SubmissionSummary]:
    submissions = db.scalars(select(Submission).where(Submission.batch_id == batch_id)).all()
    return [_submission_summary(item) for item in submissions]


@router.post(
    "/batches/{batch_id}/evaluate", response_model=list[EvaluationSummary], status_code=202
)
def evaluate_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[EvaluationSummary]:
    batch = db.get(SubmissionBatch, batch_id)
    if not batch:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "batch not found"}
        )
    submissions = db.scalars(select(Submission).where(Submission.batch_id == batch_id)).all()
    runs: list[EvaluationRun] = []
    for submission in submissions:
        latest = db.scalar(
            select(EvaluationRun)
            .where(EvaluationRun.submission_id == submission.id)
            .order_by(EvaluationRun.created_at.desc())
        )
        if latest and latest.state in {
            "queued",
            "preparing",
            "compiling",
            "testing",
            "analyzing",
            "validating_evidence",
            "scoring",
            "reporting",
        }:
            runs.append(latest)
            continue
        run = EvaluationRun(
            submission_id=submission.id,
            assignment_version_id=batch.assignment_version_id,
            state="queued",
            config_snapshot={"runner": settings.runner, "docker_image": settings.docker_image},
        )
        db.add(run)
        db.flush()
        runs.append(run)
    batch.status = "queued"
    db.commit()
    background_tasks.add_task(EvaluationCoordinator(settings).run_batch, batch_id)
    return [_evaluation_summary(item) for item in runs]


@router.get("/evaluations", response_model=list[EvaluationSummary])
def list_evaluations(db: Session = Depends(get_db)) -> list[EvaluationSummary]:
    runs = db.scalars(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(100)
    ).all()
    return [_evaluation_summary(item) for item in runs]


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationSummary)
def evaluation_detail(evaluation_id: str, db: Session = Depends(get_db)) -> EvaluationSummary:
    run = db.get(EvaluationRun, evaluation_id)
    if not run:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "evaluation not found"}
        )
    return _evaluation_summary(run)


@router.post("/evaluations/{evaluation_id}/cancel", response_model=EvaluationSummary)
def cancel_evaluation(evaluation_id: str, db: Session = Depends(get_db)) -> EvaluationSummary:
    run = db.get(EvaluationRun, evaluation_id)
    if not run:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "evaluation not found"}
        )
    if run.state in {"completed", "failed", "cancelled"}:
        raise _http_error("only queued or running evaluations can be cancelled", 409)
    run.state = "cancelled"
    run.current_stage = "cancelled"
    run.error_summary = "cancelled by operator"
    db.add(
        AuditEvent(
            entity_type="evaluation_run", entity_id=run.id, event_type="cancelled", details_json={}
        )
    )
    db.commit()
    return _evaluation_summary(run)


@router.post(
    "/evaluations/{evaluation_id}/retry", response_model=EvaluationSummary, status_code=202
)
def retry_evaluation(
    evaluation_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> EvaluationSummary:
    previous = db.get(EvaluationRun, evaluation_id)
    if not previous:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "evaluation not found"}
        )
    if previous.state not in {"failed", "needs_review"}:
        raise _http_error("only failed or needs-review evaluations can be retried", 409)
    run = EvaluationRun(
        submission_id=previous.submission_id,
        assignment_version_id=previous.assignment_version_id,
        state="queued",
        attempt=previous.attempt + 1,
        retry_of=previous.id,
        config_snapshot=previous.config_snapshot,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(EvaluationCoordinator(settings).evaluate_run, run.id)
    return _evaluation_summary(run)


@router.get("/submissions/{submission_id}/results", response_model=SubmissionResult)
def submission_result(submission_id: str, db: Session = Depends(get_db)) -> SubmissionResult:
    submission = db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "submission not found"}
        )
    run = db.scalar(
        select(EvaluationRun)
        .where(EvaluationRun.submission_id == submission_id)
        .order_by(EvaluationRun.created_at.desc())
    )
    score = (
        db.scalar(select(ScoreBreakdown).where(ScoreBreakdown.run_id == run.id)) if run else None
    )
    report = db.scalar(select(Report).where(Report.run_id == run.id)) if run else None
    score_response = None
    if score:
        score_response = ScoreResponse(
            total_score=score.total_score,
            finalized=score.finalized,
            scoring_rule_version=score.scoring_rule_version,
            criteria=score.criteria_json,
            calculation_trace=score.calculation_trace_json,
        )
    report_response = (
        ReportResponse(
            id=report.id,
            run_id=report.run_id,
            report=report.report_json,
            created_at=report.created_at,
        )
        if report
        else None
    )
    return SubmissionResult(
        submission=_submission_summary(submission),
        evaluation=_evaluation_summary(run) if run else None,
        score=score_response,
        report=report_response,
        source_content=submission.source_content,
    )


@router.get("/submissions/{submission_id}/evidence", response_model=list[EvidenceResponse])
def submission_evidence(
    submission_id: str, db: Session = Depends(get_db)
) -> list[EvidenceResponse]:
    rows = db.scalars(
        select(Evidence)
        .where(Evidence.submission_id == submission_id)
        .order_by(Evidence.created_at)
    ).all()
    return [
        EvidenceResponse(
            id=row.id,
            assignment_version_id=row.assignment_version_id,
            submission_id=row.submission_id,
            run_id=row.run_id,
            source_type=row.source_type,
            requirement_id=row.requirement_id,
            rubric_criterion_id=row.rubric_criterion_id,
            test_id=row.test_id,
            status=row.status,
            summary=row.summary,
            details=row.details_json,
            source_location=row.source_location_json,
            input=row.input_data,
            expected_output=row.expected_output,
            actual_output=row.actual_output,
            provenance=row.provenance_json,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/reports/{report_id}/download")
def download_report(report_id: str, format: str = "txt", db: Session = Depends(get_db)) -> Response:
    if format not in {"txt", "json"}:
        raise _http_error("format must be txt or json")
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "report not found"}
        )
    path = Path(report.json_path if format == "json" else report.text_path or "")
    if not path.exists() or path.is_dir():
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "report artifact not found"}
        )
    return FileResponse(
        path,
        media_type="application/json" if format == "json" else "text/plain",
        filename=path.name,
    )


@router.get("/similarity/findings", response_model=list[SimilarityFindingResponse])
def similarity_findings(
    assignment_version_id: str | None = None, db: Session = Depends(get_db)
) -> list[SimilarityFindingResponse]:
    statement = select(SimilarityFinding).order_by(SimilarityFinding.score.desc())
    if assignment_version_id:
        statement = statement.where(
            SimilarityFinding.assignment_version_id == assignment_version_id
        )
    rows = db.scalars(statement.limit(500)).all()
    return [
        SimilarityFindingResponse(
            id=row.id,
            assignment_version_id=row.assignment_version_id,
            left_submission_id=row.left_submission_id,
            right_submission_id=row.right_submission_id,
            score=row.score,
            method=row.method,
            details=row.details_json,
            review_status=row.review_status,
            disposition=row.disposition,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post(
    "/similarity/findings/{finding_id}/disposition", response_model=SimilarityFindingResponse
)
def similarity_disposition(
    finding_id: str, request: DispositionRequest, db: Session = Depends(get_db)
) -> SimilarityFindingResponse:
    row = db.get(SimilarityFinding, finding_id)
    if not row:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "similarity finding not found"}
        )
    row.disposition = request.disposition
    row.review_status = "reviewed"
    db.add(
        AuditEvent(
            entity_type="similarity_finding",
            entity_id=row.id,
            event_type="disposition_set",
            details_json=request.model_dump(),
        )
    )
    db.commit()
    return SimilarityFindingResponse(
        id=row.id,
        assignment_version_id=row.assignment_version_id,
        left_submission_id=row.left_submission_id,
        right_submission_id=row.right_submission_id,
        score=row.score,
        method=row.method,
        details=row.details_json,
        review_status=row.review_status,
        disposition=row.disposition,
        created_at=row.created_at,
    )


def _safe_csv(value: Any) -> Any:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


@router.get("/batches/{batch_id}/export.csv")
def export_batch_csv(batch_id: str, db: Session = Depends(get_db)) -> Response:
    batch = db.get(SubmissionBatch, batch_id)
    if not batch:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "batch not found"}
        )
    rows = db.scalars(select(Submission).where(Submission.batch_id == batch_id)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["submission", "label", "status", "score", "evaluation_state", "error"])
    for submission in rows:
        run = db.scalar(
            select(EvaluationRun)
            .where(EvaluationRun.submission_id == submission.id)
            .order_by(EvaluationRun.created_at.desc())
        )
        score = (
            db.scalar(select(ScoreBreakdown).where(ScoreBreakdown.run_id == run.id))
            if run
            else None
        )
        writer.writerow(
            [
                _safe_csv(submission.original_filename),
                _safe_csv(submission.label),
                _safe_csv(submission.status),
                _safe_csv(score.total_score if score else None),
                _safe_csv(run.state if run else None),
                _safe_csv(run.error_summary if run else None),
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="autograder-{batch_id}.csv"'},
    )
