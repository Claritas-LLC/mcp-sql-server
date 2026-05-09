from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest

from src.models import AuthConfig
from src.security.auth_provider import AzureEntraTokenVerifier, build_auth_provider


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _jwks_for_public_key(public_key: Any, kid: str) -> dict[str, Any]:
    numbers = public_key.public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "use": "sig",
                "alg": "RS256",
                "n": _b64url_uint(numbers.n),
                "e": _b64url_uint(numbers.e),
            }
        ]
    }


def _sign_token(private_key: Any, *, kid: str, claims: dict[str, Any]) -> str:
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def _mock_http_client(openid_payload: dict[str, Any], jwks_payload: dict[str, Any]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=openid_payload)
        if url == openid_payload["jwks_uri"]:
            return httpx.Response(200, json=jwks_payload)
        return httpx.Response(404, json={"error": "not_found"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_verify_token_accepts_valid_token() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    kid = "k1"
    tenant = "tenant-abc"
    aud = "api://example-resource"
    now = int(time.time())

    openid = {
        "issuer": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "jwks_uri": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
    }
    jwks = _jwks_for_public_key(public_key, kid)
    client = _mock_http_client(openid, jwks)

    verifier = AzureEntraTokenVerifier(
        tenant_id=tenant,
        client_id="client-id",
        identifier_uri=aud,
        required_scopes=["read"],
        http_client=client,
        base_url="https://mcp.example.com",
        group_claim_name="groups",
    )

    token = _sign_token(
        private_key,
        kid=kid,
        claims={
            "iss": openid["issuer"],
            "aud": aud,
            "exp": now + 3600,
            "iat": now,
            "oid": "user-oid",
            "preferred_username": "user@example.com",
            "scp": "read write",
            "groups": ["g-read"],
            "azp": "client-app",
        },
    )

    async def _run() -> Any:
        try:
            return await verifier.verify_token(token)
        finally:
            await client.aclose()

    access = asyncio.run(_run())

    assert access is not None
    assert access.client_id == "client-app"
    assert "read" in access.scopes
    assert access.claims["oid"] == "user-oid"


def test_verify_token_rejects_invalid_audience() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    kid = "k2"
    tenant = "tenant-abc"
    now = int(time.time())

    openid = {
        "issuer": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "jwks_uri": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
    }
    jwks = _jwks_for_public_key(public_key, kid)
    client = _mock_http_client(openid, jwks)

    verifier = AzureEntraTokenVerifier(
        tenant_id=tenant,
        client_id="client-id",
        identifier_uri="api://expected",
        required_scopes=["read"],
        http_client=client,
        base_url="https://mcp.example.com",
        group_claim_name="groups",
    )

    token = _sign_token(
        private_key,
        kid=kid,
        claims={
            "iss": openid["issuer"],
            "aud": "api://wrong",
            "exp": now + 3600,
            "iat": now,
            "scp": "read",
        },
    )

    async def _run() -> Any:
        try:
            return await verifier.verify_token(token)
        finally:
            await client.aclose()

    access = asyncio.run(_run())

    assert access is None


def test_verify_token_rejects_missing_required_scope() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    kid = "k3"
    tenant = "tenant-abc"
    now = int(time.time())

    openid = {
        "issuer": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "jwks_uri": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
    }
    jwks = _jwks_for_public_key(public_key, kid)
    client = _mock_http_client(openid, jwks)

    verifier = AzureEntraTokenVerifier(
        tenant_id=tenant,
        client_id="client-id",
        identifier_uri="api://expected",
        required_scopes=["write"],
        http_client=client,
        base_url="https://mcp.example.com",
        group_claim_name="groups",
    )

    token = _sign_token(
        private_key,
        kid=kid,
        claims={
            "iss": openid["issuer"],
            "aud": "api://expected",
            "exp": now + 3600,
            "iat": now,
            "scp": "read",
        },
    )

    async def _run() -> Any:
        try:
            return await verifier.verify_token(token)
        finally:
            await client.aclose()

    access = asyncio.run(_run())
    assert access is None


def test_verify_token_rejects_expired_token() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    kid = "k4"
    tenant = "tenant-abc"
    now = int(time.time())

    openid = {
        "issuer": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "jwks_uri": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
    }
    jwks = _jwks_for_public_key(public_key, kid)
    client = _mock_http_client(openid, jwks)

    verifier = AzureEntraTokenVerifier(
        tenant_id=tenant,
        client_id="client-id",
        identifier_uri="api://expected",
        required_scopes=["read"],
        http_client=client,
        base_url="https://mcp.example.com",
        group_claim_name="groups",
    )

    token = _sign_token(
        private_key,
        kid=kid,
        claims={
            "iss": openid["issuer"],
            "aud": "api://expected",
            "exp": now - 10,
            "iat": now - 3600,
            "scp": "read",
        },
    )

    async def _run() -> Any:
        try:
            return await verifier.verify_token(token)
        finally:
            await client.aclose()

    access = asyncio.run(_run())
    assert access is None


def test_build_auth_provider_missing_config_raises() -> None:
    cfg = AuthConfig(
        auth_mode="azure_token_verifier",
        azure_auth_enabled=True,
        azure_tenant_id=None,
        azure_client_id=None,
    )

    async def _run() -> None:
        client = httpx.AsyncClient()
        try:
            with pytest.raises(ValueError, match="required settings"):
                build_auth_provider(cfg, client, lambda _r: {})
        finally:
            await client.aclose()

    asyncio.run(_run())


def test_build_auth_provider_returns_verifier_when_enabled() -> None:
    cfg = AuthConfig(
        auth_mode="azure_token_verifier",
        azure_auth_enabled=True,
        azure_tenant_id="tenant-id",
        azure_client_id="client-id",
        azure_identifier_uri="api://resource",
        azure_required_scopes=["read"],
        azure_base_url="https://mcp.example.com",
    )

    async def _run() -> Any:
        client = httpx.AsyncClient()
        try:
            return build_auth_provider(cfg, client, lambda _r: {})
        finally:
            await client.aclose()

    provider = asyncio.run(_run())

    assert isinstance(provider, AzureEntraTokenVerifier)
