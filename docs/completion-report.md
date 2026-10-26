# AutoGrader completion report

## Implemented

### Backend

- FastAPI application with typed Pydantic request/response/domain contracts.
- SQLite/SQLAlchemy persistence and Alembic migration `0001_initial`.
- Assignment creation, immutable preparation versions, rules hash, provenance,
  ambiguity warnings and activation gating.
- Safe `.c` batch upload with size, UTF-8, filename, duplicate-name and exact
  duplicate-content validation.
- Durable evaluation runs with explicit legal states, progress, retries,
  cancellation endpoint, audit events, evidence, score breakdowns and reports.
- Health/dependency endpoints, OpenAPI docs, report downloads and CSV export.

### Agents and evaluation

- Role 1: deterministic assignment understanding/test-design normalizer; it
  preserves explicit instructor tests and refuses to activate unverified
  score-affecting oracles.
- Role 2: typed deterministic source/complexity analysis with findings and
  uncertainty labels.
- Role 3: assignment-scoped normalized token fingerprints and review-only
  similarity findings.
- Role 4: evidence-linked deterministic report template with usefulness and
  limitations examples.
- Role 5: Python coordinator/state machine with Bubblewrap, optional Docker and
  fake runner adapters.
- Pure deterministic score engine; unavailable evidence is not silently turned
  into a pass or an arbitrary zero.
- Bounded Ollama client with configurable endpoint/model, timeout, retry and
  concurrency policy. Deterministic mode works without Ollama.

### UI

- React/TypeScript/Vite single dashboard with overview, assignments,
  submissions/results, investigation, similarity review, evaluation runs and
  settings/health pages.
- Responsive premium SaaS/developer-workbench visual language, accessible
  labels/status text, loading/empty/error/review states and source/evidence
  investigation workspace.

### Security and documentation

- Bubblewrap namespace policy, optional Docker policy, no-host-execution
  fallback, resource controls and untrusted-output handling documented in
  `docs/security.md`.
- Architecture, flow, API, decisions, testing and benchmark documents.
- Example assignment/rules and correct/buggy C fixtures under
  `examples/add_two_integers/`.

## Architecture deviations

1. **No live Ollama reasoning in the ordinary test path.** The environment does
   not provide Ollama, so deterministic typed analyzers/templates are the safe
   default. The Ollama integration is present and bounded but optional.
2. **Bubblewrap is the default real Linux runner.** The Linux-native sandbox
   was verified for compilation, execution, host-path isolation, resource
   limits and local C static-analysis tools. Docker remains optional and was
   not required for the default path.
3. **No Playwright suite in this environment.** The environment lacks the
   browser/X runtime needed for a stable browser run. Vitest/RTL covers the
   core dashboard workflow instead.
4. **V1 accepts one `.c` per submission.** Multiple uploaded files are separate
   submissions; multi-file C projects and archive uploads are intentionally not
   part of this first implementation.

## How to run

```bash
cp .env.example backend/.env
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "backend[dev]"
npm --prefix frontend install
bash scripts/setup_linux_sandbox.sh
cd backend && alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
npm --prefix frontend run dev
```

Install the real Linux sandbox before grading native C:

```bash
bash scripts/setup_linux_sandbox.sh
```

## Checks executed

- `python -m pytest tests -q` from `backend/`: **23 passed**, one upstream
  Starlette/httpx deprecation warning.
- `python -m pytest tests --cov=app --cov-report=term-missing`: **83% measured
  backend application coverage**.
- `python -m ruff check app tests`: passed.
- `python -m ruff format --check app tests`: passed.
- `alembic upgrade head` and `alembic current`: migration `0001_initial` at
  head.
- `python -m compileall -q app migrations`: passed.
- `npm test -- --run --coverage` from `frontend/`: **3 passed**, **94.62%
  measured frontend coverage**.
- `npm run typecheck`: passed.
- `npm run lint`: passed.
- `npm run format:check`: passed.
- `npm run build`: passed.
- `npm audit --omit=dev`: no production vulnerabilities reported.
- Manual API smoke: `GET /api/health` returned `{"status":"ok",...}`.
- Sample CLI smoke: the `examples/add_two_integers/` fixture completed through
  the Bubblewrap runner and emitted a durable `batch=<id>`.
- Bubblewrap smoke: completed real compile/run, host-path isolation, non-root
  execution, resource-limit termination and local C-tool evidence checks.
- Live Ollama smoke: **not run** because `ollama`/server/model is unavailable.
- Playwright E2E: **not run** because the available environment has no browser
  display/runtime.

## Security status

Implemented controls include Bubblewrap namespace isolation, non-root
execution, dropped capabilities, read-only toolchain mounts, bounded writable
workspace, PID/CPU/memory/file/stack/output/time limits, UTF-8 and file-size
validation, safe server-generated artifact locations, bounded diagnostics,
formula-safe CSV output, and fail-closed behavior when Bubblewrap is missing.

Bubblewrap is not a formal proof of native-code isolation. The local API has no
authentication, and the initial coordinator assumes one backend worker. These
are documented operational boundaries, not hidden claims of production
hardening.

## Performance

No ordinary Ollama batch benchmark was claimed. The current environment record
is Python 3.11.2, GCC 12.2.0, Node 22.23.3, 23 backend
tests in about 42 seconds, and three frontend tests in about 28 seconds. These
are test-suite timings, not an under-10-minute batch guarantee.

## Known limitations

- Finite validated tests cannot prove correctness for all C inputs.
- Ambiguous assignment semantics require operator review and can block version
  activation.
- The source heuristics are useful evidence but are not equivalent to Cppcheck,
  Lizard or a formal complexity proof.
- Similarity cannot establish copying or LLM authorship.
- Bubblewrap/host/kernel vulnerabilities remain residual risk.
- Multi-worker job claiming, authentication and Playwright coverage need a
  deployment-specific hardening pass.

## Next steps

1. Run the Bubblewrap smoke suite against hostile looping, crashing,
   memory-heavy and output-heavy fixtures on each target Linux distribution.
2. Configure one Ollama model and exercise bounded model response validation,
   timeout and malformed-output tests against the live endpoint.
3. Add browser-backed Playwright tests in a CI environment with a browser.
4. Add database-backed worker claim locking and authentication before exposing
   the dashboard beyond a trusted local operator.
