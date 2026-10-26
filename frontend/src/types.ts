export type Assignment = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
};

export type Criterion = {
  id: string;
  name: string;
  analyzer: string;
  weight: number;
  description: string;
  params: Record<string, unknown>;
  scoring_mode: string;
  missing_evidence: string;
  max_points: number;
};

export type TestCase = {
  id: string;
  input: string;
  expected_output: string | null;
  expected_behavior: string | null;
  comparator: string;
  rationale: string;
  provenance: string;
  status: string;
  requirement_id: string | null;
  score_affecting: boolean;
  validation_note: string | null;
  metadata: Record<string, unknown>;
};

export type AssignmentSpec = {
  schema_version: string;
  requirements: Array<Record<string, unknown>>;
  constraints: Record<string, unknown>;
  criteria: Criterion[];
  tests: TestCase[];
  ambiguities: Array<{ id: string; severity: string; message: string }>;
  summary: string;
  provenance: Record<string, unknown>;
};

export type AssignmentVersion = {
  id: string;
  assignment_id: string;
  version_number: number;
  status: string;
  version_hash: string;
  created_at: string;
  activated_at: string | null;
  spec: AssignmentSpec | null;
};

export type Batch = {
  id: string;
  assignment_version_id: string;
  status: string;
  summary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type LiveStageEvent = {
  id: string;
  event_type: string;
  state: string | null;
  stage: string | null;
  stage_label: string | null;
  detail: string | null;
  progress: number | null;
  created_at: string;
};

export type LiveEvaluation = {
  id: string;
  submission_id: string;
  submission_label: string;
  state: string;
  progress: number;
  current_stage: string | null;
  current_stage_label: string;
  current_detail: string | null;
  next_stage: string | null;
  next_stage_label: string | null;
  attempt: number;
  error_summary: string | null;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
  stage_history: LiveStageEvent[];
};

export type BatchLive = {
  batch: Batch;
  total_submissions: number;
  queued: number;
  running: number;
  completed: number;
  needs_review: number;
  failed: number;
  cancelled: number;
  overall_progress: number;
  last_updated_at: string;
  runs: LiveEvaluation[];
  active_runs: LiveEvaluation[];
  recent_events: LiveStageEvent[];
};

export type Submission = {
  id: string;
  batch_id: string;
  assignment_version_id: string;
  label: string;
  original_filename: string;
  content_hash: string;
  source_size: number;
  status: string;
  created_at: string;
};

export type Evaluation = {
  id: string;
  submission_id: string;
  assignment_version_id: string;
  state: string;
  progress: number;
  current_stage: string | null;
  attempt: number;
  error_summary: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CriterionScore = {
  criterion_id: string;
  name: string;
  weight: number;
  points: number | null;
  contribution: number | null;
  status: string;
  reason: string;
  evidence_ids: string[];
};

export type Score = {
  total_score: number | null;
  finalized: boolean;
  scoring_rule_version: string;
  criteria: CriterionScore[];
  calculation_trace: Record<string, unknown>;
};

export type Evidence = {
  id: string;
  assignment_version_id: string;
  submission_id: string;
  run_id: string;
  source_type: string;
  requirement_id: string | null;
  rubric_criterion_id: string | null;
  test_id: string | null;
  status: string;
  summary: string;
  details: Record<string, unknown>;
  source_location: Record<string, unknown> | null;
  input: string | null;
  expected_output: string | null;
  actual_output: string | null;
  provenance: Record<string, unknown>;
  created_at: string;
};

export type SubmissionResult = {
  submission: Submission;
  evaluation: Evaluation | null;
  score: Score | null;
  report: {
    id: string;
    run_id: string;
    report: Record<string, unknown>;
    created_at: string;
  } | null;
  source_content: string | null;
};

export type SimilarityFinding = {
  id: string;
  assignment_version_id: string;
  left_submission_id: string;
  right_submission_id: string;
  score: number;
  method: string;
  details: Record<string, unknown>;
  review_status: string;
  disposition: string | null;
  created_at: string;
};

export type Dependency = {
  name: string;
  available: boolean;
  detail: string;
  version?: string | null;
};
