from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import HTTPException
from jwt import InvalidTokenError


@dataclass(frozen=True)
class JwtVerifierConfig:
    secret: str
    issuer: str | None
    audience: str | None


def decode_bearer_token(authorization: str | None, config: JwtVerifierConfig) -> dict[str, Any]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.split(" ", maxsplit=1)[1].strip()
    decode_kwargs: dict[str, Any] = {}
    if config.audience is not None:
        decode_kwargs["audience"] = config.audience
    if config.issuer is not None:
        decode_kwargs["issuer"] = config.issuer

    try:
        payload = jwt.decode(
            token,
            config.secret,
            algorithms=["HS256"],
            **decode_kwargs,
        )
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid bearer token") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="invalid bearer token")

    return payload


def extract_roles(payload: dict[str, Any]) -> set[str]:
    roles: set[str] = set()

    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict):
        realm_roles = realm_access.get("roles")
        if isinstance(realm_roles, list):
            roles.update(str(item) for item in realm_roles)

    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        for resource in resource_access.values():
            if not isinstance(resource, dict):
                continue
            resource_roles = resource.get("roles")
            if isinstance(resource_roles, list):
                roles.update(str(item) for item in resource_roles)

    root_roles = payload.get("roles")
    if isinstance(root_roles, list):
        roles.update(str(item) for item in root_roles)

    return roles


def require_any_role(
    authorization: str | None,
    *,
    allowed_roles: set[str],
    config: JwtVerifierConfig,
) -> str:
    payload = decode_bearer_token(authorization, config)
    roles = extract_roles(payload)
    intersection = roles & allowed_roles
    if not intersection:
        raise HTTPException(status_code=403, detail="insufficient role for command mutation")
    return sorted(intersection)[0]
