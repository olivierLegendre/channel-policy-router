from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from psycopg import connect
from psycopg.connection import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from channel_policy_router.application.uow import UnitOfWork
from channel_policy_router.domain.entities import (
    Channel,
    Command,
    CommandClass,
    CommandStatus,
    IncidentHookEvent,
)


def _sql_path() -> Path:
    return Path(__file__).resolve().parents[4] / "scripts" / "init_postgres.sql"


def ensure_schema(dsn: str) -> None:
    sql = _sql_path().read_text(encoding="utf-8")
    with connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def _to_command(row: dict) -> Command:
    return Command(
        command_id=row["command_id"],
        organization_id=row["organization_id"],
        site_id=row["site_id"],
        point_id=row["point_id"],
        command_class=CommandClass(row["command_class"]),
        status=CommandStatus(row["status"]),
        requested_channel=Channel(row["requested_channel"]),
        effective_channel=Channel(row["effective_channel"]),
        idempotency_key=row["idempotency_key"],
        correlation_id=row["correlation_id"],
        payload=row["payload_json"] or {},
        parent_command_id=row["parent_command_id"],
        queue_priority=row["queue_priority"],
        queue_seq=row["queue_seq"],
        override_reason=row["override_reason"],
        reconciliation_deadline_at=row["reconciliation_deadline_at"],
        dispatched_at=row["dispatched_at"],
        completed_at=row["completed_at"],
        result_reason=row["result_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_incident(row: dict) -> IncidentHookEvent:
    return IncidentHookEvent(
        event_id=row["event_id"],
        command_id=row["command_id"],
        organization_id=row["organization_id"],
        site_id=row["site_id"],
        severity=row["severity"],
        reason=row["reason"],
        manual_action_required=row["manual_action_required"],
        payload=row["payload_json"] or {},
        attempt_count=row["attempt_count"],
        next_attempt_at=row["next_attempt_at"],
        delivered_at=row["delivered_at"],
        last_error=row["last_error"],
        created_at=row["created_at"],
    )


class PostgresCommandRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def add(self, item: Command) -> Command:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO commands (
                    command_id,
                    organization_id,
                    site_id,
                    point_id,
                    command_class,
                    status,
                    requested_channel,
                    effective_channel,
                    idempotency_key,
                    correlation_id,
                    payload_json,
                    parent_command_id,
                    queue_priority,
                    queue_seq,
                    override_reason,
                    reconciliation_deadline_at,
                    dispatched_at,
                    completed_at,
                    result_reason,
                    created_at,
                    updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    item.command_id,
                    item.organization_id,
                    item.site_id,
                    item.point_id,
                    item.command_class.value,
                    item.status.value,
                    item.requested_channel.value,
                    item.effective_channel.value,
                    item.idempotency_key,
                    item.correlation_id,
                    Jsonb(item.payload),
                    item.parent_command_id,
                    item.queue_priority,
                    item.queue_seq,
                    item.override_reason,
                    item.reconciliation_deadline_at,
                    item.dispatched_at,
                    item.completed_at,
                    item.result_reason,
                    item.created_at,
                    item.updated_at,
                ),
            )
        return item

    def update(self, item: Command) -> Command:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE commands
                SET
                  status = %s,
                  effective_channel = %s,
                  override_reason = %s,
                  dispatched_at = %s,
                  completed_at = %s,
                  result_reason = %s,
                  updated_at = %s
                WHERE command_id = %s
                """,
                (
                    item.status.value,
                    item.effective_channel.value,
                    item.override_reason,
                    item.dispatched_at,
                    item.completed_at,
                    item.result_reason,
                    item.updated_at,
                    item.command_id,
                ),
            )
        return item

    def get(self, command_id: str) -> Command | None:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM commands WHERE command_id = %s", (command_id,))
            row = cur.fetchone()
        return _to_command(row) if row else None

    def find_recent_by_idempotency(
        self,
        *,
        site_id: str,
        idempotency_key: str,
        since: datetime,
    ) -> Command | None:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM commands
                WHERE site_id = %s
                  AND idempotency_key = %s
                  AND created_at >= %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (site_id, idempotency_key, since),
            )
            row = cur.fetchone()
        return _to_command(row) if row else None

    def find_recent_by_correlation(
        self,
        *,
        site_id: str,
        correlation_id: str,
        since: datetime,
    ) -> Command | None:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM commands
                WHERE site_id = %s
                  AND correlation_id = %s
                  AND created_at >= %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (site_id, correlation_id, since),
            )
            row = cur.fetchone()
        return _to_command(row) if row else None

    def count_pending_for_point(self, *, site_id: str, point_id: str) -> int:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT count(*) AS c
                FROM commands
                WHERE site_id = %s
                  AND point_id = %s
                  AND status IN ('accepted', 'queued', 'dispatched')
                """,
                (site_id, point_id),
            )
            row = cur.fetchone()
        return int(row["c"]) if row else 0

    def find_inflight_for_point(self, *, site_id: str, point_id: str) -> Command | None:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM commands
                WHERE site_id = %s
                  AND point_id = %s
                  AND status = 'dispatched'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (site_id, point_id),
            )
            row = cur.fetchone()
        return _to_command(row) if row else None

    def find_accepted_for_point(self, *, site_id: str, point_id: str) -> Command | None:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM commands
                WHERE site_id = %s
                  AND point_id = %s
                  AND status = 'accepted'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (site_id, point_id),
            )
            row = cur.fetchone()
        return _to_command(row) if row else None

    def next_queue_seq(self, *, site_id: str, point_id: str) -> int:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT COALESCE(max(queue_seq), 0) + 1 AS seq
                FROM commands
                WHERE site_id = %s
                  AND point_id = %s
                  AND status = 'queued'
                """,
                (site_id, point_id),
            )
            row = cur.fetchone()
        return int(row["seq"]) if row else 1

    def list_queued_for_point(self, *, site_id: str, point_id: str) -> Sequence[Command]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM commands
                WHERE site_id = %s
                  AND point_id = %s
                  AND status = 'queued'
                ORDER BY queue_priority ASC, queue_seq ASC, created_at ASC
                """,
                (site_id, point_id),
            )
            rows = cur.fetchall()
        return [_to_command(row) for row in rows]

    def list_active_with_deadline_before(
        self,
        *,
        before: datetime,
        limit: int,
    ) -> Sequence[Command]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM commands
                WHERE status IN ('accepted', 'queued', 'dispatched')
                  AND reconciliation_deadline_at < %s
                ORDER BY reconciliation_deadline_at ASC
                LIMIT %s
                """,
                (before, limit),
            )
            rows = cur.fetchall()
        return [_to_command(row) for row in rows]


class PostgresIncidentHookRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def add(self, item: IncidentHookEvent) -> IncidentHookEvent:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incident_hook_events (
                    event_id,
                    command_id,
                    organization_id,
                    site_id,
                    severity,
                    reason,
                    manual_action_required,
                    payload_json,
                    attempt_count,
                    next_attempt_at,
                    delivered_at,
                    last_error,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    item.event_id,
                    item.command_id,
                    item.organization_id,
                    item.site_id,
                    item.severity,
                    item.reason,
                    item.manual_action_required,
                    Jsonb(item.payload),
                    item.attempt_count,
                    item.next_attempt_at,
                    item.delivered_at,
                    item.last_error,
                    item.created_at,
                ),
            )
        return item

    def list_recent(self, *, limit: int) -> Sequence[IncidentHookEvent]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM incident_hook_events
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [_to_incident(row) for row in rows]

    def list_pending_for_delivery(
        self,
        *,
        before: datetime,
        limit: int,
    ) -> Sequence[IncidentHookEvent]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM incident_hook_events
                WHERE delivered_at IS NULL
                  AND next_attempt_at <= %s
                ORDER BY next_attempt_at ASC
                LIMIT %s
                """,
                (before, limit),
            )
            rows = cur.fetchall()
        return [_to_incident(row) for row in rows]

    def mark_delivered(self, *, event_id: str, delivered_at: datetime) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE incident_hook_events
                SET delivered_at = %s,
                    last_error = NULL
                WHERE event_id = %s
                """,
                (delivered_at, event_id),
            )

    def mark_delivery_failed(
        self,
        *,
        event_id: str,
        attempt_count: int,
        next_attempt_at: datetime,
        last_error: str,
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE incident_hook_events
                SET attempt_count = %s,
                    next_attempt_at = %s,
                    last_error = %s
                WHERE event_id = %s
                """,
                (attempt_count, next_attempt_at, last_error, event_id),
            )


class PostgresBatchLockRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def try_acquire(
        self,
        *,
        lease_name: str,
        owner_id: str,
        now: datetime,
        ttl_seconds: int,
    ) -> bool:
        expires_at = now + timedelta(seconds=ttl_seconds)
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO batch_leases (lease_name, owner_id, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (lease_name)
                DO UPDATE SET
                  owner_id = EXCLUDED.owner_id,
                  expires_at = EXCLUDED.expires_at
                WHERE batch_leases.expires_at <= %s
                   OR batch_leases.owner_id = EXCLUDED.owner_id
                RETURNING owner_id
                """,
                (lease_name, owner_id, expires_at, now),
            )
            row = cur.fetchone()
        return row is not None and row["owner_id"] == owner_id

    def release(self, *, lease_name: str, owner_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM batch_leases
                WHERE lease_name = %s
                  AND owner_id = %s
                """,
                (lease_name, owner_id),
            )


class PostgresUnitOfWork(UnitOfWork):
    def __init__(self, dsn: str, auto_init_schema: bool = True) -> None:
        self._dsn = dsn
        self._auto_init_schema = auto_init_schema
        self._schema_initialized = False
        self._conn: Connection | None = None

    def __enter__(self) -> "PostgresUnitOfWork":
        if self._auto_init_schema and not self._schema_initialized:
            ensure_schema(self._dsn)
            self._schema_initialized = True
        self._conn = connect(self._dsn)
        self.commands = PostgresCommandRepository(self._conn)
        self.incidents = PostgresIncidentHookRepository(self._conn)
        self.locks = PostgresBatchLockRepository(self._conn)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._conn is None:
            return
        if exc_type:
            self.rollback()
        self._conn.close()
        self._conn = None

    def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()
