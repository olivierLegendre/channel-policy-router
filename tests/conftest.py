import pytest
from fastapi.testclient import TestClient

from channel_policy_router.main import create_app


@pytest.fixture
def in_memory_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_PERSISTENCE_BACKEND", "in_memory")
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_POSTGRES_AUTO_INIT", "false")
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_SLA_DEADLINE_OFFSET_SECONDS", "0")
    app = create_app()
    with TestClient(app) as client:
        yield client
