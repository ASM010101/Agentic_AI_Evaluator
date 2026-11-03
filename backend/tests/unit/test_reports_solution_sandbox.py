from __future__ import annotations

import pytest

from app.agents.report_agent import build_report, render_text
from app.agents.solution_agent import analyze_solution
from app.sandbox.runner import CompileResult, ExecutionResult, FakeSandboxRunner, RunnerConfig
from app.testing.comparators import ComparatorError, normalize_output


def test_report_template_contains_only_supplied_failure_evidence():
    report = build_report(
        assignment={
            "id": "assignment-1",
            "name": "Add two integers",
            "version_number": 3,
            "problem_statement": "Read two integers and print their sum.",
        },
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
                "source_type": "test_runner",
                "test_id": "overflow",
                "status": "fail",
                "summary": "boundary test failed",
                "input": "2147483647 1",
                "expected_output": "2147483648",
                "actual_output": "-2147483648",
                "details": {},
            },
            {
                "id": "e-tool",
                "source_type": "static_analysis_tool",
                "status": "review_signal",
                "summary": "cppcheck reported review-only findings.",
                "details": {"scoring_impact": False},
            },
        ],
        version_hash="sha256:demo",
    )
    text = render_text(report)
    assert "42.50 / 100" in text
    assert "Assignment:       Add two integers" in text
    assert "Submission file:  broken.c" in text
    assert "VALIDATED TEST RESULTS" in text
    assert "2147483647 1" in text
    assert "sha256:demo" in text
    assert "Review signals (no grade impact)" in text
    assert report["review_signals"][0]["evidence_id"] == "e-tool"
    assert len(report["usefulness_limitations"]["limitations"]) == 4
    assert report["summary"]["failed_tests"] == 1
    assert report["test_results"][0]["test_id"] == "overflow"


def test_report_fallback_feedback_is_student_usable_without_an_llm():
    report = build_report(
        assignment={"name": "Find a value", "problem_statement": "Search the array."},
        submission={"filename": "student.c"},
        evaluation={"run_id": "run-2", "state": "completed"},
        score={
            "total_score": 50.0,
            "finalized": True,
            "criteria": [
                {
                    "criterion_id": "correctness",
                    "name": "Correctness",
                    "weight": 1.0,
                    "points": 0.5,
                    "contribution": 50.0,
                    "status": "fail",
                    "reason": "1/2 validated tests passed",
                    "evidence_ids": ["test-wrong"],
                }
            ],
        },
        evidence=[
            {
                "id": "test-pass",
                "source_type": "test_runner",
                "test_id": "first",
                "status": "pass",
                "summary": "Test first passed.",
                "input": "3 5 7 3",
                "expected_output": "0",
                "actual_output": "0",
                "details": {},
            },
            {
                "id": "test-wrong",
                "source_type": "test_runner",
                "test_id": "missing",
                "status": "fail",
                "summary": "Test missing failed: output mismatch.",
                "input": "3 5 7 9",
                "expected_output": "-1",
                "actual_output": "0",
                "details": {},
            },
        ],
        version_hash="sha256:report",
    )

    assert report["feedback"]["status"] == "deterministic"
    assert report["feedback"]["issues"]
    assert report["feedback"]["next_steps"]
    assert "student_report" in report
    assert "What needs improvement:" in report["student_report"]
    assert "Validated test 'missing' failed" in report["student_report"]


def test_solution_analysis_distinguishes_simple_and_nested_loops():
    simple = analyze_solution("int main(void) { return 0; }")
    nested = analyze_solution(
        "int main(void) { for (int i=0;i<10;i++){ for (int j=0;j<10;j++){} } return 0; }"
    )
    assert simple.estimated_time_complexity == "O(1)"
    assert nested.estimated_time_complexity.startswith("O(n^2)")
    assert nested.findings


def test_solution_analysis_recognizes_halving_and_composed_search_loops():
    binary = """
    int search(int *values, int n, int target) {
        int left = 0, right = n - 1;
        while (left <= right) {
            int middle = left + (right - left) / 2;
            if (values[middle] == target) return middle;
            if (values[middle] < target) left = middle + 1;
            else right = middle - 1;
        }
        return -1;
    }
    """
    composed = binary + "\nint main(void) { for (int q=0; q<10; ++q) search(0, 0, q); }"
    assert analyze_solution(binary).estimated_time_complexity.startswith("O(logn)")
    assert analyze_solution(composed).estimated_time_complexity.startswith("O(nlogn)")


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
