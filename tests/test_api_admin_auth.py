"""Admin-plane JWT auth tests: Authentik-style OIDC verification (task e70e6bfb).

These tests exercise the NestQuest API's admin plane against the ASGI
app with httpx, using a locally generated RSA key pair and a stubbed
JWKS fetcher — NO network access:

- ``GET /api/v1/admin/ping`` requires a valid Authentik OIDC JWT: a
  request with NO ``Authorization`` header and a MALFORMED header
  return 401; a garbage, expired, wrong-issuer, wrong-audience,
  not-yet-valid (future ``nbf``), unknown-``kid``, or bad-signature
  token returns 401; a token without ``exp`` is rejected; a VALID
  token returns 200 with the verified subject.
- Every 401 carries the SAME detail — nothing in the response
  distinguishes which check failed.
- The token's HEADER is validated BEFORE the JWKS cache is touched: a
  garbage or non-RS256 token triggers NO fetch at all.
- A JWKS entry that matches the ``kid`` but carries corrupt key
  material maps to the same uniform 401.
- The JWKS document is fetched ONCE through the app's
  :class:`api.auth.JwksCache` and then reused across requests (the
  stub fetcher counts calls); a zero TTL refetches.
- A JWKS OUTAGE fails fast: after one failed fetch the cache re-raises
  the fault for the whole backoff window without further fetches, even
  under a burst of concurrent requests; an unknown ``kid`` forces one
  TTL-bypassing refetch, throttled to at most one per interval.

``ApiConfig.from_env`` requires the three OIDC variables
(``NESTQUEST_OIDC_ISSUER``, ``NESTQUEST_OIDC_AUDIENCE``,
``NESTQUEST_OIDC_JWKS_URL``) with the same fail-fast discipline as
``NESTQUEST_DB_PATH`` / ``NESTQUEST_PANEL_TOKEN``: tests build the app
with explicit ApiConfig values so they stay hermetic.

The signature/expiry/audience proof is real, not stubbed: tokens are
signed with a locally generated RSA private key, the app verifies
against the JWKS built from its public key, and the wrong-signature
case signs with a SECOND locally generated key pair.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from api.app import create_app
from api.auth import ADMIN_GROUP, JwksCache
from api.config import ApiConfig, ConfigError

#: The configured OIDC settings the test apps run with (values a real
#: deployment would get from the NESTQUEST_OIDC_* environment vars).
ISSUER = "https://authentik.example.com/application/o/nestquest/"
AUDIENCE = "nestquest-api"
JWKS_URL = "https://authentik.example.com/application/o/nestquest/jwks/"

#: The ``kid`` the test tokens carry, matching the JWKS entry.
KID = "admin-test-key-1"

#: The subject a valid token authenticates as.
SUBJECT = "admin-user-1"

#: The uniform 401 detail every rejection must carry.
REJECTION_DETAIL = "Missing or invalid admin credentials"

#: The 403 detail for the panel service token on an admin route.
PANEL_TOKEN_REJECTION_DETAIL = (
    "This credential type is not accepted for admin access"
)

#: The 403 detail for a valid JWT without the admin group.
FORBIDDEN_DETAIL = (
    "Admin access requires membership in the nestquest-admins group"
)


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


def _jwks_for(private_key: rsa.RSAPrivateKey, kid: str) -> dict[str, object]:
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


class _StubbedFetch:
    """A JWKS fetcher stub: returns a fixed document, counts calls."""

    def __init__(self, document: dict[str, object]) -> None:
        self.document = document
        self.calls = 0

    async def __call__(self, url: str) -> dict[str, object]:
        self.calls += 1
        return self.document


class _FailingFetch:
    """A JWKS fetcher stub that always fails, counting the attempts."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, url: str) -> dict[str, object]:
        self.calls += 1
        raise httpx.ConnectError("provider unreachable")


class _FlakyFetch:
    """A fetcher that succeeds ONCE, then fails on every later call."""

    def __init__(self, document: dict[str, object]) -> None:
        self.document = document
        self.calls = 0

    async def __call__(self, url: str) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            return self.document
        raise httpx.ConnectError("provider unreachable")


class _FailThenServe:
    """A fetcher that fails the FIRST call, then serves the document."""

    def __init__(self, document: dict[str, object]) -> None:
        self.document = document
        self.calls = 0

    async def __call__(self, url: str) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            raise httpx.ConnectError("provider unreachable")
        return self.document


def _make_token(
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


def _token_with_header(
    header: dict[str, object], payload: dict[str, object]
) -> str:
    """Build a JWT with an EXACT header (bypassing jwt.encode's rules).

    Used to prove header checks (``alg``, ``kid``) happen before the
    JWKS cache is consulted; the signature segment is never reached.
    """
    def part(obj: dict[str, object]) -> str:
        raw = json.dumps(obj).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{part(header)}.{part(payload)}.c2lnbmF0dXJl"


def _verified_payload() -> dict[str, object]:
    """Claims that would verify — the header checks fire before them."""
    now = int(time.time())
    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": SUBJECT,
        "exp": now + 300,
        "nbf": now - 1,
    }


class _AdminRunner:
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
        self.fetch = _StubbedFetch(jwks_document)
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


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """A fresh per-test SQLite path under pytest's tmp_path."""
    return str(tmp_path / "nestquest.db")


@pytest.fixture
async def admin_client(
    temp_db_path: str,
) -> httpx.AsyncClient:
    """An app client whose provider publishes the admin test key."""
    async with _AdminRunner(temp_db_path, _jwks_for(ADMIN_KEY, KID)) as client:
        yield client


# --- the happy path -------------------------------------------------------


async def test_valid_token_returns_200_with_subject(
    admin_client: httpx.AsyncClient,
) -> None:
    """A valid token returns 200 with the status and verified subject."""
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {_make_token()}"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "sub": SUBJECT}


async def test_bearer_scheme_is_case_insensitive(
    admin_client: httpx.AsyncClient,
) -> None:
    """``bearer`` (lowercase) is accepted, as RFC 9110 requires."""
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"bearer {_make_token()}"},
    )
    assert response.status_code == 200


# --- 401s: missing / malformed credentials --------------------------------


async def test_missing_token_is_unauthorized(
    admin_client: httpx.AsyncClient,
) -> None:
    """A request with no Authorization header returns 401."""
    response = await admin_client.get("/api/v1/admin/ping")
    assert response.status_code == 401
    assert response.json()["detail"] == REJECTION_DETAIL
    assert "www-authenticate" in {
        key.lower() for key in response.headers
    }


@pytest.mark.parametrize(
    "header",
    [
        "Basic cGFuZWw6dG9rZW4=",  # wrong scheme
        "Bearer",  # scheme, no credential
        "Bearer    ",  # blank credential
        "BearerNotAToken",  # no scheme separator at all
    ],
)
async def test_malformed_header_is_unauthorized(
    admin_client: httpx.AsyncClient, header: str
) -> None:
    """A malformed Authorization header returns 401."""
    response = await admin_client.get(
        "/api/v1/admin/ping", headers={"Authorization": header}
    )
    assert response.status_code == 401


async def test_garbage_token_is_unauthorized(
    admin_client: httpx.AsyncClient,
) -> None:
    """A Bearer credential that is not a JWT at all returns 401."""
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 401


# --- 401s: token content the verifier must reject ---------------------------


async def test_expired_token_is_unauthorized(
    admin_client: httpx.AsyncClient,
) -> None:
    """A token whose exp has passed returns 401."""
    token = _make_token(expires_in=-60)
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


async def test_wrong_issuer_is_unauthorized(
    admin_client: httpx.AsyncClient,
) -> None:
    """A token issued by another issuer returns 401."""
    token = _make_token(iss="https://evil.example.com/application/o/nestquest/")
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


async def test_wrong_audience_is_unauthorized(
    admin_client: httpx.AsyncClient,
) -> None:
    """A token minted for another audience returns 401."""
    token = _make_token(aud="some-other-client")
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


async def test_future_nbf_is_unauthorized(
    admin_client: httpx.AsyncClient,
) -> None:
    """A token that is not yet valid (future nbf) returns 401."""
    token = _make_token(nbf_in=3600)
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


async def test_token_without_exp_is_unauthorized(
    admin_client: httpx.AsyncClient,
) -> None:
    """A token with no exp claim returns 401 (expiry is REQUIRED)."""
    token = _make_token(expires_in=None)
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


async def test_unknown_kid_is_unauthorized(
    admin_client: httpx.AsyncClient,
) -> None:
    """A token naming a kid the JWKS does not publish returns 401."""
    token = _make_token(kid="no-such-key")
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


async def test_bad_signature_is_unauthorized(
    admin_client: httpx.AsyncClient,
) -> None:
    """A token signed by a key the provider never published returns 401.

    Signed with the SECOND local key pair (header kid still points at
    the published key), so the signature check itself must fail.
    """
    token = _make_token(signing_key=OTHER_KEY)
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


async def test_corrupt_jwks_entry_matching_kid_is_unauthorized(
    temp_db_path: str,
) -> None:
    """A JWKS entry matching the kid but with corrupt key data → 401.

    ``RSAAlgorithm.from_jwk`` raises ValueError/TypeError (NOT a
    PyJWTError) on such an entry; it must map to the SAME uniform 401,
    not surface as a server error.
    """
    corrupt_jwks: dict[str, object] = {
        "keys": [
            {"kty": "RSA", "kid": KID, "n": "AQ", "e": "AQAB"},
        ]
    }
    runner = _AdminRunner(temp_db_path, corrupt_jwks)
    async with runner as client:
        response = await client.get(
            "/api/v1/admin/ping",
            headers={"Authorization": f"Bearer {_make_token()}"},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == REJECTION_DETAIL


# --- the header is checked BEFORE the JWKS cache -----------------------------


async def test_garbage_token_triggers_no_jwks_fetch(
    temp_db_path: str,
) -> None:
    """A token that is not a JWT costs NO fetch, lock or provider load."""
    runner = _AdminRunner(temp_db_path, _jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        response = await client.get(
            "/api/v1/admin/ping",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == REJECTION_DETAIL
    assert runner.fetch.calls == 0


async def test_non_rs256_token_triggers_no_jwks_fetch(
    temp_db_path: str,
) -> None:
    """A structurally valid JWT with a non-RS256 alg is 401 pre-cache.

    The header carries a kid pointing at the published key, so ONLY the
    early alg check can reject it — the fetcher must never be called.
    """
    runner = _AdminRunner(temp_db_path, _jwks_for(ADMIN_KEY, KID))
    token = _token_with_header(
        {"alg": "HS256", "typ": "JWT", "kid": KID}, _verified_payload()
    )
    async with runner as client:
        response = await client.get(
            "/api/v1/admin/ping",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == REJECTION_DETAIL
    assert runner.fetch.calls == 0


# --- the uniform 401 contract -----------------------------------------------


async def test_every_rejection_carries_the_same_detail(
    admin_client: httpx.AsyncClient,
) -> None:
    """No failure mode is distinguishable in the response body.

    Collects the (status, detail) pair for every rejection — missing
    and malformed headers, garbage, expired, wrong issuer, wrong
    audience, future nbf, missing exp, unknown kid, bad signature —
    and asserts they are ALL the same one 401.
    """
    cases: list[dict[str, str]] = [
        {},
        {"Authorization": "Basic cGFuZWw6dG9rZW4="},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": f"Bearer {_make_token(expires_in=-60)}"},
        {"Authorization": f"Bearer {_make_token(iss='https://evil.example.com/')}"},
        {"Authorization": f"Bearer {_make_token(aud='other-client')}"},
        {"Authorization": f"Bearer {_make_token(nbf_in=3600)}"},
        {"Authorization": f"Bearer {_make_token(expires_in=None)}"},
        {"Authorization": f"Bearer {_make_token(kid='no-such-key')}"},
        {"Authorization": f"Bearer {_make_token(signing_key=OTHER_KEY)}"},
    ]
    observed = set()
    for headers in cases:
        response = await admin_client.get("/api/v1/admin/ping", headers=headers)
        observed.add((response.status_code, response.json()["detail"]))
    assert observed == {(401, REJECTION_DETAIL)}


# --- the JWKS cache ----------------------------------------------------------


async def test_jwks_is_fetched_once_across_requests(
    temp_db_path: str,
) -> None:
    """Multiple requests reuse ONE cached JWKS document.

    Three separately authenticated requests trigger exactly ONE stub
    fetch — the cache is per app and never per request.
    """
    runner = _AdminRunner(temp_db_path, _jwks_for(ADMIN_KEY, KID))
    token = _make_token()
    async with runner as client:
        for _ in range(3):
            response = await client.get(
                "/api/v1/admin/ping",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
    assert runner.fetch.calls == 1


async def test_expired_ttl_refetches_the_jwks(temp_db_path: str) -> None:
    """A lapsed TTL triggers a fresh fetch instead of serving stale keys."""
    runner = _AdminRunner(
        temp_db_path, _jwks_for(ADMIN_KEY, KID), ttl_seconds=0.0
    )
    token = _make_token()
    async with runner as client:
        for _ in range(2):
            response = await client.get(
                "/api/v1/admin/ping",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
    assert runner.fetch.calls == 2


# --- the JWKS cache under an outage: fail fast, don't amplify ---------------


async def test_jwks_outage_fails_fast_during_backoff() -> None:
    """After one failed fetch, later requests fail fast for the window."""
    fetch = _FailingFetch()
    cache = JwksCache(JWKS_URL, fetcher=fetch)
    for _ in range(4):
        with pytest.raises(httpx.ConnectError):
            await cache.get()
    assert fetch.calls == 1


async def test_jwks_outage_burst_calls_the_fetcher_once() -> None:
    """A burst of concurrent requests costs ONE fetch, not one each.

    The first caller fetches and fails; every other caller — queued on
    the lock or arriving inside the backoff window — fails fast on the
    recorded fault without touching the fetcher.
    """
    fetch = _FailingFetch()
    cache = JwksCache(JWKS_URL, fetcher=fetch)
    results = await asyncio.gather(
        *(cache.get() for _ in range(6)), return_exceptions=True
    )
    assert fetch.calls == 1
    assert all(
        isinstance(result, httpx.ConnectError) for result in results
    )


async def test_jwks_backoff_lapses_and_recovers() -> None:
    """A backoff window is not a lockout: retries resume after it.

    With a zero-length window the very next request retries (and the
    successful document is then served from the cache), proving a
    failed state is never cached for good.
    """
    document = _jwks_for(ADMIN_KEY, KID)
    fetch = _FailThenServe(document)
    cache = JwksCache(JWKS_URL, fetcher=fetch, backoff_seconds=0.0)
    with pytest.raises(httpx.ConnectError):
        await cache.get()
    assert await cache.get() == document
    assert await cache.get() == document
    assert fetch.calls == 2


async def test_jwks_outage_is_a_server_fault_not_a_401(
    temp_db_path: str,
) -> None:
    """A provider outage propagates as a fault, never as a 401."""
    runner = _AdminRunner(temp_db_path, _jwks_for(ADMIN_KEY, KID))
    runner.app.state.jwks_cache = JwksCache(JWKS_URL, fetcher=_FailingFetch())
    async with runner as client:
        with pytest.raises(httpx.ConnectError):
            await client.get(
                "/api/v1/admin/ping",
                headers={"Authorization": f"Bearer {_make_token()}"},
            )


# --- the unknown-kid refetch: one forced, bounded attempt --------------------


async def test_unknown_kid_refetch_picks_up_a_rotated_key(
    temp_db_path: str,
) -> None:
    """An unmatched kid forces ONE refetch, and the retry can verify.

    The JWKS first publishes a DIFFERENT kid: the token is 401 after
    exactly two fetches (normal + forced).  When the rotated key lands
    in the provider's document, the NEXT token forces another refetch
    that picks it up — the same token verifies WITHOUT waiting out the
    TTL.
    """
    runner = _AdminRunner(
        temp_db_path, _jwks_for(ADMIN_KEY, "other-key"), kid_refetch_seconds=0.0
    )
    token = _make_token()
    async with runner as client:
        response = await client.get(
            "/api/v1/admin/ping",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == REJECTION_DETAIL
        assert runner.fetch.calls == 2

        # The rotation lands at the provider (same stub fetcher).
        runner.fetch.document = _jwks_for(ADMIN_KEY, KID)
        response = await client.get(
            "/api/v1/admin/ping",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert runner.fetch.calls == 3


async def test_unknown_kid_refetch_is_throttled(temp_db_path: str) -> None:
    """Back-to-back unknown-kid tokens force at most one refetch.

    The interval bounds forced refetches: the second unknown-kid token
    inside it is served from the cached document (still unmatched →
    401) with no further fetch.
    """
    runner = _AdminRunner(temp_db_path, _jwks_for(ADMIN_KEY, "other-key"))
    token = _make_token()
    async with runner as client:
        for _ in range(2):
            response = await client.get(
                "/api/v1/admin/ping",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 401
    assert runner.fetch.calls == 2


async def test_unknown_kid_refetch_resumes_after_the_interval(
    temp_db_path: str,
) -> None:
    """A lapsed interval allows the next forced refetch again.

    With a zero-length interval every request may force its refetch:
    the first costs one normal fetch plus one forced (two), and the
    second — its cached document still fresh — costs just the forced
    one (three in total), proving the throttle is a bounded interval
    rather than a permanent lockout.
    """
    runner = _AdminRunner(
        temp_db_path, _jwks_for(ADMIN_KEY, "other-key"), kid_refetch_seconds=0.0
    )
    token = _make_token()
    async with runner as client:
        for _ in range(2):
            response = await client.get(
                "/api/v1/admin/ping",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 401
    assert runner.fetch.calls == 3


async def test_failed_forced_refetch_propagates_then_fails_fast(
    temp_db_path: str,
) -> None:
    """A failed forced refetch is a fault, and its backoff bounds the rest.

    First request: cache fills (1 fetch), the kid is unmatched, the
    forced refetch FAILS (2 fetches) and propagates as the server
    fault.  Second request inside the backoff window: the cached
    document is served, the match fails, and the token is 401 — with
    NO third fetch.
    """
    runner = _AdminRunner(temp_db_path, _jwks_for(ADMIN_KEY, KID))
    runner.app.state.jwks_cache = JwksCache(
        JWKS_URL, fetcher=_FlakyFetch(_jwks_for(ADMIN_KEY, "other-key"))
    )
    token = _make_token()
    async with runner as client:
        with pytest.raises(httpx.ConnectError):
            await client.get(
                "/api/v1/admin/ping",
                headers={"Authorization": f"Bearer {token}"},
            )
        response = await client.get(
            "/api/v1/admin/ping",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == REJECTION_DETAIL


# --- ApiConfig.from_env: the OIDC settings -----------------------------------


def _full_env() -> dict[str, str]:
    """A from_env dict with every required variable set to a valid value."""
    return {
        "NESTQUEST_DB_PATH": "/data/nq.db",
        "NESTQUEST_PANEL_TOKEN": "panel-token",
        "NESTQUEST_OIDC_ISSUER": ISSUER,
        "NESTQUEST_OIDC_AUDIENCE": AUDIENCE,
        "NESTQUEST_OIDC_JWKS_URL": JWKS_URL,
    }


def test_from_env_reads_oidc_settings() -> None:
    """Set, non-empty OIDC env values are returned verbatim."""
    cfg = ApiConfig.from_env(_full_env())
    assert cfg.oidc_issuer == ISSUER
    assert cfg.oidc_audience == AUDIENCE
    assert cfg.oidc_jwks_url == JWKS_URL


@pytest.mark.parametrize(
    "env_var",
    [
        "NESTQUEST_OIDC_ISSUER",
        "NESTQUEST_OIDC_AUDIENCE",
        "NESTQUEST_OIDC_JWKS_URL",
    ],
)
def test_from_env_requires_oidc_setting(env_var: str) -> None:
    """A missing OR empty OIDC variable raises ConfigError (fail fast)."""
    env = _full_env()
    del env[env_var]
    with pytest.raises(ConfigError):
        ApiConfig.from_env(env)
    env[env_var] = "   "
    with pytest.raises(ConfigError):
        ApiConfig.from_env(env)


# --- the nestquest-admins group gate (task 0f2afb29) -------------------------


async def test_admin_jwt_with_group_returns_200(
    admin_client: httpx.AsyncClient,
) -> None:
    """A valid JWT whose groups claim names nestquest-admins returns 200."""
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {_make_token()}"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "sub": SUBJECT}


async def test_non_admin_jwt_is_forbidden(
    admin_client: httpx.AsyncClient,
) -> None:
    """A valid JWT WITHOUT nestquest-admins in groups returns 403."""
    token = _make_token(groups=("some-other-group",))
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == FORBIDDEN_DETAIL


async def test_empty_groups_is_forbidden(
    admin_client: httpx.AsyncClient,
) -> None:
    """A valid JWT with an EMPTY groups list returns 403."""
    token = _make_token(groups=())
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("groups", ["nestquest-admins", None])
async def test_malformed_groups_is_forbidden(
    admin_client: httpx.AsyncClient, groups: object
) -> None:
    """A valid JWT with a non-list (or missing) groups claim returns 403.

    Even a plain STRING naming the group is not enough — the claim must
    be a list, so a token crafted with a scalar ``groups`` cannot pass.
    """
    token = _make_token(groups=groups)
    response = await admin_client.get(
        "/api/v1/admin/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == FORBIDDEN_DETAIL


async def test_panel_service_token_is_refused_outright(
    temp_db_path: str,
) -> None:
    """The panel service token on an admin route is 403, never a JWT.

    403 (not the uniform 401) proves the credential was refused as a
    TYPE, not run through JWT verification — and the JWKS fetcher is
    never called, proving it was not treated as a token to verify.
    """
    runner = _AdminRunner(temp_db_path, _jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        response = await client.get(
            "/api/v1/admin/ping",
            headers={"Authorization": "Bearer admin-test-panel-token"},
        )
    assert response.status_code == 403
    assert response.json()["detail"] == PANEL_TOKEN_REJECTION_DETAIL
    assert runner.fetch.calls == 0


async def test_admin_router_is_wired_through_require_admin(
    temp_db_path: str,
) -> None:
    """The admin router's dependency IS the one require_admin dependency.

    The router-level dependency list carries
    :func:`api.auth.require_admin`, so every admin route (current and
    later) inherits the service-token refusal and the group gate.
    """
    from api.auth import require_admin
    from api.routes_admin import router as admin_router

    dependencies = [d.dependency for d in admin_router.dependencies]
    assert require_admin in dependencies

    # Behavioral proof: the probe returns 200 for an admin JWT through
    # the same dependency.
    runner = _AdminRunner(temp_db_path, _jwks_for(ADMIN_KEY, KID))
    async with runner as client:
        response = await client.get(
            "/api/v1/admin/ping",
            headers={"Authorization": f"Bearer {_make_token()}"},
        )
    assert response.status_code == 200

