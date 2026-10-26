from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.main import app


def minimal_rules() -> dict:
    return {
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
                "id": "empty",
                "input": "",
                "expected_output": "",
                "rationale": "fixture",
                "provenance": "explicit_rule",
                "status": "validated",
            }
        ],
    }


def active_version(client: TestClient) -> str:
    created = client.post(
        "/api/assignments",
        json={
            "name": "Upload security",
            "problem_statement": "No output.",
            "rules": minimal_rules(),
        },
    )
    assignment_id = created.json()["id"]
    client.post(f"/api/assignments/{assignment_id}/prepare")
    client.post(f"/api/assignments/{assignment_id}/versions/1/activate")
    return assignment_id


def test_upload_rejects_path_traversal_and_duplicate_content():
    with TestClient(app) as client:
        assignment_id = active_version(client)
        traversal = client.post(
            f"/api/assignments/{assignment_id}/batches",
            data={"version_number": "1"},
            files={
                "files": ("../evil.c", io.BytesIO(b"int main(void) { return 0; }"), "text/plain")
            },
        )
        assert traversal.status_code == 422
        duplicate = client.post(
            f"/api/assignments/{assignment_id}/batches",
            data={"version_number": "1"},
            files=[
                ("files", ("one.c", io.BytesIO(b"int main(void) { return 0; }"), "text/plain")),
                ("files", ("two.c", io.BytesIO(b"int main(void) { return 0; }"), "text/plain")),
            ],
        )
        assert duplicate.status_code == 422
