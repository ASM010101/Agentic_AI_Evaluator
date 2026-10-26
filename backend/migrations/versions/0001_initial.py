"""create initial AutoGrader tables

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _json():
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("rules_json", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "assignment_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("rules_json", _json(), nullable=False),
        sa.Column("spec_json", _json(), nullable=False),
        sa.Column("version_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", "version_number", name="ix_assignment_version_unique"),
    )
    op.create_index("ix_assignment_versions_assignment_id", "assignment_versions", ["assignment_id"])
    op.create_index("ix_assignment_versions_version_hash", "assignment_versions", ["version_hash"])
    op.create_table(
        "test_cases",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("assignment_version_id", sa.String(length=36), nullable=False),
        sa.Column("input_data", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=True),
        sa.Column("expected_behavior", sa.Text(), nullable=True),
        sa.Column("comparator_json", _json(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("provenance", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requirement_id", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", _json(), nullable=False),
        sa.Column("score_affecting", sa.Boolean(), nullable=False),
        sa.Column("validation_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["assignment_version_id"], ["assignment_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_cases_assignment_version_id", "test_cases", ["assignment_version_id"])
    op.create_table(
        "submission_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assignment_version_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary_json", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assignment_version_id"], ["assignment_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_submission_batches_assignment_version_id", "submission_batches", ["assignment_version_id"])
    op.create_table(
        "submissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_version_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_content", sa.Text(), nullable=False),
        sa.Column("source_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assignment_version_id"], ["assignment_versions.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["submission_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "original_filename", name="ix_submission_batch_filename"),
    )
    op.create_index("ix_submissions_batch_id", "submissions", ["batch_id"])
    op.create_index("ix_submissions_assignment_version_id", "submissions", ["assignment_version_id"])
    op.create_index("ix_submissions_content_hash", "submissions", ["content_hash"])
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_version_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_stage", sa.String(length=64), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("retry_of", sa.String(length=36), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("config_snapshot", _json(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assignment_version_id"], ["assignment_versions.id"]),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_runs_submission_id", "evaluation_runs", ["submission_id"])
    op.create_index("ix_evaluation_runs_assignment_version_id", "evaluation_runs", ["assignment_version_id"])
    op.create_index("ix_evaluation_runs_state", "evaluation_runs", ["state"])
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assignment_version_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("requirement_id", sa.String(length=120), nullable=True),
        sa.Column("rubric_criterion_id", sa.String(length=120), nullable=True),
        sa.Column("test_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details_json", _json(), nullable=False),
        sa.Column("source_location_json", _json(), nullable=True),
        sa.Column("input_data", sa.Text(), nullable=True),
        sa.Column("expected_output", sa.Text(), nullable=True),
        sa.Column("actual_output", sa.Text(), nullable=True),
        sa.Column("provenance_json", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assignment_version_id"], ["assignment_versions.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_assignment_version_id", "evidence", ["assignment_version_id"])
    op.create_index("ix_evidence_submission_id", "evidence", ["submission_id"])
    op.create_index("ix_evidence_run_id", "evidence", ["run_id"])
    op.create_index("ix_evidence_rubric_criterion_id", "evidence", ["rubric_criterion_id"])
    op.create_index("ix_evidence_test_id", "evidence", ["test_id"])
    op.create_table(
        "score_breakdowns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("finalized", sa.Boolean(), nullable=False),
        sa.Column("scoring_rule_version", sa.String(length=64), nullable=False),
        sa.Column("criteria_json", _json(), nullable=False),
        sa.Column("calculation_trace_json", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("report_json", _json(), nullable=False),
        sa.Column("json_path", sa.String(length=500), nullable=True),
        sa.Column("text_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_table(
        "similarity_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assignment_version_id", sa.String(length=36), nullable=False),
        sa.Column("left_submission_id", sa.String(length=36), nullable=False),
        sa.Column("right_submission_id", sa.String(length=36), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("method", sa.String(length=128), nullable=False),
        sa.Column("details_json", _json(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("disposition", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assignment_version_id"], ["assignment_versions.id"]),
        sa.ForeignKeyConstraint(["left_submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["right_submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_similarity_findings_assignment_version_id", "similarity_findings", ["assignment_version_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("details_json", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_entity_type", "audit_events", ["entity_type"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_entity_id", table_name="audit_events")
    op.drop_index("ix_audit_events_entity_type", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_similarity_findings_assignment_version_id", table_name="similarity_findings")
    op.drop_table("similarity_findings")
    op.drop_table("reports")
    op.drop_table("score_breakdowns")
    op.drop_index("ix_evidence_test_id", table_name="evidence")
    op.drop_index("ix_evidence_rubric_criterion_id", table_name="evidence")
    op.drop_index("ix_evidence_run_id", table_name="evidence")
    op.drop_index("ix_evidence_submission_id", table_name="evidence")
    op.drop_index("ix_evidence_assignment_version_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_evaluation_runs_state", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_assignment_version_id", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_submission_id", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_submissions_content_hash", table_name="submissions")
    op.drop_index("ix_submissions_assignment_version_id", table_name="submissions")
    op.drop_index("ix_submissions_batch_id", table_name="submissions")
    op.drop_table("submissions")
    op.drop_index("ix_submission_batches_assignment_version_id", table_name="submission_batches")
    op.drop_table("submission_batches")
    op.drop_index("ix_test_cases_assignment_version_id", table_name="test_cases")
    op.drop_table("test_cases")
    op.drop_index("ix_assignment_versions_version_hash", table_name="assignment_versions")
    op.drop_index("ix_assignment_versions_assignment_id", table_name="assignment_versions")
    op.drop_table("assignment_versions")
    op.drop_table("assignments")
