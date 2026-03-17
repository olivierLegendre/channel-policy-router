from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CommandSubmitRequest(BaseModel):
    organization_id: str = Field(min_length=1)
    site_id: str = Field(min_length=1)
    point_id: str = Field(min_length=1)
    command_class: Literal[
        "safety_critical",
        "interactive_control",
        "routine_automation",
        "bulk_non_critical",
    ]
    payload: dict[str, Any]
    idempotency_key: str | None = None
    correlation_id: str | None = None
    parent_command_id: str | None = None


class CommandResponse(BaseModel):
    command_id: str
    organization_id: str
    site_id: str
    point_id: str
    command_class: str
    status: str
    requested_channel: str
    effective_channel: str
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


class CommandSubmitResponse(BaseModel):
    duplicate_of: str | None
    generated_idempotency_key: str | None
    generated_correlation_id: str | None
    command: CommandResponse


class ListCommandsResponse(BaseModel):
    items: list[CommandResponse]


class OverrideRequest(BaseModel):
    actor_role: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    channel: Literal["API", "MQTT"]


class ReissueRequest(BaseModel):
    actor_role: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class QueueResponse(BaseModel):
    items: list[CommandResponse]


class PolicyResponse(BaseModel):
    command_class: str
    primary_channel: str
    api_timeout_seconds: int
    api_attempts_before_fallback: int
    mqtt_retry_budget: int
    mqtt_fallback_allowed: bool
    reconciliation_sla_seconds: int


class DispatchRequest(BaseModel):
    site_id: str = Field(min_length=1)
    point_id: str = Field(min_length=1)


class ReconcileRequest(BaseModel):
    observed_match: bool


class SlaCheckResponse(BaseModel):
    breached: bool
    alert_required: bool
    manual_action_required: bool
    command: CommandResponse


class SlaBatchEvaluateRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)


class SlaBatchEvaluateResponse(BaseModel):
    lock_acquired: bool
    breached_count: int
    items: list[SlaCheckResponse]


class IncidentHookResponse(BaseModel):
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


class IncidentDeliveryRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)


class IncidentDeliveryResponse(BaseModel):
    lock_acquired: bool
    delivered_count: int
    failed_count: int


class GovernanceSnapshotResponse(BaseModel):
    site_id: str
    queueDepth: int
    slaBreaches24h: int
    rejected50324h: int
