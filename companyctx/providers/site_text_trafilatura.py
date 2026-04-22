"""Zero-key stealth provider — homepage + about + services text extraction.

Attempt 1 of the Deterministic Waterfall. Given a site (or a fixture slug),
fetch the homepage / about / services pages and populate ``SiteSignals`` with
raw observations only — no inference.

**Stealth-lib pick.** The real-network path uses ``curl_cffi`` pinned to
``impersonate="chrome146"``. The pick is measured in
``research/2026-04-21-tls-impersonation-spike.md`` and accepted in
``decisions/2026-04-20-zero-key-stealth-strategy.md``. The API shape is
drop-in compatible with the stdlib-style ``requests.get`` the provider
already expected, so the swap is contained to this module. ``robots.txt``
is still respected by default.

The ``--mock`` path is what the tests in this PR exercise; it reads
``fixtures/<slug>/{homepage,about,services}.html`` and returns deterministic
output modulo ``fetched_at`` (which is stamped by :mod:`companyctx.core`).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import ClassVar, Literal
from urllib.parse import urlparse

from curl_cffi import requests

from companyctx.extract import detect_tech_stack, extract_body_text, extract_services
from companyctx.providers.base import FetchContext
from companyctx.robots import is_allowed
from companyctx.schema import ProviderRunMetadata, SiteSignals

_VERSION = "0.1.0"
# curl_cffi types ``impersonate`` as a ``Literal`` of supported browser names.
# Keeping this as a Literal (rather than plain ``str``) threads through mypy
# strict without loosening the call-site signature. Bump with each curl_cffi
# release — fingerprint freshness is the real decay mode; see
# research/2026-04-21-tls-impersonation-spike.md.
_IMPERSONATE: Literal["chrome146"] = "chrome146"
_SAFE_FIXTURE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class Provider:
    """``site_text_trafilatura`` — zero-key homepage/about/services extractor."""

    slug: ClassVar[str] = "site_text_trafilatura"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = _VERSION

    def fetch(
        self,
        site: str,
        *,
        ctx: FetchContext,
    ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
        start = time.monotonic()
        try:
            if ctx.mock:
                signals = _from_fixture(site, ctx.fixtures_dir)
            else:
                signals = _from_network(site, ctx)
        except _BlockedError as exc:
            return None, _failed(exc.reason, start, self.version, mock=ctx.mock)
        except _MissingFixtureError as exc:
            return None, _failed(str(exc), start, self.version, mock=ctx.mock)
        except Exception as exc:  # pragma: no cover — defensive boundary
            return None, _failed(f"unexpected: {exc!r}", start, self.version, mock=ctx.mock)

        # Mock mode has no real network latency; zero it so --mock runs are
        # byte-identical across invocations (the determinism contract).
        latency_ms = 0 if ctx.mock else _elapsed_ms(start)
        return signals, ProviderRunMetadata(
            status="ok",
            latency_ms=latency_ms,
            error=None,
            provider_version=self.version,
            cost_incurred=0,
        )


class _BlockedError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _MissingFixtureError(Exception):
    pass


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _failed(reason: str, start: float, version: str, *, mock: bool = False) -> ProviderRunMetadata:
    return ProviderRunMetadata(
        status="failed",
        latency_ms=0 if mock else _elapsed_ms(start),
        error=reason,
        provider_version=version,
        cost_incurred=0,
    )


def _from_fixture(site: str, fixtures_dir: str | None) -> SiteSignals:
    if fixtures_dir is None:
        raise _MissingFixtureError("mock mode requires fixtures_dir")
    root = Path(fixtures_dir) / _slug_for(site)
    # Sentinel for committed network-failure regressions. The file's contents
    # become the BlockedError reason verbatim, which the orchestrator surfaces
    # as `provenance[slug].error`. See fixtures/README.md ("Network-failure
    # regressions") and the rationale in issue #40.
    block = root / "fixture-block.txt"
    if block.exists():
        reason = block.read_text(encoding="utf-8").strip()
        raise _BlockedError(reason or "blocked")
    homepage = root / "homepage.html"
    if not homepage.exists():
        raise _MissingFixtureError(f"fixture not found: {homepage}")
    homepage_html = homepage.read_text(encoding="utf-8")
    homepage_text = extract_body_text(homepage_html)
    about = root / "about.html"
    about_text = extract_body_text(about.read_text(encoding="utf-8")) if about.exists() else None
    services_path = root / "services.html"
    services = (
        extract_services(services_path.read_text(encoding="utf-8"))
        if services_path.exists()
        else []
    )
    tech_stack = detect_tech_stack(homepage_html)
    return SiteSignals(
        homepage_text=homepage_text,
        about_text=about_text,
        services=services,
        tech_stack=tech_stack,
    )


def _from_network(site: str, ctx: FetchContext) -> SiteSignals:
    base = _normalize_base_url(site)
    homepage_html = _stealth_fetch(base, ctx)
    homepage_text = extract_body_text(homepage_html)
    about_html = _try_fetch(f"{base}/about", ctx)
    about_text = extract_body_text(about_html) if about_html else None
    services_html = _try_fetch(f"{base}/services", ctx)
    services = extract_services(services_html) if services_html else []
    tech_stack = detect_tech_stack(homepage_html)
    return SiteSignals(
        homepage_text=homepage_text,
        about_text=about_text,
        services=services,
        tech_stack=tech_stack,
    )


def _stealth_fetch(url: str, ctx: FetchContext) -> str:
    if not ctx.ignore_robots and not is_allowed(url, user_agent=ctx.user_agent):
        raise _BlockedError("blocked_by_robots")
    # curl_cffi's ``impersonate`` sets the TLS ClientHello + HTTP/2 SETTINGS
    # frame + header order. Passing a custom User-Agent here would desynchronise
    # the presented UA from the impersonated fingerprint (cheap anti-bot tell),
    # so we deliberately don't override it.
    try:
        resp = requests.get(
            url,
            impersonate=_IMPERSONATE,
            timeout=ctx.timeout_s,
            allow_redirects=True,
        )
    except requests.RequestsError as exc:
        raise _BlockedError(f"network error: {exc.__class__.__name__}") from exc
    if resp.status_code in (401, 403):
        raise _BlockedError(f"blocked_by_antibot (HTTP {resp.status_code})")
    if resp.status_code >= 400:
        raise _BlockedError(f"HTTP {resp.status_code}")
    return resp.text


def _try_fetch(url: str, ctx: FetchContext) -> str | None:
    try:
        return _stealth_fetch(url, ctx)
    except _BlockedError:
        return None


def _normalize_base_url(site: str) -> str:
    parsed = urlparse(site if "://" in site else f"https://{site}")
    scheme = parsed.scheme or "https"
    host = parsed.netloc or parsed.path
    if scheme not in {"http", "https"}:
        raise _BlockedError(f"unsupported scheme: {scheme}")
    if not host or host in {".", ".."} or any(sep in host for sep in ("/", "\\")):
        raise _BlockedError("invalid site")
    return f"{scheme}://{host}".rstrip("/")


def _slug_for(site: str) -> str:
    parsed = urlparse(site if "://" in site else f"https://{site}")
    host = (parsed.netloc or parsed.path).lower().rstrip("/")
    if host.startswith("www."):
        host = host[4:]
    # fixtures/<slug>/ — the sanitized corpus uses stemmed slugs (no TLD).
    slug, _, _ = host.partition(".")
    if not slug or not _SAFE_FIXTURE_SLUG_RE.fullmatch(slug):
        raise _MissingFixtureError(f"invalid fixture slug: {slug or host!r}")
    return slug


__all__ = ["Provider"]
