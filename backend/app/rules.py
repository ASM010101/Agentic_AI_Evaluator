from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.schemas import (
    AssignmentSpec,
    NormalizedCriterion,
    NormalizedTest,
    RulesDocument,
)


class RulesError(ValueError):
    """Raised when instructor rules cannot be normalized safely."""


@dataclass(frozen=True)
class NormalizedRules:
    raw: dict[str, Any]
    document: RulesDocument
    spec: AssignmentSpec
    rules_hash: str


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _inferred_scoring(analyzer: str) -> str:
    if analyzer in {"io_tests", "validated_tests", "edge_case_runner"}:
        return "test_ratio"
    if analyzer in {"similarity_flag", "compiler_warnings", "sanitizer_run", "static_analysis"}:
        return "evidence_score"
    return "evidence_score"


def _criteria(document: RulesDocument) -> list[NormalizedCriterion]:
    result: list[NormalizedCriterion] = []
    if document.metrics:
        weight_total = sum(metric.weight for metric in document.metrics)
        if abs(weight_total - 1.0) > 0.0001:
            raise RulesError(f"metric weights must sum to 1.0; received {weight_total:.6f}")
        names: set[str] = set()
        for metric in document.metrics:
            criterion_id = metric.name.strip().lower().replace(" ", "_")
            if criterion_id in names:
                raise RulesError(f"duplicate metric name: {metric.name}")
            names.add(criterion_id)
            scoring = metric.scoring
            result.append(
                NormalizedCriterion(
                    id=criterion_id,
                    name=metric.name,
                    analyzer=metric.analyzer,
                    weight=metric.weight,
                    description=f"Evaluate {metric.name} using {metric.analyzer}.",
                    params=metric.params,
                    scoring_mode=(
                        scoring.mode
                        if scoring and scoring.mode
                        else _inferred_scoring(metric.analyzer)
                    ),
                    missing_evidence=(scoring.missing_evidence if scoring else "needs_review"),
                    max_points=(scoring.max_points if scoring else 100.0),
                )
            )
    elif document.criteria:
        point_total = sum(criterion.max_points for criterion in document.criteria)
        if point_total <= 0:
            raise RulesError("criteria must contain positive points")
        for criterion in document.criteria:
            scoring = criterion.scoring
            result.append(
                NormalizedCriterion(
                    id=criterion.id,
                    name=criterion.name or criterion.id,
                    analyzer=criterion.analyzer,
                    weight=criterion.max_points / point_total,
                    description=criterion.description,
                    params=criterion.params,
                    scoring_mode=(
                        scoring.mode
                        if scoring and scoring.mode
                        else _inferred_scoring(criterion.analyzer)
                    ),
                    missing_evidence=(scoring.missing_evidence if scoring else "needs_review"),
                    max_points=criterion.max_points,
                )
            )
    if not result:
        raise RulesError("at least one rubric criterion is required")
    return result


def _tests(document: RulesDocument, criteria: list[NormalizedCriterion]) -> list[NormalizedTest]:
    tests: list[NormalizedTest] = []
    seen: set[str] = set()
    for test in document.tests:
        if test.id in seen:
            raise RulesError(f"duplicate test id: {test.id}")
        seen.add(test.id)
        if test.status == "validated" and test.expected_output is None and test.expected_behavior:
            # A behavior-only test is valid for review but cannot be executed by
            # the deterministic comparator.
            test = test.model_copy(
                update={"score_affecting": False, "validation_note": "behavior-only test"}
            )
        tests.append(
            NormalizedTest(
                id=test.id,
                input=test.input,
                expected_output=test.expected_output,
                expected_behavior=test.expected_behavior,
                comparator=test.comparator,
                rationale=test.rationale,
                provenance=test.provenance,
                status=test.status,
                requirement_id=test.requirement_id or criteria[0].id,
                score_affecting=test.score_affecting,
                validation_note=test.validation_note,
                metadata=test.metadata,
            )
        )
    return tests


def normalize_rules(raw: dict[str, Any], problem_statement: str) -> NormalizedRules:
    try:
        document = RulesDocument.model_validate(raw)
    except ValidationError as exc:
        raise RulesError(str(exc)) from exc

    criteria = _criteria(document)
    tests = _tests(document, criteria)
    ambiguities: list[dict[str, Any]] = []
    if not tests:
        ambiguities.append(
            {
                "id": "missing-explicit-tests",
                "severity": "material",
                "message": "No explicit executable test cases were supplied; execution-based criteria need review.",
            }
        )
    for test in tests:
        if test.score_affecting and test.status != "validated":
            ambiguities.append(
                {
                    "id": f"unvalidated-test:{test.id}",
                    "severity": "material",
                    "message": f"Test {test.id} is not validated and cannot affect a grade.",
                }
            )
    for criterion in criteria:
        if criterion.scoring_mode == "test_ratio" and not any(
            test.status == "validated" and test.score_affecting for test in tests
        ):
            ambiguities.append(
                {
                    "id": f"criterion-without-tests:{criterion.id}",
                    "severity": "material",
                    "message": f"Criterion {criterion.id} requires validated tests but none are available.",
                }
            )

    requirements = [
        {
            "id": "REQ-PROBLEM",
            "kind": "functional",
            "text": problem_statement.strip()[:10_000],
            "mandatory": True,
            "provenance": "problem_statement",
        }
    ]
    constraints = {
        "time_limit_s": document.time_limit_s,
        "memory_limit_mb": document.memory_limit_mb,
        "comparison": document.comparison,
        "execution": document.execution,
    }
    spec = AssignmentSpec(
        requirements=requirements,
        constraints=constraints,
        criteria=criteria,
        tests=tests,
        ambiguities=ambiguities,
        summary=(
            f"{len(criteria)} rubric criteria and {len(tests)} supplied test cases were parsed. "
            f"{len(ambiguities)} material review item(s) remain."
        ),
        provenance={"method": "deterministic_rules_normalizer", "schema_version": "1.0"},
    )
    return NormalizedRules(raw=raw, document=document, spec=spec, rules_hash=canonical_hash(raw))


def activation_warnings(spec: AssignmentSpec) -> list[str]:
    return [item["message"] for item in spec.ambiguities if item.get("severity") == "material"]


def can_activate(spec: AssignmentSpec) -> tuple[bool, list[str]]:
    warnings = activation_warnings(spec)
    # Material ambiguity is always visible and blocking in v1. This prevents a
    # version from becoming active merely because a criterion happened not to
    # use executable tests; an operator must resolve or remove the ambiguity.
    return not warnings, warnings
