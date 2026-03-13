from datetime import UTC, datetime, timedelta
from uuid import uuid4

from channel_policy_router.application.policy import POLICY_MATRIX
from channel_policy_router.application.uow import UnitOfWork
from channel_policy_router.domain.entities import (
    Channel,
    Command,
    CommandClass,
    CommandStatus,
    IncidentDeliveryBatchResult,
    IncidentHookEvent,
    SlaBatchResult,
    SlaCheckResult,
    SubmissionResult,
)
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


class CommandRouterUseCases:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        queue_max_depth_per_point: int,
        queue_retry_after_seconds: int,
        idempotency_window_seconds: int,
        correlation_window_seconds: int,
        sla_deadline_offset_seconds: int,
        sla_batch_lock_ttl_seconds: int,
        incident_delivery_lock_ttl_seconds: int,
        incident_delivery_backoff_base_seconds: int,
        incident_delivery_backoff_max_seconds: int,
    ) -> None:
        self._uow = uow
        self._queue_max_depth_per_point = queue_max_depth_per_point
        self._queue_retry_after_seconds = queue_retry_after_seconds
        self._idempotency_window = timedelta(seconds=idempotency_window_seconds)
        self._correlation_window = timedelta(seconds=correlation_window_seconds)
        self._sla_deadline_offset_seconds = sla_deadline_offset_seconds
        self._sla_batch_lock_ttl_seconds = sla_batch_lock_ttl_seconds
        self._incident_delivery_lock_ttl_seconds = incident_delivery_lock_ttl_seconds
        self._incident_delivery_backoff_base_seconds = incident_delivery_backoff_base_seconds
        self._incident_delivery_backoff_max_seconds = incident_delivery_backoff_max_seconds

    def submit_command(
        self,
        *,
        organization_id: str,
        site_id: str,
        point_id: str,
        command_class: CommandClass,
        payload: dict[str, object],
        idempotency_key: str | None,
        correlation_id: str | None,
        parent_command_id: str | None,
    ) -> SubmissionResult:
        now = datetime.now(tz=UTC)
        policy = POLICY_MATRIX[command_class]

        generated_idempotency_key: str | None = None
        generated_correlation_id: str | None = None

        if command_class == CommandClass.safety_critical and not idempotency_key:
            raise ValidationError("idempotency_key is required for safety_critical")
        if command_class == CommandClass.safety_critical and not correlation_id:
            raise ValidationError("correlation_id is required for safety_critical")

        if not idempotency_key:
            generated_idempotency_key = str(uuid4())
            idempotency_key = generated_idempotency_key
        if not correlation_id:
            generated_correlation_id = str(uuid4())
            correlation_id = generated_correlation_id

        with self._uow as uow:
            dedup = uow.commands.find_recent_by_idempotency(
                site_id=site_id,
                idempotency_key=idempotency_key,
                since=now - self._idempotency_window,
            )
            if dedup is not None:
                return SubmissionResult(
                    command=dedup,
                    duplicate_of=dedup.command_id,
                    generated_idempotency_key=generated_idempotency_key,
                    generated_correlation_id=generated_correlation_id,
                )

            existing_corr = uow.commands.find_recent_by_correlation(
                site_id=site_id,
                correlation_id=correlation_id,
                since=now - self._correlation_window,
            )
            if existing_corr is not None:
                raise CorrelationConflictError(correlation_id, existing_corr.command_id)

            pending_depth = uow.commands.count_pending_for_point(site_id=site_id, point_id=point_id)
            if pending_depth >= self._queue_max_depth_per_point:
                raise QueueOverflowError(
                    queue_depth=pending_depth,
                    retry_after_seconds=self._queue_retry_after_seconds,
                )

            inflight = uow.commands.find_inflight_for_point(site_id=site_id, point_id=point_id)
            status = (
                CommandStatus.accepted
                if inflight is None and pending_depth == 0
                else CommandStatus.queued
            )

            queue_priority = 0 if command_class == CommandClass.safety_critical else 1
            queue_seq = (
                0
                if status == CommandStatus.accepted
                else uow.commands.next_queue_seq(site_id=site_id, point_id=point_id)
            )

            command = Command(
                command_id=str(uuid4()),
                organization_id=organization_id,
                site_id=site_id,
                point_id=point_id,
                command_class=command_class,
                status=status,
                requested_channel=Channel.api,
                effective_channel=policy.primary_channel,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                payload=payload,
                parent_command_id=parent_command_id,
                queue_priority=queue_priority,
                queue_seq=queue_seq,
                override_reason=None,
                reconciliation_deadline_at=(
                    now
                    + timedelta(seconds=policy.reconciliation_sla_seconds)
                    + timedelta(seconds=self._sla_deadline_offset_seconds)
                ),
                dispatched_at=None,
                completed_at=None,
                result_reason=None,
                created_at=now,
                updated_at=now,
            )
            persisted = uow.commands.add(command)
            uow.commit()

        return SubmissionResult(
            command=persisted,
            duplicate_of=None,
            generated_idempotency_key=generated_idempotency_key,
            generated_correlation_id=generated_correlation_id,
        )

    def get_command(self, command_id: str) -> Command:
        with self._uow as uow:
            row = uow.commands.get(command_id)
            if row is None:
                raise NotFoundError(f"command not found: {command_id}")
            return row

    def cancel_command(self, command_id: str) -> Command:
        with self._uow as uow:
            row = uow.commands.get(command_id)
            if row is None:
                raise NotFoundError(f"command not found: {command_id}")
            if row.status not in {CommandStatus.accepted, CommandStatus.queued}:
                raise CancelNotAllowedError("cancel is allowed only before dispatch")

            updated = Command(
                **{
                    **row.__dict__,
                    "status": CommandStatus.canceled,
                    "updated_at": datetime.now(tz=UTC),
                }
            )
            persisted = uow.commands.update(updated)
            uow.commit()
            return persisted

    def override_channel(
        self,
        *,
        command_id: str,
        actor_role: str,
        reason: str,
        requested_channel: Channel,
    ) -> Command:
        allowed_roles = {"org_admin", "operations_override"}
        if actor_role not in allowed_roles:
            raise OverrideNotAllowedError("override role required")
        if not reason.strip():
            raise ValidationError("override reason is required")

        with self._uow as uow:
            row = uow.commands.get(command_id)
            if row is None:
                raise NotFoundError(f"command not found: {command_id}")

            updated = Command(
                **{
                    **row.__dict__,
                    "effective_channel": requested_channel,
                    "override_reason": reason,
                    "updated_at": datetime.now(tz=UTC),
                }
            )
            persisted = uow.commands.update(updated)
            uow.commit()
            return persisted

    def dispatch_next(self, *, site_id: str, point_id: str) -> Command:
        now = datetime.now(tz=UTC)
        with self._uow as uow:
            inflight = uow.commands.find_inflight_for_point(site_id=site_id, point_id=point_id)
            if inflight is not None:
                raise DispatchNotAllowedError("point has in-flight command")

            candidate = uow.commands.find_accepted_for_point(site_id=site_id, point_id=point_id)
            if candidate is None:
                queue_rows = list(
                    uow.commands.list_queued_for_point(site_id=site_id, point_id=point_id)
                )
                if not queue_rows:
                    raise NotFoundError("no dispatchable command")
                candidate = queue_rows[0]

            updated = Command(
                **{
                    **candidate.__dict__,
                    "status": CommandStatus.dispatched,
                    "dispatched_at": now,
                    "updated_at": now,
                }
            )
            persisted = uow.commands.update(updated)
            uow.commit()
            return persisted

    def reconcile_command(self, *, command_id: str, observed_match: bool) -> Command:
        now = datetime.now(tz=UTC)
        with self._uow as uow:
            row = uow.commands.get(command_id)
            if row is None:
                raise NotFoundError(f"command not found: {command_id}")
            if row.status != CommandStatus.dispatched:
                raise ReconciliationNotAllowedError(
                    "reconciliation allowed only for dispatched command"
                )

            status = CommandStatus.applied_confirmed if observed_match else CommandStatus.failed
            reason = None if observed_match else "observed_state_mismatch"
            updated = Command(
                **{
                    **row.__dict__,
                    "status": status,
                    "completed_at": now,
                    "result_reason": reason,
                    "updated_at": now,
                }
            )
            persisted = uow.commands.update(updated)
            uow.commit()
            return persisted

    def check_sla(self, *, command_id: str) -> SlaCheckResult:
        now = datetime.now(tz=UTC)
        with self._uow as uow:
            row = uow.commands.get(command_id)
            if row is None:
                raise NotFoundError(f"command not found: {command_id}")

            active_states = {CommandStatus.accepted, CommandStatus.queued, CommandStatus.dispatched}
            if row.status not in active_states or now <= row.reconciliation_deadline_at:
                return SlaCheckResult(
                    breached=False,
                    command=row,
                    alert_required=False,
                    manual_action_required=False,
                )

            persisted, alert, manual = self._mark_failed_for_sla(uow=uow, row=row, now=now)
            uow.commit()
            return SlaCheckResult(
                breached=True,
                command=persisted,
                alert_required=alert,
                manual_action_required=manual,
            )

    def evaluate_sla_batch(self, *, limit: int = 100) -> SlaBatchResult:
        now = datetime.now(tz=UTC)
        owner_id = str(uuid4())
        lease_name = "sla_evaluator"

        with self._uow as uow:
            acquired = uow.locks.try_acquire(
                lease_name=lease_name,
                owner_id=owner_id,
                now=now,
                ttl_seconds=self._sla_batch_lock_ttl_seconds,
            )
            if not acquired:
                return SlaBatchResult(lock_acquired=False, items=[])

            results: list[SlaCheckResult] = []
            try:
                rows = uow.commands.list_active_with_deadline_before(before=now, limit=limit)
                for row in rows:
                    persisted, alert, manual = self._mark_failed_for_sla(uow=uow, row=row, now=now)
                    results.append(
                        SlaCheckResult(
                            breached=True,
                            command=persisted,
                            alert_required=alert,
                            manual_action_required=manual,
                        )
                    )
                uow.commit()
            finally:
                uow.locks.release(lease_name=lease_name, owner_id=owner_id)

            return SlaBatchResult(lock_acquired=True, items=results)

    def deliver_incident_hooks_batch(self, *, limit: int = 100) -> IncidentDeliveryBatchResult:
        now = datetime.now(tz=UTC)
        owner_id = str(uuid4())
        lease_name = "incident_delivery"

        with self._uow as uow:
            acquired = uow.locks.try_acquire(
                lease_name=lease_name,
                owner_id=owner_id,
                now=now,
                ttl_seconds=self._incident_delivery_lock_ttl_seconds,
            )
            if not acquired:
                return IncidentDeliveryBatchResult(
                    lock_acquired=False,
                    delivered_count=0,
                    failed_count=0,
                )

            delivered_count = 0
            failed_count = 0
            try:
                rows = uow.incidents.list_pending_for_delivery(before=now, limit=limit)
                for row in rows:
                    should_fail = bool(
                        row.payload.get("command_payload", {}).get("simulate_delivery_failure")
                    )
                    if should_fail:
                        attempt = row.attempt_count + 1
                        backoff = min(
                            self._incident_delivery_backoff_base_seconds * (2 ** (attempt - 1)),
                            self._incident_delivery_backoff_max_seconds,
                        )
                        uow.incidents.mark_delivery_failed(
                            event_id=row.event_id,
                            attempt_count=attempt,
                            next_attempt_at=now + timedelta(seconds=backoff),
                            last_error="simulated_delivery_failure",
                        )
                        failed_count += 1
                    else:
                        uow.incidents.mark_delivered(event_id=row.event_id, delivered_at=now)
                        delivered_count += 1

                uow.commit()
            finally:
                uow.locks.release(lease_name=lease_name, owner_id=owner_id)

            return IncidentDeliveryBatchResult(
                lock_acquired=True,
                delivered_count=delivered_count,
                failed_count=failed_count,
            )

    def list_incident_hooks(self, *, limit: int = 100) -> list[IncidentHookEvent]:
        with self._uow as uow:
            return list(uow.incidents.list_recent(limit=limit))

    def _mark_failed_for_sla(
        self,
        *,
        uow: UnitOfWork,
        row: Command,
        now: datetime,
    ) -> tuple[Command, bool, bool]:
        updated = Command(
            **{
                **row.__dict__,
                "status": CommandStatus.failed,
                "completed_at": now,
                "result_reason": "reconciliation_sla_breach",
                "updated_at": now,
            }
        )
        persisted = uow.commands.update(updated)
        is_safety = persisted.command_class == CommandClass.safety_critical

        if is_safety:
            event = IncidentHookEvent(
                event_id=str(uuid4()),
                command_id=persisted.command_id,
                organization_id=persisted.organization_id,
                site_id=persisted.site_id,
                severity="high",
                reason="safety_critical_sla_breach",
                manual_action_required=True,
                payload={
                    "command_id": persisted.command_id,
                    "site_id": persisted.site_id,
                    "organization_id": persisted.organization_id,
                    "deadline": persisted.reconciliation_deadline_at.isoformat(),
                    "checked_at": now.isoformat(),
                    "command_payload": persisted.payload,
                },
                attempt_count=0,
                next_attempt_at=now,
                delivered_at=None,
                last_error=None,
                created_at=now,
            )
            uow.incidents.add(event)

        return persisted, is_safety, is_safety

    def list_point_queue(self, *, site_id: str, point_id: str) -> list[Command]:
        with self._uow as uow:
            return list(uow.commands.list_queued_for_point(site_id=site_id, point_id=point_id))

    def class_policy(self, command_class: CommandClass):
        return POLICY_MATRIX[command_class]
