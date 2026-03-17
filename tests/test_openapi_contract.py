import json
from pathlib import Path

import pytest

from channel_policy_router.main import create_app

EXPECTED_PATHS = {
    "/healthz",
    "/api/v1/commands",
    "/api/v1/commands/{command_id}/reissue",
    "/api/v1/commands/{command_id}",
    "/api/v1/commands/{command_id}/cancel",
    "/api/v1/commands/{command_id}/override-channel",
    "/api/v1/commands/{command_id}/reconcile",
    "/api/v1/commands/{command_id}/check-sla",
    "/api/v1/policy/{command_class}",
    "/api/v1/queue",
    "/api/v1/dispatch-next",
    "/api/v1/sla/evaluate",
    "/api/v1/incidents/hooks",
    "/api/v1/governance/snapshot",
    "/api/v1/incidents/hooks/deliver",
}


def test_openapi_contains_expected_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_PERSISTENCE_BACKEND", "in_memory")
    app = create_app()
    schema = app.openapi()
    assert EXPECTED_PATHS.issubset(schema["paths"].keys())


def test_openapi_contract_file_exists_and_is_consistent(monkeypatch: pytest.MonkeyPatch) -> None:
    contract_path = Path(__file__).resolve().parent.parent / "contracts" / "openapi-v1.json"
    assert contract_path.exists(), "Run scripts/export_openapi.py to create the contract file"

    monkeypatch.setenv("CHANNEL_POLICY_ROUTER_PERSISTENCE_BACKEND", "in_memory")
    app = create_app()
    current = app.openapi()
    baseline = json.loads(contract_path.read_text(encoding="utf-8"))

    assert set(current["paths"].keys()) == set(baseline["paths"].keys())
