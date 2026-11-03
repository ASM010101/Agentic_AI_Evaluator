from __future__ import annotations

import asyncio
import re

from app.agents.runtime import AgentRuntime
from app.core.config import Settings
from app.core.db import new_session
from app.db.models import Evidence, Report, SimilarityFinding, Submission
from app.schemas import CreateAssignmentRequest
from app.sandbox.runner import FakeSandboxRunner
from app.services.assignments import activate_version, create_assignment, prepare_assignment
from app.services.evaluation import EvaluationCoordinator
from app.services.uploads import create_batch


class FakeAgentClient:
    def __init__(self):
        self.prompts: list[str] = []

    async def generate_json(self, prompt: str, _schema_hint: dict) -> dict:
        self.prompts.append(prompt)
        if "You are Agent 1" in prompt:
            return {
                "summary": "The assignment requires a zero-output program.",
                "requirements": [
                    {
                        "id": "output",
                        "text": "The program must produce no output.",
                        "mandatory": True,
                        "rationale": "Explicitly stated by the assignment.",
                    }
                ],
                "candidate_tests": [
                    {
                        "id": "extra-whitespace",
                        "input": "",
                        "expected_output": "",
                        "rationale": "Checks the empty-output boundary.",
                        "requirement_id": "REQ-PROBLEM",
                        "oracle_basis": "The problem statement requires no output.",
                    }
                ],
                "ambiguities": [],
            }
        if "You are Agent 2" in prompt:
            return {
                "algorithm_summary": "The submission returns from main without work.",
                "estimated_time_complexity": "O(1)",
                "estimated_space_complexity": "O(1)",
                "findings": [
                    {
                        "status": "supported",
                        "summary": "The implementation matches the supplied empty-output example.",
                        "severity": "info",
                        "confidence": "high",
                        "evidence_ids": [],
                    }
                ],
            }
        if "You are Agent 3" in prompt:
            return {
                "classification": "common_solution",
                "explanation": "The exact match is expected for this tiny assignment.",
                "caveats": ["A small assignment can produce common token sequences."],
            }
        evidence_ids = re.findall(r'"id":\s*"([^"]+)"', prompt)
        return {
            "summary": "The deterministic result is supported by the recorded evidence.",
            "strengths": ["The program remains within the supplied execution example."],
            "issues": [
                {
                    "summary": "No additional evidence-backed issue was found.",
                    "evidence_ids": evidence_ids[:1],
                    "suggested_fix": "",
                }
            ],
            "next_steps": ["Add instructor-approved boundary tests when the rubric defines them."],
        }


class InvalidAgentClient:
    async def generate_json(self, _prompt: str, _schema_hint: dict) -> dict:
        return {"issues": "not-a-list"}


def settings() -> Settings:
    return Settings(
        runner="fake",
        use_llm=True,
        llm_provider="openai_compatible",
        openai_api_key="test-key",
        openai_model="test-model",
        ollama_max_retries=0,
    )


def test_openrouter_key_alias_is_loaded_without_changing_provider_selection(monkeypatch):
    monkeypatch.delenv("AUTOGRADER_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OpenRouter_API_KEY", "alias-test-key")
    configured = Settings(
        _env_file=None,
        use_llm=True,
        llm_provider="openai_compatible",
        openai_base_url="https://openrouter.ai/api/v1",
    )

    assert configured.openai_api_key == "alias-test-key"
    assert configured.openai_base_url == "https://openrouter.ai/api/v1"


def test_agent_runtime_marks_invalid_model_output_without_crashing():
    runtime = AgentRuntime(settings(), InvalidAgentClient())
    from app.agents.contracts import FeedbackAgentOutput

    result = runtime.run(
        agent="feedback_and_report",
        role="feedback and report generation",
        prompt="Return feedback.",
        output_model=FeedbackAgentOutput,
    )

    assert result.status == "invalid_output"
    assert result.output is None


def test_agent_runtime_records_disabled_mode_without_calling_provider():
    client = FakeAgentClient()
    disabled = settings().model_copy(update={"use_llm": False})
    runtime = AgentRuntime(disabled, client)
    from app.agents.contracts import FeedbackAgentOutput

    result = runtime.run(
        agent="feedback_and_report",
        role="feedback and report generation",
        prompt="Return feedback.",
        output_model=FeedbackAgentOutput,
    )

    assert result.status == "skipped"
    assert client.prompts == []


def test_assignment_agent_adds_non_scoring_candidate_and_records_call():
    request = CreateAssignmentRequest(
        name="Agent assignment",
        problem_statement="Produce no output.",
        rules={
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
                    "id": "explicit",
                    "input": "",
                    "expected_output": "",
                    "rationale": "Instructor fixture",
                    "provenance": "explicit_rule",
                    "status": "validated",
                }
            ],
        },
    )
    from app.agents.assignment_agent import AssignmentUnderstandingAgent
    from app.rules import normalize_rules

    fake = FakeAgentClient()
    runtime = AgentRuntime(settings(), fake)
    spec = AssignmentUnderstandingAgent(settings(), runtime).prepare(
        normalize_rules(request.rules, request.problem_statement), request.problem_statement
    )

    candidate = next(test for test in spec.tests if test.provenance == "llm_candidate")
    assert candidate.status == "candidate"
    assert candidate.score_affecting is False
    assert spec.provenance["agent_1"]["status"] == "completed"
    assert len(fake.prompts) == 1


def test_evaluation_coordinator_runs_agents_two_three_and_four_without_changing_score():
    app_settings = settings()
    fake = FakeAgentClient()
    runtime = AgentRuntime(app_settings, fake)
    db = new_session()
    try:
        request = CreateAssignmentRequest(
            name="Agent evaluation",
            problem_statement="Produce no output.",
            rules={
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
                        "id": "explicit",
                        "input": "",
                        "expected_output": "",
                        "rationale": "Instructor fixture",
                        "provenance": "explicit_rule",
                        "status": "validated",
                    }
                ],
            },
        )
        assignment = create_assignment(db, request)
        version, warnings = prepare_assignment(
            db, assignment, request, app_settings, agent_runtime=runtime
        )
        assert warnings == []
        version = activate_version(db, version)

        class LocalUpload:
            def __init__(self, filename: str):
                self.filename = filename

            async def read(self, _limit: int | None = None) -> bytes:
                return b"int main(void) { return 0; }\n"

        batch, _ = asyncio.run(
            create_batch(
                db,
                version,
                [LocalUpload("one.c"), LocalUpload("two.c")],
                app_settings,
            )
        )
        EvaluationCoordinator(
            app_settings,
            runner=FakeSandboxRunner(),
            agent_runtime=runtime,
        ).run_batch(batch.id)

        evidence = db.query(Evidence).all()
        source_types = {item.source_type for item in evidence}
        assert "llm_solution_agent" in source_types
        assert "llm_feedback_agent" in source_types
        assert all(
            item.details_json.get("scoring_impact") is False
            for item in evidence
            if item.source_type.startswith("llm_")
        )
        findings = db.query(SimilarityFinding).all()
        assert len(findings) == 1
        assert findings[0].details_json["agent_3_review"]["status"] == "completed"
        assert sum("You are Agent 2" in prompt for prompt in fake.prompts) == 2
        assert sum("You are Agent 3" in prompt for prompt in fake.prompts) == 1
        assert sum("You are Agent 4" in prompt for prompt in fake.prompts) == 2
        # The concrete role names are persisted in provenance, not inferred from UI labels.
        assert any(
            item.provenance_json.get("agent") == "solution_compliance_complexity"
            for item in evidence
        )
        assert any(item.provenance_json.get("agent") == "feedback_and_report" for item in evidence)
        reports = db.query(Report).all()
        assert len(reports) == 2
        assert all(report.report_json["feedback"]["status"] == "completed" for report in reports)
        submission = db.query(Submission).first()
        assert submission is not None
        assert all(report.report_json["score"]["total_score"] == 100.0 for report in reports)
    finally:
        db.close()
