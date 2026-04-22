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
    "detect_tech_stack",
    "extract_body_text",
    "extract_services",
    "site_signals_from_homepage_bytes",
]
