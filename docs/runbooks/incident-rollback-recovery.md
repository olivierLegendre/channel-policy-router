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
2. If incident root cause includes schema drift, rollback one migration step with migrator role:

```bash
export CHANNEL_POLICY_ROUTER_MIGRATOR_DSN='postgresql://svc_channel_policy_router_migrator:***@<host>:<port>/channel_policy_router'
./scripts/migrate_postgres.sh downgrade -1
```

3. Restart SLA evaluator and incident-delivery workers.
4. Resume command intake only after queue policy checks pass.

## Recovery Validation

```bash
source .venv/bin/activate
python scripts/export_openapi.py
ruff check .
mypy src
pytest -m "not postgres_integration"
./scripts/run_postgres_integration_tests.sh
./scripts/migrate_postgres.sh current
python scripts/run_sla_evaluator.py
python scripts/run_incident_delivery_worker.py
```

## Post-Incident

1. Record root cause with command class/channel impact.
2. Link incident hook delivery evidence.
3. Add regression test for failed policy edge case.

## Wave 8 Hardening And Namespace Migration Notes

1. If release is blocked by vulnerability gate, capture the exact HIGH/CRITICAL finding list and either:
- patch and rebuild immediately; or
- apply documented risk acceptance exception before re-run.
2. If keyless OIDC signing/verification fails, treat this as release-blocking identity drift.
3. If namespace migration issues occur (`ghcr.io/ramery/...`), rollback by pinning the last known good immutable tag in deployment manifest and rerun pullability checks.
4. Always attach evidence artifacts (scan output, signature verify output, pullability check result) to incident record.
