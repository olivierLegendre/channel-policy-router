from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from channel_policy_router.application.uow import UnitOfWork
from channel_policy_router.domain.entities import Command, CommandStatus, IncidentHookEvent


@dataclass
class _InMemoryStore:
    commands: dict[str, Command] = field(default_factory=dict)
    incidents: dict[str, IncidentHookEvent] = field(default_factory=dict)
    leases: dict[str, tuple[str, datetime]] = field(default_factory=dict)


class InMemoryCommandRepository:
    def __init__(self, store: _InMemoryStore) -> None:
        self._store = store

    def add(self, item: Command) -> Command:
        self._store.commands[item.command_id] = item
        return item

    def update(self, item: Command) -> Command:
        self._store.commands[item.command_id] = item
        return item

    def get(self, command_id: str) -> Command | None:
        return self._store.commands.get(command_id)

    def list_recent(self, *, site_id: str, status: str | None, limit: int) -> Sequence[Command]:
        rows = [row for row in self._store.commands.values() if row.site_id == site_id]
        if status is not None:
            rows = [row for row in rows if row.status.value == status]
        rows.sort(key=lambda row: row.created_at, reverse=True)
        return rows[:limit]

    def count_recent_by_status(self, *, site_id: str, status: str, since: datetime) -> int:
        return sum(
            1
            for row in self._store.commands.values()
            if row.site_id == site_id and row.status.value == status and row.created_at >= since
        )

    def count_queued(self, *, site_id: str) -> int:
        return sum(
            1
            for row in self._store.commands.values()
            if row.site_id == site_id and row.status == CommandStatus.queued
        )

    def find_recent_by_idempotency(
        self,
        *,
        site_id: str,
        idempotency_key: str,
        since: datetime,
    ) -> Command | None:
        rows = [
            row
            for row in self._store.commands.values()
            if row.site_id == site_id
            and row.idempotency_key == idempotency_key
            and row.created_at >= since
        ]
        rows.sort(key=lambda row: row.created_at, reverse=True)
        return rows[0] if rows else None

    def find_recent_by_correlation(
        self,
        *,
        site_id: str,
        correlation_id: str,
        since: datetime,
    ) -> Command | None:
        rows = [
            row
            for row in self._store.commands.values()
            if row.site_id == site_id
            and row.correlation_id == correlation_id
            and row.created_at >= since
        ]
        rows.sort(key=lambda row: row.created_at, reverse=True)
        return rows[0] if rows else None

    def count_pending_for_point(self, *, site_id: str, point_id: str) -> int:
        pending = {CommandStatus.accepted, CommandStatus.queued, CommandStatus.dispatched}
        return sum(
            1
            for row in self._store.commands.values()
            if row.site_id == site_id and row.point_id == point_id and row.status in pending
        )

    def find_inflight_for_point(self, *, site_id: str, point_id: str) -> Command | None:
        for row in self._store.commands.values():
            if (
                row.site_id == site_id
                and row.point_id == point_id
                and row.status == CommandStatus.dispatched
            ):
                return row
        return None

    def find_accepted_for_point(self, *, site_id: str, point_id: str) -> Command | None:
        rows = [
            row
            for row in self._store.commands.values()
            if (
                row.site_id == site_id
                and row.point_id == point_id
                and row.status == CommandStatus.accepted
            )
        ]
        rows.sort(key=lambda row: row.created_at)
        return rows[0] if rows else None

    def next_queue_seq(self, *, site_id: str, point_id: str) -> int:
        max_seq = 0
        for row in self._store.commands.values():
            if (
                row.site_id == site_id
                and row.point_id == point_id
                and row.status == CommandStatus.queued
            ):
                max_seq = max(max_seq, row.queue_seq)
        return max_seq + 1

    def list_queued_for_point(self, *, site_id: str, point_id: str) -> Sequence[Command]:
        rows = [
            row
            for row in self._store.commands.values()
            if (
                row.site_id == site_id
                and row.point_id == point_id
                and row.status == CommandStatus.queued
            )
        ]
        rows.sort(key=lambda row: (row.queue_priority, row.queue_seq, row.created_at))
        return rows

    def list_active_with_deadline_before(
        self,
        *,
        before: datetime,
        limit: int,
    ) -> Sequence[Command]:
        active = {CommandStatus.accepted, CommandStatus.queued, CommandStatus.dispatched}
        rows = [
            row
            for row in self._store.commands.values()
            if row.status in active and row.reconciliation_deadline_at < before
        ]
        rows.sort(key=lambda row: row.reconciliation_deadline_at)
        return rows[:limit]


class InMemoryIncidentHookRepository:
    def __init__(self, store: _InMemoryStore) -> None:
        self._store = store

    def add(self, item: IncidentHookEvent) -> IncidentHookEvent:
        self._store.incidents[item.event_id] = item
        return item

    def list_recent(self, *, limit: int) -> Sequence[IncidentHookEvent]:
        rows = list(self._store.incidents.values())
        rows.sort(key=lambda row: row.created_at, reverse=True)
        return rows[:limit]

    def list_pending_for_delivery(
        self,
        *,
        before: datetime,
        limit: int,
    ) -> Sequence[IncidentHookEvent]:
        rows = [
            row
            for row in self._store.incidents.values()
            if row.delivered_at is None and row.next_attempt_at <= before
        ]
        rows.sort(key=lambda row: row.next_attempt_at)
        return rows[:limit]

    def mark_delivered(self, *, event_id: str, delivered_at: datetime) -> None:
        row = self._store.incidents[event_id]
        self._store.incidents[event_id] = IncidentHookEvent(
            **{**row.__dict__, "delivered_at": delivered_at, "last_error": None}
        )

    def mark_delivery_failed(
        self,
        *,
        event_id: str,
        attempt_count: int,
        next_attempt_at: datetime,
        last_error: str,
    ) -> None:
        row = self._store.incidents[event_id]
        self._store.incidents[event_id] = IncidentHookEvent(
            **{
                **row.__dict__,
                "attempt_count": attempt_count,
                "next_attempt_at": next_attempt_at,
                "last_error": last_error,
            }
        )


class InMemoryBatchLockRepository:
    def __init__(self, store: _InMemoryStore) -> None:
        self._store = store

    def try_acquire(
        self,
        *,
        lease_name: str,
        owner_id: str,
        now: datetime,
        ttl_seconds: int,
    ) -> bool:
        current = self._store.leases.get(lease_name)
        expires_at = now + timedelta(seconds=ttl_seconds)
        if current is None:
            self._store.leases[lease_name] = (owner_id, expires_at)
            return True

        current_owner, current_expires = current
        if current_owner == owner_id or current_expires <= now:
            self._store.leases[lease_name] = (owner_id, expires_at)
            return True
        return False

    def release(self, *, lease_name: str, owner_id: str) -> None:
        current = self._store.leases.get(lease_name)
        if current is None:
            return
        current_owner, _ = current
        if current_owner == owner_id:
            self._store.leases.pop(lease_name, None)


class InMemoryUnitOfWork(UnitOfWork):
    def __init__(self, store: _InMemoryStore | None = None) -> None:
        self._store = store or _InMemoryStore()

    def __enter__(self) -> "InMemoryUnitOfWork":
        self.commands = InMemoryCommandRepository(self._store)
        self.incidents = InMemoryIncidentHookRepository(self._store)
        self.locks = InMemoryBatchLockRepository(self._store)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type:
            self.rollback()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None
