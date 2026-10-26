from __future__ import annotations

import pytest

from app.rules import RulesError, can_activate, normalize_rules


def valid_rules() -> dict:
    return {
        "time_limit_s": 1,
        "memory_limit_mb": 64,
        "metrics": [
            {
                "name": "correctness",
                "analyzer": "io_tests",
                "weight": 1.0,
                "scoring": {"mode": "test_ratio"},
            }
        ],
        "tests": [
            {
                "id": "sample",
                "input": "7 5\n",
                "expected_output": "12\n",
                "rationale": "explicit problem example",
                "provenance": "problem_statement",
                "status": "validated",
            }
        ],
    }


def test_normalizes_rules_and_hash_is_stable():
    first = normalize_rules(valid_rules(), "Read two integers and print their sum.")
    second = normalize_rules(valid_rules(), "Read two integers and print their sum.")
    assert first.rules_hash == second.rules_hash
    assert first.spec.criteria[0].id == "correctness"
    assert first.spec.tests[0].status == "validated"
    assert can_activate(first.spec)[0] is True


def test_unvalidated_score_affecting_test_blocks_activation():
    rules = valid_rules()
    rules["tests"][0]["status"] = "candidate"
    normalized = normalize_rules(rules, "problem")
    allowed, warnings = can_activate(normalized.spec)
    assert allowed is False
    assert any("cannot affect a grade" in warning for warning in warnings)


def test_weights_must_sum_to_one():
    rules = valid_rules()
    rules["metrics"][0]["weight"] = 0.5
    with pytest.raises(RulesError, match="sum to 1.0"):
        normalize_rules(rules, "problem")


def test_unknown_rule_key_is_rejected():
    rules = valid_rules()
    rules["not_a_rule"] = True
    with pytest.raises(RulesError, match="not_a_rule"):
        normalize_rules(rules, "problem")
