from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from channel_policy_router.main import create_app


def test_healthz(in_memory_client: TestClient) -> None:
    r = in_memory_client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_safety_requires_idempotency_and_correlation(in_memory_client: TestClient) -> None:
    body = {
        "organization_id": "org-1",
        "site_id": "site-1",
        "point_id": "p-1",
        "command_class": "safety_critical",
        "payload": {"target": "off"},
    }
    r = in_memory_client.post("/api/v1/commands", json=body)
    assert r.status_code == 422


def test_non_safety_generates_missing_keys(in_memory_client: TestClient) -> None:
    body = {
        "organization_id": "org-1",
        "site_id": "site-1",
        "point_id": "p-1",
        "command_class": "interactive_control",
        "payload": {"target": 20},
    }
    r = in_memory_client.post("/api/v1/commands", json=body)
    assert r.status_code == 202
    payload = r.json()
    assert payload["generated_idempotency_key"]
    assert payload["generated_correlation_id"]


def test_idempotency_deduplicates_per_site(in_memory_client: TestClient) -> None:
    body = {
        "organization_id": "org-1",
        "site_id": "site-1",
        "point_id": "p-1",
        "command_class": "routine_automation",
        "payload": {"target": "on"},
        "idempotency_key": "idem-1",
        "correlation_id": "corr-a",
    }
    first = in_memory_client.post("/api/v1/commands", json=body)
    assert first.status_code == 202
    second = in_memory_client.post("/api/v1/commands", json={**body, "correlation_id": "corr-b"})
    assert second.status_code == 202
    assert second.json()["duplicate_of"] == first.json()["command"]["command_id"]


def test_correlation_conflict_returns_409(in_memory_client: TestClient) -> None:
    body = {
        "organization_id": "org-1",
        "site_id": "site-1",
        "point_id": "p-1",
        "command_class": "interactive_control",
        "payload": {"target": 21},
        "idempotency_key": "idem-2",
        "correlation_id": "corr-dup",
    }
    first = in_memory_client.post("/api/v1/commands", json=body)
    assert first.status_code == 202
    second = in_memory_client.post("/api/v1/commands", json={**body, "idempotency_key": "idem-3"})
    assert second.status_code == 409


def test_queue_overflow_503_and_retry_after(in_memory_client: TestClient) -> None:
    for i in range(5):
        r = in_memory_client.post(
            "/api/v1/commands",
            json={
                "organization_id": "org-1",
                "site_id": "site-1",
                "point_id": "p-over",
                "command_class": "interactive_control",
                "payload": {"target": i},
                "idempotency_key": f"idem-over-{i}",
                "correlation_id": f"corr-over-{i}",
            },
        )
        assert r.status_code == 202

    overflow = in_memory_client.post(
        "/api/v1/commands",
        json={
            "organization_id": "org-1",
            "site_id": "site-1",
            "point_id": "p-over",
            "command_class": "interactive_control",
            "payload": {"target": 999},
            "idempotency_key": "idem-over-x",
            "correlation_id": "corr-over-x",
        },
    )
    assert overflow.status_code == 503
    assert overflow.headers["Retry-After"] == "30"


def test_safety_is_prioritized_in_queue(in_memory_client: TestClient) -> None:
    # first accepted, next queued
    for i in range(2):
        in_memory_client.post(
            "/api/v1/commands",
            json={
                "organization_id": "org-1",
                "site_id": "site-q",
                "point_id": "p-q",
                "command_class": "interactive_control",
                "payload": {"target": i},
                "idempotency_key": f"idem-q-{i}",
                "correlation_id": f"corr-q-{i}",
            },
        )

    in_memory_client.post(
        "/api/v1/commands",
        json={
            "organization_id": "org-1",
            "site_id": "site-q",
            "point_id": "p-q",
            "command_class": "safety_critical",
            "payload": {"target": "off"},
            "idempotency_key": "idem-q-safety",
            "correlation_id": "corr-q-safety",
        },
    )

    queue = in_memory_client.get("/api/v1/queue", params={"site_id": "site-q", "point_id": "p-q"})
    assert queue.status_code == 200
    items = queue.json()["items"]
    assert items[0]["command_class"] == "safety_critical"


def test_cancel_allowed_only_before_dispatch(in_memory_client: TestClient) -> None:
    submitted = in_memory_client.post(
        "/api/v1/commands",
        json={
            "organization_id": "org-1",
            "site_id": "site-1",
            "point_id": "p-can",
            "command_class": "interactive_control",
            "payload": {"target": 1},
            "idempotency_key": "idem-can",
            "correlation_id": "corr-can",
        },
    )
    assert submitted.status_code == 202
    command_id = submitted.json()["command"]["command_id"]

    cancel = in_memory_client.post(f"/api/v1/commands/{command_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "canceled"


def test_dispatch_and_reconcile_success(in_memory_client: TestClient) -> None:
    submitted = in_memory_client.post(
        "/api/v1/commands",
        json={
            "organization_id": "org-1",
            "site_id": "site-d",
            "point_id": "p-d",
            "command_class": "interactive_control",
            "payload": {"target": 22},
            "idempotency_key": "idem-d",
            "correlation_id": "corr-d",
        },
    )
    command_id = submitted.json()["command"]["command_id"]

    dispatched = in_memory_client.post(
        "/api/v1/dispatch-next",
        json={"site_id": "site-d", "point_id": "p-d"},
    )
    assert dispatched.status_code == 200
    assert dispatched.json()["status"] == "dispatched"

    reconciled = in_memory_client.post(
        f"/api/v1/commands/{command_id}/reconcile",
        json={"observed_match": True},
    )
    assert reconciled.status_code == 200
    assert reconciled.json()["status"] == "applied_confirmed"


def test_deadline_serialization_is_present(in_memory_client: TestClient) -> None:
    submitted = in_memory_client.post(
        "/api/v1/commands",
        json={
            "organization_id": "org-1",
            "site_id": "site-ts",
            "point_id": "p-ts",
            "command_class": "bulk_non_critical",
            "payload": {"target": "eco"},
            "idempotency_key": "idem-ts",
            "correlation_id": "corr-ts",
        },
    )
    assert submitted.status_code == 202
    cmd = submitted.json()["command"]
    deadline = datetime.fromisoformat(cmd["reconciliation_deadline_at"].replace("Z", "+00:00"))
    assert deadline > datetime.now(tz=UTC) - timedelta(seconds=5)


def test_batch_sla_evaluator_and_incident_hook_for_safety(monkeypatch) -> None:
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_PERSISTENCE_BACKEND", "in_memory")
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_POSTGRES_AUTO_INIT", "false")
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_SLA_DEADLINE_OFFSET_SECONDS", "-120")

    with TestClient(create_app()) as client:
        submitted = client.post(
            "/api/v1/commands",
            json={
                "organization_id": "org-1",
                "site_id": "site-sla",
                "point_id": "p-sla",
                "command_class": "safety_critical",
                "payload": {"target": "off"},
                "idempotency_key": "idem-sla",
                "correlation_id": "corr-sla",
            },
        )
        assert submitted.status_code == 202

        batch = client.post("/api/v1/sla/evaluate", json={"limit": 100})
        assert batch.status_code == 200
        body = batch.json()
        assert body["lock_acquired"] is True
        assert body["breached_count"] >= 1
        assert body["items"][0]["alert_required"] is True
        assert body["items"][0]["manual_action_required"] is True

        hooks = client.get("/api/v1/incidents/hooks", params={"limit": 20})
        assert hooks.status_code == 200
        rows = hooks.json()
        assert rows
        assert rows[0]["reason"] == "safety_critical_sla_breach"


def test_incident_delivery_retry_and_backoff(monkeypatch) -> None:
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_PERSISTENCE_BACKEND", "in_memory")
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_POSTGRES_AUTO_INIT", "false")
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_SLA_DEADLINE_OFFSET_SECONDS", "-120")
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_INCIDENT_DELIVERY_BACKOFF_BASE_SECONDS", "5")

    with TestClient(create_app()) as client:
        fail_cmd = client.post(
            "/api/v1/commands",
            json={
                "organization_id": "org-1",
                "site_id": "site-delivery",
                "point_id": "p-delivery-1",
                "command_class": "safety_critical",
                "payload": {"target": "off", "simulate_delivery_failure": True},
                "idempotency_key": "idem-delivery-1",
                "correlation_id": "corr-delivery-1",
            },
        )
        assert fail_cmd.status_code == 202
        client.post("/api/v1/sla/evaluate", json={"limit": 100})

        first_delivery = client.post("/api/v1/incidents/hooks/deliver", json={"limit": 100})
        assert first_delivery.status_code == 200
        assert first_delivery.json()["lock_acquired"] is True
        assert first_delivery.json()["failed_count"] >= 1

        success_cmd = client.post(
            "/api/v1/commands",
            json={
                "organization_id": "org-1",
                "site_id": "site-delivery",
                "point_id": "p-delivery-2",
                "command_class": "safety_critical",
                "payload": {"target": "off"},
                "idempotency_key": "idem-delivery-2",
                "correlation_id": "corr-delivery-2",
            },
        )
        assert success_cmd.status_code == 202
        client.post("/api/v1/sla/evaluate", json={"limit": 100})

        second_delivery = client.post("/api/v1/incidents/hooks/deliver", json={"limit": 100})
        assert second_delivery.status_code == 200
        assert second_delivery.json()["delivered_count"] >= 1

        hooks = client.get("/api/v1/incidents/hooks", params={"limit": 20})
        assert hooks.status_code == 200
        rows = hooks.json()
        assert rows[0]["attempt_count"] >= 0
