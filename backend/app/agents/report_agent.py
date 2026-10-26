from __future__ import annotations

from typing import Any


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


def build_report(
    *,
    submission: dict[str, Any],
    evaluation: dict[str, Any],
    score: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
    version_hash: str,
) -> dict[str, Any]:
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
    return {
        "schema_version": "1.0",
        "submission": submission,
        "assignment_version_hash": version_hash,
        "evaluation": evaluation,
        "score": score,
        "confirmed_failures": failures,
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


def render_text(report: dict[str, Any]) -> str:
    score = report.get("score") or {}
    grade = score.get("total_score")
    grade_text = (
        f"{grade:.2f} / 100"
        if isinstance(grade, (int, float))
        else "Needs review (not all scoring evidence is available)"
    )
    lines = [
        f"===== AutoGrader report for {report['submission'].get('filename', 'submission.c')} =====",
        f"Overall grade: {grade_text}",
        "",
        "Metric                         Weight   Points   Contribution   Status / reason",
    ]
    for criterion in score.get("criteria", []):
        points = "—" if criterion.get("points") is None else f"{criterion['points'] * 100:.1f}/100"
        contribution = (
            "—" if criterion.get("contribution") is None else f"{criterion['contribution']:.2f}"
        )
        lines.append(
            f"{criterion['name'][:30]:30} {criterion['weight'] * 100:5.1f}%   {points:>8}   {contribution:>12}   {criterion['status']}: {criterion['reason']}"
        )
    failures = report.get("confirmed_failures", [])
    if failures:
        lines.extend(["", "--- Confirmed failures ---"])
        for failure in failures:
            lines.append(f"- [{failure['evidence_id']}] {failure['summary']}")
            if failure.get("input") is not None:
                lines.append(f"  INPUT:    {failure['input']!r}")
                lines.append(f"  EXPECTED: {failure.get('expected')!r}")
                lines.append(f"  ACTUAL:   {failure.get('actual')!r}")
    lines.extend(
        [
            "",
            "--- Reproducibility ---",
            f"Assignment version hash: {report['assignment_version_hash']}",
            f"Evidence items: {report['evidence_count']}",
            "Similarity findings, if any, are review flags and never automatic grade deductions.",
        ]
    )
    return "\n".join(lines) + "\n"
