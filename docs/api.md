# API quick reference

The backend exposes OpenAPI at `/docs` when running locally. All application
routes are under `/api`.

| Route | Purpose |
|---|---|
| `GET /api/health` | API liveness |
| `GET /api/health/dependencies` | Configured runner, GCC, Bubblewrap and Ollama readiness |
| `GET/POST /api/assignments` | List/create assignments |
| `GET /api/assignments/{id}` | Assignment and versions |
| `POST /api/assignments/{id}/prepare` | Create a new immutable prepared version |
| `POST /api/assignments/{id}/versions/{version}/activate` | Activate a validated version |
| `POST /api/assignments/{id}/batches` | Upload `.c` files for an active version |
| `POST /api/batches/{id}/evaluate` | Queue/idempotently start evaluation |
| `GET /api/batches/{id}/live` | Live batch progress, current/next stage and audit-backed activity |
| `GET /api/evaluations/{id}` | Poll a durable run |
| `GET /api/submissions/{id}/results` | Score, report and source summary |
| `GET /api/submissions/{id}/evidence` | Evidence-first findings and test output |
| `GET /api/similarity/findings` | Assignment-scoped review flags |
| `POST /api/similarity/findings/{id}/disposition` | Persist manual review disposition |
| `GET /api/reports/{id}/download?format=txt` | Download a student report |
| `GET /api/batches/{id}/export.csv` | Download aggregate CSV |

The dashboard polls `GET /api/batches/{id}/live` while a batch is queued or
running. The response includes `overall_progress`, queued/running/completed/
failed counts, each run's `current_stage_label`, `current_detail`,
`next_stage_label`, and recent stage events. A batch is simply a group of one or
more student `.c` submissions evaluated against the same active assignment
version; it is not a grade or a student account.

## Create a version

```json
{
  "name": "Add two integers",
  "problem_statement": "Read two integers and print their sum followed by a newline.",
  "rules": {
    "time_limit_s": 1,
    "memory_limit_mb": 64,
    "metrics": [
      {"name": "correctness", "analyzer": "io_tests", "weight": 1.0,
       "scoring": {"mode": "test_ratio"}}
    ],
    "tests": [
      {"id": "sample", "input": "7 5\n", "expected_output": "12\n",
       "rationale": "statement sample", "provenance": "problem_statement",
       "status": "validated"}
    ]
  }
}
```

The rules are instructor-owned. Model-generated candidates, missing expected
behavior and unresolved contradictory policies are not silently activated.
