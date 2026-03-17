from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from channel_policy_router.application.use_cases import CommandRouterUseCases
from channel_policy_router.domain.entities import Channel, CommandClass
from channel_policy_router.domain.errors import (
    CancelNotAllowedError,
    CorrelationConflictError,
    DispatchNotAllowedError,
    NotFoundError,
    OverrideNotAllowedError,
    QueueOverflowError,
    ReconciliationNotAllowedError,
    ValidationError,
)
from channel_policy_router.security.auth import JwtVerifierConfig, require_any_role
from channel_policy_router.settings import Settings

from .schemas import (
    CommandResponse,
    CommandSubmitRequest,
    CommandSubmitResponse,
    DispatchRequest,
    GovernanceSnapshotResponse,
    IncidentDeliveryRequest,
    IncidentDeliveryResponse,
    IncidentHookResponse,
    ListCommandsResponse,
    OverrideRequest,
    PolicyResponse,
    QueueResponse,
    ReconcileRequest,
    ReissueRequest,
    SlaBatchEvaluateRequest,
    SlaBatchEvaluateResponse,
    SlaCheckResponse,
)


def _to_command_response(item: Any) -> CommandResponse:
    return CommandResponse(
        command_id=item.command_id,
        organization_id=item.organization_id,
        site_id=item.site_id,
        point_id=item.point_id,
        command_class=item.command_class.value,
        status=item.status.value,
        requested_channel=item.requested_channel.value,
        effective_channel=item.effective_channel.value,
        idempotency_key=item.idempotency_key,
        correlation_id=item.correlation_id,
        payload=item.payload,
        parent_command_id=item.parent_command_id,
        queue_priority=item.queue_priority,
        queue_seq=item.queue_seq,
        override_reason=item.override_reason,
        reconciliation_deadline_at=item.reconciliation_deadline_at,
        dispatched_at=item.dispatched_at,
        completed_at=item.completed_at,
        result_reason=item.result_reason,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


JWT_CONFIG = JwtVerifierConfig(
    secret=Settings().auth_jwt_secret,
    issuer=Settings().auth_jwt_issuer,
    audience=Settings().auth_jwt_audience,
)


def create_router(use_cases: CommandRouterUseCases) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "channel-policy-router"}

    @router.get("/api/v1/policy/{command_class}", response_model=PolicyResponse)
    def get_policy(command_class: str) -> PolicyResponse:
        try:
            cls = CommandClass(command_class)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid command_class") from exc
        policy = use_cases.class_policy(cls)
        return PolicyResponse(
            command_class=policy.command_class.value,
            primary_channel=policy.primary_channel.value,
            api_timeout_seconds=policy.api_timeout_seconds,
            api_attempts_before_fallback=policy.api_attempts_before_fallback,
            mqtt_retry_budget=policy.mqtt_retry_budget,
            mqtt_fallback_allowed=policy.mqtt_fallback_allowed,
            reconciliation_sla_seconds=policy.reconciliation_sla_seconds,
        )

    @router.post("/api/v1/commands", response_model=CommandSubmitResponse, status_code=202)
    def submit_command(body: CommandSubmitRequest) -> CommandSubmitResponse:
        try:
            result = use_cases.submit_command(
                organization_id=body.organization_id,
                site_id=body.site_id,
                point_id=body.point_id,
                command_class=CommandClass(body.command_class),
                payload=body.payload,
                idempotency_key=body.idempotency_key,
                correlation_id=body.correlation_id,
                parent_command_id=body.parent_command_id,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.detail) from exc
        except CorrelationConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "correlation_id conflict",
                    "correlation_id": exc.correlation_id,
                    "existing_command_id": exc.existing_command_id,
                },
            ) from exc
        except QueueOverflowError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "queue overflow",
                    "queue_depth": exc.queue_depth,
                },
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc

        return CommandSubmitResponse(
            duplicate_of=result.duplicate_of,
            generated_idempotency_key=result.generated_idempotency_key,
            generated_correlation_id=result.generated_correlation_id,
            command=_to_command_response(result.command),
        )

    @router.get("/api/v1/commands", response_model=ListCommandsResponse)
    def list_commands(
        site_id: str = Query(min_length=1),
        status: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> ListCommandsResponse:
        rows = use_cases.list_commands(site_id=site_id, status=status, limit=limit)
        return ListCommandsResponse(items=[_to_command_response(row) for row in rows])

    @router.get("/api/v1/commands/{command_id}", response_model=CommandResponse)
    def get_command(command_id: str) -> CommandResponse:
        try:
            row = use_cases.get_command(command_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_command_response(row)

    @router.post("/api/v1/commands/{command_id}/cancel", response_model=CommandResponse)
    def cancel_command(command_id: str) -> CommandResponse:
        try:
            row = use_cases.cancel_command(command_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CancelNotAllowedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _to_command_response(row)

    @router.post(
        "/api/v1/commands/{command_id}/reissue",
        response_model=CommandSubmitResponse,
        status_code=202,
    )
    def reissue_command(
        command_id: str,
        body: ReissueRequest,
        authorization: str | None = Header(default=None),
    ) -> CommandSubmitResponse:
        actor_role = require_any_role(
            authorization,
            allowed_roles={"org_admin", "site_admin", "operations_override"},
            config=JWT_CONFIG,
        )
        try:
            result = use_cases.reissue_command(
                command_id=command_id,
                actor_role=actor_role,
                reason=body.reason,
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OverrideNotAllowedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.detail) from exc
        return CommandSubmitResponse(
            duplicate_of=result.duplicate_of,
            generated_idempotency_key=result.generated_idempotency_key,
            generated_correlation_id=result.generated_correlation_id,
            command=_to_command_response(result.command),
        )

    @router.post("/api/v1/commands/{command_id}/override-channel", response_model=CommandResponse)
    def override_channel(command_id: str, body: OverrideRequest) -> CommandResponse:
        try:
            row = use_cases.override_channel(
                command_id=command_id,
                actor_role=body.actor_role,
                reason=body.reason,
                requested_channel=Channel(body.channel),
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OverrideNotAllowedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.detail) from exc
        return _to_command_response(row)

    @router.post("/api/v1/dispatch-next", response_model=CommandResponse)
    def dispatch_next(body: DispatchRequest) -> CommandResponse:
        try:
            row = use_cases.dispatch_next(site_id=body.site_id, point_id=body.point_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DispatchNotAllowedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _to_command_response(row)

    @router.post("/api/v1/commands/{command_id}/reconcile", response_model=CommandResponse)
    def reconcile_command(command_id: str, body: ReconcileRequest) -> CommandResponse:
        try:
            row = use_cases.reconcile_command(
                command_id=command_id,
                observed_match=body.observed_match,
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ReconciliationNotAllowedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _to_command_response(row)

    @router.post("/api/v1/commands/{command_id}/check-sla", response_model=SlaCheckResponse)
    def check_sla(command_id: str) -> SlaCheckResponse:
        try:
            result = use_cases.check_sla(command_id=command_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return SlaCheckResponse(
            breached=result.breached,
            alert_required=result.alert_required,
            manual_action_required=result.manual_action_required,
            command=_to_command_response(result.command),
        )

    @router.post("/api/v1/sla/evaluate", response_model=SlaBatchEvaluateResponse)
    def evaluate_sla_batch(body: SlaBatchEvaluateRequest) -> SlaBatchEvaluateResponse:
        result = use_cases.evaluate_sla_batch(limit=body.limit)
        rows = [
            SlaCheckResponse(
                breached=row.breached,
                alert_required=row.alert_required,
                manual_action_required=row.manual_action_required,
                command=_to_command_response(row.command),
            )
            for row in result.items
        ]
        return SlaBatchEvaluateResponse(
            lock_acquired=result.lock_acquired,
            breached_count=len(rows),
            items=rows,
        )

    @router.post("/api/v1/incidents/hooks/deliver", response_model=IncidentDeliveryResponse)
    def deliver_incident_hooks(body: IncidentDeliveryRequest) -> IncidentDeliveryResponse:
        result = use_cases.deliver_incident_hooks_batch(limit=body.limit)
        return IncidentDeliveryResponse(
            lock_acquired=result.lock_acquired,
            delivered_count=result.delivered_count,
            failed_count=result.failed_count,
        )

    @router.get("/api/v1/incidents/hooks", response_model=list[IncidentHookResponse])
    def list_incident_hooks(
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[IncidentHookResponse]:
        rows = use_cases.list_incident_hooks(limit=limit)
        return [
            IncidentHookResponse(
                event_id=row.event_id,
                command_id=row.command_id,
                organization_id=row.organization_id,
                site_id=row.site_id,
                severity=row.severity,
                reason=row.reason,
                manual_action_required=row.manual_action_required,
                payload=row.payload,
                attempt_count=row.attempt_count,
                next_attempt_at=row.next_attempt_at,
                delivered_at=row.delivered_at,
                last_error=row.last_error,
                created_at=row.created_at,
            )
            for row in rows
        ]

    @router.get("/api/v1/governance/snapshot", response_model=GovernanceSnapshotResponse)
    def governance_snapshot(site_id: str = Query(min_length=1)) -> GovernanceSnapshotResponse:
        row = use_cases.get_governance_snapshot(site_id=site_id)
        return GovernanceSnapshotResponse(
            site_id=row.site_id,
            queueDepth=row.queue_depth,
            slaBreaches24h=row.sla_breaches_24h,
            rejected50324h=row.rejected_503_24h,
        )

    @router.get("/api/v1/queue", response_model=QueueResponse)
    def list_queue(
        site_id: str = Query(min_length=1),
        point_id: str = Query(min_length=1),
    ) -> QueueResponse:
        rows = use_cases.list_point_queue(site_id=site_id, point_id=point_id)
        return QueueResponse(items=[_to_command_response(row) for row in rows])

    return router
