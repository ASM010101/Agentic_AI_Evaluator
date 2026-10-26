from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.schemas import CriterionScore, NormalizedCriterion, NormalizedTest


SCORING_RULE_VERSION = "deterministic-v1"


@dataclass(frozen=True)
class EvidenceLike:
    id: str
    criterion_id: str | None
    test_id: str | None
    status: str
    details: dict[str, Any]


@dataclass(frozen=True)
class ScoreResult:
    total_score: float | None
    finalized: bool
    criteria: list[CriterionScore]
    calculation_trace: dict[str, Any]


def _evidence_score(evidence: Iterable[EvidenceLike]) -> tuple[float | None, str, list[str]]:
    items = list(evidence)
    ids = [item.id for item in items]
    values = [item.details.get("normalized_score") for item in items]
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if numeric:
        return max(0.0, min(1.0, sum(numeric) / len(numeric))), "deterministic evidence score", ids
    statuses = {item.status for item in items}
    if statuses & {"unavailable", "inconclusive", "requires_review"}:
        return None, "evidence is unavailable or requires review", ids
    if statuses & {"fail", "violated"}:
        return 0.0, "at least one evidence item failed", ids
    if statuses & {"pass", "supported"}:
        return 1.0, "evidence supports the criterion", ids
    return None, "no usable evidence", ids


def calculate_score(
    criteria: list[NormalizedCriterion],
    tests: list[NormalizedTest],
    evidences: list[EvidenceLike],
) -> ScoreResult:
    breakdown: list[CriterionScore] = []
    trace: dict[str, Any] = {"version": SCORING_RULE_VERSION, "criteria": []}
    total = 0.0
    finalized = True
    validated_test_ids = {
        test.id for test in tests if test.status == "validated" and test.score_affecting
    }

    for criterion in criteria:
        relevant = [item for item in evidences if item.criterion_id == criterion.id]
        evidence_ids = [item.id for item in relevant]
        points: float | None
        reason: str
        status: str
        if criterion.scoring_mode == "test_ratio":
            test_evidence = [item for item in relevant if item.test_id in validated_test_ids]
            tested_ids = {item.test_id for item in test_evidence if item.test_id}
            passes = sum(item.status == "pass" for item in test_evidence)
            if not tested_ids:
                points, reason, status = (
                    None,
                    "no validated executable test evidence",
                    "unavailable",
                )
            else:
                points = passes / len(tested_ids)
                status = "pass" if passes == len(tested_ids) else "fail"
                reason = f"{passes}/{len(tested_ids)} validated tests passed"
        elif criterion.scoring_mode == "fixed":
            points, reason, status = _evidence_score(relevant)
            if points is None:
                fixed = criterion.params.get("score")
                points = float(fixed) if isinstance(fixed, (int, float)) else None
                reason = (
                    "fixed score from explicit criterion configuration"
                    if points is not None
                    else reason
                )
                status = "pass" if points is not None else "unavailable"
        else:
            points, reason, ids = _evidence_score(relevant)
            evidence_ids = ids
            status = (
                "pass"
                if points is not None and points >= 1
                else "fail"
                if points == 0
                else "unavailable"
            )

        if points is None:
            finalized = False if criterion.missing_evidence == "needs_review" else finalized
            contribution = None
        else:
            points = max(0.0, min(1.0, float(points)))
            contribution = round(points * criterion.weight * 100, 4)
            total += contribution
        breakdown.append(
            CriterionScore(
                criterion_id=criterion.id,
                name=criterion.name,
                weight=criterion.weight,
                points=(round(points, 6) if points is not None else None),
                contribution=contribution,
                status=status,
                reason=reason,
                evidence_ids=evidence_ids,
            )
        )
        trace["criteria"].append(
            {
                "criterion_id": criterion.id,
                "weight": criterion.weight,
                "points": points,
                "contribution": contribution,
                "evidence_ids": evidence_ids,
                "missing_evidence_policy": criterion.missing_evidence,
            }
        )

    return ScoreResult(
        total_score=round(total, 4) if finalized else None,
        finalized=finalized,
        criteria=breakdown,
        calculation_trace=trace,
    )
