"""Shared admin-plane JWT test harness: local keys, stubbed JWKS.

The admin-plane API test modules share ONE harness instead of
duplicating it: the auth contract tests (:mod:`tests.test_api_admin_auth`)
and the children route tests (:mod:`tests.test_api_admin_children`) both
drive the ASGI app with httpx using a locally generated RSA key pair and
a stubbed JWKS fetcher — NO network access:

- ``ADMIN_KEY`` signs the test tokens; :func:`jwks_for` builds the JWKS
  document publishing its public half, so genuinely signed tokens
  verify, and tokens signed with the second pair (``OTHER_KEY``) fail
  the signature check for real.
- :func:`make_token` mints one RS256 JWT the way Authentik would (its
  claims, our key), defaulting ``groups`` to the admin group a real
  admin's token carries.
- :class:`StubbedFetch` is the counting JWKS fetcher stub.
- :class:`AdminRunner` runs the app's lifespan around an httpx
  AsyncClient (httpx's ASGI transport does not run the lifespan, so it
  is driven explicitly and shut down in ``__aexit__``'s finally block
  even on failure) with the app's JWKS cache swapped for one built
  around the stub fetcher.

The harness carries no tests itself; the ``admin_client`` fixture in
``tests/conftest.py`` hands its runner to the test modules.
"""
from __future__ import annotations

import base64
import time

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from api.app import create_app
from api.auth import ADMIN_GROUP, JwksCache
from api.config import ApiConfig

#: The configured OIDC settings the test apps run with (values a real
#: deployment would get from the NESTQUEST_OIDC_* environment vars).
ISSUER = "https://authentik.example.com/application/o/nestquest/"
AUDIENCE = "nestquest-api"
JWKS_URL = "https://authentik.example.com/application/o/nestquest/jwks/"

#: The ``kid`` the test tokens carry, matching the JWKS entry.
KID = "admin-test-key-1"

#: The subject a valid token authenticates as.
SUBJECT = "admin-user-1"


def _generate_key() -> rsa.RSAPrivateKey:
    """Generate one local RSA key pair (no network, no fixtures)."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


#: The key pair whose PUBLIC half the stubbed JWKS publishes — tokens
#: signed with it verify; the second pair below proves they don't when
#: signed otherwise.
ADMIN_KEY = _generate_key()
OTHER_KEY = _generate_key()


def _b64url_uint(value: int) -> str:
    """Base64url-encode a non-negative integer (no padding), per JWK."""
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def jwks_for(private_key: rsa.RSAPrivateKey, kid: str) -> dict[str, object]:
    """Build a JWKS document publishing ``private_key``'s public half."""
    numbers = private_key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": kid,
                "n": _b64url_uint(numbers.n),
                "e": _b64url_uint(numbers.e),
            }
        ]
    }


class StubbedFetch:
    """A JWKS fetcher stub: returns a fixed document, counts calls."""

    def __init__(self, document: dict[str, object]) -> None:
        self.document = document
        self.calls = 0

    async def __call__(self, url: str) -> dict[str, object]:
        self.calls += 1
        return self.document


def make_token(
    signing_key: rsa.RSAPrivateKey = ADMIN_KEY,
    *,
    kid: str | None = KID,
    iss: str = ISSUER,
    aud: object = AUDIENCE,
    sub: str = SUBJECT,
    expires_in: int | None = 300,
    nbf_in: int | None = -1,
    groups: object = (ADMIN_GROUP,),
) -> str:
    """Mint one RS256 JWT the way Authentik would (its claims, our key).

    ``groups`` defaults to the admin group (what a real admin user's
    token carries); tests pass a different value — or ``None`` for NO
    groups claim at all — to prove the group gate rejects it.
    """
    now = int(time.time())
    claims: dict[str, object] = {"iss": iss, "aud": aud, "sub": sub, "iat": now}
    if groups is not None:
        claims["groups"] = (
            list(groups) if isinstance(groups, (list, tuple)) else groups
        )
    if nbf_in is not None:
        claims["nbf"] = now + nbf_in
    if expires_in is not None:
        claims["exp"] = now + expires_in
    headers: dict[str, str] = {}
    if kid is not None:
        headers["kid"] = kid
    return jwt.encode(
        claims, signing_key, algorithm="RS256", headers=headers
    )


class AdminRunner:
    """Run the app's lifespan around an httpx AsyncClient.

    Same pattern as test_api_health.py's ``_AppRunner``: httpx's ASGI
    transport does not run the lifespan, so it is driven explicitly and
    shut down in ``__aexit__``'s finally block even on failure.

    The app's JWKS cache is replaced (before the lifespan runs) with
    one built around a counting stub fetcher, so verification goes
    through the REAL cache logic but never the network.
    """

    def __init__(
        self,
        db_path: str,
        jwks_document: dict[str, object],
        *,
        ttl_seconds: float | None = None,
        backoff_seconds: float | None = None,
        kid_refetch_seconds: float | None = None,
    ) -> None:
        self.app = create_app(
            ApiConfig(
                db_path=db_path,
                panel_token="admin-test-panel-token",
                oidc_issuer=ISSUER,
                oidc_audience=AUDIENCE,
                oidc_jwks_url=JWKS_URL,
            )
        )
        self.fetch = StubbedFetch(jwks_document)
        cache_kwargs: dict[str, float] = {}
        if ttl_seconds is not None:
            cache_kwargs["ttl_seconds"] = ttl_seconds
        if backoff_seconds is not None:
            cache_kwargs["backoff_seconds"] = backoff_seconds
        if kid_refetch_seconds is not None:
            cache_kwargs["kid_refetch_seconds"] = kid_refetch_seconds
        self.app.state.jwks_cache = JwksCache(
            JWKS_URL, fetcher=self.fetch, **cache_kwargs
        )

    async def __aenter__(self) -> httpx.AsyncClient:
        self._lifespan = self.app.router.lifespan_context(self.app)
        await self._lifespan.__aenter__()
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        return await self._client.__aenter__()

    async def __aexit__(self, *exc) -> None:
        try:
            await self._client.__aexit__(*exc)
        finally:
            await self._lifespan.__aexit__(*exc)
