# Incident / Rollback / Recovery Runbook

## Scope

Service: `channel-policy-router`
Critical path: command admission, queueing, dispatch, reconciliation, incident hooks.

## Incident Response

1. Identify impacted site(s), command class, and channel policy.
2. Capture queue depth, SLA status, and incident hook backlog.
3. If safety critical path is unstable, block new commands and page immediately.

## Rollback

1. Re-deploy last known good release artifact for `channel-policy-router`.
2. Restart SLA evaluator and incident-delivery workers.
3. Resume command intake only after queue policy checks pass.

## Recovery Validation

```bash
source .venv/bin/activate
python scripts/export_openapi.py
ruff check .
mypy src
pytest -m "not postgres_integration"
./scripts/run_postgres_integration_tests.sh
python scripts/run_sla_evaluator.py
python scripts/run_incident_delivery_worker.py
```

## Post-Incident

1. Record root cause with command class/channel impact.
2. Link incident hook delivery evidence.
3. Add regression test for failed policy edge case.
