from __future__ import annotations

import json
import time
from typing import Any, Callable

import httpx
import jwt
from fastmcp.server.auth import AccessToken, TokenVerifier

from src.models import AuthConfig


class AzureEntraTokenVerifier(TokenVerifier):
    """Validates Azure Entra bearer tokens using OIDC discovery + JWKS."""

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        identifier_uri: str | None,
        required_scopes: list[str] | None,
        http_client: httpx.AsyncClient,
        base_url: str | None,
        group_claim_name: str,
        config_cache_ttl_sec: int = 300,
    ) -> None:
        super().__init__(base_url=base_url, required_scopes=required_scopes)
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._identifier_uri = identifier_uri
        self._http_client = http_client
        self._group_claim_name = group_claim_name
        self._config_cache_ttl_sec = config_cache_ttl_sec
        self._openid_config_cache: dict[str, Any] | None = None
        self._openid_config_cache_at: float = 0.0
        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_cache_at: float = 0.0

    @property
    def scopes_supported(self) -> list[str]:
        return self.required_scopes or []

    def _discovery_url(self) -> str:
        return f"https://login.microsoftonline.com/{self._tenant_id}/v2.0/.well-known/openid-configuration"

    async def _get_openid_config(self) -> dict[str, Any]:
        now = time.time()
        if self._openid_config_cache and (now - self._openid_config_cache_at) < self._config_cache_ttl_sec:
            return self._openid_config_cache

        response = await self._http_client.get(self._discovery_url())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("jwks_uri") or not payload.get("issuer"):
            raise ValueError("Azure OpenID configuration is missing required fields")
        self._openid_config_cache = payload
        self._openid_config_cache_at = now
        return payload

    async def _get_jwks(self, jwks_uri: str, force_refresh: bool = False) -> dict[str, Any]:
        now = time.time()
        if (
            not force_refresh
            and self._jwks_cache
            and (now - self._jwks_cache_at) < self._config_cache_ttl_sec
        ):
            return self._jwks_cache

        response = await self._http_client.get(jwks_uri)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise ValueError("Azure JWKS payload is invalid")
        self._jwks_cache = payload
        self._jwks_cache_at = now
        return payload

    @staticmethod
    def _extract_scopes(claims: dict[str, Any]) -> list[str]:
        value = claims.get("scp")
        if isinstance(value, str):
            return [scope.strip() for scope in value.split(" ") if scope.strip()]
        return []

    def _validate_required_scopes(self, scopes: list[str]) -> bool:
        required = self.required_scopes or []
        if not required:
            return True
        token_scopes = set(scopes)
        return all(scope in token_scopes for scope in required)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            return None

        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg")
        if not kid or not alg:
            return None

        try:
            openid_config = await self._get_openid_config()
            jwks_uri = str(openid_config["jwks_uri"])
            issuer = str(openid_config["issuer"])
        except Exception:
            return None

        try:
            jwks = await self._get_jwks(jwks_uri)
            key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
            if key_data is None:
                jwks = await self._get_jwks(jwks_uri, force_refresh=True)
                key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
            if key_data is None:
                return None

            signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
            audience = self._identifier_uri or self._client_id
            claims = jwt.decode(
                token,
                key=signing_key,
                algorithms=[str(alg)],
                audience=audience,
                issuer=issuer,
                options={"require": ["exp", "iss", "aud"]},
            )
            if not isinstance(claims, dict):
                return None
        except jwt.PyJWTError:
            return None
        except Exception:
            return None

        scopes = self._extract_scopes(claims)
        if not self._validate_required_scopes(scopes):
            return None

        # Preserve group claim for downstream privilege mapping in later phases.
        if self._group_claim_name and self._group_claim_name not in claims:
            claims[self._group_claim_name] = []

        expires_at = claims.get("exp")
        client_id = claims.get("azp") or claims.get("appid") or claims.get("aud") or self._client_id
        return AccessToken(
            token=token,
            client_id=str(client_id),
            scopes=scopes,
            expires_at=int(expires_at) if isinstance(expires_at, (int, float)) else None,
            claims=claims,
        )


def build_auth_provider(
    auth_config: AuthConfig,
    http_client: httpx.AsyncClient,
    secret_resolver: Callable[[str], dict[str, str]],
) -> Any:
    """Build MCP auth provider from runtime config."""
    _ = secret_resolver

    if not auth_config.azure_auth_enabled and auth_config.auth_mode == "disabled":
        return None

    if auth_config.auth_mode not in {"azure_token_verifier", "disabled"}:
        raise ValueError(f"Unsupported auth_mode: {auth_config.auth_mode}")

    if not (auth_config.azure_auth_enabled or auth_config.auth_mode == "azure_token_verifier"):
        return None

    missing: list[str] = []
    if not auth_config.azure_tenant_id:
        missing.append("azure_tenant_id")
    if not auth_config.azure_client_id:
        missing.append("azure_client_id")
    if missing:
        raise ValueError(
            "Azure Entra auth is enabled but required settings are missing: " + ", ".join(missing)
        )

    return AzureEntraTokenVerifier(
        tenant_id=auth_config.azure_tenant_id,
        client_id=auth_config.azure_client_id,
        identifier_uri=auth_config.azure_identifier_uri,
        required_scopes=auth_config.azure_required_scopes,
        http_client=http_client,
        base_url=auth_config.azure_base_url,
        group_claim_name=auth_config.azure_group_claim_name,
    )
