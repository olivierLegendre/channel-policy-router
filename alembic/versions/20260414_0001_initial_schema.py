"""initial schema

Revision ID: 20260414_0001
Revises:
Create Date: 2026-04-14 13:31:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260414_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS commands (
  command_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  point_id TEXT NOT NULL,
  command_class TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_channel TEXT NOT NULL,
  effective_channel TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  parent_command_id TEXT,
  queue_priority INT NOT NULL,
  queue_seq BIGINT NOT NULL,
  override_reason TEXT,
  reconciliation_deadline_at TIMESTAMPTZ NOT NULL,
  dispatched_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  result_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_commands_site_idempotency_created
  ON commands (site_id, idempotency_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_commands_site_correlation_created
  ON commands (site_id, correlation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_commands_point_status_order
  ON commands (site_id, point_id, status, queue_priority, queue_seq, created_at);

CREATE TABLE IF NOT EXISTS incident_hook_events (
  event_id TEXT PRIMARY KEY,
  command_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  site_id TEXT NOT NULL,
  severity TEXT NOT NULL,
  reason TEXT NOT NULL,
  manual_action_required BOOLEAN NOT NULL,
  payload_json JSONB NOT NULL,
  attempt_count INT NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_incident_hooks_delivery
  ON incident_hook_events (delivered_at, next_attempt_at, created_at);

CREATE TABLE IF NOT EXISTS batch_leases (
  lease_name TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_batch_leases_expires_at
  ON batch_leases (expires_at);
"""
    )


def downgrade() -> None:
    op.execute(
        """
DROP TABLE IF EXISTS batch_leases;
DROP TABLE IF EXISTS incident_hook_events;
DROP TABLE IF EXISTS commands;
"""
    )
