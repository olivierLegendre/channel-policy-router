# channel-policy-router

Wave 4 command and safety plane service.

## Scope (Wave 4 baseline)

- Command class policy matrix (API primary, MQTT fallback by class).
- Idempotency and correlation constraints by site.
- Queue depth guardrails (`503` + `Retry-After`) and safety-priority queue ordering.
- Cancel-before-dispatch and restricted channel override.
- Dispatch/reconciliation state transitions and SLA check endpoint.
- Batch SLA evaluator + safety incident-hook events.

## Setup

```bash
PYTHON_BIN=python3.12 ./scripts/setup_dev.sh
source .venv/bin/activate
```

## Run

```bash
uvicorn channel_policy_router.main:app --reload
```

## Endpoints

- `POST /api/v1/commands`
- `GET /api/v1/commands/{command_id}`
- `POST /api/v1/commands/{command_id}/cancel`
- `POST /api/v1/commands/{command_id}/override-channel`
- `POST /api/v1/dispatch-next`
- `POST /api/v1/commands/{command_id}/reconcile`
- `POST /api/v1/commands/{command_id}/check-sla`
- `POST /api/v1/sla/evaluate`
- `GET /api/v1/incidents/hooks`
- `GET /api/v1/policy/{command_class}`
- `GET /api/v1/queue`
- `GET /healthz`

## Test

```bash
python scripts/export_openapi.py
ruff check .
mypy src
pytest -m "not postgres_integration"
```

PostgreSQL integration tests:

```bash
./scripts/run_postgres_integration_tests.sh
```
