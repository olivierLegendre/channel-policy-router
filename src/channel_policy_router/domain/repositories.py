from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from channel_policy_router.domain.entities import Command, IncidentHookEvent


class CommandRepository(Protocol):
    def add(self, item: Command) -> Command: ...

    def update(self, item: Command) -> Command: ...

    def get(self, command_id: str) -> Command | None: ...

    def list_recent(
        self,
        *,
        site_id: str,
        status: str | None,
        limit: int,
    ) -> Sequence[Command]: ...

    def count_recent_by_status(
        self,
        *,
        site_id: str,
        status: str,
        since: datetime,
    ) -> int: ...

    def count_queued(self, *, site_id: str) -> int: ...

    def find_recent_by_idempotency(
        self,
        *,
        site_id: str,
        idempotency_key: str,
        since: datetime,
    ) -> Command | None: ...

    def find_recent_by_correlation(
        self,
        *,
        site_id: str,
        correlation_id: str,
        since: datetime,
    ) -> Command | None: ...

    def count_pending_for_point(self, *, site_id: str, point_id: str) -> int: ...

    def find_inflight_for_point(self, *, site_id: str, point_id: str) -> Command | None: ...

    def find_accepted_for_point(self, *, site_id: str, point_id: str) -> Command | None: ...

    def next_queue_seq(self, *, site_id: str, point_id: str) -> int: ...

    def list_queued_for_point(self, *, site_id: str, point_id: str) -> Sequence[Command]: ...

    def list_active_with_deadline_before(
        self,
        *,
        before: datetime,
        limit: int,
    ) -> Sequence[Command]: ...


class IncidentHookRepository(Protocol):
    def add(self, item: IncidentHookEvent) -> IncidentHookEvent: ...

    def list_recent(self, *, limit: int) -> Sequence[IncidentHookEvent]: ...

    def list_pending_for_delivery(
        self,
        *,
        before: datetime,
        limit: int,
    ) -> Sequence[IncidentHookEvent]: ...

    def mark_delivered(self, *, event_id: str, delivered_at: datetime) -> None: ...

    def mark_delivery_failed(
        self,
        *,
        event_id: str,
        attempt_count: int,
        next_attempt_at: datetime,
        last_error: str,
    ) -> None: ...


class BatchLockRepository(Protocol):
    def try_acquire(
        self,
        *,
        lease_name: str,
        owner_id: str,
        now: datetime,
        ttl_seconds: int,
    ) -> bool: ...

    def release(self, *, lease_name: str, owner_id: str) -> None: ...
