# Architectural decisions

## 2026-10-24 — Start with a modular monolith

The repository was empty apart from the assignment materials. A FastAPI,
SQLAlchemy, SQLite, React and Vite modular monolith is the smallest design that
supports a durable single-dashboard workflow without introducing Redis,
Celery, Kubernetes or a second service boundary.

## 2026-10-26 — Replace Docker as the default Linux execution boundary

The target deployment is a Linux environment without Docker. The default runner
is now Bubblewrap, using unprivileged user/mount/PID/IPC/UTS/network namespaces,
read-only toolchain mounts, an isolated writable workspace, rlimits and a
parent-side timeout. Bubblewrap is a low-level primitive, so the repository
owns the exact policy and documents the residual kernel/toolchain risks. The
existing Docker adapter remains optional for deployments that already provide
it; neither adapter falls back to unsandboxed host execution.

This choice is based on Bubblewrap's upstream design: it is intended for
unprivileged user-namespace sandbox construction, while the application supplies
the explicit filesystem, namespace and resource policy required for grading.

## 2026-10-24 — Deterministic fallback for optional model work

The ordinary path does not require Ollama. Source heuristics and a template
report provide bounded, reproducible behavior in deterministic mode. Ollama is
centralized behind a typed client for future assignment preparation or targeted
review, but model output cannot set rubric weights or final points.

## 2026-10-24 — Similarity is review-only

Normalized token fingerprints produce assignment-scoped candidate pairs and
matched excerpts. The similarity result is persisted as evidence and explicitly
does not deduct points or establish cheating.

## 2026-10-24 — Minimal first-version upload contract

V1 accepts one UTF-8 `.c` file per submission. Multiple files in a batch are
separate submissions, not a multi-file C project. Archive extraction is not
implemented.
