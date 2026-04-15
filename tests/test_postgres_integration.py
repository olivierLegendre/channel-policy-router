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
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_POSTGRES_AUTO_INIT", "false")

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


@pytest.mark.postgres_integration
def test_postgres_site_scope_isolation_for_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    dsn = os.getenv("CHANNEL_POLICY_ROUTER_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("CHANNEL_POLICY_ROUTER_TEST_POSTGRES_DSN is not set")

    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_PERSISTENCE_BACKEND", "postgres")
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_POSTGRES_DSN", dsn)
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_POSTGRES_AUTO_INIT", "false")

    client = TestClient(create_app())

    create_a = client.post(
        "/api/v1/commands",
        json={
            "organization_id": "org-a",
            "site_id": "site-a",
            "point_id": "point-1",
            "command_class": "interactive_control",
            "payload": {"target": 21},
            "idempotency_key": "idem-site-a",
        },
    )
    assert create_a.status_code == 202
    cmd_a = create_a.json()["command"]["command_id"]

    create_b = client.post(
        "/api/v1/commands",
        json={
            "organization_id": "org-b",
            "site_id": "site-b",
            "point_id": "point-2",
            "command_class": "interactive_control",
            "payload": {"target": 22},
            "idempotency_key": "idem-site-b",
        },
    )
    assert create_b.status_code == 202
    cmd_b = create_b.json()["command"]["command_id"]

    listed_a = client.get("/api/v1/commands", params={"site_id": "site-a", "limit": 50})
    assert listed_a.status_code == 200
    ids_a = {row["command_id"] for row in listed_a.json()["items"]}
    assert cmd_a in ids_a
    assert cmd_b not in ids_a

    listed_b = client.get("/api/v1/commands", params={"site_id": "site-b", "limit": 50})
    assert listed_b.status_code == 200
    ids_b = {row["command_id"] for row in listed_b.json()["items"]}
    assert cmd_b in ids_b
    assert cmd_a not in ids_b
