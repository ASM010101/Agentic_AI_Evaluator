# AutoGrader

AutoGrader is a local-first dashboard for evaluating multiple student C
submissions against one instructor-owned assignment version. It turns a
problem statement and JSON rubric into a validated, immutable version, runs
approved tests and source checks, stores typed evidence, calculates a
deterministic score, and produces an evidence-linked report.

It deliberately does **not** claim formal correctness, automatic proof of
plagiarism, reliable AI-authorship detection, or perfect native-code isolation.
Similarity is a review signal, not a grade deduction. There is no hidden
reference solution dependency.

## What is implemented

- FastAPI + Pydantic + SQLAlchemy/SQLite backend.
- Assignment creation, rule validation, immutable versions and activation
  gating for unvalidated score-affecting tests.
- Durable batches, submissions, evaluation runs, explicit lifecycle states,
  evidence, scores, reports, audit events and similarity findings.
- Deterministic scoring engine with criterion-level points, contributions,
  missing-evidence policy and calculation trace.
- Linux-native Bubblewrap/GCC C11 sandbox adapter with user, mount, PID, IPC,
  UTS and network namespace isolation, a non-root sandbox UID, read-only
  toolchain mounts, an isolated writable workspace, resource limits and a
  host timeout. It fails closed when Bubblewrap/GCC is not available.
- Optional Docker/GCC adapter remains available for deployments that already
  operate Docker, but Docker is not required by the default Linux path.
- Deterministic fake runner for tests and development without Docker.
- Assignment-scoped normalized token similarity with review dispositions.
- Optional bounded Ollama client; deterministic mode works without Ollama.
- Local C static-analysis evidence from Cppcheck, Flawfinder and Clang-Tidy;
  tool findings are review evidence and do not silently deduct points.
- React + TypeScript + Vite dashboard with overview, assignment, upload/results,
  investigation, similarity and health pages.
- JSON and text report artifacts plus CSV export with formula-prefix escaping.
- Alembic initial migration and documented security/testing decisions.

## Architecture

See [docs/architecture.md](docs/architecture.md) and
[docs/evaluation-flow.md](docs/evaluation-flow.md) plus
[docs/static-analysis.md](docs/static-analysis.md). The application uses five
logical roles:

1. Assignment understanding and test design.
2. Solution, compliance and complexity analysis.
3. Similarity and originality evidence.
4. Feedback and report generation.
5. Python coordination/state machine.

The backend includes a bounded Ollama client and health check, but the current
grading path is intentionally deterministic: scoring and reports do not call
the model automatically. Role 5 is not an LLM worker. Ollama setup is therefore
optional for the current dashboard demo.

## Prerequisites

- Python 3.11+ (the target contract is Python 3.12+).
- Node.js 20+ and npm.
- Bubblewrap (`bwrap`) and GCC for real C compilation/execution on Linux.
- Optional: Docker if a deployment chooses the legacy container adapter.
- Optional: Codacy repository analysis for Git-backed repository reporting;
  it is not required for uploaded-submission grading.
- Optional: Ollama and one locally installed model for bounded model-assisted
  analysis. No particular GPU or model is assumed.

The Linux development environment needs Python 3.11+, Node 20+, GCC and
Bubblewrap. The application default is `AUTOGRADER_RUNNER=bubblewrap`; the
fake runner is reserved for unit tests and must not be used to claim that C
execution occurred.

## Fresh setup

From the repository root:

```bash
cp .env.example backend/.env
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e "backend[dev]"
npm --prefix frontend install
```

If you prefer a conventional requirements file instead of the editable
`pyproject.toml` install, use:

```bash
python -m pip install -r backend/requirements-dev.txt
```

### WSL quick start

Run this from the WSL terminal, not from a Windows Command Prompt. If the
project was previously used by a container or another Linux user, remove stale
generated metadata before installing:

```bash
cd /mnt/c/Users/amash/Downloads/AutoG
source .venv/bin/activate
rm -rf backend/autograder_backend.egg-info backend/build backend/dist
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-dev.txt
npm ci --prefix frontend
cp -n .env.example backend/.env

cd backend
python -m alembic upgrade head
```

The WSL terminal must use a Linux Node.js installation. Check it before
starting Vite:

```bash
node -p "process.platform + ' ' + process.arch"
type -a node npm
```

The first command must print `linux x64`. If it prints `win32`, WSL is calling
Windows `npm`; install/use Node.js inside WSL, then reinstall frontend packages
so native dependencies match Linux:

```bash
sudo apt update
sudo apt install -y curl build-essential
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install --lts
nvm use --lts
cd /mnt/c/Users/amash/Downloads/AutoG
rm -rf frontend/node_modules
npm ci --prefix frontend
```

Do not use `sudo npm`, and do not mix Windows `node_modules` with WSL Node.js.

## Sharing the project

Share the clean source archive, not local environments or generated state. The
archive should contain the source, migrations, tests, examples, documentation,
`package-lock.json`, `backend/requirements*.txt`, and `.env.example`. It should
not contain `.venv`, `frontend/node_modules`, databases, test artifacts, build
output, caches, `.vscode`, or `backend/.env`.

For real C grading, teammates should run the backend in Linux or WSL. After
extracting the archive, from its root, create the environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
cp .env.example backend/.env
python -m pip install -r backend/requirements-dev.txt
npm ci --prefix frontend
bash scripts/setup_linux_sandbox.sh
cd backend
python -m alembic upgrade head
```

Start the backend in one terminal:

```bash
cd backend
source ../.venv/bin/activate
export AUTOGRADER_RUNNER=bubblewrap
python -m uvicorn app.main:app --reload --port 8000
```

Start the frontend in a second terminal using the Linux Node.js installation:

```bash
cd /path/to/AutoG
source .venv/bin/activate
npm --prefix frontend run dev
```

Then open `http://127.0.0.1:5173`. Do not copy your local `backend/.env` or
database to teammates; each person should create their own local environment.

Install the Linux execution and local C-analysis tools on Debian/Ubuntu:

```bash
bash scripts/setup_linux_sandbox.sh
```

The script installs Bubblewrap, GCC, Cppcheck, Flawfinder and Clang-Tidy. The
application does not require Docker for the default runner.

If the backend reports `sqlite3.OperationalError: attempt to write a readonly
database` while creating an assignment, the generated SQLite files were likely
created earlier by a root/container process. This is a filesystem-permission
problem, not an invalid assignment. Check and repair only the generated local
data directory:

```bash
cd /mnt/c/Users/amash/Downloads/AutoG
ls -ld backend/data backend/data/autograder.db
chmod -R a+rwX backend/data
```

If `chmod` is denied, use `sudo` for that one repair command, then run the
application normally as your WSL user:

```bash
sudo chmod -R a+rwX backend/data
```

Stop and restart Uvicorn after repairing the permissions. Do not use `sudo`
when starting the backend, because that would recreate the same ownership
problem.

If `.venv` does not exist yet, create it before `source`:

```bash
cd /mnt/c/Users/amash/Downloads/AutoG
python3 -m venv .venv
source .venv/bin/activate
```

If the cleanup reports `Permission denied`, repeat only the cleanup with
`sudo`, then run pip normally as your own user:

```bash
sudo rm -rf backend/autograder_backend.egg-info backend/build backend/dist
python -m pip install -r backend/requirements-dev.txt
```

On WSL, if editable installation reports `Cannot update time stamp of directory
'autograder_backend.egg-info'`, remove stale build metadata created by another
user/environment and retry:

```bash
rm -rf backend/autograder_backend.egg-info backend/build backend/dist
python -m pip install -e "backend[dev]"
```

This directory is generated by setuptools and is ignored by the repository; it
is not application source code. If the files are owned by `root` because a
previous container command created them, the same cleanup may require:

```bash
sudo rm -rf backend/autograder_backend.egg-info backend/build backend/dist
```

The virtual environment is intentionally not committed: it is platform- and
machine-specific. Create it locally with `python -m venv .venv`.

Create the database with Alembic when using a clean environment:

```bash
cd backend
alembic upgrade head
cd ..
```

The application also creates missing tables at startup for simple local use.
Alembic remains the repeatable migration path.

### Windows PowerShell quick start

Run these commands from `C:\Users\amash\Downloads\AutoG`:

```powershell
py -3 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements-dev.txt
Copy-Item .env.example backend\.env

cd backend
python -m alembic upgrade head
$env:AUTOGRADER_RUNNER = "fake"
python -m uvicorn app.main:app --reload --port 8000
```

In a second PowerShell window:

```powershell
cd C:\Users\amash\Downloads\AutoG
.\.venv\Scripts\Activate.ps1
npm --prefix frontend install
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173` and check the API with:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Use `AUTOGRADER_RUNNER="bubblewrap"` for real Linux C execution. The runner
does not require a daemon or a container image. It fails closed if Bubblewrap
or GCC is unavailable. The fake runner remains available only for tests and
fixtures; it never executes arbitrary C code.

## Start the application

Terminal 1 — backend:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Terminal 2 — frontend:

```bash
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173`. The API docs are at
`http://127.0.0.1:8000/docs`.

For a deterministic test-only runner without executing C:

```bash
AUTOGRADER_RUNNER=fake uvicorn app.main:app --reload --port 8000
```

The fake runner is a test double. It must not be represented as real C
compilation in a report.

The dashboard polls the live batch monitor while work is active and shows the
current stage, the next stage, per-submission progress, and recent audit-backed
stage events. The production path uses the real Bubblewrap runner; the fake
runner is limited to automated tests.

## Optional Ollama setup

Ollama is not required to open or test the dashboard. The current application
uses deterministic source analysis and scoring; Ollama is currently used by the
backend for availability checks and the bounded client seam, not as an
automatic scoring dependency.

Install Ollama in WSL if it is not already installed:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Start the Ollama server in its own terminal. Yes, `ollama serve` is the correct
command when no Ollama desktop/service is already running:

```bash
ollama serve
```

Leave that terminal open. In another WSL terminal, download the model configured
by `.env` and confirm that it is installed:

```bash
ollama pull llama3.1:latest
ollama list
curl http://127.0.0.1:11434/api/tags
```

The backend configuration should contain:

```dotenv
AUTOGRADER_OLLAMA_BASE_URL=http://127.0.0.1:11434
AUTOGRADER_OLLAMA_MODEL=llama3.1:latest
AUTOGRADER_USE_LLM=false
```

Keep `AUTOGRADER_USE_LLM=false` for deterministic grading. Changing it to
`true` is safe for health-check experiments, but it does not currently change
the deterministic grading path.

If Ollama Desktop is already running on Windows, do not start a second
`ollama serve` on the same address. First test the existing service:

```bash
curl http://127.0.0.1:11434/api/tags
```

## Linux sandbox policy

The default runner is Bubblewrap, not Docker. For every compile/run operation
it creates a fresh namespace sandbox with:

- no network namespace access;
- isolated user, mount, PID, IPC and UTS namespaces;
- non-root UID/GID inside the sandbox;
- read-only mounts for `/usr`, libraries, `/etc` and `/usr/local`;
- a fresh `/proc`, `/dev` and `/tmp` plus one writable `/work` directory;
- inherited CPU, address-space, file-size, file-count, stack and process limits;
- bounded stdout/stderr and a parent-death kill path.

Bubblewrap is a low-level primitive, so these command-line mounts and limits
are part of AutoGrader's security policy. It is not a claim of perfect kernel
isolation. A hardened deployment should run the grading worker under a separate
Linux account/VM and keep the host patched.

Docker remains an optional adapter for environments that explicitly choose it:

```bash
AUTOGRADER_RUNNER=docker python -m uvicorn app.main:app --reload --port 8000
```

The normal Linux command is simply:

```bash
AUTOGRADER_RUNNER=bubblewrap python -m uvicorn app.main:app --reload --port 8000
```

## Create and evaluate an assignment

The UI can create an assignment. The minimal API flow is:

```bash
curl -X POST http://127.0.0.1:8000/api/assignments \
  -H 'Content-Type: application/json' \
  --data @examples/add_two_integers/assignment.json
```

The example JSON contains `name`, `problem_statement`, and `rules`. After the
response returns an assignment ID:

```bash
curl -X POST http://127.0.0.1:8000/api/assignments/<ASSIGNMENT_ID>/prepare
curl -X POST http://127.0.0.1:8000/api/assignments/<ASSIGNMENT_ID>/versions/1/activate
curl -X POST \
  -F version_number=1 \
  -F files=@examples/add_two_integers/correct.c \
  -F files=@examples/add_two_integers/buggy.c \
  http://127.0.0.1:8000/api/assignments/<ASSIGNMENT_ID>/batches
curl -X POST http://127.0.0.1:8000/api/batches/<BATCH_ID>/evaluate
```

Poll `/api/evaluations/<RUN_ID>` and inspect
`/api/submissions/<SUBMISSION_ID>/results` plus
`/api/submissions/<SUBMISSION_ID>/evidence`.

The local CLI is also available:

```bash
AUTOGRADER_RUNNER=fake python -m app.cli \
  --assignment ../examples/add_two_integers/assignment.json \
  --submission ../examples/add_two_integers/correct.c \
  --submission ../examples/add_two_integers/buggy.c
```

## Rules and oracle policy

Rules stay outside the agent source code. A metric can use a built-in analyzer
such as `io_tests`, `compiler_warnings`, `static_analysis`, `function_split`,
`complexity_estimator`, `sanitizer_run`, `readability`, or `similarity_flag`.
The rubric controls weights and applicability; the agent does not invent a
universal correctness percentage.

Score-affecting tests must be `validated` and have an explicit expected output
or an independently justified executable behavior. Candidate/unverified tests
remain visible but cannot silently reduce a grade. A missing oracle becomes
`needs_review`, not a zero.

## Tests, lint, type checks and build

Backend from `backend/`:

```bash
python -m pytest tests -q
python -m pytest tests --cov=app --cov-report=term-missing
python -m ruff check app tests
python -m ruff format --check app tests
```

Frontend from the repository root:

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend run format:check
```

Playwright and sandbox-backed smoke tests are environment-dependent and are not
part of the deterministic default suite. See [docs/testing.md](docs/testing.md).

## Health and troubleshooting

- **Bubblewrap unavailable:** run `bash scripts/setup_linux_sandbox.sh` on
  Debian/Ubuntu. Do not switch to host execution for untrusted submissions.
- **Ollama unavailable/model missing:** leave `AUTOGRADER_USE_LLM=false` for
  deterministic mode, or start Ollama with `ollama serve` and install the
  model named in `.env`.
- **Port collision:** change the Uvicorn `--port` and set `VITE_API_URL` for the
  frontend if the backend is not on port 8000.
- **Activation blocked:** inspect the assignment version preview. A material
  ambiguity or unvalidated score-affecting test must be resolved first.
- **Report missing:** inspect the evaluation state and error summary. Compiler,
  sandbox and model problems are recorded as unavailable/failure states rather
  than student failures.

## Security and limitations

Read [docs/security.md](docs/security.md) for the boundary and residual risks.
Read [docs/benchmark.md](docs/benchmark.md) for the honest benchmark status.
The factual implementation and verification record is in
[docs/completion-report.md](docs/completion-report.md).
The required usefulness and limitations examples are included in every report
and described in [backend/app/agents/report_agent.py](backend/app/agents/report_agent.py).
