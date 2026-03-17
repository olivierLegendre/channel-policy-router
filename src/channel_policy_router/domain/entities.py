from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class CommandClass(StrEnum):
    safety_critical = "safety_critical"
    interactive_control = "interactive_control"
    routine_automation = "routine_automation"
    bulk_non_critical = "bulk_non_critical"


class CommandStatus(StrEnum):
    accepted = "accepted"
    queued = "queued"
    dispatched = "dispatched"
    canceled = "canceled"
    failed = "failed"
    applied_confirmed = "applied_confirmed"


class Channel(StrEnum):
    api = "API"
    mqtt = "MQTT"


@dataclass(frozen=True)
class ClassPolicy:
    command_class: CommandClass
    primary_channel: Channel
    api_timeout_seconds: int
    api_attempts_before_fallback: int
    mqtt_retry_budget: int
    mqtt_fallback_allowed: bool
    reconciliation_sla_seconds: int


@dataclass(frozen=True)
class Command:
    command_id: str
    organization_id: str
    site_id: str
    point_id: str
    command_class: CommandClass
    status: CommandStatus
    requested_channel: Channel
    effective_channel: Channel
    idempotency_key: str
    correlation_id: str
    payload: dict[str, Any]
    parent_command_id: str | None
    queue_priority: int
    queue_seq: int
    override_reason: str | None
    reconciliation_deadline_at: datetime
    dispatched_at: datetime | None
    completed_at: datetime | None
    result_reason: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SubmissionResult:
    command: Command
    duplicate_of: str | None
    generated_idempotency_key: str | None
    generated_correlation_id: str | None


@dataclass(frozen=True)
class SlaCheckResult:
    breached: bool
    command: Command
    alert_required: bool
    manual_action_required: bool


@dataclass(frozen=True)
class SlaBatchResult:
    lock_acquired: bool
    items: list[SlaCheckResult]


@dataclass(frozen=True)
class IncidentHookEvent:
    event_id: str
    command_id: str
    organization_id: str
    site_id: str
    severity: str
    reason: str
    manual_action_required: bool
    payload: dict[str, Any]
    attempt_count: int
    next_attempt_at: datetime
    delivered_at: datetime | None
    last_error: str | None
    created_at: datetime


@dataclass(frozen=True)
class IncidentDeliveryBatchResult:
    lock_acquired: bool
    delivered_count: int
    failed_count: int


@dataclass(frozen=True)
class GovernanceSnapshot:
    site_id: str
    queue_depth: int
    sla_breaches_24h: int
    rejected_503_24h: int
