import type {
  Assignment,
  AssignmentVersion,
  Batch,
  BatchLive,
  Dependency,
  Evaluation,
  Evidence,
  SimilarityFinding,
  Submission,
  SubmissionResult,
} from "../types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : JSON.stringify(payload?.detail ?? response.statusText);
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; service: string; version: string }>("/health"),
  dependencies: () =>
    request<{ dependencies: Dependency[]; configured_runner: string }>("/health/dependencies"),
  assignments: () => request<Assignment[]>("/assignments"),
  assignment: (id: string) =>
    request<
      Assignment & {
        problem_statement: string;
        rules: Record<string, unknown>;
        versions: AssignmentVersion[];
      }
    >(`/assignments/${id}`),
  createAssignment: (payload: {
    name: string;
    problem_statement: string;
    rules: Record<string, unknown>;
  }) =>
    request<Assignment>("/assignments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  prepare: (
    id: string,
    payload?: { name: string; problem_statement: string; rules: Record<string, unknown> },
  ) =>
    request<{ version: AssignmentVersion; warnings: string[] }>(`/assignments/${id}/prepare`, {
      method: "POST",
      ...(payload
        ? {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          }
        : {}),
    }),
  activate: (id: string, version: number) =>
    request<AssignmentVersion>(`/assignments/${id}/versions/${version}/activate`, {
      method: "POST",
    }),
  createBatch: async (assignmentId: string, version: number, files: File[]) => {
    const form = new FormData();
    form.append("version_number", String(version));
    files.forEach((file) => form.append("files", file));
    return request<Batch>(`/assignments/${assignmentId}/batches`, { method: "POST", body: form });
  },
  batchSubmissions: (id: string) => request<Submission[]>(`/batches/${id}/submissions`),
  evaluate: (id: string) => request<Evaluation[]>(`/batches/${id}/evaluate`, { method: "POST" }),
  batch: (id: string) => request<Batch>(`/batches/${id}`),
  batchLive: (id: string) => request<BatchLive>(`/batches/${id}/live`),
  evaluations: () => request<Evaluation[]>("/evaluations"),
  evaluation: (id: string) => request<Evaluation>(`/evaluations/${id}`),
  result: (id: string) => request<SubmissionResult>(`/submissions/${id}/results`),
  evidence: (id: string) => request<Evidence[]>(`/submissions/${id}/evidence`),
  similarity: () => request<SimilarityFinding[]>("/similarity/findings"),
  disposition: (id: string, disposition: string) =>
    request<SimilarityFinding>(`/similarity/findings/${id}/disposition`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disposition }),
    }),
};

export function reportDownloadUrl(reportId: string, format: "txt" | "json" = "txt"): string {
  return `${API_URL}/reports/${reportId}/download?format=${format}`;
}
