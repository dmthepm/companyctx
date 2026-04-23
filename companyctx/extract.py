"""Shared HTML → SiteSignals extractors.

The zero-key provider and the smart-proxy recovery path both need to turn raw
HTML into ``SiteSignals``. Provider modules are forbidden from importing each
other (see ``docs/PROVIDERS.md``), so the shared muscle lives here.

These helpers are deterministic: given the same bytes, they produce the same
output. That's what keeps ``--mock`` runs byte-identical and makes the
regression corpus a meaningful guard rail.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

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
    """Deterministic, high-confidence tech fingerprinting from the HTML surface.

    "High-confidence" means signals the site physically asserts about its
    own stack:

    1. ``<meta name="generator">`` — the canonical platform declaration.
    2. Framework-owned asset hostnames / paths in ``<script src>`` /
       ``<link href>`` (e.g. ``cdn.shopify.com``, ``/wp-content/``,
       ``wixstatic.com``, ``static1.squarespace.com``). A matching URL
       there means the page is *loading* the framework, not just naming
       it.
    3. Framework-specific class tokens or ``data-*`` attributes on the
       ``<html>`` / ``<body>`` element (e.g. ``wp-elementor``,
       ``sqs-site``, ``data-wf-site``). These are author-controlled
       page-shell markers, not incidental strings.

    Bare mentions of a framework name in prose, legacy HTML comments,
    unrelated third-party widget src URLs, or a blog post body do **not**
    count. That was the false-positive vector that produced
    ``["WordPress", "Shopify", "Squarespace"]`` on a single page during
    the v0.2.0 RC dogfood (#78 / COX-43) — three mutually-exclusive
    platforms asserting co-presence is the diagnostic signature of a
    substring match laundering *mention* as *presence*, which crosses
    into inference (invariant #7).
    """
    soup = BeautifulSoup(html, "lxml")
    hits: list[str] = []

    generator = ""
    generator_meta = soup.find("meta", attrs={"name": re.compile(r"^generator$", re.I)})
    if isinstance(generator_meta, Tag):
        content = generator_meta.get("content")
        if isinstance(content, str):
            generator = content.lower()
    generator_tokens = set(re.findall(r"[a-z0-9.]+", generator))

    # Load-bearing resource URLs only. ``<script src>`` is always a load;
    # ``<link>`` is only a load when ``rel`` names one of the fetch-type
    # relations (``stylesheet``, ``preload`` with a script/style ``as``
    # hint, ``modulepreload``). Hint-style relations (``preconnect``,
    # ``dns-prefetch``), pointer-style relations (``canonical``,
    # ``alternate``), and chrome-adjacent relations (``icon``,
    # ``apple-touch-icon``, ``manifest``) name a URL without loading it —
    # a preconnect to ``cdn.shopify.com`` or a canonical pointing at a
    # ``.myshopify.com`` feed is not evidence the page runs Shopify.
    _LOAD_BEARING_LINK_RELS = {"stylesheet", "preload", "modulepreload"}
    asset_urls: list[str] = []
    for tag in soup.find_all(["script", "link"]):
        if not isinstance(tag, Tag):
            continue
        if tag.name == "script":
            src = tag.get("src")
            if isinstance(src, str) and src:
                asset_urls.append(src.lower())
            continue
        rel_raw = tag.get("rel")
        rels: list[str] = []
        if isinstance(rel_raw, list):
            rels = [str(r).lower() for r in rel_raw]
        elif isinstance(rel_raw, str):
            rels = [rel_raw.lower()]
        if not any(r in _LOAD_BEARING_LINK_RELS for r in rels):
            continue
        if "preload" in rels:
            as_attr = tag.get("as")
            as_val = as_attr.lower() if isinstance(as_attr, str) else ""
            if as_val not in {"script", "style"}:
                continue
        href = tag.get("href")
        if isinstance(href, str) and href:
            asset_urls.append(href.lower())

    html_tag = soup.html if isinstance(soup.html, Tag) else None
    body_tag = soup.body if isinstance(soup.body, Tag) else None

    def _class_tokens(tag: Tag | None) -> list[str]:
        if tag is None:
            return []
        raw = tag.get("class")
        if isinstance(raw, list):
            return [str(c).lower() for c in raw]
        if isinstance(raw, str):
            return [raw.lower()]
        return []

    def _attr_names(tag: Tag | None) -> list[str]:
        if tag is None:
            return []
        return [name.lower() for name in tag.attrs]

    body_classes = _class_tokens(body_tag)
    html_classes = _class_tokens(html_tag)
    html_attr_names = _attr_names(html_tag)
    body_attr_names = _attr_names(body_tag)

    def _in_assets(needle: str) -> bool:
        return any(needle in url for url in asset_urls)

    def _generator_has_token(token: str) -> bool:
        return token in generator_tokens

    def _generator_has_all_tokens(*tokens: str) -> bool:
        return all(token in generator_tokens for token in tokens)

    def _class_token_matches(*prefixes: str) -> bool:
        """Match full class token exactly, or as a hyphen-delimited prefix.

        ``class="wp-elementor"`` matches ``wp-elementor`` exactly; ``class=
        "elementor-default"`` matches prefix ``elementor`` (token starts with
        ``elementor-``). ``class="content-elementor-like"`` matches neither,
        so arbitrary substrings containing a framework name don't fire.
        """
        for tok in body_classes + html_classes:
            for p in prefixes:
                if tok == p or tok.startswith(f"{p}-"):
                    return True
        return False

    def _has_attr(name: str) -> bool:
        return name in html_attr_names or name in body_attr_names

    if (
        _generator_has_token("wordpress")
        or _in_assets("/wp-content/")
        or _in_assets("/wp-includes/")
    ):
        hits.append("WordPress")

    if (
        _generator_has_token("elementor")
        or _class_token_matches("elementor", "wp-elementor")
        or _in_assets("/plugins/elementor/")
    ):
        hits.append("Elementor")

    if (
        _generator_has_token("shopify")
        or _in_assets("cdn.shopify.com")
        or _in_assets(".myshopify.com")
    ):
        hits.append("Shopify")

    if (
        _generator_has_token("squarespace")
        or _in_assets(".squarespace.com")
        or _class_token_matches("sqs-site")
    ):
        hits.append("Squarespace")

    if (
        _generator_has_token("wix.com")
        or _generator_has_all_tokens("wix", "website")
        or _in_assets("wixstatic.com")
        or _class_token_matches("wix-site")
    ):
        hits.append("Wix")

    if (
        _generator_has_token("webflow")
        or _has_attr("data-wf-site")
        or _has_attr("data-wf-page")
        or _in_assets(".webflow.com")
        or _in_assets("assets.website-files.com")
        or _in_assets("uploads-ssl.webflow.com")
    ):
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
