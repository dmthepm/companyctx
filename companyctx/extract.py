"""Shared HTML → SiteSignals extractors.

The zero-key provider and the smart-proxy recovery path both need to turn raw
HTML into ``SiteSignals``. Provider modules are forbidden from importing each
other (see ``docs/PROVIDERS.md``), so the shared muscle lives here.

These helpers are deterministic: given the same bytes, they produce the same
output. That's what keeps ``--mock`` runs byte-identical and makes the
regression corpus a meaningful guard rail.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from companyctx.schema import SiteSignals

# Empty-response honesty threshold (COX-44 + COX-52). The measure is
# UTF-8 byte length, not ``len(text)`` — a 40-character CJK or accented
# homepage that extracts to ~120 UTF-8 bytes is fine; raw character
# count would mis-flag multibyte scripts. Below the cutoff the fetch
# worked but the site returned too little to synthesise a brief from
# (blank body, login-wall stub, JS-only landing with no SSR content,
# Wix/SPA shell that only renders after JS). The v0.3.0 cutoff of 64
# bytes only caught truly-empty bodies; the v0.2 partner-integration
# validation (n=209, `research/2026-04-22-v0.2-joel-integration-
# validation.md` §3) measured 41 / 209 = 19.6 % of `status: ok`
# envelopes returning <1 KiB of extracted text — "FM-7 thin-body."
# These were `ok`-but-partner-unusable. v0.4.0 raises the floor to
# 1024 bytes so the thin-body class surfaces as structured
# `empty_response` instead of silent success. The p50 extracted-text
# size on successful runs in that validation was 2.29 KiB, well above
# the new floor, so raising it loses ~0 legitimate `ok` envelopes.
# Both the zero-key provider and the smart-proxy recovery path consult
# this gate so Attempt 1 and Attempt 2 enforce the same contract.
EMPTY_RESPONSE_BYTES = 1024
EMPTY_RESPONSE_ERROR = "empty_response"


def is_empty_response(homepage_text: str) -> bool:
    """Return True when the extracted text is below the empty-response cutoff.

    Measures UTF-8 byte length so multibyte scripts don't false-positive
    as empty. Called after extraction, not on raw response bytes — the
    gate is about "was there anything useful to say" after trafilatura /
    BS4 stripped chrome.
    """
    return len(homepage_text.encode("utf-8")) < EMPTY_RESPONSE_BYTES


def extract_body_text(html: str) -> str:
    """Return the main-body text of one HTML document.

    Uses ``trafilatura`` first (its extractor strips navs/chrome); falls back
    to a plain ``<body>`` text sweep when trafilatura returns nothing (empty
    / JS-only pages). The fallback keeps the output a deterministic non-null
    string so callers can assert shape without None-guards.
    """
    import trafilatura  # noqa: PLC0415

    extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
    if extracted:
        return extracted.strip()
    soup = BeautifulSoup(html, "lxml")
    body = soup.body
    return body.get_text(separator="\n", strip=True) if body else ""


def extract_services(html: str) -> list[str]:
    """Pull a services list from a ``<ul>`` block. Returns [] when nothing matches."""
    soup = BeautifulSoup(html, "lxml")
    items: list[str] = []
    for li in soup.select("ul li"):
        strong = li.find("strong")
        raw = strong.get_text(strip=True) if strong else li.get_text(" ", strip=True)
        cleaned = raw.rstrip(". ").strip()
        if cleaned:
            items.append(cleaned)
    return items


def detect_tech_stack(html: str) -> list[str]:
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
    seen: set[str] = set()
    out: list[str] = []
    for tech in hits:
        if tech not in seen:
            seen.add(tech)
            out.append(tech)
    return out


def site_signals_from_homepage_bytes(body: bytes) -> SiteSignals:
    """Build a ``pages``-slot payload from raw homepage bytes only.

    Used by the waterfall's Attempt-2 smart-proxy recovery: the smart-proxy
    hands back raw bytes for the homepage URL, and this function projects
    those bytes into the same schema slot the zero-key extractor would fill.
    ``about_text`` and ``services`` stay unset — recovering them would
    require additional proxy calls (scope for a follow-on).
    """
    try:
        html = body.decode("utf-8")
    except UnicodeDecodeError:
        html = body.decode("utf-8", errors="replace")
    return SiteSignals(
        homepage_text=extract_body_text(html),
        about_text=None,
        services=[],
        tech_stack=detect_tech_stack(html),
    )


__all__ = [
    "EMPTY_RESPONSE_BYTES",
    "EMPTY_RESPONSE_ERROR",
    "detect_tech_stack",
    "extract_body_text",
    "extract_services",
    "is_empty_response",
    "site_signals_from_homepage_bytes",
]
