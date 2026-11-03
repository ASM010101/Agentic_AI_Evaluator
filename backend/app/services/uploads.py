from __future__ import annotations

import hashlib
import json
from pathlib import PurePath

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import AssignmentVersion, Submission, SubmissionBatch


class UploadValidationError(ValueError):
    pass


class UploadConflictError(UploadValidationError):
    pass


def _parse_labels(labels_json: str | None) -> dict[str, object]:
    try:
        labels = json.loads(labels_json) if labels_json else {}
    except json.JSONDecodeError as exc:
        raise UploadValidationError("labels_json must be valid JSON") from exc
    if not isinstance(labels, dict):
        raise UploadValidationError("labels_json must be an object keyed by filename")
    return labels


async def _build_submissions(
    files: list[UploadFile],
    batch_id: str,
    assignment_version_id: str,
    settings: Settings,
    labels: dict[str, object],
    existing_names: set[str] | None = None,
) -> list[Submission]:
    seen_names = set(existing_names or ())
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
        label = str(labels.get(name) or name)
        submissions.append(
            Submission(
                batch_id=batch_id,
                assignment_version_id=assignment_version_id,
                label=label[:200],
                original_filename=name[:255],
                content_hash=content_hash,
                source_content=source,
                source_size=len(content),
            )
        )
    return submissions


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
    labels = _parse_labels(labels_json)

    batch = SubmissionBatch(assignment_version_id=version.id, status="created", summary_json={})
    db.add(batch)
    db.flush()
    submissions = await _build_submissions(
        files,
        batch.id,
        version.id,
        settings,
        labels,
    )
    db.add_all(submissions)
    batch.summary_json = {"total": len(submissions), "queued": 0, "completed": 0, "failed": 0}
    db.commit()
    for submission in submissions:
        db.refresh(submission)
    db.refresh(batch)
    return batch, submissions


async def append_to_batch(
    db: Session,
    batch: SubmissionBatch,
    files: list[UploadFile],
    settings: Settings,
    labels_json: str | None = None,
) -> list[Submission]:
    if batch.status in {"queued", "evaluating"}:
        raise UploadConflictError("cannot add submissions while the batch is being evaluated")
    if not files:
        raise UploadValidationError("at least one .c file is required")

    existing = db.scalars(select(Submission).where(Submission.batch_id == batch.id)).all()
    if len(existing) + len(files) > settings.max_batch_files:
        raise UploadValidationError(f"batch exceeds the {settings.max_batch_files}-file limit")
    labels = _parse_labels(labels_json)
    submissions = await _build_submissions(
        files,
        batch.id,
        batch.assignment_version_id,
        settings,
        labels,
        existing_names={item.original_filename for item in existing},
    )
    db.add_all(submissions)
    batch.status = "created"
    batch.summary_json = {**(batch.summary_json or {}), "total": len(existing) + len(submissions)}
    db.commit()
    for submission in submissions:
        db.refresh(submission)
    db.refresh(batch)
    return submissions
