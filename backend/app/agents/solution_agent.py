from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class SolutionFinding(BaseModel):
    requirement_id: str | None = None
    status: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    severity: str = "info"
    confidence: str = "medium"
    source_location: dict[str, Any] | None = None


class SolutionAnalysis(BaseModel):
    algorithm_summary: str
    estimated_time_complexity: str
    estimated_space_complexity: str
    findings: list[SolutionFinding] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


def _function_count(source: str) -> int:
    pattern = re.compile(r"(?:[A-Za-z_][\w\s\*]*?)\s+[A-Za-z_]\w*\s*\([^;{}]*\)\s*\{")
    return len(pattern.findall(source))


def analyze_solution(source: str, complexity_required: str | None = None) -> SolutionAnalysis:
    loops = len(re.findall(r"\b(for|while|do)\b", source))
    conditions = len(re.findall(r"\b(if|switch|case)\b|&&|\|\|", source))
    functions = _function_count(source)
    complexity = "O(1)" if loops == 0 else "O(n) or problem-dependent"
    if loops >= 2 or re.search(r"for\s*\([^)]*\)\s*\{[^{}]*(?:for|while)\b", source, re.DOTALL):
        complexity = "O(n^2) or nested-loop dependent"
    findings: list[SolutionFinding] = []
    if "main(" not in source:
        findings.append(
            SolutionFinding(
                status="violated", summary="No main() function was detected.", severity="error"
            )
        )
    if functions <= 1:
        findings.append(
            SolutionFinding(
                status="inconclusive",
                summary="Only main() or one function was detected; modularity depends on the rubric.",
                severity="info",
                confidence="high",
            )
        )
    return SolutionAnalysis(
        algorithm_summary=f"Detected approximately {functions} function(s), {loops} loop(s), and {conditions} branch/operator condition(s).",
        estimated_time_complexity=complexity,
        estimated_space_complexity="O(1) auxiliary space by source heuristic"
        if "malloc" not in source
        else "dynamic allocation detected",
        findings=findings,
        provenance={
            "method": "deterministic_source_heuristic_v1",
            "complexity_requirement": complexity_required,
        },
    )
