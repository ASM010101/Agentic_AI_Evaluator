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


def _function_bodies(source: str) -> list[tuple[str, str]]:
    """Return approximate function bodies for bounded source heuristics."""

    pattern = re.compile(r"(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{")
    result: list[tuple[str, str]] = []
    for match in pattern.finditer(source):
        depth = 1
        cursor = match.end()
        while cursor < len(source) and depth:
            if source[cursor] == "{":
                depth += 1
            elif source[cursor] == "}":
                depth -= 1
            cursor += 1
        result.append((match.group("name"), source[match.end() : max(match.end(), cursor - 1)]))
    return result


def _has_logarithmic_loop(body: str) -> bool:
    midpoint = bool(re.search(r"\b(?:mid|middle)\b\s*=.*(?:/\s*2|>>\s*1)", body))
    shrinking_bounds = bool(
        re.search(
            r"\b(?:left|right|low|high|lo|hi)\s*=\s*(?:[^;]*\b(?:mid|middle)\b|[^;]*/\s*2)",
            body,
        )
    )
    return midpoint and shrinking_bounds and bool(re.search(r"\b(?:while|for)\b", body))


def _has_loop(body: str) -> bool:
    return bool(re.search(r"\b(?:for|while|do)\b", body))


def _has_nested_loop(source: str) -> bool:
    return bool(
        re.search(
            r"\b(?:for|while)\s*\([^{}]*\)\s*\{[^{}]*\b(?:for|while)\s*\(",
            source,
            re.DOTALL,
        )
    )


def _estimate_complexity(source: str) -> str:
    """Estimate common loop compositions without pretending to parse all C."""

    functions = _function_bodies(source)
    logarithmic_functions = {name for name, body in functions if _has_logarithmic_loop(body)}
    looping_functions = {name for name, body in functions if _has_loop(body)}

    if _has_nested_loop(source):
        return "O(n^2) or nested-loop dependent"

    # A loop that repeatedly calls a binary-search helper is O(n log n) (or
    # O(q log n) for multiple queries), even though the loops are in separate
    # function bodies.
    for caller, body in functions:
        if not _has_loop(body):
            continue
        for callee in logarithmic_functions:
            if callee != caller and re.search(rf"\b{re.escape(callee)}\s*\(", body):
                return "O(nlogn) or loop-composition dependent"

    # The same composition with a linear helper is quadratic.
    for caller, body in functions:
        if not _has_loop(body):
            continue
        for callee in looping_functions - logarithmic_functions:
            if callee != caller and re.search(rf"\b{re.escape(callee)}\s*\(", body):
                return "O(n^2) or loop-composition dependent"

    if logarithmic_functions:
        return "O(logn) or halving-loop dependent"
    if not re.search(r"\b(?:for|while|do)\b", source):
        return "O(1)"
    return "O(n) or linear-loop dependent"


def analyze_solution(source: str, complexity_required: str | None = None) -> SolutionAnalysis:
    loops = len(re.findall(r"\b(for|while|do)\b", source))
    conditions = len(re.findall(r"\b(if|switch|case)\b|&&|\|\|", source))
    functions = _function_count(source)
    complexity = _estimate_complexity(source)
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
            "method": "deterministic_source_heuristic_v2",
            "complexity_requirement": complexity_required,
        },
    )
