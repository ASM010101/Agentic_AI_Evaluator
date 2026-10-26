# Testing guide

## Deterministic default checks

Run from `backend/`:

```bash
python -m pytest tests -q
python -m pytest tests --cov=app --cov-report=term-missing
python -m ruff check app tests
python -m ruff format --check app tests
```

The suite uses an isolated SQLite database and a deterministic fake runner. It
does not require a Docker daemon or live Ollama model. It covers rules and
activation gating, pure scoring, state transitions, comparison policy,
similarity normalization, upload/evaluation API behavior, and fail-closed
sandbox behavior. The current run is 20 passed with 83% measured backend
application coverage.

## Frontend checks

Run from `frontend/`:

```bash
npm test -- --run
npm run typecheck
npm run build
npm run lint
npm run format:check
```

## Environment-dependent checks

With Docker installed and the sandbox image built:

```bash
docker build -t autograder-sandbox:latest sandbox
AUTOGRADER_RUNNER=docker python -m pytest tests -q
```

The current development environment does not include Docker or Ollama, so the
real native-code execution and live-model checks are not reported as passed.
Playwright is also optional in this first local build; the frontend test suite
keeps the dashboard shell deterministic without depending on model latency. The
current Vitest run is 3 passed with 94.62% measured frontend coverage.
