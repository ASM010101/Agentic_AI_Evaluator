import { useCallback, useEffect, useState, type ReactElement, type ReactNode } from "react";
import { api, reportDownloadUrl } from "./lib/api";
import type {
  Assignment,
  AssignmentVersion,
  BatchLive,
  Dependency,
  Evaluation,
  Evidence,
  LiveEvaluation,
  SimilarityFinding,
  Submission,
  SubmissionResult,
} from "./types";

type Page = "overview" | "assignments" | "submissions" | "similarity" | "runs" | "settings";

const navItems: Array<{ id: Page; label: string; icon: string; description: string }> = [
  { id: "overview", label: "Overview", icon: "◈", description: "Queue health and activity" },
  {
    id: "assignments",
    label: "Assignments",
    icon: "□",
    description: "Rules and immutable versions",
  },
  {
    id: "submissions",
    label: "Submissions & Results",
    icon: "↥",
    description: "Upload, evaluate and inspect",
  },
  {
    id: "similarity",
    label: "Similarity Review",
    icon: "⌘",
    description: "Evidence-backed overlap flags",
  },
  { id: "runs", label: "Evaluation Runs", icon: "◷", description: "Durable lifecycle status" },
  {
    id: "settings",
    label: "Settings & Health",
    icon: "⚙",
    description: "Sandbox and model readiness",
  },
];

const exampleRules = JSON.stringify(
  {
    problem: "add_two_integers",
    time_limit_s: 1,
    memory_limit_mb: 64,
    metrics: [
      { name: "correctness", analyzer: "io_tests", weight: 0.7, scoring: { mode: "test_ratio" } },
      {
        name: "readability",
        analyzer: "readability",
        weight: 0.3,
        scoring: { mode: "evidence_score" },
      },
    ],
    tests: [
      {
        id: "sample",
        input: "7 5\n",
        expected_output: "12\n",
        rationale: "Instructor-provided sample",
        provenance: "problem_statement",
        status: "validated",
      },
      {
        id: "zero",
        input: "0 0\n",
        expected_output: "0\n",
        rationale: "Explicit boundary case",
        provenance: "explicit_rule",
        status: "validated",
      },
    ],
  },
  null,
  2,
);

function routeFromHash(): { page: Page; id?: string } {
  const value = window.location.hash.replace(/^#\/?/, "");
  if (value.startsWith("submissions/")) return { page: "submissions", id: value.split("/")[1] };
  const page = value.split("/")[0] as Page;
  return { page: navItems.some((item) => item.id === page) ? page : "overview" };
}

function navigate(page: Page, id?: string): void {
  window.location.hash = id ? `#/submissions/${id}` : `#/${page}`;
}

function Badge({ value }: { value: string }): ReactElement {
  const tone =
    value.includes("fail") || value === "failed"
      ? "danger"
      : value.includes("review")
        ? "warning"
        : value === "completed" || value === "active" || value === "pass"
          ? "success"
          : "neutral";
  return <span className={`badge badge-${tone}`}>{value.replaceAll("_", " ")}</span>;
}

const pipelineStages = [
  { key: "queued", label: "Queued" },
  { key: "preparing", label: "Preparing" },
  { key: "compiling", label: "Compile" },
  { key: "validated_tests", label: "Tests" },
  { key: "source_and_safety_analysis", label: "Source analysis" },
  { key: "evidence_validation", label: "Evidence" },
  { key: "scoring", label: "Score" },
  { key: "reporting", label: "Report" },
  { key: "completed", label: "Done" },
];

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function stagePosition(run: LiveEvaluation): number {
  const key = run.current_stage ?? (run.state === "queued" ? "queued" : run.state);
  const position = pipelineStages.findIndex((stage) => stage.key === key);
  return position >= 0 ? position : run.state === "completed" ? pipelineStages.length - 1 : 0;
}

function LivePipeline({ run }: { run: LiveEvaluation }): ReactElement {
  const currentPosition = stagePosition(run);
  const isTerminal = ["completed", "failed", "needs_review", "cancelled"].includes(run.state);
  return (
    <div className="live-pipeline" aria-label={`Evaluation pipeline for ${run.submission_label}`}>
      <div className="pipeline-track">
        {pipelineStages.map((stage, index) => {
          const complete = run.state === "completed" ? true : index < currentPosition;
          const current = !isTerminal && index === currentPosition;
          return (
            <div
              className={`pipeline-step ${complete ? "complete" : ""} ${current ? "current" : ""}`}
              key={stage.key}
            >
              <span className="pipeline-dot">{complete ? "✓" : index + 1}</span>
              <small>{stage.label}</small>
            </div>
          );
        })}
      </div>
      <div className="pipeline-caption">
        <span>
          <strong>{run.current_stage_label}</strong>
          {run.current_detail ? ` · ${run.current_detail}` : ""}
          {run.next_stage_label ? ` · next: ${run.next_stage_label}` : ""}
        </span>
        <span>{run.progress}%</span>
      </div>
    </div>
  );
}

function LiveBatchMonitor({
  live,
  onRefresh,
}: {
  live: BatchLive;
  onRefresh: () => void;
}): ReactElement {
  const finalized = live.completed + live.failed + live.needs_review + live.cancelled;
  const hasActiveWork = live.queued + live.running > 0;
  const readyToStart = live.batch.status === "created" && live.total_submissions > 0;
  return (
    <Panel
      title="Live evaluation monitor"
      eyebrow={hasActiveWork ? "UPDATING AUTOMATICALLY" : "LATEST RUN STATE"}
      action={
        <div className="live-panel-actions">
          <span className="last-updated">Updated {formatTime(live.last_updated_at)}</span>
          <button className="button button-ghost" onClick={onRefresh}>
            Refresh now
          </button>
        </div>
      }
    >
      <div className="live-overview">
        <div className="live-progress-card">
          <div className="live-progress-heading">
            <div>
              <strong>{live.overall_progress}% overall progress</strong>
              <small>
                {finalized} of {live.total_submissions} submissions finished
              </small>
            </div>
            <Badge value={live.batch.status} />
          </div>
          <div className="large-progress-line">
            <span style={{ width: `${live.overall_progress}%` }} />
          </div>
          <div className="live-counts">
            <span>
              <b>{live.queued}</b> queued
            </span>
            <span>
              <b>{live.running}</b> running
            </span>
            <span>
              <b>{live.completed}</b> completed
            </span>
            <span>
              <b>{live.failed + live.needs_review}</b> attention
            </span>
          </div>
        </div>
        <div className="live-next-card">
          <span className="stat-label">WHAT HAPPENS NEXT</span>
          {live.active_runs[0] ? (
            <>
              <strong>{live.active_runs[0].next_stage_label ?? "Finish this run"}</strong>
              <small>
                {live.active_runs[0].submission_label} is currently in{" "}
                {live.active_runs[0].current_stage_label.toLowerCase()}.
              </small>
            </>
          ) : readyToStart ? (
            <>
              <strong>Evaluate this batch</strong>
              <small>Uploaded files are ready. Click “Evaluate batch” to start the pipeline.</small>
            </>
          ) : hasActiveWork ? (
            <>
              <strong>Waiting for a worker</strong>
              <small>The queued submission will begin with preparation.</small>
            </>
          ) : (
            <>
              <strong>Review the results</strong>
              <small>Open a submission below to inspect evidence and download its report.</small>
            </>
          )}
        </div>
      </div>

      <div className="live-section-heading">
        <strong>
          {hasActiveWork ? "Currently running" : readyToStart ? "Ready to start" : "Run summary"}
        </strong>
        <span>
          {hasActiveWork
            ? `${live.active_runs.length} active run(s)`
            : readyToStart
              ? "No evaluation started"
              : "No work is running"}
        </span>
      </div>
      {hasActiveWork ? (
        <div className="live-run-list">
          {live.active_runs.map((run) => (
            <div className="live-run-card" key={run.id}>
              <div className="live-run-heading">
                <div>
                  <strong>{run.submission_label}</strong>
                  <small>
                    {run.state.replaceAll("_", " ")} · attempt {run.attempt} · updated{" "}
                    {formatTime(run.updated_at)}
                  </small>
                </div>
                <Badge value={run.state} />
              </div>
              <LivePipeline run={run} />
              {run.error_summary && <div className="live-run-error">{run.error_summary}</div>}
            </div>
          ))}
        </div>
      ) : readyToStart ? (
        <div className="ready-to-start">
          <span className="ready-icon">→</span>
          <div>
            <strong>Files uploaded successfully.</strong>
            <small>
              The next step is to start evaluation. Your progress will appear here as each stage
              completes.
            </small>
          </div>
        </div>
      ) : (
        <div className="live-finished-list">
          {live.runs.map((run) => (
            <div className="finished-run-row" key={run.id}>
              <span className={`health-dot ${run.state === "completed" ? "online" : "offline"}`} />
              <strong>{run.submission_label}</strong>
              <Badge value={run.state} />
              <small>
                {run.completed_at ? `finished ${formatTime(run.completed_at)}` : "not started"}
              </small>
            </div>
          ))}
        </div>
      )}

      {live.recent_events.length > 0 && (
        <details className="live-events">
          <summary>Recent activity ({live.recent_events.length})</summary>
          <div className="event-list">
            {live.recent_events.slice(0, 8).map((event) => (
              <div className="event-row" key={event.id}>
                <span className="event-time">{formatTime(event.created_at)}</span>
                <span>
                  <strong>{event.stage_label ?? event.stage ?? event.event_type}</strong>
                  {event.detail && <small> · {event.detail}</small>}
                  {event.progress != null && <small> · {event.progress}%</small>}
                </span>
                {event.state && <Badge value={event.state} />}
              </div>
            ))}
          </div>
        </details>
      )}
    </Panel>
  );
}

function Panel({
  title,
  eyebrow,
  action,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}): ReactElement {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function EmptyState({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
}): ReactElement {
  return (
    <div className="empty-state">
      <div className="empty-mark">∅</div>
      <h3>{title}</h3>
      <p>{detail}</p>
      {action}
    </div>
  );
}

function OverviewPage(): ReactElement {
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [dependencies, setDependencies] = useState<Dependency[]>([]);
  const [configuredRunner, setConfiguredRunner] = useState("bubblewrap");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([api.assignments(), api.dependencies()])
      .then(([nextAssignments, health]) => {
        setAssignments(nextAssignments);
        setDependencies(health.dependencies);
        setConfiguredRunner(health.configured_runner || "bubblewrap");
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);
  const available = dependencies.filter((item) => item.available).length;
  return (
    <div className="page-stack">
      <div className="hero-grid">
        <div className="hero-copy">
          <div className="eyebrow">LOCAL-FIRST EVALUATION CONTROL ROOM</div>
          <h1>Grade C submissions with evidence, not guesswork.</h1>
          <p>
            Create an immutable assignment version, validate its tests, run submissions in a
            constrained sandbox, and inspect every score from one workspace.
          </p>
          <div className="hero-actions">
            <button className="button button-primary" onClick={() => navigate("assignments")}>
              Create assignment <span>→</span>
            </button>
            <button className="button button-secondary" onClick={() => navigate("submissions")}>
              Upload a batch
            </button>
          </div>
        </div>
        <div className="hero-orbit" aria-hidden="true">
          <div className="orbit-ring ring-one" />
          <div className="orbit-ring ring-two" />
          <div className="orbit-core">
            <span>AG</span>
            <small>evidence</small>
          </div>
        </div>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}
      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Assignments</span>
          <strong>{assignments.length}</strong>
          <small>versioned problem spaces</small>
        </div>
        <div className="stat-card">
          <span className="stat-label">Runtime readiness</span>
          <strong>
            {available}/{dependencies.length || 3}
          </strong>
          <small>dependencies available</small>
        </div>
        <div className="stat-card">
          <span className="stat-label">Scoring policy</span>
          <strong>Deterministic</strong>
          <small>immutable rubric + evidence</small>
        </div>
        <div className="stat-card">
          <span className="stat-label">Isolation</span>
          <strong>Fail closed</strong>
          <small>{configuredRunner} Linux sandbox for real C runs</small>
        </div>
      </div>
      <div className="two-column">
        <Panel title="Start here" eyebrow="FIRST RUN">
          <div className="step-list">
            <div className="step">
              <span>01</span>
              <div>
                <strong>Define the assignment</strong>
                <p>Write the statement and provide instructor-owned JSON rules.</p>
              </div>
            </div>
            <div className="step">
              <span>02</span>
              <div>
                <strong>Validate the version</strong>
                <p>Review tests, oracle provenance and any material ambiguity before activation.</p>
              </div>
            </div>
            <div className="step">
              <span>03</span>
              <div>
                <strong>Evaluate a cohort</strong>
                <p>
                  Upload several `.c` files and follow durable evaluation states through to reports.
                </p>
              </div>
            </div>
          </div>
        </Panel>
        <Panel title="Operating principles" eyebrow="TRUST MODEL">
          <ul className="principle-list">
            <li>
              <span className="principle-dot blue" />
              No reference solution dependency; expected outputs come from validated specification
              evidence.
            </li>
            <li>
              <span className="principle-dot green" />
              Scores are pure calculations over an immutable version and typed evidence.
            </li>
            <li>
              <span className="principle-dot amber" />
              Similarity is a human-review flag, never an automatic penalty.
            </li>
            <li>
              <span className="principle-dot red" />
              The configured Linux sandbox must be available; there is no host execution fallback.
            </li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}

function AssignmentsPage(): ReactElement {
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [selected, setSelected] = useState<(Assignment & { versions: AssignmentVersion[] }) | null>(
    null,
  );
  const [name, setName] = useState("Add two integers");
  const [problem, setProblem] = useState(
    "Read two integers and print their sum followed by a newline.",
  );
  const [rulesText, setRulesText] = useState(exampleRules);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(
    () =>
      api
        .assignments()
        .then(setAssignments)
        .catch((reason: Error) => setError(reason.message)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  const create = async (): Promise<void> => {
    setError(null);
    setMessage(null);
    try {
      const rules = JSON.parse(rulesText) as Record<string, unknown>;
      const assignment = await api.createAssignment({ name, problem_statement: problem, rules });
      const prepared = await api.prepare(assignment.id);
      setMessage(
        `Created version ${prepared.version.version_number}. Review its validation state before activation.`,
      );
      setSelected(await api.assignment(assignment.id));
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create assignment");
    }
  };
  const selectAssignment = async (id: string): Promise<void> => {
    try {
      const detail = await api.assignment(id);
      setSelected(detail);
      setName(detail.name);
      setProblem(detail.problem_statement);
      setRulesText(JSON.stringify(detail.rules, null, 2));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load assignment");
    }
  };
  const prepare = async (): Promise<void> => {
    if (!selected) return;
    try {
      const rules = JSON.parse(rulesText) as Record<string, unknown>;
      const result = await api.prepare(selected.id, {
        name,
        problem_statement: problem,
        rules,
      });
      setMessage(`Prepared version ${result.version.version_number}.`);
      await selectAssignment(selected.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not prepare version");
    }
  };
  const activate = async (version: AssignmentVersion): Promise<void> => {
    try {
      await api.activate(version.assignment_id, version.version_number);
      setMessage(`Version ${version.version_number} is now active.`);
      setSelected(await api.assignment(version.assignment_id));
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not activate version");
    }
  };
  return (
    <div className="page-stack">
      <div className="page-title-row">
        <div>
          <div className="eyebrow">ASSIGNMENT WORKSPACE</div>
          <h1>Assignments</h1>
          <p>Turn an instructor specification into an immutable, reviewable grading version.</p>
        </div>
        <Badge value="no hidden rubric" />
      </div>
      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-danger">{error}</div>}
      <div className="two-column assignment-layout">
        <Panel
          title="Create assignment"
          eyebrow="DRAFT → PREPARED → ACTIVE"
          action={<span className="tiny-label">JSON rules are source of truth</span>}
        >
          <div className="form-grid">
            <label>
              Short label
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label>
              Problem statement
              <textarea
                value={problem}
                onChange={(event) => setProblem(event.target.value)}
                rows={5}
              />
            </label>
            <label>
              JSON rules / rubric
              <textarea
                className="code-input"
                value={rulesText}
                onChange={(event) => setRulesText(event.target.value)}
                rows={20}
                spellCheck={false}
              />
            </label>
            <button className="button button-primary" onClick={() => void create()}>
              Create and prepare <span>→</span>
            </button>
          </div>
        </Panel>
        <div className="page-stack compact-stack">
          <Panel
            title="Saved assignments"
            eyebrow={`${assignments.length} WORKSPACE${assignments.length === 1 ? "" : "S"}`}
          >
            {assignments.length === 0 ? (
              <EmptyState
                title="No assignments yet"
                detail="Create the first assignment to start building a validated version."
              />
            ) : (
              <div className="assignment-list">
                {assignments.map((assignment) => (
                  <button
                    className={`assignment-row ${selected?.id === assignment.id ? "selected" : ""}`}
                    key={assignment.id}
                    onClick={() => void selectAssignment(assignment.id)}
                  >
                    <span className="assignment-mark">
                      {assignment.name.slice(0, 1).toUpperCase()}
                    </span>
                    <span>
                      <strong>{assignment.name}</strong>
                      <small>{new Date(assignment.updated_at).toLocaleString()}</small>
                    </span>
                    <span className="row-arrow">→</span>
                  </button>
                ))}
              </div>
            )}
          </Panel>
          {selected && (
            <Panel
              title={selected.name}
              eyebrow="VERSION HISTORY"
              action={
                <button className="button button-ghost" onClick={() => void prepare()}>
                  Prepare new version
                </button>
              }
            >
              <div className="version-list">
                {selected.versions.map((version) => (
                  <div className="version-row" key={version.id}>
                    <div>
                      <strong>Version {version.version_number}</strong>
                      <small>{version.spec?.summary ?? "No preparation summary"}</small>
                    </div>
                    <div className="version-actions">
                      <Badge value={version.status} />
                      {version.status === "prepared" && (
                        <button
                          className="button button-small"
                          onClick={() => void activate(version)}
                        >
                          Activate
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {selected.versions[0]?.spec && (
                <div className="spec-preview">
                  <div className="spec-header">
                    <strong>Preparation preview</strong>
                    <Badge
                      value={`${selected.versions[0].spec.tests.filter((test) => test.status === "validated").length} validated tests`}
                    />
                  </div>
                  <p>{selected.versions[0].spec.summary}</p>
                  {selected.versions[0].spec.ambiguities.map((item) => (
                    <div className="notice-line" key={item.id}>
                      <span>!</span>
                      {item.message}
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

function SubmissionsPage({ detailId }: { detailId?: string }): ReactElement {
  if (detailId) return <SubmissionDetail id={detailId} />;
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [versions, setVersions] = useState<AssignmentVersion[]>([]);
  const [assignmentId, setAssignmentId] = useState("");
  const [versionNumber, setVersionNumber] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [batch, setBatch] = useState<{
    id: string;
    status: string;
    summary: Record<string, unknown>;
  } | null>(null);
  const [live, setLive] = useState<BatchLive | null>(null);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [dependencies, setDependencies] = useState<Dependency[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([api.assignments(), api.dependencies()])
      .then(([nextAssignments, health]) => {
        setAssignments(nextAssignments);
        setDependencies(health.dependencies);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);
  useEffect(() => {
    if (!assignmentId) {
      setVersions([]);
      return;
    }
    api
      .assignment(assignmentId)
      .then((result) => {
        setVersions(result.versions);
        const active = result.versions.find((version) => version.status === "active");
        setVersionNumber(
          String(active?.version_number ?? result.versions[0]?.version_number ?? ""),
        );
      })
      .catch((reason: Error) => setError(reason.message));
  }, [assignmentId]);
  const batchId = batch?.id;
  const refresh = useCallback(async (): Promise<void> => {
    if (!batchId) return;
    try {
      const [nextLive, nextSubmissions, nextEvaluations] = await Promise.all([
        api.batchLive(batchId),
        api.batchSubmissions(batchId),
        api.evaluations(),
      ]);
      setLive(nextLive);
      setBatch(nextLive.batch);
      setSubmissions(nextSubmissions);
      setEvaluations(
        nextEvaluations.filter((item) =>
          nextSubmissions.some((submission) => submission.id === item.submission_id),
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not refresh batch");
    }
  }, [batchId]);
  useEffect(() => {
    if (!batchId || !live || live.queued + live.running === 0) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 1000);
    return () => window.clearInterval(timer);
  }, [batchId, live, refresh]);
  const upload = async (): Promise<void> => {
    setError(null);
    if (!assignmentId || !versionNumber || files.length === 0) {
      setError("Choose an assignment version and at least one .c file.");
      return;
    }
    try {
      const nextBatch = await api.createBatch(assignmentId, Number(versionNumber), files);
      setBatch(nextBatch);
      const [nextSubmissions, nextLive] = await Promise.all([
        api.batchSubmissions(nextBatch.id),
        api.batchLive(nextBatch.id),
      ]);
      setSubmissions(nextSubmissions);
      setLive(nextLive);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not upload batch");
    }
  };
  const evaluate = async (): Promise<void> => {
    if (!batch) return;
    try {
      setEvaluations(await api.evaluate(batch.id));
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start evaluation");
    }
  };
  return (
    <div className="page-stack">
      <div className="page-title-row">
        <div>
          <div className="eyebrow">COHORT EVALUATION</div>
          <h1>Submissions & Results</h1>
          <p>
            Upload multiple independent C files, then follow the evidence trail through scoring.
          </p>
        </div>
        {batch && <Badge value={batch.status} />}
      </div>
      {error && <div className="alert alert-danger">{error}</div>}
      <Panel title="Upload a batch" eyebrow="SAFE FILE INTAKE">
        <div className="readiness-strip">
          <span className="readiness-label">READY CHECK</span>
          {dependencies.length === 0 ? (
            <span className="muted">Checking configured dependencies…</span>
          ) : (
            dependencies.map((dependency) => (
              <span className="readiness-item" key={dependency.name}>
                <span className={`health-dot ${dependency.available ? "online" : "offline"}`} />
                {dependency.name}: {dependency.available ? "available" : "unavailable"}
              </span>
            ))
          )}
        </div>
        <div className="upload-grid">
          <label>
            Assignment
            <select value={assignmentId} onChange={(event) => setAssignmentId(event.target.value)}>
              <option value="">Select assignment</option>
              {assignments.map((assignment) => (
                <option key={assignment.id} value={assignment.id}>
                  {assignment.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Active version
            <select
              value={versionNumber}
              onChange={(event) => setVersionNumber(event.target.value)}
            >
              <option value="">Select version</option>
              {versions.map((version) => (
                <option key={version.id} value={version.version_number}>
                  v{version.version_number} · {version.status}
                </option>
              ))}
            </select>
          </label>
          <label className="file-drop">
            C source files
            <input
              type="file"
              accept=".c,text/x-c"
              multiple
              onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
            />
            <span>
              {files.length ? `${files.length} file(s) selected` : "Drop files here or browse"}
            </span>
          </label>
          <div className="upload-actions">
            <button className="button button-primary" onClick={() => void upload()}>
              Create batch
            </button>
            {batch && (
              <button
                className="button button-secondary"
                onClick={() => void evaluate()}
                disabled={batch.status === "evaluating"}
              >
                Evaluate batch <span>→</span>
              </button>
            )}
          </div>
        </div>
        {files.length > 0 && (
          <div className="file-chips">
            {files.map((file) => (
              <span key={`${file.name}-${file.size}`} className="file-chip">
                {file.name}
                <small>{Math.ceil(file.size / 1024)} KB</small>
              </span>
            ))}
          </div>
        )}
      </Panel>
      {live && <LiveBatchMonitor live={live} onRefresh={() => void refresh()} />}
      <Panel
        title="Consolidated results"
        eyebrow={batch ? `BATCH ${batch.id.slice(0, 8)}` : "NO ACTIVE BATCH"}
        action={
          batch && (
            <a
              className="button button-ghost"
              href={`http://127.0.0.1:8000/api/batches/${batch.id}/export.csv`}
            >
              Export CSV
            </a>
          )
        }
      >
        {submissions.length === 0 ? (
          <EmptyState
            title="Nothing to evaluate"
            detail="Upload a batch above. Results will remain persisted when the page refreshes."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Submission</th>
                  <th>Status</th>
                  <th>Evaluation</th>
                  <th>Progress</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {submissions.map((submission) => {
                  const evaluation = evaluations.find(
                    (item) => item.submission_id === submission.id,
                  );
                  return (
                    <tr key={submission.id}>
                      <td>
                        <strong>{submission.label}</strong>
                        <small>
                          {submission.original_filename} ·{" "}
                          {Math.ceil(submission.source_size / 1024)} KB
                        </small>
                      </td>
                      <td>
                        <Badge value={submission.status} />
                      </td>
                      <td>
                        {evaluation ? (
                          <Badge value={evaluation.state} />
                        ) : (
                          <span className="muted">not started</span>
                        )}
                      </td>
                      <td>
                        <div className="progress-line">
                          <span style={{ width: `${evaluation?.progress ?? 0}%` }} />
                        </div>
                        <small>{evaluation?.progress ?? 0}%</small>
                      </td>
                      <td>
                        <button
                          className="button button-small"
                          onClick={() => navigate("submissions", submission.id)}
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

function SubmissionDetail({ id }: { id: string }): ReactElement {
  const [result, setResult] = useState<SubmissionResult | null>(null);
  const [liveRun, setLiveRun] = useState<LiveEvaluation | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(
    () =>
      Promise.all([api.result(id), api.evidence(id)])
        .then(async ([nextResult, nextEvidence]) => {
          setResult(nextResult);
          setEvidence(nextEvidence);
          const live = await api.batchLive(nextResult.submission.batch_id);
          setLiveRun(live.runs.find((run) => run.submission_id === id) ?? null);
        })
        .catch((reason: Error) => setError(reason.message)),
    [id],
  );
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (!liveRun || ["completed", "failed", "needs_review", "cancelled"].includes(liveRun.state))
      return;
    const timer = window.setInterval(() => {
      void load();
    }, 1000);
    return () => window.clearInterval(timer);
  }, [liveRun, load]);
  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!result)
    return (
      <div className="loading-state">
        <span className="spinner" />
        Loading evidence workspace…
      </div>
    );
  const score = result.score;
  return (
    <div className="page-stack">
      <div className="back-row">
        <button className="button button-ghost" onClick={() => navigate("submissions")}>
          ← Back to results
        </button>
        <Badge value={result.evaluation?.state ?? "not started"} />
      </div>
      <div className="page-title-row">
        <div>
          <div className="eyebrow">INDIVIDUAL INVESTIGATION</div>
          <h1>{result.submission.label}</h1>
          <p>
            {result.submission.original_filename} · {result.submission.content_hash.slice(0, 16)}… ·
            version-bound evidence
          </p>
        </div>
        <div className="grade-lockup">
          <span>GRADE</span>
          <strong>{score?.total_score == null ? "—" : score.total_score.toFixed(1)}</strong>
          <small>{score?.finalized ? "/ 100" : "needs review"}</small>
        </div>
      </div>
      {result.evaluation?.error_summary && (
        <div className="alert alert-danger">{result.evaluation.error_summary}</div>
      )}
      {liveRun && (
        <Panel
          title="What is happening now"
          eyebrow={
            ["completed", "failed", "needs_review", "cancelled"].includes(liveRun.state)
              ? "RUN FINISHED"
              : "LIVE RUN MONITOR"
          }
          action={<span className="last-updated">Updated {formatTime(liveRun.updated_at)}</span>}
        >
          <div className="detail-live-heading">
            <div>
              <strong>{liveRun.current_stage_label}</strong>
              <small>
                {liveRun.current_detail ? `${liveRun.current_detail} ` : ""}
                {liveRun.next_stage_label
                  ? `Next: ${liveRun.next_stage_label}`
                  : liveRun.state === "completed"
                    ? "The report is ready to review."
                    : "Inspect the error or review state below."}
              </small>
            </div>
            <Badge value={liveRun.state} />
          </div>
          <LivePipeline run={liveRun} />
          {liveRun.stage_history.length > 0 && (
            <div className="mini-history">
              {liveRun.stage_history.slice(0, 6).map((event) => (
                <span key={event.id}>
                  {event.stage_label ?? event.stage} · {formatTime(event.created_at)}
                </span>
              ))}
            </div>
          )}
        </Panel>
      )}
      <div className="investigation-grid">
        <Panel title="Rubric breakdown" eyebrow="DETERMINISTIC SCORING">
          {!score ? (
            <EmptyState
              title="Score not available"
              detail="The run has not produced a score yet, or the sandbox failed closed."
            />
          ) : (
            <div className="rubric-list">
              {score.criteria.map((criterion) => (
                <div className="rubric-row" key={criterion.criterion_id}>
                  <div>
                    <strong>{criterion.name}</strong>
                    <small>{criterion.reason}</small>
                  </div>
                  <span className="rubric-points">
                    {criterion.contribution == null ? "—" : criterion.contribution.toFixed(2)}
                  </span>
                  <Badge value={criterion.status} />
                </div>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="Evidence summary" eyebrow={`${evidence.length} TYPED ITEMS`}>
          <div className="evidence-summary">
            <div>
              <strong>{evidence.filter((item) => item.status === "pass").length}</strong>
              <span>passed</span>
            </div>
            <div>
              <strong>{evidence.filter((item) => item.status === "fail").length}</strong>
              <span>failed</span>
            </div>
            <div>
              <strong>
                {
                  evidence.filter(
                    (item) => item.status === "requires_review" || item.status === "unavailable",
                  ).length
                }
              </strong>
              <span>uncertain</span>
            </div>
          </div>
          <div className="audit-note">
            Every report claim links back to a run, criterion, test, or tool provenance record.
          </div>
        </Panel>
      </div>
      <div className="two-column evidence-layout">
        <Panel
          title="Source code"
          eyebrow="READ-ONLY VIEWER"
          action={
            <span className="tiny-label">
              UTF-8 · {result.source_content?.split("\n").length ?? 0} lines
            </span>
          }
        >
          <pre className="source-viewer">
            {(result.source_content ?? "").split("\n").map((line, index) => (
              <code key={`${index}-${line}`}>
                <span>{String(index + 1).padStart(3, " ")}</span>
                {line}
              </code>
            ))}
          </pre>
        </Panel>
        <Panel title="Findings & tests" eyebrow="EVIDENCE-FIRST FEEDBACK">
          <div className="evidence-list">
            {evidence.length === 0 ? (
              <EmptyState
                title="No evidence yet"
                detail="The coordinator has not produced findings."
              />
            ) : (
              evidence.map((item) => (
                <div className={`evidence-item evidence-${item.status}`} key={item.id}>
                  <div className="evidence-top">
                    <Badge value={item.status} />
                    <span>
                      {item.source_type}
                      {item.test_id ? ` · ${item.test_id}` : ""}
                    </span>
                  </div>
                  <strong>{item.summary}</strong>
                  {item.input !== null && (
                    <div className="io-grid">
                      <div>
                        <small>INPUT</small>
                        <pre>{item.input}</pre>
                      </div>
                      <div>
                        <small>EXPECTED</small>
                        <pre>{item.expected_output}</pre>
                      </div>
                      <div>
                        <small>ACTUAL</small>
                        <pre>{item.actual_output}</pre>
                      </div>
                    </div>
                  )}
                  <small className="evidence-id">{item.id}</small>
                </div>
              ))
            )}
          </div>
        </Panel>
      </div>
      {result.report && (
        <Panel
          title="Feedback report"
          eyebrow="TEMPLATE-VALIDATED OUTPUT"
          action={
            <a
              className="button button-small"
              href={reportDownloadUrl(result.report.id, "txt")}
              target="_blank"
              rel="noreferrer"
            >
              Download report
            </a>
          }
        >
          <pre className="report-preview">{JSON.stringify(result.report.report, null, 2)}</pre>
        </Panel>
      )}
    </div>
  );
}

function SimilarityPage(): ReactElement {
  const [findings, setFindings] = useState<SimilarityFinding[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(
    () =>
      api
        .similarity()
        .then(setFindings)
        .catch((reason: Error) => setError(reason.message)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  const setDisposition = async (id: string, disposition: string): Promise<void> => {
    try {
      await api.disposition(id, disposition);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save disposition");
    }
  };
  return (
    <div className="page-stack">
      <div className="page-title-row">
        <div>
          <div className="eyebrow">ASSIGNMENT-SCOPED EVIDENCE</div>
          <h1>Similarity Review</h1>
          <p>
            Inspect normalized token overlap without turning a heuristic into a misconduct verdict
            or grade deduction.
          </p>
        </div>
        <Badge value="review only" />
      </div>
      {error && <div className="alert alert-danger">{error}</div>}
      <Panel
        title="Candidate pairs"
        eyebrow={`${findings.length} FLAGGED PAIR${findings.length === 1 ? "" : "S"}`}
      >
        <div className="review-banner">
          <span>i</span>
          <div>
            <strong>Similarity is not proof.</strong>
            <p>
              Review matched regions, assignment size and distinctive shared mistakes before
              recording a disposition.
            </p>
          </div>
        </div>
        {findings.length === 0 ? (
          <EmptyState
            title="No candidate pairs"
            detail="Similarity runs after a batch is evaluated. Clean results remain unflagged."
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Pair</th>
                  <th>Score</th>
                  <th>Method</th>
                  <th>Review state</th>
                  <th>Disposition</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((finding) => (
                  <tr key={finding.id}>
                    <td>
                      <strong>
                        {finding.left_submission_id.slice(0, 8)} ↔{" "}
                        {finding.right_submission_id.slice(0, 8)}
                      </strong>
                      <small>{String(finding.details.left_excerpt ?? "No excerpt")}</small>
                    </td>
                    <td>
                      <strong className="score-accent">{(finding.score * 100).toFixed(1)}%</strong>
                      <small>threshold {String(finding.details.threshold ?? "configured")}</small>
                    </td>
                    <td>
                      <span className="mono">{finding.method}</span>
                    </td>
                    <td>
                      <Badge value={finding.review_status} />
                    </td>
                    <td>
                      <select
                        value={finding.disposition ?? ""}
                        onChange={(event) => {
                          if (event.target.value)
                            void setDisposition(finding.id, event.target.value);
                        }}
                      >
                        <option value="">Choose disposition</option>
                        <option value="confirmed_overlap">Confirmed overlap</option>
                        <option value="benign_similarity">Benign similarity</option>
                        <option value="needs_manual_review">Needs manual review</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

function RunsPage(): ReactElement {
  const [runs, setRuns] = useState<Evaluation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(
    () =>
      api
        .evaluations()
        .then(setRuns)
        .catch((reason: Error) => setError(reason.message)),
    [],
  );
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [load]);
  return (
    <div className="page-stack">
      <div className="page-title-row">
        <div>
          <div className="eyebrow">DURABLE LIFECYCLE</div>
          <h1>Evaluation Runs</h1>
          <p>Queued work, stage progress and failures remain inspectable across refreshes.</p>
        </div>
        <button className="button button-secondary" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}
      <Panel title="Recent runs" eyebrow={`${runs.length} RUNS`}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>State</th>
                <th>Stage</th>
                <th>Progress</th>
                <th>Attempt</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>
                    <span className="mono">{run.id.slice(0, 12)}</span>
                    <small>{new Date(run.created_at).toLocaleString()}</small>
                  </td>
                  <td>
                    <Badge value={run.state} />
                  </td>
                  <td>{run.current_stage ?? "—"}</td>
                  <td>
                    <div className="progress-line">
                      <span style={{ width: `${run.progress}%` }} />
                    </div>
                    <small>{run.progress}%</small>
                  </td>
                  <td>#{run.attempt}</td>
                  <td>{run.error_summary ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {runs.length === 0 && (
          <EmptyState
            title="No evaluation runs"
            detail="Start a batch evaluation to see its lifecycle here."
          />
        )}
      </Panel>
    </div>
  );
}

function SettingsPage(): ReactElement {
  const [dependencies, setDependencies] = useState<Dependency[]>([]);
  const [configuredRunner, setConfiguredRunner] = useState("bubblewrap");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(
    () =>
      api
        .dependencies()
        .then((result) => {
          setDependencies(result.dependencies);
          setConfiguredRunner(result.configured_runner || "bubblewrap");
        })
        .catch((reason: Error) => setError(reason.message)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="page-stack">
      <div className="page-title-row">
        <div>
          <div className="eyebrow">RUNTIME DIAGNOSTICS</div>
          <h1>Settings & Health</h1>
          <p>Configuration status is visible without exposing model credentials or host paths.</p>
        </div>
        <button className="button button-secondary" onClick={() => void load()}>
          Run checks
        </button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}
      <div className="two-column">
        <Panel title="Dependencies" eyebrow="READINESS">
          <div className="dependency-list">
            {dependencies.map((dependency) => (
              <div className="dependency-row" key={dependency.name}>
                <span className={`health-dot ${dependency.available ? "online" : "offline"}`} />
                <div>
                  <strong>{dependency.name}</strong>
                  <small>{dependency.detail}</small>
                </div>
                <Badge value={dependency.available ? "available" : "unavailable"} />
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Safety posture" eyebrow="CURRENT POLICY">
          <ul className="principle-list">
            <li>
              <span className="principle-dot green" />
              Student code is only accepted as UTF-8 `.c` text with size and batch limits.
            </li>
            <li>
              <span className="principle-dot blue" />
              Production execution uses the configured Linux namespace sandbox with no network,
              read-only system mounts, a writable submission workspace and resource limits.
            </li>
            <li>
              <span className="principle-dot red" />
              When the configured sandbox is unavailable, real execution fails closed rather than
              using the host.
            </li>
            <li>
              <span className="principle-dot amber" />
              Ollama is optional for deterministic mode; malformed or unavailable model output
              cannot set points.
            </li>
          </ul>
        </Panel>
      </div>
      <Panel title="Configuration reference" eyebrow="ENVIRONMENT">
        <div className="config-grid">
          <div>
            <span>AUTOGRADER_RUNNER</span>
            <strong>{configuredRunner}</strong>
          </div>
          <div>
            <span>AUTOGRADER_OLLAMA_MODEL</span>
            <strong>configured by .env</strong>
          </div>
          <div>
            <span>COMPILER</span>
            <strong>GCC / C11</strong>
          </div>
          <div>
            <span>PERSISTENCE</span>
            <strong>SQLite + audit events</strong>
          </div>
        </div>
      </Panel>
    </div>
  );
}

export default function App(): ReactElement {
  const [route, setRoute] = useState(routeFromHash());
  useEffect(() => {
    const onHash = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const active = route.page;
  const page =
    active === "overview" ? (
      <OverviewPage />
    ) : active === "assignments" ? (
      <AssignmentsPage />
    ) : active === "submissions" ? (
      <SubmissionsPage detailId={route.id} />
    ) : active === "similarity" ? (
      <SimilarityPage />
    ) : active === "runs" ? (
      <RunsPage />
    ) : (
      <SettingsPage />
    );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">AG</div>
          <div>
            <strong>AutoGrader</strong>
            <span>control room</span>
          </div>
        </div>
        <div className="sidebar-rule" />
        <nav aria-label="Primary navigation">
          {navItems.map((item) => (
            <button
              className={`nav-item ${active === item.id ? "active" : ""}`}
              key={item.id}
              onClick={() => navigate(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>
                <strong>{item.label}</strong>
                <small>{item.description}</small>
              </span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="environment-chip">
            <span className="health-dot online" />
            <div>
              <strong>Local workspace</strong>
              <small>operator mode · v0.1.0</small>
            </div>
          </div>
          <div className="sidebar-footnote">
            Scores are reproducible from immutable versions and typed evidence.
          </div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="crumbs">
            <span>WORKSPACE</span>
            <b>/</b>
            <strong>{navItems.find((item) => item.id === active)?.label ?? "Overview"}</strong>
          </div>
          <div className="topbar-actions">
            <span className="live-indicator">
              <span />
              API connected when backend is running
            </span>
            <button className="icon-button" title="Keyboard navigation is supported">
              ?
            </button>
          </div>
        </header>
        <div className="content">{page}</div>
      </main>
    </div>
  );
}
