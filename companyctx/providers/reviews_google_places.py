"""``reviews_google_places`` — direct-API Attempt-3 provider for aggregate reviews.

Google Places (legacy web-service API) is the cheapest ToS-safe source for
aggregate review count + average rating for small-local-biz sites. The
provider takes a site hostname, runs a Text Search to resolve candidate
places, picks the best match by website-domain equality (falling back to
Google's prominence ordering on ties), and issues one Place Details call to
read ``user_ratings_total`` + ``rating``.

**Never raises.** Missing key → ``status="not_configured"`` with an
actionable ``suggestion`` pointing at ``GOOGLE_PLACES_API_KEY``. 401 / 403
/ ``REQUEST_DENIED`` / ``OVER_QUERY_LIMIT`` / timeouts / malformed JSON all
map to ``status="failed"`` with a structured error prefix the orchestrator's
classifier can read.

**Cost accounting.** ``ProviderRunMetadata.cost_incurred`` is integer US
cents. Per the COX-5 scope comment, real pricing must be confirmed against
Google's page at measurement time before any vendor claim lands in
``docs/PROVIDERS.md``. This module encodes the *current* published rates
(Text Search $32/1k + Place Details $17/1k ≈ 5 cents for the happy path) as
a source-cited constant; bump the constant when pricing changes.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal, cast
from urllib.parse import urlencode, urlparse

from curl_cffi import requests

from companyctx.providers.base import FetchContext
from companyctx.schema import ProviderRunMetadata, ReviewsSignals

_VERSION = "0.1.0"
ENV_KEY = "GOOGLE_PLACES_API_KEY"
SOURCE_SLUG = "reviews_google_places"
NOT_CONFIGURED_SUGGESTION = (
    "export GOOGLE_PLACES_API_KEY=<your-key> "
    "(see https://developers.google.com/maps/documentation/places/web-service/get-api-key)"
)

# Integer US cents charged on the happy path (Text Search + Place Details).
# Google bills Place Details per field-bundle SKU in the legacy web-service
# pricing table at COX-5 measurement time:
#   - Text Search (Basic)                   $32/1k = 3.2c/call
#   - Place Details Basic                   $17/1k = 1.7c/call
#   - Place Details Atmosphere (adder)       $5/1k = 0.5c/call
# ``rating`` and ``user_ratings_total`` sit in the Atmosphere bundle, so a
# Details call that reads them is billed Basic + Atmosphere = 2.2c/call.
# We sum fractional cents per-leg and ceil the total at emission time so
# partial billing never reads as free and the integer ``cost_incurred``
# never undercounts real spend. Source: Google's "Places API Pricing"
# (legacy) and "Place Data Fields (Legacy)" docs — cited in COX-5 review.
_TENTHS_OF_CENT_PER_DOLLAR = 1000  # 1$ = 100c = 1000 tenths
_TEXT_SEARCH_TENTHS = 32  # $32/1k → 3.2c → 32 tenths of a cent per call
_DETAILS_BASIC_ATMOSPHERE_TENTHS = 17 + 5  # Basic+Atmosphere = $22/1k = 22 tenths

_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
# Only ask for the fields we actually map onto ``ReviewsSignals``. Google
# bills Place Details per Basic/Contact/Atmosphere bundle — requesting
# ``website`` would pull in the Contact bundle and raise cost for no
# benefit (the candidate picker no longer uses it — see note at
# ``_pick_candidate``).
_DETAILS_FIELDS = "place_id,rating,user_ratings_total"


def _cost_cents(*tenths: int) -> int:
    """Ceil fractional tenths-of-a-cent into integer cents."""
    total_tenths = sum(tenths)
    return (total_tenths + 9) // 10


class Provider:
    """``reviews_google_places`` — direct-API Attempt-3 reviews provider."""

    slug: ClassVar[str] = SOURCE_SLUG
    category: ClassVar[Literal["reviews"]] = "reviews"
    cost_hint: ClassVar[Literal["per-1k"]] = "per-1k"
    version: ClassVar[str] = _VERSION
    required_env: ClassVar[tuple[str, ...]] = (ENV_KEY,)

    def fetch(
        self,
        site: str,
        *,
        ctx: FetchContext,
    ) -> tuple[ReviewsSignals | None, ProviderRunMetadata]:
        api_key = os.environ.get(ENV_KEY, "").strip()
        if not api_key:
            return None, ProviderRunMetadata(
                status="not_configured",
                latency_ms=0,
                error=f"missing env var: {ENV_KEY} — {NOT_CONFIGURED_SUGGESTION}",
                provider_version=self.version,
                cost_incurred=0,
            )

        # --mock mode short-circuits the network. Fixtures sit under
        # ``fixtures/<slug>/google_places.json`` with the shape
        # ``{"text_search": {...}, "details": {...}}`` — see the COX-5
        # fixture docs. This keeps golden-file tests byte-identical without
        # exercising the real API (and without leaking the key).
        if ctx.mock:
            return _from_fixture(site, ctx, version=self.version)

        return _from_network(site, api_key, ctx, version=self.version)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Candidate:
    place_id: str
    name: str


def _from_network(
    site: str,
    api_key: str,
    ctx: FetchContext,
    *,
    version: str,
) -> tuple[ReviewsSignals | None, ProviderRunMetadata]:
    hostname = _hostname_for(site)
    if hostname is None:
        return None, _failed(
            error=f"invalid site for places lookup: {site!r}",
            version=version,
            latency_ms=0,
            cost=0,
        )

    start = time.monotonic()

    # Text Search — always bills.
    try:
        search_payload = _request_json(
            _TEXT_SEARCH_URL,
            {"query": hostname, "key": api_key},
            timeout_s=ctx.timeout_s,
        )
    except _PlacesHTTPError as exc:
        return None, _failed(
            error=str(exc),
            version=version,
            latency_ms=_elapsed_ms(start),
            cost=_cost_cents(_TEXT_SEARCH_TENTHS),
        )

    search_err = _places_status_error(search_payload, leg="textsearch")
    if search_err is not None:
        return None, _failed(
            error=search_err,
            version=version,
            latency_ms=_elapsed_ms(start),
            cost=_cost_cents(_TEXT_SEARCH_TENTHS),
        )

    candidates = _candidates_from_search(search_payload)
    if not candidates:
        return None, _failed(
            error=f"no places result for hostname {hostname!r}",
            version=version,
            latency_ms=_elapsed_ms(start),
            cost=_cost_cents(_TEXT_SEARCH_TENTHS),
        )

    chosen = _pick_candidate(candidates)

    # Place Details — bills regardless of whether the fields come back populated.
    try:
        details_payload = _request_json(
            _DETAILS_URL,
            {"place_id": chosen.place_id, "fields": _DETAILS_FIELDS, "key": api_key},
            timeout_s=ctx.timeout_s,
        )
    except _PlacesHTTPError as exc:
        return None, _failed(
            error=str(exc),
            version=version,
            latency_ms=_elapsed_ms(start),
            cost=_cost_cents(_TEXT_SEARCH_TENTHS, _DETAILS_BASIC_ATMOSPHERE_TENTHS),
        )

    details_err = _places_status_error(details_payload, leg="details")
    if details_err is not None:
        return None, _failed(
            error=details_err,
            version=version,
            latency_ms=_elapsed_ms(start),
            cost=_cost_cents(_TEXT_SEARCH_TENTHS, _DETAILS_BASIC_ATMOSPHERE_TENTHS),
        )

    result = _reviews_from_details(details_payload)
    if result is None:
        return None, _failed(
            error=f"places details missing user_ratings_total for {hostname!r}",
            version=version,
            latency_ms=_elapsed_ms(start),
            cost=_cost_cents(_TEXT_SEARCH_TENTHS, _DETAILS_BASIC_ATMOSPHERE_TENTHS),
        )

    return result, ProviderRunMetadata(
        status="ok",
        latency_ms=_elapsed_ms(start),
        error=None,
        provider_version=version,
        cost_incurred=_cost_cents(_TEXT_SEARCH_TENTHS, _DETAILS_BASIC_ATMOSPHERE_TENTHS),
    )


def _from_fixture(
    site: str,
    ctx: FetchContext,
    *,
    version: str,
) -> tuple[ReviewsSignals | None, ProviderRunMetadata]:
    """Read a Places fixture and return the same shape as the network path.

    Deterministic: latency is zero and ``cost_incurred`` is zero in --mock
    mode so byte-identical re-runs are guaranteed (the charge is a real-
    network concern).
    """
    if ctx.fixtures_dir is None:
        return None, _failed(
            error="mock mode requires fixtures_dir",
            version=version,
            latency_ms=0,
            cost=0,
        )
    slug = _fixture_slug(site)
    if slug is None:
        return None, _failed(
            error=f"invalid fixture slug for site {site!r}",
            version=version,
            latency_ms=0,
            cost=0,
        )

    base = Path(ctx.fixtures_dir).resolve(strict=False)
    fixture_path = (base / slug / "google_places.json").resolve(strict=False)
    try:
        fixture_path.relative_to(base)
    except ValueError:
        return None, _failed(
            error=f"fixture path escapes fixtures_dir: {fixture_path}",
            version=version,
            latency_ms=0,
            cost=0,
        )
    if not fixture_path.exists():
        return None, _failed(
            error=f"google_places fixture not found: {fixture_path}",
            version=version,
            latency_ms=0,
            cost=0,
        )

    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, _failed(
            error=f"google_places fixture unreadable: {exc.__class__.__name__}: {exc}",
            version=version,
            latency_ms=0,
            cost=0,
        )
    if not isinstance(payload, dict):
        return None, _failed(
            error="google_places fixture must be a JSON object",
            version=version,
            latency_ms=0,
            cost=0,
        )

    # Two accepted fixture shapes:
    #   1. Full: ``{"text_search": {...}, "details": {...}}`` — exercises
    #      the candidate-picker heuristic end-to-end.
    #   2. Details-only: the raw Place Details response (the
    #      ``{"result": {...}, "status": "OK"}`` shape). Treated as a
    #      single-candidate lookup so existing fixtures written before
    #      the provider landed (e.g. ``fixtures/acme-bakery/
    #      google_places.json``) keep working.
    if "details" in payload or "text_search" in payload:
        search_payload = payload.get("text_search") or {}
        details_payload = payload.get("details") or {}
    else:
        search_payload = {}
        details_payload = payload

    if not isinstance(search_payload, dict) or not isinstance(details_payload, dict):
        return None, _failed(
            error="google_places fixture: text_search + details must be objects",
            version=version,
            latency_ms=0,
            cost=0,
        )

    if search_payload:
        search_err = _places_status_error(search_payload, leg="textsearch")
        if search_err is not None:
            return None, _failed(error=search_err, version=version, latency_ms=0, cost=0)

        candidates = _candidates_from_search(search_payload)
        if not candidates:
            hostname = _hostname_for(site) or site
            return None, _failed(
                error=f"no places result for hostname {hostname!r}",
                version=version,
                latency_ms=0,
                cost=0,
            )

    details_err = _places_status_error(details_payload, leg="details")
    if details_err is not None:
        return None, _failed(error=details_err, version=version, latency_ms=0, cost=0)

    result = _reviews_from_details(details_payload)
    if result is None:
        return None, _failed(
            error="places details missing user_ratings_total in fixture",
            version=version,
            latency_ms=0,
            cost=0,
        )

    return result, ProviderRunMetadata(
        status="ok",
        latency_ms=0,
        error=None,
        provider_version=version,
        cost_incurred=0,
    )


class _PlacesHTTPError(Exception):
    """Raised by :func:`_request_json` when the HTTP layer fails.

    Internal to this module; the provider catches it at its boundary and
    returns a ``failed`` row.
    """


def _request_json(
    url: str,
    params: dict[str, str],
    *,
    timeout_s: float,
) -> dict[str, Any]:
    query = f"{url}?{urlencode(params)}"
    try:
        resp = requests.get(query, timeout=timeout_s, allow_redirects=False)
    except requests.RequestsError as exc:
        message = _redact_key(f"network error: {exc.__class__.__name__}", params)
        # Normalize timeout into the orchestrator's substring classifier.
        if "timeout" in exc.__class__.__name__.lower():
            message = "network_timeout: " + message
        raise _PlacesHTTPError(message) from exc

    status_code = getattr(resp, "status_code", 0)
    if status_code in (401, 403):
        resp.close()  # type: ignore[no-untyped-call]
        # Route into the classifier's ``blocked_by_antibot`` lane — for a
        # direct-API provider this reads as "auth/quota denial," which is
        # the closest existing code in the closed envelope-error set.
        raise _PlacesHTTPError(f"blocked_by_antibot (HTTP {status_code})")
    if status_code >= 400:
        resp.close()  # type: ignore[no-untyped-call]
        raise _PlacesHTTPError(f"places HTTP {status_code}")

    try:
        body = resp.text
    finally:
        resp.close()  # type: ignore[no-untyped-call]
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise _PlacesHTTPError(f"places JSON decode error: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise _PlacesHTTPError("places response was not a JSON object")
    return cast("dict[str, Any]", payload)


def _places_status_error(payload: dict[str, Any], *, leg: str) -> str | None:
    """Map a Places ``status`` + ``error_message`` to a failure string.

    Returns ``None`` when the payload's status is ``"OK"`` or
    ``"ZERO_RESULTS"`` (the zero-results branch is handled by the caller —
    it's not a failure, just an empty candidate list). Every other status
    prefixes with the Places code so the orchestrator's substring-based
    classifier can route it.
    """
    status = payload.get("status")
    if status in ("OK", "ZERO_RESULTS", None):
        return None
    message = payload.get("error_message") or status
    if status == "REQUEST_DENIED":
        return f"blocked_by_antibot (places {leg} REQUEST_DENIED: {message})"
    if status == "OVER_QUERY_LIMIT":
        return f"blocked_by_antibot (places {leg} OVER_QUERY_LIMIT: {message})"
    if status == "INVALID_REQUEST":
        return f"places {leg} INVALID_REQUEST: {message}"
    return f"places {leg} status {status}: {message}"


def _candidates_from_search(payload: dict[str, Any]) -> list[_Candidate]:
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    out: list[_Candidate] = []
    for raw in results:
        if not isinstance(raw, dict):
            continue
        place_id = raw.get("place_id")
        if not isinstance(place_id, str) or not place_id:
            continue
        name = raw.get("name") if isinstance(raw.get("name"), str) else ""
        out.append(_Candidate(place_id=place_id, name=str(name or "")))
    return out


def _pick_candidate(candidates: list[_Candidate]) -> _Candidate:
    """Pick the first Text Search result — Google's prominence ordering.

    An earlier draft tried to pick by matching a candidate's ``website``
    against the input site, but the legacy Text Search endpoint does NOT
    return ``website`` in its result bundle (see Google's "Text Search
    (Legacy)" + "Place Data Fields (Legacy)" docs). Verifying the pick
    would require a Place Details + Contact-bundle billing hit per
    candidate, which dwarfs the $32/1k Text Search cost. We accept the
    first result and surface the ``place_id`` in the provenance row so
    downstream agents can branch on ambiguity if they need to.
    """
    return candidates[0]


def _reviews_from_details(payload: dict[str, Any]) -> ReviewsSignals | None:
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    count_raw = result.get("user_ratings_total")
    if not isinstance(count_raw, int):
        return None
    rating_raw = result.get("rating")
    rating = float(rating_raw) if isinstance(rating_raw, (int, float)) else None
    return ReviewsSignals(count=count_raw, rating=rating, source=SOURCE_SLUG)


def _hostname_for(site: str) -> str | None:
    if not site:
        return None
    parsed = urlparse(site if "://" in site else f"https://{site}")
    host = (parsed.netloc or parsed.path).lower().strip("/")
    if not host or "/" in host or "\\" in host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


_SAFE_SLUG_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-_")


def _fixture_slug(site: str) -> str | None:
    host = _hostname_for(site)
    if host is None:
        return None
    slug, _, _ = host.partition(".")
    if not slug:
        return None
    if not all(ch in _SAFE_SLUG_CHARS for ch in slug):
        return None
    return slug


def _redact_key(message: str, params: dict[str, str]) -> str:
    key = params.get("key")
    if key:
        return message.replace(key, "<redacted>")
    return message


def _failed(
    *,
    error: str,
    version: str,
    latency_ms: int,
    cost: int,
) -> ProviderRunMetadata:
    return ProviderRunMetadata(
        status="failed",
        latency_ms=latency_ms,
        error=error,
        provider_version=version,
        cost_incurred=cost,
    )


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


__all__ = [
    "ENV_KEY",
    "NOT_CONFIGURED_SUGGESTION",
    "Provider",
    "SOURCE_SLUG",
]
