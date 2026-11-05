# AutoGrader

AutoGrader is an automated evaluation platform for C programming assignments. It combines **Linux-native sandbox isolation** with **specialized agentic language models** to perform reliable test generation, deterministic scoring, static code analysis, and actionable student feedback.

---

## Key Features

- **Linux-Native Sandbox Security:** Compiles and executes student submissions inside unprivileged Linux namespaces using **Bubblewrap (`bwrap`)** with CPU time limits, memory caps, read-only system toolchain mounts, and full network isolation (`--unshare-net`).
- **Deterministic Scoring Engine:** Grades are calculated strictly through mathematical aggregation of verified test outcomes, compiler diagnostics, and rubric weights. Language models are strictly advisory and never assign or alter numeric scores.
- **Multi-Agent Pipeline:**
  - **Test Design Agent:** Automatically extracts assignment constraints and generates candidate edge-case test suites.
  - **Complexity Review Agent:** Analyzes submitted source code to estimate asymptotic time and space complexity ($\mathcal{O}(\log n)$, $\mathcal{O}(n)$, $\mathcal{O}(n^2)$) and check rubric compliance.
  - **Similarity Review Agent:** Evaluates candidate pairs identified by token-sequence overlap, providing contextual review signals for instructors.
  - **Feedback & Report Agent:** Synthesizes compiler diagnostics, test traces, and static analysis findings into structured student feedback (strengths, issues with evidence citations, and next steps).
- **Static Analysis Integration:** Gathers typed quality and security evidence using **GCC C11**, **Cppcheck**, **Flawfinder**, and **Clang-Tidy**.
- **Dual LLM Runtime Support:** Works out-of-the-box with local offline **Ollama** (`llama3.1`) for complete student privacy, or high-throughput cloud APIs (**Groq** / OpenAI-compatible endpoints) for large batch processing.
- **Audit Trails & Export:** Persists durable execution traces, cryptographic content hashes, machine-readable JSON artifacts, and formula-injection-safe CSV gradebook exports.

---

## Architecture Overview

```
                          +------------------------+
                          |   Assignment Prompt    |
                          +-----------+------------+
                                      |
                                      v
                          +------------------------+
                          |   Agent 1: Test Design |
                          +-----------+------------+
                                      |
                                      v
                          +------------------------+
                          |  Immutable Rubric Spec |
                          +-----------+------------+
                                      |
                          Student Submissions Uploaded
                                      |
                                      v
+----------------------------------------------------------------------------+
|                  Python Coordinator & Sandbox Runner (bwrap)               |
|  - Compiles C source via GCC C11 inside ephemeral mounts                   |
|  - Executes I/O test cases under strict CPU and memory limits              |
|  - Collects static analysis findings (Cppcheck, Flawfinder, Clang-Tidy)    |
+---------------------+--------------------------------+---------------------+
                      |                                |
                      v                                v
      +-------------------------------+    +-------------------------------+
      |  Agent 2: Complexity Analysis |    |   Agent 3: Similarity Review  |
      +---------------+---------------+    +---------------+---------------+
                      |                                    |
                      +---------------+--------------------+
                                      v
                      +--------------------------------+
                      |  Deterministic Scoring Engine  |
                      +---------------+----------------+
                                      v
                      +--------------------------------+
                      |   Agent 4: Feedback & Reports  |
                      +---------------+----------------+
                                      v
                      +--------------------------------+
                      |   Evidence Reports & CSV Export|
                      +--------------------------------+
```

---

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, SQLite, Alembic
- **Frontend:** React 18, TypeScript, Vite
- **Sandbox:** Linux Bubblewrap (`bwrap`), GCC (C11 standard)
- **Static Analysis:** Cppcheck, Flawfinder, Clang-Tidy
- **LLM Integrations:** Ollama (Local) / Groq & OpenAI-compatible endpoints (Cloud)

---

## Getting Started

### Prerequisites

- **Linux** or **Windows with WSL2 (Ubuntu)** (required for Bubblewrap sandboxing)
- **Python 3.11+**
- **Node.js 20+** and `npm`
- **Build & Sandbox Tools:**
  ```bash
  sudo apt update
  sudo apt install -y gcc bwrap cppcheck flawfinder clang-tidy
  ```

---

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ASM010101/Agentic_AI_Evaluator.git
   cd Agentic_AI_Evaluator
   ```

2. **Setup Backend:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r backend/requirements-dev.txt
   cp .env.example backend/.env
   ```

3. **Setup Frontend:**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

---

### Running the Services

Start the backend and frontend in separate terminals:

**Terminal 1 — Backend API:**
```bash
cd backend
source ../.venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend Dashboard:**
```bash
cd frontend
npm run dev
```

- Web Dashboard: `http://localhost:5173`
- Interactive API Documentation: `http://localhost:8000/docs`

---

## Configuration

Settings are managed via environment variables in `backend/.env`:

```ini
# Core Configuration
AUTOGRADER_DATABASE_URL=sqlite:///./data/autograder.db
AUTOGRADER_ARTIFACT_DIR=./data/artifacts
AUTOGRADER_RUNNER=bubblewrap
AUTOGRADER_USE_LLM=true

# Option A: Local Offline Ollama (Default for complete privacy)
AUTOGRADER_LLM_PROVIDER=ollama
AUTOGRADER_OLLAMA_BASE_URL=http://127.0.0.1:11434
AUTOGRADER_OLLAMA_MODEL=llama3.1:latest
AUTOGRADER_OLLAMA_READ_TIMEOUT_S=120

# Option B: Cloud High-Throughput (Groq / OpenAI-Compatible)
# AUTOGRADER_LLM_PROVIDER=openai_compatible
# AUTOGRADER_OPENAI_API_KEY=your_api_key_here
# AUTOGRADER_OPENAI_BASE_URL=https://api.groq.com/openai/v1
# AUTOGRADER_OPENAI_MODEL=qwen/qwen3.8-27b
```

---

## Testing

Run the automated test suite covering unit tests, sandbox fail-closed boundaries, and integration workflows:

```bash
cd backend
source ../.venv/bin/activate
pytest -v
```

---

## Database Management

To reset local evaluation runs, test artifacts, and databases:

- **Windows PowerShell:**
  ```powershell
  .\scripts\clear_db.ps1
  ```
- **Linux / WSL Bash:**
  ```bash
  bash scripts/clear_db.sh
  ```

*(FastAPI automatically reinitializes clean schema tables on startup.)*

---

## Project Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── agents/          # LLM agent definitions (Test Design, Complexity, Similarity, Feedback)
│   │   ├── api/             # FastAPI REST routes and request handlers
│   │   ├── core/            # Configuration, database engine, and settings
│   │   ├── db/              # SQLAlchemy relational models
│   │   ├── llm/             # Bounded client seam for Ollama and OpenAI-compatible providers
│   │   ├── sandbox/         # Linux Bubblewrap isolation runner
│   │   ├── scoring/         # Deterministic mathematical grading engine
│   │   ├── services/        # Evaluation coordinator and batch lifecycle state machine
│   │   └── similarity/      # Normalized tokenization and pairwise similarity matching
│   ├── data/                # Local SQLite storage and evaluation artifacts
│   ├── tests/               # Unit, security, and integration tests
│   ├── requirements.txt     # Core dependencies
│   └── requirements-dev.txt # Development and testing dependencies
├── frontend/
│   ├── src/                 # React components, pages, dashboard views, and API client
│   ├── package.json         # Node.js dependencies and build scripts
│   └── vite.config.ts       # Vite configuration
├── docs/                    # Architecture, security, and evaluation documentation
├── scripts/
│   ├── clear_db.ps1         # Database cleanup utility (PowerShell)
│   ├── clear_db.sh          # Database cleanup utility (Bash)
│   └── setup_linux_sandbox.sh # Dependency installer for Linux environments
└── README.md
```

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
