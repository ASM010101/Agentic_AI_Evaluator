from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.main import app


def rules() -> dict:
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
                "id": "empty-output-demo",
                "input": "",
                "expected_output": "",
                "rationale": "deterministic fake-runner fixture",
                "provenance": "explicit_rule",
                "status": "validated",
            }
        ],
    }


def test_assignment_batch_evaluation_and_result_report():
    with TestClient(app) as client:
        response = client.post(
            "/api/assignments",
            json={"name": "Demo", "problem_statement": "Produce no output.", "rules": rules()},
        )
        assert response.status_code == 201, response.text
        assignment_id = response.json()["id"]
        prepared = client.post(f"/api/assignments/{assignment_id}/prepare")
        assert prepared.status_code == 200, prepared.text
        activated = client.post(f"/api/assignments/{assignment_id}/versions/1/activate")
        assert activated.status_code == 200, activated.text
        batch = client.post(
            f"/api/assignments/{assignment_id}/batches",
            data={"version_number": "1"},
            files={"files": ("demo.c", io.BytesIO(b"int main(void) { return 0; }"), "text/plain")},
        )
        assert batch.status_code == 201, batch.text
        batch_id = batch.json()["id"]
        evaluated = client.post(f"/api/batches/{batch_id}/evaluate")
        assert evaluated.status_code == 202, evaluated.text
        run_id = evaluated.json()[0]["id"]
        evaluation = client.get(f"/api/evaluations/{run_id}")
        assert evaluation.status_code == 200
        assert evaluation.json()["state"] == "completed"
        submission_id = client.get(f"/api/batches/{batch_id}/submissions").json()[0]["id"]
        result = client.get(f"/api/submissions/{submission_id}/results")
        assert result.status_code == 200, result.text
        assert result.json()["score"]["total_score"] == 100.0
        assert result.json()["report"] is not None
