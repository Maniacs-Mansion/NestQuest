"""Admin-plane authentication for the NestQuest API service.

The admin plane (``/api/v1/admin/*``, D-012) is authenticated by
Authentik-issued OIDC access tokens: the admin PWA presents its JWT as
a Bearer credential and :func:`require_admin_jwt` — the ONE
implementation of that check — verifies it before any admin route runs.
Verification enforces, without exception:

- the signature, against the RSA signing key published in the
  provider's JWKS document (fetched from the configured
  ``NESTQUEST_OIDC_JWKS_URL`` and cached per app — never per request);
- the issuer (``iss`` must equal the configured
  ``NESTQUEST_OIDC_ISSUER``);
- the audience (``aud`` must carry the configured
  ``NESTQUEST_OIDC_AUDIENCE``);
- expiry (``exp`` is required and enforced, and ``nbf`` is enforced
  when the token carries it).

Every rejection raises the SAME :class:`~fastapi.HTTPException` with
the same detail — nothing in the response distinguishes which check
failed.  The check FAILS CLOSED: a missing app config, a malformed or
missing ``Authorization`` header, a non-RS256 algorithm, an unknown
``kid``, and any PyJWT verification error all yield the one 401.

The token's header (``alg``, ``kid``) is parsed and checked BEFORE the
JWKS cache is consulted, so structurally invalid tokens can never
amplify load on the provider.  An unknown ``kid`` forces ONE
TTL-bypassing refetch (throttled, see :class:`JwksCache`) so a rotated
key is picked up without waiting out the TTL, and a JWKS entry that
matches the ``kid`` but carries corrupt key material maps to the same
401.  A JWKS FETCH failure is deliberately NOT mapped to 401: the
provider being unreachable is a server-side fault (an HTTP 500
surfaces) and never poisons the cache, so the plane stays closed while
the real cause is visible in the server log instead of disguised as a
bad credential; a short backoff window after a failed fetch fails fast
(re-raising the recorded fault) rather than fetching once per request.

This module validates the TOKEN only — it is authentication, not
authorization.  Membership in the ``nestquest-admins`` group is the
NEXT task, which extends :func:`require_admin_jwt` (the verified
claims are already its return value, so no rewrite is needed).
"""
from __future__ import annotations

import asyncio
import binascii
import json
import time
from collections.abc import Awaitable, Callable
from typing import Annotated

import httpx
import jwt
from fastapi import Header, HTTPException, Request

#: The authorization scheme the admin plane expects.  Matched
#: case-insensitively, as RFC 9110 requires for scheme names.
_BEARER_SCHEME = "bearer"

#: The ONLY JWT signing algorithm accepted.  Pinned to one asymmetric
#: algorithm (Authentik's RS256 default) so neither the header's ``alg``
#: nor any JWKS key can talk the verifier into a weaker or symmetric
#: scheme; PyJWT re-enforces it at decode time.
_ALLOWED_ALGORITHM = "RS256"

#: The 401 detail shared by every rejection — deliberately uniform so
#: the response never reveals which part of the check failed.
_REJECTION_DETAIL = "Missing or invalid admin credentials"

#: Challenge header returned with a 401, per the Bearer auth scheme.
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}

#: Seconds a fetched JWKS document stays trusted before the next
#: fetch.  Five minutes bounds how long a rotated-away key keeps
#: verifying while staying far above a per-request fetch.
_JWKS_TTL_SECONDS = 300.0

#: Seconds a FAILED JWKS fetch blocks further fetch attempts.  Within
#: this window after a failure the cache fails fast — it re-raises the
#: recorded fault instead of touching the provider — so an outage is
#: never amplified into one fetch per request.
_JWKS_BACKOFF_SECONDS = 5.0

#: Seconds that must pass before ANOTHER forced (TTL-bypassing) refetch
#: may run.  An unmatched ``kid`` forces one refetch to pick up rotated
#: keys; this interval bounds it, so a flood of unknown-``kid`` tokens
#: cannot turn each request into a provider fetch either.
_JWKS_KID_REFETCH_SECONDS = 5.0

#: Seconds before the real JWKS fetch gives up on the provider.
_JWKS_TIMEOUT_SECONDS = 5.0

#: An async callable that fetches the JWKS document from a URL.  The
#: real one (:func:`_fetch_jwks`) uses httpx; tests inject a stub so
#: the suite stays hermetic (no network access).
JwksFetcher = Callable[[str], Awaitable[dict[str, object]]]


async def _fetch_jwks(url: str) -> dict[str, object]:
    """Fetch the provider's JWKS document over HTTP (the real fetch).

    Uses httpx with a short timeout; a non-2xx response or a body that
    is not a ``{"keys": [...]}`` object raises — the cache never stores
    a failed or malformed fetch.
    """
    async with httpx.AsyncClient(timeout=_JWKS_TIMEOUT_SECONDS) as client:
        response = await client.get(url)
        response.raise_for_status()
        document = response.json()
    if not isinstance(document, dict) or not isinstance(
        document.get("keys"), list
    ):
        raise ValueError("JWKS document must be an object with a keys list")
    return document


class JwksCache:
    """One app's cache of the OIDC provider's JWKS document.

    The document is fetched through ``fetcher`` (the real one uses
    httpx against the configured JWKS URL) and held for ``ttl_seconds``
    — the dependency NEVER fetches per request.  A single fetch is
    shared between concurrent requests via an :class:`asyncio.Lock`
    (double-checked around it), and a failed fetch is never cached, so
    the next request retries once the backoff window lapses rather than
    being locked out until the TTL does.

    Two bounds keep the provider out of an amplification loop:

    - ``backoff_seconds``: after a FAILED fetch, :meth:`get` fails fast
      for this long — re-raising the recorded fault WITHOUT touching
      the fetcher or even the lock — instead of retrying per request.
    - ``kid_refetch_seconds``: forced (TTL-bypassing) refetches — the
      unmatched-``kid`` path — may run at most this often; a forced
      refetch that is bounded out (or one inside the backoff window)
      is served from the cached document as-is.

    A successful fetch always clears the backoff; the document itself
    is still trusted only for ``ttl_seconds`` — nothing is cached
    indefinitely.

    One instance lives on ``app.state.jwks_cache`` (installed by
    :func:`api.app.create_app`); tests replace it with one built around
    a stub fetcher, keeping the suite hermetic.
    """

    def __init__(
        self,
        url: str,
        *,
        ttl_seconds: float = _JWKS_TTL_SECONDS,
        backoff_seconds: float = _JWKS_BACKOFF_SECONDS,
        kid_refetch_seconds: float = _JWKS_KID_REFETCH_SECONDS,
        fetcher: JwksFetcher | None = None,
    ) -> None:
        self._url = url
        self._ttl_seconds = ttl_seconds
        self._backoff_seconds = backoff_seconds
        self._kid_refetch_seconds = kid_refetch_seconds
        self._fetcher: JwksFetcher = (
            fetcher if fetcher is not None else _fetch_jwks
        )
        self._document: dict[str, object] | None = None
        self._fetched_at: float | None = None
        self._failed_until: float | None = None
        self._last_error: BaseException | None = None
        self._forced_at: float | None = None
        self._lock = asyncio.Lock()

    async def get(self, *, force: bool = False) -> dict[str, object]:
        """Return the JWKS document, refetching it if the TTL lapsed.

        With ``force=True`` the TTL is bypassed so an unmatched ``kid``
        can pick up a rotated key without waiting it out; the forced
        refetch is itself bounded (see the class docstring): inside the
        backoff window or the ``kid_refetch_seconds`` interval the
        cached document is served as-is instead.  A failed fetch is
        re-raised to the caller (a provider outage is a server fault,
        never a 401) and starts the backoff window, during which every
        caller — including forced ones with nothing cached — fails fast
        on the recorded fault.
        """
        if not force:
            fresh = self._fresh_document()
            if fresh is not None:
                return fresh
        error = self._backoff_error()
        if error is not None:
            # Fail fast OUTSIDE the lock: a request inside the backoff
            # window must not queue behind an in-flight fetch.
            if force:
                document = self._document
                if document is not None:
                    return document
            raise error
        async with self._lock:
            if not force:
                fresh = self._fresh_document()
                if fresh is not None:
                    return fresh
            error = self._backoff_error()
            if error is not None:
                if force:
                    document = self._document
                    if document is not None:
                        return document
                raise error
            if force and self._refetch_throttled():
                document = self._document
                if document is not None:
                    return document
            return await self._fetch_locked(force=force)

    def _fresh_document(self) -> dict[str, object] | None:
        """The cached document if one exists and is inside its TTL."""
        document = self._document
        fetched_at = self._fetched_at
        if (
            document is not None
            and fetched_at is not None
            and (time.monotonic() - fetched_at) < self._ttl_seconds
        ):
            return document
        return None

    def _backoff_error(self) -> BaseException | None:
        """The recorded fetch fault while the backoff window is open."""
        failed_until = self._failed_until
        last_error = self._last_error
        if (
            failed_until is not None
            and last_error is not None
            and time.monotonic() < failed_until
        ):
            return last_error
        return None

    def _refetch_throttled(self) -> bool:
        """Whether a forced refetch ran too recently to run another."""
        forced_at = self._forced_at
        return forced_at is not None and (
            time.monotonic() - forced_at
        ) < self._kid_refetch_seconds

    async def _fetch_locked(self, *, force: bool) -> dict[str, object]:
        """Run ONE fetch attempt (caller holds the lock) and record it.

        A failed fetch starts the ``backoff_seconds`` window and is
        re-raised; a successful one stores the document, restarts the
        TTL and clears the backoff.  A forced attempt stamps
        ``_forced_at`` so the ``kid_refetch_seconds`` interval bounds
        how often forced refetches may run back-to-back.
        """
        if force:
            self._forced_at = time.monotonic()
        try:
            document = await self._fetcher(self._url)
        except Exception as error:
            self._failed_until = time.monotonic() + self._backoff_seconds
            self._last_error = error
            raise
        self._document = document
        self._fetched_at = time.monotonic()
        self._failed_until = None
        self._last_error = None
        return document


def _reject() -> HTTPException:
    """Build the single 401 the dependency raises for every failure."""
    return HTTPException(
        status_code=401,
        detail=_REJECTION_DETAIL,
        headers=_WWW_AUTHENTICATE,
    )


def _matching_key(jwks: dict[str, object], kid: str) -> object | None:
    """Return the RSA signing key named ``kid`` from the JWKS.

    Only ``kty: RSA`` entries are considered (the pinned RS256 scheme
    is asymmetric RSA); anything else — a missing ``keys`` list, no
    entry with that ``kid`` — returns ``None`` rather than falling back
    to "some" key.  The key is built through PyJWT's JWKS decoder, and
    an entry that MATCHES the ``kid`` but carries corrupt key material
    (a malformed ``n``/``e`` raises ``ValueError`` — ``binascii.Error``
    is its subclass — or ``TypeError`` instead of a ``PyJWTError``) is
    mapped to the one 401 like every other rejection: the caller must
    never see a half-built key.
    """
    keys = jwks.get("keys")
    if not isinstance(keys, list):
        raise _reject()
    for entry in keys:
        if not isinstance(entry, dict):
            continue
        if entry.get("kid") != kid or entry.get("kty") != "RSA":
            continue
        try:
            return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(entry))
        except (
            jwt.PyJWTError,
            binascii.Error,
            ValueError,
            TypeError,
            KeyError,
        ):
            raise _reject() from None
    return None


async def verify_admin_token(
    request: Request, token: str
) -> dict[str, object]:
    """Verify ONE admin bearer token and return its verified claims.

    Reads the OIDC settings off ``app.state.config`` and the JWKS cache
    off ``app.state.jwks_cache`` (both installed by
    :func:`api.app.create_app`) so the check carries no module state.
    A missing config or cache, an EMPTY configured issuer/audience/JWKS
    URL, a non-RS256 ``alg`` header, an absent ``kid``, an unknown
    ``kid``, and any PyJWT verification failure (bad signature,
    expired, wrong issuer, wrong audience, not-yet-valid, missing
    ``exp``) raise the SAME 401 — the failure mode is never leaked.
    ``exp`` is REQUIRED (a token that never expires is never accepted)
    and PyJWT enforces ``nbf`` when the token carries it.

    The token's HEADER (``alg``, ``kid``) is parsed and enforced BEFORE
    the JWKS cache is consulted, so a structurally invalid token costs
    no fetch, no lock, no provider load.  When the cached document has
    no entry for the ``kid``, ONE forced (TTL-bypassing, throttled)
    refetch is made and the match retried once — a rotated key is
    picked up without waiting out the TTL — before the 401.

    A JWKS fetch failure propagates (see the module docstring): the
    provider being down is a server fault, not a bad credential.
    """
    config = getattr(request.app.state, "config", None)
    if (
        config is None
        or not config.oidc_issuer
        or not config.oidc_audience
        or not config.oidc_jwks_url
    ):
        raise _reject()
    cache = getattr(request.app.state, "jwks_cache", None)
    if cache is None:
        raise _reject()
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise _reject() from None
    if header.get("alg") != _ALLOWED_ALGORITHM:
        raise _reject()
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise _reject()
    jwks = await cache.get()
    try:
        key = _matching_key(jwks, kid)
        if key is None:
            # The kid is not in the cached document: force ONE
            # TTL-bypassing refetch (bounded by the cache) and retry
            # the match once before rejecting.
            jwks = await cache.get(force=True)
            key = _matching_key(jwks, kid)
            if key is None:
                raise _reject()
        claims = jwt.decode(
            token,
            key=key,
            algorithms=[_ALLOWED_ALGORITHM],
            issuer=config.oidc_issuer,
            audience=config.oidc_audience,
            options={"require": ["exp"]},
        )
    except jwt.PyJWTError:
        raise _reject() from None
    return claims


async def require_admin_jwt(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    """Reject the request with 401 unless it carries a valid admin JWT.

    Extracts the Bearer credential — a missing or malformed
    ``Authorization`` header (wrong scheme, empty credential) raises
    the one 401 — and delegates the verification to
    :func:`verify_admin_token`, returning the verified claims for the
    route to use (the probe route surfaces the token's ``sub``).

    The nestquest-admins GROUP check is the NEXT task: it extends this
    dependency (e.g. by inspecting the returned claims) so every admin
    route inherits it — the 401 contract stays exactly this uniform.
    """
    if authorization is None:
        raise _reject()
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != _BEARER_SCHEME or not credential.strip():
        raise _reject()
    return await verify_admin_token(request, credential.strip())


__all__ = ["JwksCache", "JwksFetcher", "require_admin_jwt", "verify_admin_token"]
