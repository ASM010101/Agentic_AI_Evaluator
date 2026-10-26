# AutoGrader implementation plan

## Repository audit — 2026-10-24

The repository initially contained only the assignment PDF and
`autograder_master_development_prompt.md`; there was no application source,
dependency manifest, test suite, Git metadata, or existing UI to preserve.

The runtime has Python 3.11.2, Node.js 22.23.3, npm 10.9.9, and GCC 12.2.0.
The target Linux environment does not provide Docker, so Bubblewrap/GCC is the
default real execution boundary. An optional Docker adapter remains available
for compatible deployments, and both real adapters fail closed when unavailable.
Ollama remains optional; deterministic fakes are limited to tests.

## Vertical slices and test gates

1. **Foundation:** FastAPI, typed configuration, SQLAlchemy/SQLite persistence,
   migrations, health endpoints, React/Vite shell, and baseline tests.
2. **Assignments:** rule validation, immutable assignment versions, explicit
   test/oracle provenance, preparation output, activation gating, and UI forms.
3. **Sandbox:** typed runner interface, fail-closed Bubblewrap and optional
   Docker adapters, deterministic fake runner, output comparison, limits, and
   security tests.
4. **Evaluation lifecycle:** batches, safe `.c` uploads, durable state machine,
   coordinator, evidence aggregation, deterministic scoring, reports, and API.
5. **Similarity and review:** normalized assignment-scoped fingerprints,
   review dispositions, evidence views, and CSV/report downloads.
6. **Dashboard:** assignment workflow, upload/evaluation results, evidence
   investigation, similarity review, settings/health, responsive states.
7. **Hardening:** regression, security-focused tests, documentation, and an
   environment-aware benchmark report.

## Current implementation status

Milestones 1–6 are implemented in the current workspace: the backend API and
SQLite model, assignment/rule workflow, Bubblewrap, optional Docker and fake runner interfaces,
durable coordinator, evidence/scoring/report path, similarity review, and the
React dashboard are all present. The default backend suite contains 20 tests
with 83% measured application coverage; the frontend suite contains 3 tests
with 94.62% measured coverage. Bubblewrap-backed execution is verified on the
Linux toolchain; Ollama and Playwright remain environment-dependent.

## Planned verification commands

```text
python -m pytest backend/tests -q
python -m ruff check backend
python -m ruff format --check backend
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Sandbox smoke tests, live Ollama tests and Playwright are environment-dependent
and will be reported separately rather than represented as passed when the tools
are unavailable.
