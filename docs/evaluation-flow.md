# Evaluation flow

```mermaid
flowchart TD
    A[Create assignment] --> B[Validate problem + JSON rules]
    B --> C[Agent 1: extract requirements and propose candidate tests]
    C --> D[Record typed assignment spec and test provenance]
    D --> E{Score-affecting ambiguity?}
    E -- Yes --> F[needs_review; block activation]
    E -- No --> G[Activate version]
    F --> H[Operator edits or explicitly approves tests]
    H --> C
    G --> I[Upload one or more .c files]
    I --> J[Create durable evaluation runs]
    J --> K[Compile in Bubblewrap sandbox]
    J --> L[Source/static checks]
    J --> M[Agent 2: solution/compliance/complexity review]
    J --> N[Agent 3: review selected similarity candidates]
    K --> O[Run only validated executable tests]
    L --> P[Typed evidence]
    M --> P
    N --> P
    O --> P
    P --> Q{Missing or uncertain scoring evidence?}
    Q -- Yes --> R[needs_review; no silent zero]
    Q -- No --> S[Pure deterministic score]
    S --> T[Agent 4: evidence-linked feedback]
    R --> T
    T --> U[Persist report + audit trail]
```

The UI reads persisted run and audit events through
`GET /api/batches/{id}/live`. While a run is active it shows the current stage,
the next stage, per-submission progress and recent activity. The production
Linux path uses the real Bubblewrap runner; the fake runner is limited to
automated tests.

## Run states

`queued → preparing → compiling → testing → analyzing → validating_evidence →
scoring → reporting → completed` is the normal path. `needs_review`, `failed`,
and `cancelled` are explicit terminal or operator-action states. Illegal
transitions are rejected by the state machine and covered by unit tests.

`requires_review` is reserved for missing or uncertain score-affecting evidence.
Non-scoring observations from local analysis tools, similarity comparison and
the advisory LLM agents use `review_signal`: they remain visible for instructor
inspection but do not block or change a finalized grade. Agent 4 receives the
final deterministic score and can only write validated feedback around it.

## No-reference-solution policy

AutoGrader does not request, generate, or compare against a hidden reference
program. Executable expected output must come from an instructor-provided
example/rule or another explicitly justified, validated oracle. A behavior-only
candidate or an unverified model proposal cannot affect a score. If an
assignment is underspecified, the version remains visible as needing review.
