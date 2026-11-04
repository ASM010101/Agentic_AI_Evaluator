from __future__ import annotations

import re
from typing import Any

from app.agents.contracts import FeedbackAgentOutput


USEFULNESS_LIMITATIONS = {
    "usefulness": [
        {
            "use_case": "Large introductory programming classes",
            "example": "An instructor evaluates 200 C submissions against one immutable assignment version and reviews only failed or uncertain evidence.",
            "benefit": "Reduces repetitive compilation and test execution while keeping an evidence trail.",
        },
        {
            "use_case": "Coding interviews and hiring screens",
            "example": "A team runs a small, explicitly specified C exercise and compares compile status, validated tests and resource-limit behavior.",
            "benefit": "Produces consistent first-pass feedback without treating a similarity flag as a hiring decision.",
        },
        {
            "use_case": "Autograding in lab environments",
            "example": "Teaching assistants inspect sanitizer, timeout and compiler diagnostics from one consolidated results table.",
            "benefit": "Makes technical feedback faster and easier to reproduce.",
        },
        {
            "use_case": "Academic integrity triage",
            "example": "Assignment-scoped normalized fingerprints identify distinctive overlapping regions for human review.",
            "benefit": "Focuses manual inspection on evidence-backed candidate pairs without automatic punishment.",
        },
    ],
    "limitations": [
        {
            "limitation": "Finite tests cannot prove general correctness",
            "example": "A program passes every validated case but fails on an untested input class.",
            "mitigation": "Use explicit specification-derived properties, add instructor-approved boundary tests, and label the result as empirical rather than formal proof.",
        },
        {
            "limitation": "Ambiguous specifications can make grading unreliable",
            "example": "The statement does not define whether extra output whitespace is meaningful, so two reasonable comparators disagree.",
            "mitigation": "Block score-affecting unvalidated tests and require operator review of the comparator policy.",
        },
        {
            "limitation": "Docker reduces but does not prove native-code isolation",
            "example": "A kernel or container-runtime vulnerability could let hostile native code escape the intended boundary.",
            "mitigation": "Use patched hosts, least privilege, network isolation, resource limits and a separate hardened grading worker for high-risk workloads.",
        },
        {
            "limitation": "Similarity is not proof of copying or AI authorship",
            "example": "A small assignment causes unrelated students to produce nearly identical token patterns.",
            "mitigation": "Show matched evidence and caveats, keep review disposition separate, and require human judgment.",
        },
    ],
}


def _extract_student_name(filename: str, label: str | None = None) -> str:
    """Extract a clean, readable student name from filename or label.

    Handles conventions dynamically for any student:
      - Jane_Doe_assg01.c -> Jane Doe
      - student101_assg01.c -> student101
      - Alex-assignment1.c -> Alex
      - assg01_Rohan.c -> Rohan
      - Alice.c -> Alice
    """
    if label and label != filename:
        return label

    stem = filename or ""
    if stem.lower().endswith(".c"):
        stem = stem[:-2]

    parts = [p for p in re.split(r"[_\-]+", stem) if p]
    if len(parts) >= 2:
        prefix_pattern = r"^(?:assg|assignment|hw|homework|lab|task|problem|prob|p|ex|exercise)\d*$"
        if re.match(prefix_pattern, parts[0], re.IGNORECASE):
            return " ".join(parts[1:])
        if re.match(prefix_pattern, parts[-1], re.IGNORECASE):
            return " ".join(parts[:-1])
        return " ".join(parts)
    return stem or "Anonymous Student"


def build_report(
    *,
    assignment: dict[str, Any] | None = None,
    submission: dict[str, Any],
    evaluation: dict[str, Any],
    score: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
    version_hash: str,
    agent_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assignment = assignment or {}
    filename = submission.get("filename") or "submission.c"
    label = submission.get("label") or filename
    student_name = submission.get("student_name") or _extract_student_name(filename, label)
    submission_payload = {
        **submission,
        "filename": filename,
        "label": label,
        "student_name": student_name,
    }
    assignment_payload = {
        "id": assignment.get("id"),
        "name": assignment.get("name") or "Untitled assignment",
        "version_number": assignment.get("version_number"),
        "problem_statement": assignment.get("problem_statement") or "",
    }
    test_results = _test_results(evidence)
    compiler = next((item for item in evidence if item.get("source_type") == "compiler"), None)
    similarity_evidence = [item for item in evidence if item.get("source_type") == "similarity"]
    similarity_flagged = any(
        bool(item.get("details", {}).get("flagged")) or item.get("status") == "review_signal"
        for item in similarity_evidence
    )
    similarity_score = max(
        (
            item.get("details", {}).get("maximum_similarity")
            for item in similarity_evidence
            if isinstance(item.get("details", {}).get("maximum_similarity"), (int, float))
        ),
        default=None,
    )
    failures = [
        {
            "evidence_id": item["id"],
            "summary": item["summary"],
            "input": item.get("input"),
            "expected": item.get("expected_output"),
            "actual": item.get("actual_output"),
            "details": item.get("details", {}),
        }
        for item in evidence
        if item.get("status") in {"fail", "violated"}
    ]
    review_signals = [
        {
            "evidence_id": item["id"],
            "source_type": item.get("source_type"),
            "summary": item["summary"],
            "details": item.get("details", {}),
        }
        for item in evidence
        if item.get("status") == "review_signal"
        or item.get("details", {}).get("scoring_impact") is False
    ]
    deterministic_feedback = _deterministic_feedback(
        score=score,
        test_results=test_results,
        evidence=evidence,
        similarity_flagged=similarity_flagged,
    )
    llm_feedback_used = bool(agent_feedback and agent_feedback.get("status") == "completed")
    if llm_feedback_used:
        feedback = {
            **agent_feedback,
            "student_facing": True,
            "strengths": agent_feedback.get("strengths") or deterministic_feedback["strengths"],
            "issues": agent_feedback.get("issues") or deterministic_feedback["issues"],
            "next_steps": agent_feedback.get("next_steps") or deterministic_feedback["next_steps"],
        }
    else:
        feedback = deterministic_feedback
    llm_status = (agent_feedback or {}).get("provenance", {}).get("status")
    if not llm_status and agent_feedback:
        llm_status = agent_feedback.get("status")
    criteria = (score or {}).get("criteria", [])
    passed_tests = sum(item["status"] == "pass" for item in test_results)
    failed_tests = sum(item["status"] == "fail" for item in test_results)
    unavailable_tests = sum(item["status"] == "unavailable" for item in test_results)
    grade = (score or {}).get("total_score")
    report = {
        "schema_version": "1.0",
        "student_name": student_name,
        "assignment": assignment_payload,
        "submission": submission_payload,
        "assignment_version_hash": version_hash,
        "evaluation": evaluation,
        "score": score,
        "summary": {
            "overall_score": grade,
            "grade_status": "finalized"
            if (score or {}).get("finalized")
            else "requires_instructor_review",
            "validated_tests": len(test_results),
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "unavailable_tests": unavailable_tests,
            "compiler_status": compiler.get("status") if compiler else "not_recorded",
            "similarity_flagged": similarity_flagged,
        },
        "criterion_results": criteria,
        "test_results": test_results,
        "compilation": compiler,
        "confirmed_failures": failures,
        "review_signals": review_signals,
        "similarity_review": {
            "status": "flagged_for_manual_review" if similarity_flagged else "no_flag",
            "flagged": similarity_flagged,
            "maximum_similarity": similarity_score,
            "message": (
                "Potential overlap was detected. This is a review signal, not proof of copying, "
                "and it does not change the grade automatically."
                if similarity_flagged
                else "No submission pair exceeded the configured similarity threshold."
            ),
            "pairs": [
                pair
                for item in similarity_evidence
                for pair in item.get("details", {}).get("similarity_pairs", [])
            ],
        },
        "feedback": feedback,
        "feedback_generation": {
            "mode": "llm_assisted" if llm_feedback_used else "deterministic_evidence",
            "llm_status": llm_status,
            "student_safe": True,
        },
        "evidence_count": len(evidence),
        "usefulness_limitations": USEFULNESS_LIMITATIONS,
        "flags": [
            {
                "type": "similarity_review",
                "message": "Similarity findings are review evidence only and do not change the score automatically.",
            }
        ]
        if any(item.get("source_type") == "similarity" for item in evidence)
        else [],
    }
    report["student_report"] = render_text(report)
    return report


def _test_results(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse criterion-specific test evidence into one student-facing row per test."""

    grouped: dict[str, dict[str, Any]] = {}
    priority = {"pass": 0, "unavailable": 1, "fail": 2}
    for item in evidence:
        if item.get("source_type") != "test_runner":
            continue
        test_id = str(item.get("test_id") or "unnamed-test")
        current = grouped.setdefault(
            test_id,
            {
                "test_id": test_id,
                "status": "pass",
                "summary": item.get("summary", "Test completed."),
                "input": item.get("input"),
                "expected_output": item.get("expected_output"),
                "actual_output": item.get("actual_output"),
                "evidence_ids": [],
            },
        )
        status = str(item.get("status") or "unavailable")
        if priority.get(status, 1) >= priority.get(current["status"], 1):
            current["status"] = status
            current["summary"] = item.get("summary", current["summary"])
            current["actual_output"] = item.get("actual_output")
        if item.get("input") is not None:
            current["input"] = item.get("input")
        if item.get("expected_output") is not None:
            current["expected_output"] = item.get("expected_output")
        if item.get("id") not in current["evidence_ids"]:
            current["evidence_ids"].append(item.get("id"))
    return list(grouped.values())


def _deterministic_feedback(
    *,
    score: dict[str, Any] | None,
    test_results: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    similarity_flagged: bool,
) -> dict[str, Any]:
    """Create useful student feedback when an optional model is unavailable."""

    grade = (score or {}).get("total_score")
    passed = sum(item["status"] == "pass" for item in test_results)
    failed = sum(item["status"] == "fail" for item in test_results)
    unavailable = sum(item["status"] == "unavailable" for item in test_results)
    if isinstance(grade, (int, float)):
        summary = f"The submission received {grade:.2f}/100 and passed {passed} of {len(test_results)} validated tests."
    else:
        summary = "A final score could not be issued because some score-affecting evidence requires instructor review."
    strengths: list[str] = []
    compiler = next((item for item in evidence if item.get("source_type") == "compiler"), None)
    if compiler and compiler.get("status") == "pass":
        strengths.append(
            "The C source compiled successfully under the configured C11 compiler checks."
        )
    if passed:
        strengths.append(
            f"The submission passed {passed} validated test{'s' if passed != 1 else ''}."
        )
    if not strengths:
        strengths.append(
            "The submission was processed and deterministic evidence was recorded for review."
        )

    issues: list[dict[str, Any]] = []
    for test in test_results:
        if test["status"] == "fail":
            issues.append(
                {
                    "summary": f"Validated test '{test['test_id']}' failed: {test['summary']}",
                    "evidence_ids": test["evidence_ids"],
                    "suggested_fix": "Compare the expected and actual output for this case, then correct the input handling or algorithm branch that produced the mismatch.",
                }
            )
    if compiler and compiler.get("status") in {"fail", "unavailable"}:
        issues.append(
            {
                "summary": f"Compilation check: {compiler.get('summary', 'The source did not compile successfully.')}",
                "evidence_ids": [compiler.get("id")],
                "suggested_fix": "Read the compiler diagnostic, correct the reported source location, and compile again with C11 enabled.",
            }
        )
    for criterion in (score or {}).get("criteria", []):
        if criterion.get("status") in {"fail", "unavailable", "inconclusive"} and len(issues) < 8:
            issues.append(
                {
                    "summary": f"{criterion.get('name', criterion.get('criterion_id', 'Criterion'))}: {criterion.get('reason', 'criterion evidence needs review.')}",
                    "evidence_ids": criterion.get("evidence_ids", []),
                    "suggested_fix": "Review the criterion evidence and update the implementation or the instructor-approved test/rubric definition as appropriate.",
                }
            )
    if unavailable and not any(item["status"] == "unavailable" for item in test_results):
        issues.append(
            {
                "summary": "Some evaluation evidence was unavailable, so the result needs instructor review.",
                "evidence_ids": [],
                "suggested_fix": "Resolve the unavailable tool or sandbox check and run the submission again.",
            }
        )
    next_steps = []
    if failed:
        next_steps.append(
            "Fix every failed validated test and run the complete assignment test set again."
        )
    if unavailable:
        next_steps.append(
            "Ask the instructor to review unavailable checks before treating the score as final."
        )
    if similarity_flagged:
        next_steps.append(
            "The instructor should inspect the Similarity Review pair before making any academic-integrity decision."
        )
    if not next_steps:
        next_steps.append(
            "Continue testing boundary and malformed-input cases defined by the assignment."
        )
    return {
        "status": "deterministic",
        "agent": "evidence_based_report",
        "student_facing": True,
        "summary": summary,
        "strengths": strengths,
        "issues": issues,
        "next_steps": next_steps,
    }


def validate_feedback(
    output: FeedbackAgentOutput,
    *,
    call_metadata: dict[str, Any],
    evidence_ids: set[str],
) -> dict[str, Any]:
    """Keep only feedback that can be linked to persisted evidence.

    The model is allowed to explain facts, but it cannot create a new failure,
    score, criterion or evidence reference.  Issues without at least one valid
    evidence reference are omitted from the saved feedback.
    """

    issues: list[dict[str, Any]] = []
    dropped = 0
    for issue in output.issues:
        valid_ids = [item for item in issue.evidence_ids if item in evidence_ids]
        if not valid_ids:
            dropped += 1
            continue
        issues.append(
            {
                "summary": issue.summary,
                "evidence_ids": valid_ids,
                "suggested_fix": issue.suggested_fix,
            }
        )
    return {
        "status": "completed",
        "agent": "feedback_and_report",
        "summary": output.summary,
        "strengths": list(output.strengths),
        "issues": issues,
        "next_steps": list(output.next_steps),
        "provenance": call_metadata,
        "validation": {
            "evidence_references_checked": True,
            "dropped_unlinked_issues": dropped,
        },
    }


def render_text(report: dict[str, Any]) -> str:
    score = report.get("score") or {}
    assignment = report.get("assignment") or {}
    submission = report.get("submission") or {}
    filename = submission.get("filename") or "submission.c"
    label = submission.get("label") or filename
    student_name = (
        submission.get("student_name")
        or report.get("student_name")
        or _extract_student_name(filename, label)
    )
    summary = report.get("summary") or {}
    grade = summary.get("overall_score", score.get("total_score"))
    grade_text = f"{grade:.2f} / 100" if isinstance(grade, (int, float)) else "Not finalized"
    grade_status = (
        "Finalized" if summary.get("grade_status") == "finalized" else "Requires instructor review"
    )
    similarity = report.get("similarity_review") or {}
    lines = [
        "=" * 78,
        "AutoGrader | Student Evaluation Report",
        "=" * 78,
        f"Student Name:     {student_name}",
        f"Submission file:  {filename}",
        f"Submission label: {label}",
        f"Assignment:       {assignment.get('name', 'Untitled assignment')}",
        f"Evaluation:       {grade_status}",
        f"Overall score:    {grade_text}",
        "",
        "EXECUTIVE SUMMARY",
        "------------------",
        f"Report for Student: {student_name} (File: {filename})",
        str(
            (report.get("feedback") or {}).get("summary")
            or "The deterministic evaluation is complete."
        ),
        f"Validated tests:  {summary.get('passed_tests', 0)} passed, "
        f"{summary.get('failed_tests', 0)} failed, "
        f"{summary.get('unavailable_tests', 0)} unavailable "
        f"({summary.get('validated_tests', 0)} total)",
        "",
        "ASSIGNMENT",
        "----------",
    ]
    statement = assignment.get("problem_statement") or "Not supplied."
    _append_block(lines, "Problem statement", statement)
    lines.extend(["", "CRITERION RESULTS", "-----------------"])
    for criterion in score.get("criteria", []):
        points = "—" if criterion.get("points") is None else f"{criterion['points'] * 100:.1f}/100"
        contribution = (
            "—" if criterion.get("contribution") is None else f"{criterion['contribution']:.2f}"
        )
        weight = criterion.get("weight")
        weight_text = f"{weight * 100:.1f}%" if isinstance(weight, (int, float)) else "—"
        lines.append(
            f"- {criterion.get('name', criterion.get('criterion_id', 'Criterion'))}: "
            f"{_status_label(criterion.get('status'))} | Weight {weight_text} | "
            f"Points {points} | Contribution {contribution}"
        )
        lines.append(f"  Reason: {criterion.get('reason', 'No reason recorded.')}")
    lines.extend(["", "VALIDATED TEST RESULTS", "----------------------"])
    tests = report.get("test_results") or []
    if not tests:
        lines.append("No validated executable tests were recorded.")
    for test in tests:
        lines.append(
            f"- {test.get('test_id', 'unnamed-test')}: {_status_label(test.get('status'))}"
        )
        lines.append(f"  Result: {test.get('summary', 'No test summary recorded.')}")
        _append_block(lines, "Input", test.get("input"))
        _append_block(lines, "Expected output", test.get("expected_output"))
        _append_block(lines, "Actual output", test.get("actual_output"))
        if test.get("evidence_ids"):
            lines.append(f"  Evidence: {', '.join(test['evidence_ids'])}")
    lines.extend(["", "COMPILATION", "-----------"])
    compiler = report.get("compilation")
    if compiler:
        lines.append(f"Status: {_status_label(compiler.get('status'))}")
        lines.append(f"{compiler.get('summary', 'No compiler summary recorded.')}")
        details = compiler.get("details") or {}
        if details.get("stderr"):
            _append_block(lines, "Compiler diagnostics", details.get("stderr"))
    else:
        lines.append("No compiler evidence was recorded.")
    lines.extend(["", "FEEDBACK FOR THE STUDENT", "-------------------------"])
    feedback = report.get("feedback") or {}
    if feedback.get("summary"):
        lines.append(feedback["summary"])
    strengths = feedback.get("strengths", [])
    if strengths:
        lines.append("Strengths:")
        lines.extend(f"- {item}" for item in strengths)
    issues = feedback.get("issues", [])
    if issues:
        lines.append("What needs improvement:")
        for issue in issues:
            references = ", ".join(issue.get("evidence_ids", [])) or "not linked"
            lines.append(
                f"- {issue.get('summary', 'Evidence-backed issue')} (Evidence: {references})"
            )
            if issue.get("suggested_fix"):
                lines.append(f"  Recommended correction: {issue['suggested_fix']}")
    next_steps = feedback.get("next_steps", [])
    if next_steps:
        lines.append("Next steps:")
        lines.extend(f"- {item}" for item in next_steps)
    lines.extend(["", "SIMILARITY / ORIGINALITY REVIEW", "-------------------------------"])
    if similarity.get("flagged"):
        lines.append("STATUS: FLAGGED FOR MANUAL REVIEW")
        if similarity.get("maximum_similarity") is not None:
            lines.append(f"Maximum normalized similarity: {similarity['maximum_similarity']:.3f}")
        lines.append(
            "This is a candidate overlap signal only. It is not proof of copying or AI authorship "
            "and does not automatically change the grade."
        )
        for pair in similarity.get("pairs", []):
            lines.append(
                f"- Compared with {pair.get('filename', pair.get('submission_id', 'another submission'))} "
                f"(similarity {pair.get('score', '—')})"
            )
    else:
        lines.append("STATUS: No similarity candidate exceeded the configured threshold.")
    lines.extend(["", "REVIEW-ONLY TECHNICAL SIGNALS", "-----------------------------"])
    lines.append("Review signals (no grade impact):")
    technical_signals = [
        item
        for item in report.get("review_signals", [])
        if item.get("source_type") not in {"similarity", "llm_solution_agent", "llm_feedback_agent"}
    ]
    if technical_signals:
        for signal in technical_signals:
            lines.append(
                f"- {signal.get('source_type', 'observation')}: {signal.get('summary', 'No summary recorded.')}"
            )
    else:
        lines.append("No additional review-only technical signals were recorded.")
    lines.extend(
        [
            "",
            "REPRODUCIBILITY",
            "----------------",
            f"Evaluation run: {report.get('evaluation', {}).get('run_id', '—')}",
            f"Assignment version hash: {report.get('assignment_version_hash', '—')}",
            f"Evidence items: {report.get('evidence_count', 0)}",
            "Similarity findings are review flags and never automatic grade deductions.",
            "",
            "Generated by AutoGrader. Deterministic compiler, test and scoring evidence is authoritative; AI feedback is advisory.",
        ]
    )
    return "\n".join(lines) + "\n"


def _status_label(value: Any) -> str:
    labels = {
        "pass": "PASS",
        "fail": "FAIL",
        "violated": "FAIL",
        "unavailable": "UNAVAILABLE",
        "inconclusive": "REVIEW REQUIRED",
        "review_signal": "REVIEW SIGNAL",
    }
    return labels.get(str(value), str(value or "UNKNOWN").replace("_", " ").upper())


def _append_block(lines: list[str], label: str, value: Any) -> None:
    lines.append(f"  {label}:")
    text = "<empty>" if value is None or value == "" else str(value)
    lines.extend(f"    {line}" for line in text.splitlines() or ["<empty>"])
