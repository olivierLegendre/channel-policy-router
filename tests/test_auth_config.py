from __future__ import annotations

import pytest

from channel_policy_router.security.auth import build_jwt_verifier_config


def test_strict_mode_requires_issuer_and_audience() -> None:
    with pytest.raises(ValueError, match="strict JWT mode requires both issuer and audience"):
        build_jwt_verifier_config(
            secret="dev-wave6-change-me-32-byte-minimum-key",
            issuer=None,
            audience=None,
            require_issuer_audience=True,
            forbid_default_secret=False,
        )


def test_non_strict_mode_allows_missing_issuer_audience() -> None:
    cfg = build_jwt_verifier_config(
        secret="dev-wave6-change-me-32-byte-minimum-key",
        issuer=None,
        audience=None,
        require_issuer_audience=False,
        forbid_default_secret=False,
    )
    assert cfg.issuer is None
    assert cfg.audience is None


def test_strict_mode_accepts_both_issuer_and_audience() -> None:
    cfg = build_jwt_verifier_config(
        secret="dev-wave6-change-me-32-byte-minimum-key",
        issuer="https://idp.example/realms/iot",
        audience="iot-platform",
        require_issuer_audience=True,
        forbid_default_secret=False,
    )
    assert cfg.issuer == "https://idp.example/realms/iot"
    assert cfg.audience == "iot-platform"


def test_non_dev_mode_rejects_default_secret() -> None:
    with pytest.raises(
        ValueError,
        match="non-dev mode requires non-default JWT secret from secret manager",
    ):
        build_jwt_verifier_config(
            secret="dev-wave6-change-me-32-byte-minimum-key",
            issuer="https://idp.example/realms/iot",
            audience="iot-platform",
            require_issuer_audience=True,
            forbid_default_secret=True,
        )
