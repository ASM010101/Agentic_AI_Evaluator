import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const assignment = {
  id: "assignment-1",
  name: "Demo assignment",
  created_at: "2026-10-24T00:00:00Z",
  updated_at: "2026-10-24T00:00:00Z",
};

const spec = {
  schema_version: "1.0",
  requirements: [],
  constraints: {},
  criteria: [
    {
      id: "correctness",
      name: "Correctness",
      analyzer: "io_tests",
      weight: 1,
      description: "",
      params: {},
      scoring_mode: "test_ratio",
      missing_evidence: "needs_review",
      max_points: 100,
    },
  ],
  tests: [
    {
      id: "sample",
      input: "1 1\n",
      expected_output: "2\n",
      expected_behavior: null,
      comparator: "trim_trailing_whitespace",
      rationale: "sample",
      provenance: "problem_statement",
      status: "validated",
      requirement_id: "REQ-PROBLEM",
      score_affecting: true,
      validation_note: null,
      metadata: {},
    },
  ],
  ambiguities: [],
  summary: "1 criterion and 1 validated test.",
  provenance: {},
};

const preparedVersion = {
  id: "version-1",
  assignment_id: assignment.id,
  version_number: 1,
  status: "prepared",
  version_hash: "hash-1",
  created_at: "2026-10-24T00:00:00Z",
  activated_at: null,
  spec,
};

const activeVersion = {
  ...preparedVersion,
  status: "active",
  activated_at: "2026-10-24T00:01:00Z",
};
const submission = {
  id: "submission-1",
  batch_id: "batch-1",
  assignment_version_id: activeVersion.id,
  label: "correct.c",
  original_filename: "correct.c",
  content_hash: "abcdef1234567890",
  source_size: 33,
  status: "completed",
  created_at: "2026-10-24T00:00:00Z",
};
const batch = {
  id: "batch-1",
  assignment_version_id: activeVersion.id,
  status: "completed",
  summary: { total: 1, completed: 1 },
  created_at: "2026-10-24T00:00:00Z",
  updated_at: "2026-10-24T00:02:00Z",
};
const live = {
  batch,
  total_submissions: 1,
  queued: 0,
  running: 0,
  completed: 1,
  needs_review: 0,
  failed: 0,
  cancelled: 0,
  overall_progress: 100,
  last_updated_at: "2026-10-24T00:02:00Z",
  runs: [
    {
      id: "run-1",
      submission_id: submission.id,
      submission_label: submission.label,
      state: "completed",
      progress: 100,
      current_stage: "completed",
      current_stage_label: "Completed",
      next_stage: null,
      next_stage_label: null,
      attempt: 1,
      error_summary: null,
      started_at: "2026-10-24T00:01:00Z",
      completed_at: "2026-10-24T00:02:00Z",
      updated_at: "2026-10-24T00:02:00Z",
      stage_history: [],
    },
  ],
  active_runs: [],
  recent_events: [],
};
const evaluation = {
  id: "run-1",
  submission_id: submission.id,
  assignment_version_id: activeVersion.id,
  state: "completed",
  progress: 100,
  current_stage: "completed",
  attempt: 1,
  error_summary: null,
  started_at: "2026-10-24T00:01:00Z",
  completed_at: "2026-10-24T00:02:00Z",
  created_at: "2026-10-24T00:01:00Z",
  updated_at: "2026-10-24T00:02:00Z",
};
const evidence = [
  {
    id: "evidence-1",
    assignment_version_id: activeVersion.id,
    submission_id: submission.id,
    run_id: evaluation.id,
    source_type: "test_runner",
    requirement_id: "REQ-PROBLEM",
    rubric_criterion_id: "correctness",
    test_id: "sample",
    status: "fail",
    summary: "Test sample failed.",
    details: {},
    source_location: null,
    input: "1 1\n",
    expected_output: "2\n",
    actual_output: "0\n",
    provenance: {},
    created_at: "2026-10-24T00:02:00Z",
  },
];
const result = {
  submission,
  evaluation,
  score: {
    total_score: 0,
    finalized: true,
    scoring_rule_version: "deterministic-v1",
    criteria: [
      {
        criterion_id: "correctness",
        name: "Correctness",
        weight: 1,
        points: 0,
        contribution: 0,
        status: "fail",
        reason: "0/1 tests passed",
        evidence_ids: ["evidence-1"],
      },
    ],
    calculation_trace: {},
  },
  report: {
    id: "report-1",
    run_id: evaluation.id,
    report: { confirmed_failures: evidence },
    created_at: "2026-10-24T00:02:00Z",
  },
  source_content: "#include <stdio.h>\nint main(void) { return 0; }",
};
const similarity = {
  id: "finding-1",
  assignment_version_id: activeVersion.id,
  left_submission_id: "left-12345678",
  right_submission_id: "right-12345678",
  score: 0.94,
  method: "normalized_token_sequence_v1",
  details: { left_excerpt: "int IDENT return", threshold: 0.85 },
  review_status: "flagged",
  disposition: null,
  created_at: "2026-10-24T00:03:00Z",
};

function jsonResponse(payload: unknown, ok = true): Response {
  return { ok, status: ok ? 200 : 422, json: async () => payload } as Response;
}

describe("dashboard workflows", () => {
  beforeEach(() => {
    window.location.hash = "#/overview";
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/health/dependencies"))
          return Promise.resolve(
            jsonResponse({
              dependencies: [
                { name: "docker", available: true, detail: "ready" },
                { name: "ollama", available: false, detail: "optional" },
              ],
            }),
          );
        if (url.endsWith("/assignments") && method === "GET")
          return Promise.resolve(jsonResponse([assignment]));
        if (url.endsWith("/assignments") && method === "POST")
          return Promise.resolve(jsonResponse(assignment));
        if (url.includes("/assignments/assignment-1") && url.endsWith("/prepare"))
          return Promise.resolve(jsonResponse({ version: preparedVersion, warnings: [] }));
        if (url.includes("/versions/1/activate"))
          return Promise.resolve(jsonResponse(activeVersion));
        if (url.endsWith("/assignments/assignment-1"))
          return Promise.resolve(
            jsonResponse({
              ...assignment,
              problem_statement: "Demo",
              rules: {},
              versions: [preparedVersion],
            }),
          );
        if (url.includes("/batches/batch-1/submissions"))
          return Promise.resolve(jsonResponse([submission]));
        if (url.endsWith("/batches/batch-1/live")) return Promise.resolve(jsonResponse(live));
        if (url.includes("/batches/batch-1/evaluate"))
          return Promise.resolve(jsonResponse([evaluation]));
        if (url.endsWith("/batches/batch-1")) return Promise.resolve(jsonResponse(batch));
        if (url.endsWith("/evaluations")) return Promise.resolve(jsonResponse([evaluation]));
        if (url.includes("/evaluations/run-1")) return Promise.resolve(jsonResponse(evaluation));
        if (url.includes("/submissions/submission-1/results"))
          return Promise.resolve(jsonResponse(result));
        if (url.includes("/submissions/submission-1/evidence"))
          return Promise.resolve(jsonResponse(evidence));
        if (url.endsWith("/similarity/findings"))
          return Promise.resolve(jsonResponse([similarity]));
        if (url.includes("/similarity/findings/finding-1/disposition"))
          return Promise.resolve(
            jsonResponse({
              ...similarity,
              review_status: "reviewed",
              disposition: "benign_similarity",
            }),
          );
        if (url.includes("/assignments/assignment-1/batches"))
          return Promise.resolve(jsonResponse(batch));
        if (url.endsWith("/health")) return Promise.resolve(jsonResponse({ status: "ok" }));
        return Promise.resolve(jsonResponse({}));
      }),
    );
  });

  it("walks assignment, upload, investigation, similarity, runs and settings pages", async () => {
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: /Grade C submissions/i }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Assignments/ }));
    expect(await screen.findByRole("heading", { name: "Assignments" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Demo assignment/ }));
    await waitFor(() => expect(screen.getByText("Version 1")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Prepare new version/ }));
    fireEvent.click(screen.getByRole("button", { name: /Activate/ }));

    fireEvent.click(screen.getByRole("button", { name: /Submissions & Results/ }));
    expect(
      await screen.findByRole("heading", { name: /Submissions & Results/i }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Assignment"), { target: { value: assignment.id } });
    await waitFor(() => expect(screen.getByLabelText("Active version")).toHaveValue("1"));
    const fileInput = document.querySelector('input[type="file"]');
    if (!(fileInput instanceof HTMLInputElement)) throw new Error("file input was not rendered");
    fireEvent.change(fileInput, {
      target: { files: [new File(["int main(void) {}"], "correct.c", { type: "text/plain" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create batch" }));
    expect(await screen.findByText("correct.c")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Evaluate batch/ }));
    expect(await screen.findByRole("button", { name: "Inspect" })).toBeInTheDocument();
    expect(await screen.findByText("Live evaluation monitor")).toBeInTheDocument();
    expect(screen.getByText("Review the results")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect" }));
    expect(await screen.findByRole("heading", { name: "correct.c" })).toBeInTheDocument();
    expect(screen.getByText("Test sample failed.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Back to results/ }));

    fireEvent.click(screen.getByRole("button", { name: /Similarity Review/ }));
    expect(await screen.findByRole("heading", { name: "Similarity Review" })).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue("Choose disposition"), {
      target: { value: "benign_similarity" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Evaluation Runs/ }));
    expect(await screen.findByRole("heading", { name: "Evaluation Runs" })).toBeInTheDocument();
    expect(screen.getAllByText("completed").length).toBeGreaterThanOrEqual(1);
    fireEvent.click(screen.getByRole("button", { name: /Settings & Health/ }));
    expect(await screen.findByRole("heading", { name: "Settings & Health" })).toBeInTheDocument();
    expect(screen.getByText("GCC / C11")).toBeInTheDocument();
  });

  it("renders an API error in the operator workspace", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse({ detail: "backend unavailable" }, false))),
    );
    render(<App />);
    expect(await screen.findByText(/backend unavailable/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Settings & Health/ }));
    expect(await screen.findByRole("heading", { name: "Settings & Health" })).toBeInTheDocument();
  });
});
