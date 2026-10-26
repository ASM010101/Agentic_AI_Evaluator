# AutoGrader architecture

AutoGrader is a local-first modular monolith. The API, durable coordinator,
typed evidence model, deterministic scoring engine, and React dashboard live in
one repository and one SQLite-backed application. Student C source is treated
as hostile input and is never executed in the FastAPI process or directly on
the host.

```mermaid
flowchart TB
    OP["Single AutoGrader Dashboard"] --> UI["React + TypeScript + Vite"]
    UI --> API["FastAPI"]
    API --> AS["Assignment & Version Service"]
    API --> ORCH["Python Evaluation Coordinator"]
    AS --> DB[("SQLite")]
    ORCH --> DB

    subgraph AG["Five logical roles"]
      A1["1. Assignment understanding & test design"]
      A2["2. Solution, compliance & complexity"]
      A3["3. Similarity & originality evidence"]
      A4["4. Feedback & report"]
      A5["5. Coordinator state machine"]
    end
    AS --> A1
    ORCH --> A2
    ORCH --> A3
    ORCH --> A4
    ORCH --> A5
    A1 --> LLM["Optional one-model Ollama client"]
    A2 --> LLM
    A3 --> LLM
    A4 --> LLM

    subgraph TOOLS["Deterministic tools"]
      COMP["GCC C11 compile"]
      RUN["Bubblewrap Linux sandbox"]
      TEST["Validated test runner"]
      STAT["Local C tools / source analysis / sanitizers"]
      FP["Normalized fingerprints"]
      VALID["Evidence validation"]
      SCORE["Pure scoring engine"]
    end
    ORCH --> COMP --> RUN --> TEST --> VALID
    ORCH --> STAT --> VALID
    ORCH --> FP --> VALID
    A2 --> VALID
    A3 --> VALID
    VALID --> SCORE --> A4
    A4 --> DB
```

## Boundary responsibilities

- **API:** validates requests, persists durable objects, exposes polling and
  download routes, and never accepts a client path as a host filesystem path.
- **Assignment service:** validates instructor rules, calculates a stable hash,
  stores immutable versions, and blocks activation when score-affecting test
  oracles are not validated.
- **Coordinator:** owns legal evaluation transitions, progress, retries and
  partial-failure classification. It is role 5, not an LLM worker.
- **Sandbox adapter:** exposes a typed interface with a real Bubblewrap runner,
  an optional Docker adapter and a deterministic fake. The default Bubblewrap
  runner fails closed if the Linux namespace tool or GCC is unavailable.
- **Evidence layer:** stores tool observations and concise reasoning with source
  type, status, provenance and links to tests/criteria.
- **Scoring engine:** pure Python, no network or model calls, and no ability for
  model output to change weights or assign arbitrary points.
- **Dashboard:** one operator-facing workspace with assignment setup, upload,
  results, investigation, similarity review and health pages.

## Persistence

SQLite tables represent assignments, immutable versions, validated test cases,
batches, submissions, evaluation runs, evidence, scores, reports, similarity
findings and audit events. Source and report artifacts remain under the
configured application artifact directory; no public static route exposes them.
