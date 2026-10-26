from __future__ import annotations

import pytest

from app.agents.report_agent import build_report, render_text
from app.agents.solution_agent import analyze_solution
from app.sandbox.runner import CompileResult, ExecutionResult, FakeSandboxRunner, RunnerConfig
from app.testing.comparators import ComparatorError, normalize_output


def test_report_template_contains_only_supplied_failure_evidence():
    report = build_report(
        submission={"filename": "broken.c"},
        evaluation={"run_id": "run-1", "state": "completed"},
        score={
            "total_score": 42.5,
            "criteria": [
                {
                    "name": "Correctness",
                    "weight": 1.0,
                    "points": 0.425,
                    "contribution": 42.5,
                    "status": "fail",
                    "reason": "1/2 validated tests passed",
                }
            ],
        },
        evidence=[
            {
                "id": "e-fail",
                "status": "fail",
                "summary": "boundary test failed",
                "input": "2147483647 1",
                "expected_output": "2147483648",
                "actual_output": "-2147483648",
                "details": {},
            }
        ],
        version_hash="sha256:demo",
    )
    text = render_text(report)
    assert "42.50 / 100" in text
    assert "2147483647 1" in text
    assert "sha256:demo" in text
    assert len(report["usefulness_limitations"]["limitations"]) == 4


def test_solution_analysis_distinguishes_simple_and_nested_loops():
    simple = analyze_solution("int main(void) { return 0; }")
    nested = analyze_solution(
        "int main(void) { for (int i=0;i<10;i++){ for (int j=0;j<10;j++){} } return 0; }"
    )
    assert simple.estimated_time_complexity == "O(1)"
    assert nested.estimated_time_complexity.startswith("O(n^2)")
    assert nested.findings


def test_fake_runner_records_compile_and_run_without_executing_source():
    runner = FakeSandboxRunner(
        compile_result=CompileResult(True, 0, "", "", 2.0),
        executions={"x\n": ExecutionResult(True, 0, "ok\n", "", 3.0)},
    )
    config = RunnerConfig(1, 64, 1000)
    assert runner.availability()[0]
    assert runner.compile("not valid C", config).compiled
    assert runner.run("not valid C", "x\n", config).stdout == "ok\n"
    assert len(runner.calls) == 2


def test_comparator_normalization_rejects_unknown_policy():
    assert normalize_output("a\r\n", "trim_trailing_whitespace") == "a"
    with pytest.raises(ComparatorError):
        normalize_output("a", "not-a-policy")
