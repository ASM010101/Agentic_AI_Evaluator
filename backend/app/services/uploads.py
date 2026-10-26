from __future__ import annotations

import hashlib
import json
from pathlib import PurePath

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import AssignmentVersion, Submission, SubmissionBatch


class UploadValidationError(ValueError):
    pass


async def create_batch(
    db: Session,
    version: AssignmentVersion,
    files: list[UploadFile],
    settings: Settings,
    labels_json: str | None = None,
) -> tuple[SubmissionBatch, list[Submission]]:
    if version.status != "active":
        raise UploadValidationError("submissions require an active assignment version")
    if not files:
        raise UploadValidationError("at least one .c file is required")
    if len(files) > settings.max_batch_files:
        raise UploadValidationError(f"batch exceeds the {settings.max_batch_files}-file limit")
    try:
        labels = json.loads(labels_json) if labels_json else {}
    except json.JSONDecodeError as exc:
        raise UploadValidationError("labels_json must be valid JSON") from exc
    if not isinstance(labels, dict):
        raise UploadValidationError("labels_json must be an object keyed by filename")

    batch = SubmissionBatch(assignment_version_id=version.id, status="created", summary_json={})
    db.add(batch)
    db.flush()
    seen_hashes: set[str] = set()
    seen_names: set[str] = set()
    submissions: list[Submission] = []
    for file in files:
        name = (file.filename or "").strip()
        if not name.lower().endswith(".c"):
            raise UploadValidationError(f"{name or 'unnamed file'} is not a .c source file")
        if PurePath(name).name != name or "/" in name or "\\" in name:
            raise UploadValidationError(f"unsafe filename: {name}")
        if name in seen_names:
            raise UploadValidationError(f"duplicate filename in batch: {name}")
        seen_names.add(name)
        content = await file.read(settings.max_source_bytes + 1)
        if len(content) > settings.max_source_bytes:
            raise UploadValidationError(f"{name} exceeds the source size limit")
        try:
            source = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadValidationError(f"{name} is not valid UTF-8 text") from exc
        content_hash = hashlib.sha256(content).hexdigest()
        if content_hash in seen_hashes:
            raise UploadValidationError(f"exact duplicate upload detected: {name}")
        seen_hashes.add(content_hash)
        label = str(labels.get(name) or name)
        submissions.append(
            Submission(
                batch_id=batch.id,
                assignment_version_id=version.id,
                label=label[:200],
                original_filename=name[:255],
                content_hash=content_hash,
                source_content=source,
                source_size=len(content),
            )
        )
    db.add_all(submissions)
    batch.summary_json = {"total": len(submissions), "queued": 0, "completed": 0, "failed": 0}
    db.commit()
    for submission in submissions:
        db.refresh(submission)
    db.refresh(batch)
    return batch, submissions
