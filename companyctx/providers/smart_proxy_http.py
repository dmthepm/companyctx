"""URL-style smart-proxy provider — vendor-agnostic Attempt 2.

Reads a proxy URL from ``COMPANYCTX_SMART_PROXY_URL`` (user-embedded creds).
The env-unset case returns ``not_configured`` — the envelope surfaces it as
an actionable ``suggestion`` pointing at the env var. On configured failure
(auth error / upstream block / timeout) returns ``failed`` with a concrete
reason. Never raises.

Covers the 80% case: any residential or datacenter proxy that accepts plain
HTTP-over-CONNECT with the vendor's credentials folded into the URL. For
session-API-style vendors (per-request endpoints, JSON payload shape), a
different provider class will land alongside — this one is intentionally
narrow.

Mock mode reads ``fixtures/<slug>/homepage.html`` (same slug the zero-key
provider uses). When both ``fixture-block.txt`` and ``homepage.html`` are
present the zero-key path still raises (the sentinel wins inside that
provider), but the smart-proxy's mock path reads the homepage file to
simulate a vendor recovery — this is how the waterfall-recovery acceptance
test is wired.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import ClassVar, Literal
from urllib.parse import urljoin, urlparse

from curl_cffi import requests

from companyctx.providers.base import FetchContext
from companyctx.providers.smart_proxy_base import failed_metadata, not_configured_metadata
from companyctx.robots import is_allowed
from companyctx.schema import ProviderRunMetadata
from companyctx.security import (
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    UnsafeURLError,
    validate_public_http_url,
)

_VERSION = "0.1.0"
ENV_URL = "COMPANYCTX_SMART_PROXY_URL"
ENV_VERIFY = "COMPANYCTX_SMART_PROXY_VERIFY"
NOT_CONFIGURED_SUGGESTION = (
    "export COMPANYCTX_SMART_PROXY_URL='http://user:pass@host:port' "
    "to wire your residential-proxy vendor"
)
_SAFE_FIXTURE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class Provider:
    """Vendor-agnostic URL-style smart-proxy fetcher.

    Reads creds from ``COMPANYCTX_SMART_PROXY_URL`` and routes ``fetch()``
    calls through that proxy. The user picks their vendor; we ship the
    contract.
    """

    slug: ClassVar[str] = "smart_proxy_http"
    category: ClassVar[Literal["smart_proxy"]] = "smart_proxy"
    cost_hint: ClassVar[Literal["per-call"]] = "per-call"
    version: ClassVar[str] = _VERSION
    # Environment variables the provider needs before it can run. ``providers
    # list`` surfaces missing entries as a ``not_configured`` row with an
    # actionable reason so users see the wiring gap before the first fetch.
    required_env: ClassVar[tuple[str, ...]] = (ENV_URL,)

    def fetch(
        self,
        url: str,
        *,
        ctx: FetchContext,
    ) -> tuple[bytes | None, ProviderRunMetadata]:
        proxy_url = os.environ.get(ENV_URL, "").strip()
        if not proxy_url:
            return None, not_configured_metadata(
                provider_version=self.version,
                missing_env=ENV_URL,
                suggestion=NOT_CONFIGURED_SUGGESTION,
            )

        start = time.monotonic()
        try:
            body = (
                _from_fixture(url, ctx.fixtures_dir)
                if ctx.mock
                else _from_network(url, proxy_url, ctx)
            )
        except _ProxyError as exc:
            return None, failed_metadata(
                provider_version=self.version,
                error=str(exc),
                latency_ms=0 if ctx.mock else _elapsed_ms(start),
            )
        except Exception as exc:  # pragma: no cover — defensive boundary
            return None, failed_metadata(
                provider_version=self.version,
                error=f"unexpected: {exc!r}",
                latency_ms=0 if ctx.mock else _elapsed_ms(start),
            )

        return body, ProviderRunMetadata(
            status="ok",
            latency_ms=0 if ctx.mock else _elapsed_ms(start),
            error=None,
            provider_version=self.version,
            cost_incurred=0,
        )


class _ProxyError(Exception):
    pass


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _from_fixture(url: str, fixtures_dir: str | None) -> bytes:
    if fixtures_dir is None:
        raise _ProxyError("mock mode requires fixtures_dir")
    root = _safe_fixture_root(fixtures_dir, _slug_for(url))
    homepage = _safe_child(root, "homepage.html")
    if not homepage.exists():
        raise _ProxyError(f"smart-proxy mock: fixture missing {homepage}")
    return homepage.read_bytes()


def _from_network(url: str, proxy_url: str, ctx: FetchContext) -> bytes:
    """Fetch via the user-configured proxy with the same guardrails as the zero-key path.

    The proxy handles DNS resolution for the target, but we still validate
    the host locally so a user typo like ``fetch http://169.254.169.254``
    can't be laundered into the run. Redirects are followed manually and
    every hop is re-validated; response bytes stream in under
    :data:`MAX_RESPONSE_BYTES`.
    """
    target = url if "://" in url else f"https://{url}"
    verify_path = os.environ.get(ENV_VERIFY, "").strip()
    current = target
    seen = 0
    while True:
        _ensure_safe_for_fetch(current, ctx)
        try:
            resp = requests.get(
                current,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=ctx.timeout_s,
                # curl_cffi types ``verify`` as ``bool | None`` but accepts a
                # CA-bundle path at runtime (same shape as ``requests``).
                verify=verify_path if verify_path else True,  # type: ignore[arg-type]
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestsError as exc:
            raise _ProxyError(f"proxy network error: {exc.__class__.__name__}") from exc

        status_code = getattr(resp, "status_code", 0)
        if status_code in _REDIRECT_STATUSES:
            headers = getattr(resp, "headers", {}) or {}
            location = headers.get("location") or headers.get("Location")
            resp.close()  # type: ignore[no-untyped-call]
            if not location:
                raise _ProxyError(f"HTTP {status_code} with no Location header")
            seen += 1
            if seen > MAX_REDIRECTS:
                raise _ProxyError(f"redirect limit ({MAX_REDIRECTS}) exceeded")
            current = urljoin(current, location)
            continue

        if status_code in (401, 403):
            resp.close()  # type: ignore[no-untyped-call]
            raise _ProxyError(f"proxy auth/block (HTTP {status_code})")
        if status_code >= 400:
            resp.close()  # type: ignore[no-untyped-call]
            raise _ProxyError(f"proxy upstream HTTP {status_code}")

        try:
            return _read_capped_body(resp)
        finally:
            resp.close()  # type: ignore[no-untyped-call]


def _ensure_safe_for_fetch(url: str, ctx: FetchContext) -> None:
    """SSRF + robots.txt guardrails — order matters.

    Validate the URL before any resolution side effect. Robots is checked
    after SSRF so we never issue a ``robots.txt`` request against a
    cloud-metadata or RFC 1918 endpoint.
    """
    try:
        validate_public_http_url(url)
    except UnsafeURLError as exc:
        # Carry the category token (COX-49) so the classifier routes NXDOMAIN
        # through ``no_provider_succeeded`` rather than ``ssrf_rejected``.
        raise _ProxyError(f"unsafe_url:{exc.category}: {exc}") from exc
    if not ctx.ignore_robots and not is_allowed(url, user_agent=ctx.user_agent):
        raise _ProxyError("blocked_by_robots")


def _read_capped_body(resp: requests.Response) -> bytes:
    """Stream response bytes, refusing to exceed :data:`MAX_RESPONSE_BYTES`."""
    headers = getattr(resp, "headers", {}) or {}
    declared = headers.get("content-length") or headers.get("Content-Length")
    if declared is not None:
        try:
            if int(declared) > MAX_RESPONSE_BYTES:
                raise _ProxyError(
                    f"response_too_large: content-length {declared} exceeds {MAX_RESPONSE_BYTES}"
                )
        except ValueError:
            # Bogus / non-integer Content-Length header — ignore the declared
            # size and fall through to the streaming cap, which enforces the
            # same limit on actual bytes read.
            pass
    buf = bytearray()
    for chunk in resp.iter_content(chunk_size=8192):  # type: ignore[no-untyped-call]
        buf.extend(chunk)
        if len(buf) > MAX_RESPONSE_BYTES:
            raise _ProxyError(f"response_too_large: exceeded {MAX_RESPONSE_BYTES} bytes")
    return bytes(buf)


def _safe_fixture_root(fixtures_dir: str, slug: str) -> Path:
    """Resolve ``fixtures_dir / slug`` and refuse if it escapes the tree."""
    base = Path(fixtures_dir).resolve(strict=False)
    candidate = (base / slug).resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise _ProxyError(f"fixture path escapes fixtures_dir: {candidate}") from exc
    return candidate


def _safe_child(root: Path, name: str) -> Path:
    """Resolve ``root / name`` and refuse if the result escapes ``root``."""
    candidate = (root / name).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise _ProxyError(f"fixture file escapes fixtures_dir: {candidate}") from exc
    return candidate


def _slug_for(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path).lower().rstrip("/")
    if host.startswith("www."):
        host = host[4:]
    slug, _, _ = host.partition(".")
    if not slug or not _SAFE_FIXTURE_SLUG_RE.fullmatch(slug):
        raise _ProxyError(f"invalid fixture slug: {slug or host!r}")
    return slug


__all__ = ["ENV_URL", "ENV_VERIFY", "NOT_CONFIGURED_SUGGESTION", "Provider"]
