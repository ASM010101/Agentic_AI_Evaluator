from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.main import app


def make_rules() -> dict:
    return {
        "metrics": [
            {
                "name": "correctness",
                "analyzer": "io_tests",
                "weight": 0.5,
                "scoring": {"mode": "test_ratio"},
            },
            {
                "name": "readability",
                "analyzer": "readability",
                "weight": 0.5,
                "scoring": {"mode": "evidence_score"},
            },
        ],
        "tests": [
            {
                "id": "pass",
                "input": "",
                "expected_output": "",
                "rationale": "fixture",
                "provenance": "explicit_rule",
                "status": "validated",
            }
        ],
    }


def test_health_versions_evidence_csv_and_similarity_routes():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        created = client.post(
            "/api/assignments",
            json={"name": "Routes", "problem_statement": "No output.", "rules": make_rules()},
        )
        assert created.status_code == 201
        assignment_id = created.json()["id"]
        prepared = client.post(f"/api/assignments/{assignment_id}/prepare")
        assert prepared.status_code == 200
        assert client.get(f"/api/assignments/{assignment_id}").status_code == 200
        assert client.get(f"/api/assignments/{assignment_id}/versions").status_code == 200
        assert (
            client.post(f"/api/assignments/{assignment_id}/versions/1/activate").status_code == 200
        )
        batch_response = client.post(
            f"/api/assignments/{assignment_id}/batches",
            data={"version_number": "1"},
            files={
                "files": (
                    "routes.c",
                    io.BytesIO(b"#include <stdio.h>\nint main(void){return 0;}"),
                    "text/plain",
                )
            },
        )
        assert batch_response.status_code == 201
        batch_id = batch_response.json()["id"]
        live_before = client.get(f"/api/batches/{batch_id}/live")
        assert live_before.status_code == 200
        assert live_before.json()["total_submissions"] == 1
        assert live_before.json()["overall_progress"] == 0
        run = client.post(f"/api/batches/{batch_id}/evaluate").json()[0]
        live_after = client.get(f"/api/batches/{batch_id}/live")
        assert live_after.status_code == 200
        assert live_after.json()["runs"][0]["current_stage_label"] == "Completed"
        assert live_after.json()["runs"][0]["next_stage_label"] is None
        assert live_after.json()["runs"][0]["current_detail"] == (
            "Evaluation and report are ready for review."
        )
        assert live_after.json()["recent_events"]
        submission_id = client.get(f"/api/batches/{batch_id}/submissions").json()[0]["id"]
        assert client.get(f"/api/submissions/{submission_id}/evidence").status_code == 200
        result = client.get(f"/api/submissions/{submission_id}/results").json()
        report_id = result["report"]["id"]
        assert client.get(f"/api/reports/{report_id}/download?format=txt").status_code == 200
        assert client.get(f"/api/reports/{report_id}/download?format=json").status_code == 200
        export = client.get(f"/api/batches/{batch_id}/export.csv")
        assert export.status_code == 200
        assert "routes.c" in export.text
        assert client.get("/api/similarity/findings").status_code == 200
        assert client.get(f"/api/evaluations/{run['id']}").status_code == 200
