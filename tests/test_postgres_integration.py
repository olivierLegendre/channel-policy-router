import os

import pytest
from fastapi.testclient import TestClient

from channel_policy_router.main import create_app


@pytest.mark.postgres_integration
def test_postgres_submit_dispatch_reconcile(monkeypatch: pytest.MonkeyPatch) -> None:
    dsn = os.getenv("CHANNEL_POLICY_ROUTER_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("CHANNEL_POLICY_ROUTER_TEST_POSTGRES_DSN is not set")

    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_PERSISTENCE_BACKEND", "postgres")
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_POSTGRES_DSN", dsn)
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_POSTGRES_AUTO_INIT", "true")

    client = TestClient(create_app())
    created = client.post(
        "/api/v1/commands",
        json={
            "organization_id": "org-pg",
            "site_id": "site-pg",
            "point_id": "point-pg",
            "command_class": "interactive_control",
            "payload": {"target": 19},
            "idempotency_key": "idem-pg",
            "correlation_id": "corr-pg",
        },
    )
    assert created.status_code == 202
    command_id = created.json()["command"]["command_id"]

    dispatched = client.post(
        "/api/v1/dispatch-next",
        json={"site_id": "site-pg", "point_id": "point-pg"},
    )
    assert dispatched.status_code == 200

    reconciled = client.post(
        f"/api/v1/commands/{command_id}/reconcile",
        json={"observed_match": True},
    )
    assert reconciled.status_code == 200
    assert reconciled.json()["status"] == "applied_confirmed"
