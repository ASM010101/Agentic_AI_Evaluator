from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from app.core.db import init_db, new_session
from app.schemas import CreateAssignmentRequest
from app.services.assignments import create_assignment, prepare_assignment, activate_version
from app.services.evaluation import EvaluationCoordinator
from app.services.uploads import create_batch


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoGrader local CLI")
    parser.add_argument(
        "--assignment",
        type=Path,
        required=True,
        help="JSON file containing name, problem_statement and rules",
    )
    parser.add_argument("--submission", type=Path, action="append", required=True)
    parser.add_argument("--runner", choices=["docker", "fake"], default=None)
    args = parser.parse_args()
    settings = get_settings()
    if args.runner:
        settings.runner = args.runner
    init_db()
    payload = json.loads(args.assignment.read_text(encoding="utf-8"))
    request = CreateAssignmentRequest.model_validate(payload)
    db = new_session()
    try:
        assignment = create_assignment(db, request)
        version, warnings = prepare_assignment(db, assignment, request)
        if warnings:
            print("Assignment needs review:")
            for warning in warnings:
                print(f"- {warning}")
            return 2
        version = activate_version(db, version)

        class LocalUpload:
            def __init__(self, filename: str, content: bytes):
                self.filename = filename
                self._content = content

            async def read(self, _limit: int | None = None) -> bytes:
                return self._content

        import asyncio

        files = [LocalUpload(path.name, path.read_bytes()) for path in args.submission]
        batch, _ = asyncio.run(create_batch(db, version, files, settings))
        coordinator = EvaluationCoordinator(settings)
        coordinator.run_batch(batch.id)
        print(f"batch={batch.id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
