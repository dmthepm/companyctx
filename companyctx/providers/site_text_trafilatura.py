"""Zero-key stealth provider — homepage + about + services text extraction.

Attempt 1 of the Deterministic Waterfall. Given a site (or a fixture slug),
fetch the homepage / about / services pages and populate ``SiteSignals`` with
raw observations only — no inference.

**Stealth-lib status.** Issue #15's acceptance requires the TLS-impersonation
library choice be measured against the 30-prospect corpus before landing. That
spike is a scope gap for this PR (no network access from the agent sandbox).
The real-network path here uses ``requests`` with a realistic Chrome
User-Agent so the graceful-partial contract is exercisable end-to-end. Swap in
``curl_cffi`` behind :func:`_stealth_fetch` once the spike is done.
The placeholder still respects ``robots.txt`` by default.

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

import requests
from bs4 import BeautifulSoup

from companyctx.providers.base import FetchContext
from companyctx.robots import is_allowed
from companyctx.schema import ProviderRunMetadata, SiteSignals

_VERSION = "0.1.0"
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
    homepage = root / "homepage.html"
    if not homepage.exists():
        raise _MissingFixtureError(f"fixture not found: {homepage}")
    homepage_html = homepage.read_text(encoding="utf-8")
    homepage_text = _extract_body_text(homepage_html)
    about = root / "about.html"
    about_text = _extract_body_text(about.read_text(encoding="utf-8")) if about.exists() else None
    services_path = root / "services.html"
    services = (
        _extract_services(services_path.read_text(encoding="utf-8"))
        if services_path.exists()
        else []
    )
    tech_stack = _detect_tech_stack(homepage_html)
    return SiteSignals(
        homepage_text=homepage_text,
        about_text=about_text,
        services=services,
        tech_stack=tech_stack,
    )


def _from_network(site: str, ctx: FetchContext) -> SiteSignals:
    base = _normalize_base_url(site)
    homepage_html = _stealth_fetch(base, ctx)
    homepage_text = _extract_body_text(homepage_html)
    about_html = _try_fetch(f"{base}/about", ctx)
    about_text = _extract_body_text(about_html) if about_html else None
    services_html = _try_fetch(f"{base}/services", ctx)
    services = _extract_services(services_html) if services_html else []
    tech_stack = _detect_tech_stack(homepage_html)
    return SiteSignals(
        homepage_text=homepage_text,
        about_text=about_text,
        services=services,
        tech_stack=tech_stack,
    )


def _stealth_fetch(url: str, ctx: FetchContext) -> str:
    if not ctx.ignore_robots and not is_allowed(url, user_agent=ctx.user_agent):
        raise _BlockedError("blocked_by_robots")
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": ctx.user_agent, "Accept": "text/html,*/*;q=0.8"},
            timeout=ctx.timeout_s,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
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


def _extract_body_text(html: str) -> str:
    # Local import so the provider module itself doesn't pay the trafilatura
    # import cost when only consumers of the schema touch this file.
    import trafilatura  # noqa: PLC0415

    extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
    if extracted:
        return extracted.strip()
    # Fallback: raw body text, stripped. Trafilatura returns None on empty or
    # JS-only pages; we still want a deterministic non-null string.
    soup = BeautifulSoup(html, "lxml")
    body = soup.body
    return body.get_text(separator="\n", strip=True) if body else ""


def _extract_services(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    items: list[str] = []
    for li in soup.select("ul li"):
        strong = li.find("strong")
        raw = strong.get_text(strip=True) if strong else li.get_text(" ", strip=True)
        cleaned = raw.rstrip(". ").strip()
        if cleaned:
            items.append(cleaned)
    return items


def _detect_tech_stack(html: str) -> list[str]:
    """Minimal, deterministic tech fingerprinting from the HTML surface."""
    hits: list[str] = []
    lowered = html.lower()
    if "wp-content" in lowered or "wordpress" in lowered or "wp-elementor" in lowered:
        hits.append("WordPress")
    if "elementor" in lowered:
        hits.append("Elementor")
    if "shopify" in lowered:
        hits.append("Shopify")
    if "squarespace" in lowered or "sqs-site" in lowered:
        hits.append("Squarespace")
    if "wix-site" in lowered or "wixsite" in lowered:
        hits.append("Wix")
    if "webflow" in lowered:
        hits.append("Webflow")
    # Deduplicate while preserving first-seen order.
    seen: set[str] = set()
    out: list[str] = []
    for tech in hits:
        if tech not in seen:
            seen.add(tech)
            out.append(tech)
    return out


__all__ = ["Provider"]
