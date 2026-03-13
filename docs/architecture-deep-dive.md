# Channel Policy Router - Architecture Deep Dive

Status: Active (Wave 4)
Last updated: 2026-03-13

## What this service owns

- Command class policy matrix and channel selection constraints.
- Safety validations (`422` for missing safety idempotency/correlation).
- Queue protection (max depth 5, `503`, `Retry-After: 30`).
- Idempotency dedupe per site (1 hour) and correlation uniqueness per site (24 hours).
- Safety queue prioritization without in-flight preemption.
- Dispatch and reconciliation state machine with SLA check endpoint.
- Batch SLA evaluator and safety incident-hook emission.

## State machine

`accepted|queued -> dispatched -> applied_confirmed|failed`

Rules:
- `cancel` allowed only in `accepted|queued`.
- `reconcile` allowed only in `dispatched`.
- `check-sla` marks active commands as `failed` when deadline is breached.

## Main architectural choices

1. Hexagonal split:
- inbound HTTP adapter
- application use cases
- domain entities/rules
- in-memory + PostgreSQL outbound repositories

2. Deterministic policy matrix:
- encoded in `application/policy.py` to match V1 specification.

3. Queue ordering model:
- `queue_priority=0` for `safety_critical`, `1` otherwise.
- queued list ordered by `(priority, seq, created_at)`.

4. Transport boundary:
- this service decides channel policy and command state, but does not execute external transport itself.

## Step 3 additions (current)

- Batch endpoint: `POST /api/v1/sla/evaluate`.
- Script for scheduler/cron usage: `scripts/run_sla_evaluator.py`.
- Safety SLA breach produces persisted incident-hook event.
- Incident hook read endpoint: `GET /api/v1/incidents/hooks`.
- Incident delivery endpoint: `POST /api/v1/incidents/hooks/deliver`.
- Delivery retry/backoff policy persisted per event (`attempt_count`, `next_attempt_at`, `last_error`).
- Lease-based batch locking via `batch_leases` to avoid multi-runner overlap.

## Lease/Lock behavior

Two logical leases:
- `sla_evaluator`
- `incident_delivery`

Acquire behavior:
- worker attempts to acquire lease with TTL.
- if active lease owned by another worker and not expired, batch returns `lock_acquired=false`.
- after batch execution, lease is released.

## Incident delivery behavior

- Delivery worker reads pending events where `delivered_at IS NULL` and `next_attempt_at <= now`.
- Success marks event as delivered.
- Failure increments `attempt_count`, writes `last_error`, and schedules `next_attempt_at` with exponential backoff:
  `min(base * 2^(attempt-1), max)`.

## Next expansion for Wave 4 completion

- Wire incident hook to notifications-service and incident manager.
- Add outbox-backed external delivery channel instead of in-process simulation.
- Add delivery metrics and alerting (stuck pending events, high retry counts).
