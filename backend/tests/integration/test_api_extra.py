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
        saved_batches = client.get("/api/batches")
        assert saved_batches.status_code == 200
        assert saved_batches.json()[0]["id"] == batch_id
        assert saved_batches.json()[0]["assignment_id"] == assignment_id
        assert saved_batches.json()[0]["version_number"] == 1
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


def test_similarity_flags_identical_sources_with_different_filenames():
    with TestClient(app) as client:
        created = client.post(
            "/api/assignments",
            json={
                "name": "Similarity assignment",
                "problem_statement": "Return zero.",
                "rules": make_rules(),
            },
        )
        assert created.status_code == 201
        assignment_id = created.json()["id"]
        assignment_detail = client.get(f"/api/assignments/{assignment_id}").json()
        assert assignment_detail["rules"]["similarity"] == {
            "enabled": True,
            "flag_threshold": 0.85,
        }
        assert client.post(f"/api/assignments/{assignment_id}/prepare").status_code == 200
        assert (
            client.post(f"/api/assignments/{assignment_id}/versions/1/activate").status_code == 200
        )

        source = b'#include <stdio.h>\nint main(void) { puts("same"); return 0; }\n'
        batch = client.post(
            f"/api/assignments/{assignment_id}/batches",
            data={"version_number": "1"},
            files=[
                ("files", ("student_one.c", io.BytesIO(source), "text/plain")),
                ("files", ("student_two.c", io.BytesIO(source), "text/plain")),
            ],
        )
        assert batch.status_code == 201
        batch_payload = batch.json()
        assert client.post(f"/api/batches/{batch_payload['id']}/evaluate").status_code == 202

        submissions = client.get(f"/api/batches/{batch_payload['id']}/submissions").json()
        assert all(item["similarity_flagged"] is True for item in submissions)
        assert all(item["similarity_score"] == 1.0 for item in submissions)
        findings = client.get(
            "/api/similarity/findings",
            params={"assignment_version_id": batch_payload["assignment_version_id"]},
        )
        assert findings.status_code == 200
        assert len(findings.json()) == 1
        finding = findings.json()[0]
        assert finding["score"] == 1.0
        assert {finding["left_submission_id"], finding["right_submission_id"]} == {
            item["id"] for item in submissions
        }
        assert finding["details"]["threshold"] == 0.85

        evidence = client.get(f"/api/submissions/{submissions[0]['id']}/evidence").json()
        similarity_evidence = [item for item in evidence if item["source_type"] == "similarity"]
        assert len(similarity_evidence) == 1
        assert similarity_evidence[0]["status"] == "requires_review"

        export = client.get(f"/api/batches/{batch_payload['id']}/export.csv")
        assert export.status_code == 200
        assert "similarity_status" in export.text
        assert export.text.count(",flagged,1.0,") == 2

        second_batch = client.post(
            f"/api/assignments/{assignment_id}/batches",
            data={"version_number": "1"},
            files=[
                ("files", ("student_three.c", io.BytesIO(source), "text/plain")),
                ("files", ("student_four.c", io.BytesIO(source), "text/plain")),
            ],
        )
        assert second_batch.status_code == 201
        assert client.post(f"/api/batches/{second_batch.json()['id']}/evaluate").status_code == 202
        all_findings = client.get(
            "/api/similarity/findings",
            params={"assignment_version_id": batch_payload["assignment_version_id"]},
        )
        assert len(all_findings.json()) == 2


def test_batch_submissions_can_be_appended_before_and_after_evaluation():
    with TestClient(app) as client:
        created = client.post(
            "/api/assignments",
            json={"name": "Append files", "problem_statement": "No output.", "rules": make_rules()},
        )
        assignment_id = created.json()["id"]
        assert client.post(f"/api/assignments/{assignment_id}/prepare").status_code == 200
        assert (
            client.post(f"/api/assignments/{assignment_id}/versions/1/activate").status_code == 200
        )

        batch = client.post(
            f"/api/assignments/{assignment_id}/batches",
            data={"version_number": "1"},
            files={"files": ("first.c", io.BytesIO(b"int main(void){return 0;}"), "text/plain")},
        )
        assert batch.status_code == 201
        batch_id = batch.json()["id"]

        appended = client.post(
            f"/api/batches/{batch_id}/submissions",
            files={"files": ("second.c", io.BytesIO(b"int main(void){return 1;}"), "text/plain")},
        )
        assert appended.status_code == 201
        assert appended.json()[0]["original_filename"] == "second.c"
        assert {
            item["original_filename"]
            for item in client.get(f"/api/batches/{batch_id}/submissions").json()
        } == {"first.c", "second.c"}

        duplicate = client.post(
            f"/api/batches/{batch_id}/submissions",
            files={"files": ("first.c", io.BytesIO(b"int main(void){return 2;}"), "text/plain")},
        )
        assert duplicate.status_code == 422

        assert client.post(f"/api/batches/{batch_id}/evaluate").status_code == 202
        appended_after_evaluation = client.post(
            f"/api/batches/{batch_id}/submissions",
            files={"files": ("third.c", io.BytesIO(b"int main(void){return 3;}"), "text/plain")},
        )
        assert appended_after_evaluation.status_code == 201
        assert len(client.get(f"/api/batches/{batch_id}/submissions").json()) == 3


def test_versions_can_be_reactivated_and_unreferenced_versions_deleted():
    with TestClient(app) as client:
        created = client.post(
            "/api/assignments",
            json={
                "name": "Version controls",
                "problem_statement": "No output.",
                "rules": make_rules(),
            },
        )
        assert created.status_code == 201
        assignment_id = created.json()["id"]

        first = client.post(f"/api/assignments/{assignment_id}/prepare")
        assert first.status_code == 200
        assert (
            client.post(f"/api/assignments/{assignment_id}/versions/1/activate").status_code == 200
        )

        second = client.post(f"/api/assignments/{assignment_id}/prepare")
        assert second.status_code == 200
        assert (
            client.post(f"/api/assignments/{assignment_id}/versions/2/activate").status_code == 200
        )

        reactivated = client.post(f"/api/assignments/{assignment_id}/versions/1/activate")
        assert reactivated.status_code == 200
        assert reactivated.json()["status"] == "active"

        versions = client.get(f"/api/assignments/{assignment_id}/versions").json()
        assert {item["version_number"]: item["status"] for item in versions} == {
            1: "active",
            2: "superseded",
        }

        deleted = client.delete(f"/api/assignments/{assignment_id}/versions/2")
        assert deleted.status_code == 204
        remaining = client.get(f"/api/assignments/{assignment_id}/versions").json()
        assert [item["version_number"] for item in remaining] == [1]


def test_active_or_referenced_versions_cannot_be_deleted():
    with TestClient(app) as client:
        created = client.post(
            "/api/assignments",
            json={"name": "Delete guard", "problem_statement": "No output.", "rules": make_rules()},
        )
        assignment_id = created.json()["id"]
        assert client.post(f"/api/assignments/{assignment_id}/prepare").status_code == 200
        assert (
            client.post(f"/api/assignments/{assignment_id}/versions/1/activate").status_code == 200
        )

        active_delete = client.delete(f"/api/assignments/{assignment_id}/versions/1")
        assert active_delete.status_code == 409

        assert client.post(f"/api/assignments/{assignment_id}/prepare").status_code == 200
        assert (
            client.post(f"/api/assignments/{assignment_id}/versions/2/activate").status_code == 200
        )
        batch = client.post(
            f"/api/assignments/{assignment_id}/batches",
            data={"version_number": "2"},
            files={"files": ("guard.c", io.BytesIO(b"int main(void){return 0;}"), "text/plain")},
        )
        assert batch.status_code == 201
        assert (
            client.post(f"/api/assignments/{assignment_id}/versions/1/activate").status_code == 200
        )
        referenced_delete = client.delete(f"/api/assignments/{assignment_id}/versions/2")
        assert referenced_delete.status_code == 409
