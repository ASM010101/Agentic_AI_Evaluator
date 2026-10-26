from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.report_agent import build_report, render_text
from app.agents.solution_agent import analyze_solution
from app.core.config import Settings
from app.core.db import new_session
from app.db.models import (
    AssignmentVersion,
    AuditEvent,
    Evidence,
    EvaluationRun,
    Report,
    ScoreBreakdown,
    SimilarityFinding,
    Submission,
    SubmissionBatch,
    TestCase,
)
from app.sandbox.runner import (
    BubblewrapSandboxRunner,
    CompileResult,
    RunnerConfig,
    SandboxRunner,
    ToolAnalysisResult,
    build_runner,
)
from app.schemas import AssignmentSpec, NormalizedCriterion, NormalizedTest
from app.scoring.engine import EvidenceLike, calculate_score
from app.services.artifacts import write_report_artifacts
from app.similarity.fingerprints import compare_sources
from app.testing.comparators import compare
from app.orchestration.state_machine import RunState, transition


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _set_state(
    db: Session,
    run: EvaluationRun,
    target: str,
    stage: str,
    progress: int,
    detail: str | None = None,
) -> None:
    run.state = transition(run.state, target)
    run.current_stage = stage
    run.progress = max(0, min(100, progress))
    if run.started_at is None:
        run.started_at = utcnow()
    db.flush()
    _audit(
        db,
        "evaluation_run",
        run.id,
        "state_changed",
        {
            "state": target,
            "stage": stage,
            "progress": progress,
            **({"detail": detail} if detail else {}),
        },
    )


def _update_progress(
    db: Session, run: EvaluationRun, stage: str, progress: int, detail: str
) -> None:
    """Persist an observable checkpoint without changing the state machine state."""

    run.current_stage = stage
    run.progress = max(0, min(100, progress))
    if run.started_at is None:
        run.started_at = utcnow()
    db.flush()
    _audit(
        db,
        "evaluation_run",
        run.id,
        "progress_updated",
        {"state": run.state, "stage": stage, "progress": run.progress, "detail": detail},
    )


def _evidence(
    db: Session,
    run: EvaluationRun,
    version: AssignmentVersion,
    submission: Submission,
    *,
    source_type: str,
    status: str,
    summary: str,
    criterion_id: str | None = None,
    requirement_id: str | None = None,
    test_id: str | None = None,
    details: dict[str, Any] | None = None,
    source_location: dict[str, Any] | None = None,
    input_data: str | None = None,
    expected_output: str | None = None,
    actual_output: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> Evidence:
    item = Evidence(
        assignment_version_id=version.id,
        submission_id=submission.id,
        run_id=run.id,
        source_type=source_type,
        requirement_id=requirement_id,
        rubric_criterion_id=criterion_id,
        test_id=test_id,
        status=status,
        summary=summary,
        details_json=details or {},
        source_location_json=source_location,
        input_data=input_data,
        expected_output=expected_output,
        actual_output=actual_output,
        provenance_json=provenance or {},
    )
    db.add(item)
    db.flush()
    return item


def _runner_config(
    version: AssignmentVersion, settings: Settings, flags: tuple[str, ...] | None = None
) -> RunnerConfig:
    rules = version.rules_json
    configured_flags = tuple(flags or settings.compiler_flags)
    return RunnerConfig(
        time_limit_s=float(rules.get("time_limit_s", settings.docker_timeout_s)),
        memory_limit_mb=int(rules.get("memory_limit_mb", 128)),
        output_limit_bytes=settings.max_output_bytes,
        compile_flags=configured_flags,
    )


def _functions(source: str) -> list[tuple[str, int, int]]:
    lines = source.splitlines()
    result: list[tuple[str, int, int]] = []
    pattern = re.compile(r"^\s*(?:[A-Za-z_]\w*[\s\*]+)+(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{")
    index = 0
    while index < len(lines):
        match = pattern.match(lines[index])
        if not match:
            index += 1
            continue
        depth = 0
        end = index
        for cursor in range(index, len(lines)):
            depth += lines[cursor].count("{") - lines[cursor].count("}")
            end = cursor
            if depth <= 0:
                break
        result.append((match.group("name"), index + 1, end + 1))
        index = end + 1
    return result


def source_metrics(source: str) -> dict[str, Any]:
    lines = source.splitlines()
    functions = _functions(source)
    cyclomatic = 1 + len(re.findall(r"\b(if|for|while|case)\b|&&|\|\|", source))
    max_function_length = max((end - start + 1 for _, start, end in functions), default=len(lines))
    comments = len(re.findall(r"//|/\*", source))
    long_lines = sum(len(line) > 100 for line in lines)
    single_letter_identifiers = len(
        re.findall(r"\b(?:int|char|long|float|double)\s+[a-z]\b", source)
    )
    readability = 0.55
    if comments:
        readability += 0.15
    if long_lines == 0:
        readability += 0.1
    if single_letter_identifiers == 0:
        readability += 0.1
    if len(functions) > 1:
        readability += 0.1
    readability = max(0.0, min(1.0, readability))
    return {
        "line_count": len(lines),
        "function_count": len(functions),
        "functions": [
            {"name": name, "start_line": start, "end_line": end} for name, start, end in functions
        ],
        "cyclomatic": cyclomatic,
        "max_function_length": max_function_length,
        "comments": comments,
        "long_lines": long_lines,
        "single_letter_identifiers": single_letter_identifiers,
        "readability_score": readability,
        "has_main": bool(re.search(r"\bmain\s*\(", source)),
        "has_reader": bool(re.search(r"\b(scanf|fgets|getchar|read)\s*\(", source)),
        "has_writer": bool(re.search(r"\b(printf|puts|putchar|fwrite|write)\s*\(", source)),
    }


def _criterion(spec: AssignmentSpec, analyzer: str, fallback: str) -> NormalizedCriterion | None:
    for criterion in spec.criteria:
        if criterion.analyzer == analyzer or criterion.id == fallback:
            return criterion
    return None


def _criterion_for_test(spec: AssignmentSpec) -> list[NormalizedCriterion]:
    return [
        criterion
        for criterion in spec.criteria
        if criterion.scoring_mode == "test_ratio"
        or criterion.analyzer in {"io_tests", "validated_tests", "edge_case_runner"}
    ]


def _add_compile_evidence(
    db: Session,
    run: EvaluationRun,
    version: AssignmentVersion,
    submission: Submission,
    spec: AssignmentSpec,
    result: CompileResult,
) -> None:
    criterion = next(
        (
            item
            for item in spec.criteria
            if item.analyzer in {"compiler_warnings", "syntax", "compile"} or item.id == "syntax"
        ),
        None,
    )
    if criterion is None:
        return
    if result.unavailable:
        status = "unavailable"
        score = None
        summary = result.error or "compiler sandbox unavailable"
    elif result.compiled:
        warnings = len(re.findall(r"\bwarning:", result.stderr, flags=re.IGNORECASE))
        threshold = int(criterion.params.get("max_warnings", 0))
        score = (
            1.0 if warnings <= threshold else max(0.0, 1.0 - min(1.0, (warnings - threshold) / 10))
        )
        status = "pass" if score >= 1 else "fail"
        summary = f"Compilation succeeded with {warnings} warning(s)."
    else:
        status = "fail"
        score = 0.0
        summary = "Compilation failed."
    _evidence(
        db,
        run,
        version,
        submission,
        source_type="compiler",
        status=status,
        summary=summary,
        criterion_id=criterion.id,
        details={
            "normalized_score": score,
            "compiled": result.compiled,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
            "unavailable": result.unavailable,
        },
        provenance={"tool": "gcc", "standard": "c11"},
    )


def _add_source_evidence(
    db: Session,
    run: EvaluationRun,
    version: AssignmentVersion,
    submission: Submission,
    spec: AssignmentSpec,
    metrics: dict[str, Any],
    solution_complexity: str,
) -> None:
    for criterion in spec.criteria:
        analyzer = criterion.analyzer
        score: float | None = None
        status = "pass"
        summary = "Source analysis completed."
        details: dict[str, Any] = {"metrics": metrics}
        if analyzer in {"static_analysis", "structure"}:
            max_cyclomatic = float(criterion.params.get("max_cyclomatic", metrics["cyclomatic"]))
            max_function_length = float(
                criterion.params.get("max_function_length", metrics["max_function_length"])
            )
            score = min(
                1.0,
                (
                    1.0
                    if metrics["cyclomatic"] <= max_cyclomatic
                    else max(0.0, max_cyclomatic / metrics["cyclomatic"])
                )
                * (
                    1.0
                    if metrics["max_function_length"] <= max_function_length
                    else max(0.0, max_function_length / metrics["max_function_length"])
                ),
            )
            status = "pass" if score >= 1 else "fail"
            summary = f"Cyclomatic estimate {metrics['cyclomatic']}; longest function {metrics['max_function_length']} line(s)."
        elif analyzer in {"function_split", "modularity"}:
            minimum = int(criterion.params.get("min_functions", 2))
            score = min(1.0, metrics["function_count"] / max(1, minimum))
            status = "pass" if score >= 1 else "fail"
            summary = (
                f"Detected {metrics['function_count']} function(s); rubric minimum is {minimum}."
            )
        elif analyzer in {"readability", "llm_review"}:
            score = metrics["readability_score"]
            status = "pass" if score >= 0.7 else "fail"
            summary = "Readability heuristic inspected comments, naming, line length and function organization."
            details["analysis_mode"] = "deterministic_fallback"
        elif analyzer in {"complexity_estimator", "complexity"}:
            required = str(criterion.params.get("required", ""))
            if not required:
                status = "inconclusive"
                score = None
                summary = "No explicit complexity requirement was supplied."
            else:
                score = 1.0 if solution_complexity.lower().startswith(required.lower()) else 0.0
                status = "pass" if score else "fail"
                summary = f"Estimated complexity {solution_complexity}; required {required}."
            details["estimated_complexity"] = solution_complexity
            details["required_complexity"] = required
        elif analyzer in {"sanitizer_run", "memory_safety"}:
            # A dedicated sanitizer evidence item is added by the coordinator
            # after execution. Do not create a duplicate here.
            continue
        elif analyzer in {"similarity_flag", "originality"}:
            # Batch-scoped similarity evidence is added separately.
            continue
        elif analyzer in {"io_tests", "validated_tests", "edge_case_runner", "compiler_warnings"}:
            continue
        else:
            status = "unavailable"
            score = None
            summary = f"No built-in analyzer is registered for {analyzer}."
        _evidence(
            db,
            run,
            version,
            submission,
            source_type="static_analysis",
            status=status,
            summary=summary,
            criterion_id=criterion.id,
            details={**details, "normalized_score": score},
            provenance={"tool": "autograder_source_heuristics", "version": "1"},
        )


def _add_local_tool_evidence(
    db: Session,
    run: EvaluationRun,
    version: AssignmentVersion,
    submission: Submission,
    settings: Settings,
    runner: SandboxRunner,
) -> None:
    """Record Codacy-aligned local C tool observations without auto-scoring them."""

    if not isinstance(runner, BubblewrapSandboxRunner):
        return
    tools: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "cppcheck",
            ("--enable=warning,style,performance,portability", "--template=gcc", "--quiet"),
        ),
        ("flawfinder", ("--dataonly", "--quiet")),
        ("clang-tidy", ()),
    )
    for tool, arguments in tools:
        result: ToolAnalysisResult = runner.analyze_tool(
            submission.source_content,
            tool,
            arguments,
            output_limit=min(settings.max_output_bytes, 20_000),
        )
        if not result.available:
            continue
        findings = "\n".join(item for item in (result.stdout, result.stderr) if item).strip()
        status = "requires_review" if findings or result.timed_out else "pass"
        summary = (
            f"{tool} reported source-analysis output."
            if findings
            else f"{tool} completed without reported findings."
        )
        _evidence(
            db,
            run,
            version,
            submission,
            source_type="static_analysis_tool",
            status=status,
            summary=summary,
            details={
                "tool": tool,
                "output": findings,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
                "timed_out": result.timed_out,
                "output_truncated": result.output_truncated,
                "normalized_score": None,
                "scoring_impact": False,
            },
            provenance={
                "tool": tool,
                "source": "local_linux_toolchain",
                "codacy_comparable": True,
            },
        )


def _add_similarity_evidence(
    db: Session,
    run: EvaluationRun,
    version: AssignmentVersion,
    submission: Submission,
    spec: AssignmentSpec,
    flagged: bool,
    score: float | None,
) -> None:
    for criterion in spec.criteria:
        if criterion.analyzer not in {"similarity_flag", "originality"}:
            continue
        # Similarity flags never reduce the score automatically. A clean
        # comparison is a pass; a flagged comparison remains review evidence.
        _evidence(
            db,
            run,
            version,
            submission,
            source_type="similarity",
            status="requires_review" if flagged else "pass",
            summary=(
                f"Potential assignment-scoped overlap detected (maximum similarity {score:.3f})."
                if flagged and score is not None
                else "No assignment-scoped similarity candidate exceeded the configured threshold."
            ),
            criterion_id=criterion.id,
            details={"normalized_score": 1.0, "flagged": flagged, "maximum_similarity": score},
            provenance={"method": "normalized_token_sequence_v1", "deducts_points": False},
        )


def compare_batch_similarity(
    db: Session, batch: SubmissionBatch, version: AssignmentVersion
) -> None:
    submissions = db.scalars(select(Submission).where(Submission.batch_id == batch.id)).all()
    criterion = next(
        (
            item
            for item in AssignmentSpec.model_validate(version.spec_json).criteria
            if item.analyzer in {"similarity_flag", "originality"}
        ),
        None,
    )
    if criterion is None:
        return
    threshold = float(criterion.params.get("flag_threshold", 0.85))
    db.execute(
        delete(SimilarityFinding).where(SimilarityFinding.assignment_version_id == version.id)
    )
    for index, left in enumerate(submissions):
        for right in submissions[index + 1 :]:
            result = compare_sources(left.source_content, right.source_content)
            if result.score < threshold:
                continue
            db.add(
                SimilarityFinding(
                    assignment_version_id=version.id,
                    left_submission_id=left.id,
                    right_submission_id=right.id,
                    score=result.score,
                    method=result.method,
                    details_json={
                        "shared_tokens": result.shared_tokens,
                        "left_excerpt": result.left_excerpt,
                        "right_excerpt": result.right_excerpt,
                        "caveats": result.caveats,
                        "threshold": threshold,
                    },
                    review_status="flagged",
                )
            )
    db.flush()


def _similarity_for_submission(db: Session, submission_id: str) -> tuple[bool, float | None]:
    findings = db.scalars(
        select(SimilarityFinding).where(
            (SimilarityFinding.left_submission_id == submission_id)
            | (SimilarityFinding.right_submission_id == submission_id)
        )
    ).all()
    if not findings:
        return False, None
    return True, max(item.score for item in findings)


class EvaluationCoordinator:
    def __init__(self, settings: Settings, runner: SandboxRunner | None = None):
        self.settings = settings
        self.runner = runner or build_runner(settings)

    def run_batch(self, batch_id: str) -> None:
        db = new_session()
        try:
            batch = db.get(SubmissionBatch, batch_id)
            if not batch:
                return
            version = db.get(AssignmentVersion, batch.assignment_version_id)
            if not version:
                batch.status = "failed"
                batch.summary_json = {"error": "assignment version not found"}
                db.commit()
                return
            batch.status = "evaluating"
            db.commit()
            compare_batch_similarity(db, batch, version)
            db.commit()
            submissions = db.scalars(
                select(Submission).where(Submission.batch_id == batch.id)
            ).all()
            for submission in submissions:
                existing = db.scalar(
                    select(EvaluationRun)
                    .where(EvaluationRun.submission_id == submission.id)
                    .order_by(EvaluationRun.created_at.desc())
                )
                if existing and existing.state in {
                    RunState.COMPLETED,
                    RunState.NEEDS_REVIEW,
                    RunState.FAILED,
                }:
                    continue
                run = existing or EvaluationRun(
                    submission_id=submission.id,
                    assignment_version_id=version.id,
                    state=RunState.QUEUED,
                    config_snapshot={
                        "runner": self.settings.runner,
                        "docker_image": self.settings.docker_image,
                        "compiler_flags": list(self.settings.compiler_flags),
                        "ollama_model": self.settings.ollama_model,
                    },
                )
                if existing is None:
                    db.add(run)
                    db.flush()
                db.commit()
                self.evaluate_run(run.id)
            self._finish_batch(batch_id)
        finally:
            db.close()

    def _finish_batch(self, batch_id: str) -> None:
        db = new_session()
        try:
            batch = db.get(SubmissionBatch, batch_id)
            if not batch:
                return
            runs = db.scalars(
                select(EvaluationRun).join(Submission).where(Submission.batch_id == batch_id)
            ).all()
            counts = {
                state: sum(run.state == state for run in runs)
                for state in ["queued", "completed", "failed", "needs_review", "cancelled"]
            }
            batch.summary_json = {"total": len(runs), **counts}
            if any(run.state == RunState.NEEDS_REVIEW for run in runs):
                batch.status = "needs_review"
            elif any(run.state == RunState.FAILED for run in runs):
                batch.status = "completed_with_errors"
            else:
                batch.status = "completed"
            db.commit()
        finally:
            db.close()

    def evaluate_run(self, run_id: str) -> None:
        db = new_session()
        run: EvaluationRun | None = None
        try:
            run = db.get(EvaluationRun, run_id)
            if not run or run.state in {RunState.COMPLETED, RunState.CANCELLED}:
                return
            submission = db.get(Submission, run.submission_id)
            version = db.get(AssignmentVersion, run.assignment_version_id)
            if not submission or not version:
                raise RuntimeError("submission or assignment version is missing")
            spec = AssignmentSpec.model_validate(version.spec_json)
            _set_state(
                db,
                run,
                RunState.PREPARING,
                "preparing",
                5,
                "Loading the immutable assignment version and submission.",
            )
            db.commit()
            _set_state(
                db,
                run,
                RunState.COMPILING,
                "compiling",
                15,
                "Compiling the submitted C source with the configured runner.",
            )
            db.commit()
            compile_result = self.runner.compile(
                submission.source_content, _runner_config(version, self.settings)
            )
            _add_compile_evidence(db, run, version, submission, spec, compile_result)
            db.commit()
            if compile_result.unavailable:
                run.error_summary = compile_result.error or "sandbox unavailable"
                run.state = transition(run.state, RunState.FAILED)
                run.current_stage = "sandbox_unavailable"
                run.completed_at = utcnow()
                submission.status = "failed"
                _audit(db, "evaluation_run", run.id, "failed", {"reason": run.error_summary})
                db.commit()
                return
            if not compile_result.compiled:
                run.error_summary = "student source did not compile"
                run.state = transition(run.state, RunState.FAILED)
                run.current_stage = "compile_failed"
                run.completed_at = utcnow()
                submission.status = "failed"
                db.commit()
                return

            _set_state(
                db,
                run,
                RunState.TESTING,
                "validated_tests",
                30,
                "Preparing validated score-affecting tests.",
            )
            db.commit()
            config = _runner_config(version, self.settings)
            test_criteria = _criterion_for_test(spec)
            tests = db.scalars(
                select(TestCase).where(TestCase.assignment_version_id == version.id)
            ).all()
            validated_tests = [
                test for test in tests if test.status == "validated" and test.score_affecting
            ]
            total_tests = len(validated_tests)
            for index, test in enumerate(validated_tests):
                test_id = str(test.metadata_json.get("test_id", test.id))
                test_progress = 30 + round((index / max(1, total_tests)) * 20)
                _update_progress(
                    db,
                    run,
                    "validated_tests",
                    test_progress,
                    f"Running validated test {index + 1} of {total_tests}: {test_id}",
                )
                db.commit()
                if test.expected_output is None:
                    continue
                execution = self.runner.run(submission.source_content, test.input_data, config)
                if execution.unavailable:
                    status = "unavailable"
                    normalized_score = None
                    summary = execution.error or "sandbox unavailable during test"
                elif execution.timed_out:
                    status = "fail"
                    normalized_score = 0.0
                    summary = f"Test {test_id} timed out after {config.time_limit_s:g}s."
                elif not execution.ran or execution.exit_code != 0:
                    status = "fail"
                    normalized_score = 0.0
                    summary = f"Test {test_id} exited abnormally with code {execution.exit_code}."
                else:
                    comparison = compare(
                        test.expected_output,
                        execution.stdout,
                        str(test.comparator_json.get("mode", "trim_trailing_whitespace")),
                    )
                    status = "pass" if comparison.passed else "fail"
                    normalized_score = 1.0 if comparison.passed else 0.0
                    summary = f"Test {test_id} {'passed' if comparison.passed else 'failed'}: {comparison.reason}."
                for criterion in test_criteria:
                    _evidence(
                        db,
                        run,
                        version,
                        submission,
                        source_type="test_runner",
                        status=status,
                        summary=summary,
                        criterion_id=criterion.id,
                        test_id=test_id,
                        details={
                            "normalized_score": normalized_score,
                            "exit_code": execution.exit_code,
                            "duration_ms": execution.duration_ms,
                            "timed_out": execution.timed_out,
                            "stderr": execution.stderr,
                        },
                        input_data=test.input_data,
                        expected_output=test.expected_output,
                        actual_output=execution.stdout,
                        provenance={
                            "runner": self.settings.runner,
                            "comparator": test.comparator_json,
                        },
                    )
                completed_progress = 30 + round(((index + 1) / max(1, total_tests)) * 20)
                _update_progress(
                    db,
                    run,
                    "validated_tests",
                    completed_progress,
                    f"Finished validated test {index + 1} of {total_tests}: {test_id}",
                )
                db.commit()
            if total_tests == 0:
                _update_progress(
                    db,
                    run,
                    "validated_tests",
                    50,
                    "No validated score-affecting tests were configured.",
                )
            db.commit()

            _set_state(
                db,
                run,
                RunState.ANALYZING,
                "source_and_safety_analysis",
                55,
                "Calculating source metrics and complexity indicators.",
            )
            db.commit()
            metrics = source_metrics(submission.source_content)
            _update_progress(
                db,
                run,
                "source_and_safety_analysis",
                62,
                "Comparing source metrics with the rubric criteria.",
            )
            db.commit()
            complexity_required = next(
                (
                    str(criterion.params.get("required"))
                    for criterion in spec.criteria
                    if criterion.analyzer in {"complexity_estimator", "complexity"}
                    and criterion.params.get("required")
                ),
                None,
            )
            solution = analyze_solution(submission.source_content, complexity_required)
            _add_source_evidence(
                db, run, version, submission, spec, metrics, solution.estimated_time_complexity
            )
            _add_local_tool_evidence(db, run, version, submission, self.settings, self.runner)
            _update_progress(
                db,
                run,
                "source_and_safety_analysis",
                68,
                "Recording source findings, complexity and local C-tool evidence.",
            )
            for finding in solution.findings:
                _evidence(
                    db,
                    run,
                    version,
                    submission,
                    source_type="agent_reasoning",
                    status=finding.status,
                    summary=finding.summary,
                    requirement_id=finding.requirement_id,
                    details={"severity": finding.severity, "confidence": finding.confidence},
                    source_location=finding.source_location,
                    provenance=solution.provenance,
                )

            for criterion in spec.criteria:
                if criterion.analyzer not in {"sanitizer_run", "memory_safety"}:
                    continue
                sanitizer_test = next(
                    (test for test in validated_tests if test.expected_output is not None), None
                )
                if sanitizer_test is None:
                    _evidence(
                        db,
                        run,
                        version,
                        submission,
                        source_type="sanitizer",
                        status="unavailable",
                        summary="No validated executable test was available for sanitizer execution.",
                        criterion_id=criterion.id,
                        details={"normalized_score": None},
                        provenance={"tool": "addresssanitizer_undefinedbehaviorsanitizer"},
                    )
                else:
                    sanitizer = self.runner.run(
                        submission.source_content,
                        sanitizer_test.input_data,
                        config,
                        extra_compile_flags=(
                            "-fsanitize=address,undefined",
                            "-fno-omit-frame-pointer",
                        ),
                    )
                    clean = sanitizer.ran and sanitizer.exit_code == 0 and not sanitizer.timed_out
                    _evidence(
                        db,
                        run,
                        version,
                        submission,
                        source_type="sanitizer",
                        status="pass"
                        if clean
                        else "fail"
                        if not sanitizer.unavailable
                        else "unavailable",
                        summary="Sanitizer run completed without diagnostics."
                        if clean
                        else sanitizer.error or "Sanitizer reported a runtime problem.",
                        criterion_id=criterion.id,
                        details={
                            "normalized_score": 1.0
                            if clean
                            else 0.0
                            if not sanitizer.unavailable
                            else None,
                            "stderr": sanitizer.stderr,
                            "exit_code": sanitizer.exit_code,
                            "timed_out": sanitizer.timed_out,
                        },
                        provenance={"tool": "addresssanitizer_undefinedbehaviorsanitizer"},
                    )
            flagged, similarity_score = _similarity_for_submission(db, submission.id)
            _add_similarity_evidence(db, run, version, submission, spec, flagged, similarity_score)
            db.commit()

            _set_state(
                db,
                run,
                RunState.VALIDATING_EVIDENCE,
                "evidence_validation",
                75,
                "Checking that every score contribution has typed evidence.",
            )
            db.commit()
            evidence_rows = db.scalars(select(Evidence).where(Evidence.run_id == run.id)).all()
            evidence = [
                EvidenceLike(
                    id=item.id,
                    criterion_id=item.rubric_criterion_id,
                    test_id=item.test_id,
                    status=item.status,
                    details=item.details_json,
                )
                for item in evidence_rows
            ]
            score = calculate_score(
                spec.criteria,
                [NormalizedTest.model_validate(test) for test in spec.tests],
                evidence,
            )
            db.add(
                ScoreBreakdown(
                    run_id=run.id,
                    total_score=score.total_score,
                    finalized=score.finalized,
                    scoring_rule_version="deterministic-v1",
                    criteria_json=[item.model_dump(mode="json") for item in score.criteria],
                    calculation_trace_json=score.calculation_trace,
                )
            )
            if not score.finalized:
                _set_state(
                    db,
                    run,
                    RunState.SCORING,
                    "scoring_incomplete",
                    85,
                    "The score requires instructor review before finalization.",
                )
                run.state = transition(run.state, RunState.NEEDS_REVIEW)
            else:
                _set_state(
                    db,
                    run,
                    RunState.SCORING,
                    "scoring",
                    85,
                    "Calculating the weighted deterministic score.",
                )
                db.commit()
                _set_state(
                    db,
                    run,
                    RunState.REPORTING,
                    "reporting",
                    92,
                    "Rendering JSON and text reports from the stored evidence.",
                )
            db.commit()

            score_payload = {
                "total_score": score.total_score,
                "finalized": score.finalized,
                "scoring_rule_version": "deterministic-v1",
                "criteria": [item.model_dump(mode="json") for item in score.criteria],
                "calculation_trace": score.calculation_trace,
            }
            evidence_payload = [
                {
                    "id": item.id,
                    "source_type": item.source_type,
                    "status": item.status,
                    "summary": item.summary,
                    "input": item.input_data,
                    "expected_output": item.expected_output,
                    "actual_output": item.actual_output,
                    "details": item.details_json,
                }
                for item in evidence_rows
            ]
            report_payload = build_report(
                submission={
                    "id": submission.id,
                    "filename": submission.original_filename,
                    "label": submission.label,
                },
                evaluation={
                    "run_id": run.id,
                    "state": run.state,
                    "progress": 100 if score.finalized else 90,
                },
                score=score_payload,
                evidence=evidence_payload,
                version_hash=version.version_hash,
            )
            json_path, text_path = write_report_artifacts(
                Path(self.settings.artifact_dir),
                run.id,
                report_payload,
                render_text(report_payload),
            )
            db.add(
                Report(
                    run_id=run.id,
                    report_json=report_payload,
                    json_path=json_path,
                    text_path=text_path,
                )
            )
            run.progress = 100 if score.finalized else 90
            run.completed_at = utcnow()
            submission.status = "completed" if score.finalized else "needs_review"
            if score.finalized:
                run.state = RunState.COMPLETED
                run.current_stage = "completed"
                _audit(
                    db,
                    "evaluation_run",
                    run.id,
                    "state_changed",
                    {
                        "state": RunState.COMPLETED,
                        "stage": "completed",
                        "progress": run.progress,
                        "detail": "Evaluation and report are ready for review.",
                    },
                )
            run.updated_at = utcnow()
            db.commit()
        except Exception as exc:
            db.rollback()
            if run is not None:
                run = db.get(EvaluationRun, run.id)
                if run and run.state not in {RunState.COMPLETED, RunState.CANCELLED}:
                    try:
                        run.state = (
                            RunState.FAILED
                            if run.state
                            in {
                                RunState.QUEUED,
                                RunState.PREPARING,
                                RunState.COMPILING,
                                RunState.TESTING,
                                RunState.ANALYZING,
                                RunState.VALIDATING_EVIDENCE,
                                RunState.SCORING,
                                RunState.REPORTING,
                            }
                            else run.state
                        )
                    except Exception:
                        run.state = RunState.FAILED
                    run.error_summary = str(exc)[:4000]
                    run.completed_at = utcnow()
                    db.commit()
        finally:
            db.close()
