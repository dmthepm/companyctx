#!/usr/bin/env python3
"""Shape-balanced zero-key probe harness — Wix / Webflow / SPA homepages.

Power the site-class coverage measurement for [issue #32](https://github.com/dmthepm/companyctx/issues/32)
(Linear COX-17). The TLS-impersonation spike (#21 / PR #26) and the 100-site
durability run (#22 / PR #41) both drew from a WordPress-dominated partner
seed list; this harness lets us deliberately re-probe against Wix, Webflow,
and JS-heavy SPA homepages.

Reuses the same guardrails the zero-key provider applies in
``companyctx/providers/site_text_trafilatura.py`` so the probe's
"reachable" numbers line up with what ``companyctx fetch`` actually
exercises:

1. ``curl_cffi.requests.get(url, impersonate="chrome146")`` — the stealth
   fetcher at the library's currently-pinned Chrome fingerprint.
2. :func:`companyctx.security.validate_public_http_url` pre-flight on
   the initial URL and on every redirect hop (SSRF guard).
3. Manual redirect walk capped at :data:`MAX_REDIRECTS` hops
   (``allow_redirects=False`` on each call).
4. Streamed response with a :data:`MAX_RESPONSE_BYTES` cap
   (gzip-bomb / oversize-body guard).
5. ``trafilatura.extract`` via ``companyctx.extract.extract_body_text`` —
   the same extractor the provider uses.

``robots.txt`` is honored by default (``is_allowed`` called with the
core's :data:`DEFAULT_USER_AGENT`, matching ``companyctx fetch`` —
UA-specific robots policies do not diverge between harness and
production). Pass ``--ignore-robots`` to skip. 2-second pacing floor
between requests. :data:`DEFAULT_TIMEOUT_S` per request, matching the
core orchestrator's default.

A probe-local shape-marker detector tags each row with the platform
actually observed in the HTML (``wix``, ``webflow``, ``next``,
``react``, ``vue``, ``nuxt``, ``wordpress``, ``other``). The provider's
``detect_tech_stack`` only identifies WordPress / Elementor / Shopify /
Squarespace / Wix / Webflow; SPA framework markers are detected here,
in the harness only — no production schema change.

Input CSV columns (header required):

    expected_shape,host,note

``expected_shape`` is free-text (``wix``, ``webflow``, ``spa``) — used only
for bucketing the committed report; the harness records the measured shape
independently so mis-classifications surface honestly.

Usage:

    python3 scripts/run-shape-probe.py \\
        --candidates .context/cox-17-probe/candidates.csv \\
        --out .context/cox-17-probe
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from curl_cffi import requests

from companyctx.core import DEFAULT_TIMEOUT_S, DEFAULT_USER_AGENT
from companyctx.extract import detect_tech_stack, extract_body_text
from companyctx.robots import is_allowed
from companyctx.security import (
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    UnsafeURLError,
    validate_public_http_url,
)

PACING_FLOOR_S = 2.0
IMPERSONATE = "chrome146"
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _normalize_url(host: str) -> str:
    if "://" not in host:
        host = f"https://{host}"
    parsed = urlparse(host)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}".rstrip("/")


# Strong, high-specificity framework/platform markers. The production
# ``detect_tech_stack`` uses loose substring checks (e.g. "webflow" in the
# page is a hit) which false-positive when a competitor/integration is
# merely mentioned in prose — see linear.app carrying `shopify` + `webflow`
# + `wordpress` substrings while actually being Next.js. We need tighter
# signatures here so the shape-bucket report reflects measured platform,
# not mentioned brand-names.
_WIX_STRONG_RE = re.compile(r"static\.parastorage\.com|wixsite\.com|_wix_", re.I)
_WEBFLOW_STRONG_RE = re.compile(r"data-wf-page|data-wf-site|class=\"w-layout", re.I)
_NEXT_STRONG_RE = re.compile(r"__NEXT_DATA__|/_next/static/|\"buildId\"\\s*:", re.I)
_NUXT_STRONG_RE = re.compile(r"__NUXT__|/_nuxt/", re.I)
_REACT_RE = re.compile(r"data-reactroot|data-reactid|react-dom", re.I)
_VUE_RE = re.compile(r"data-v-[0-9a-f]{8}|__vue_app__|vue\\.js", re.I)


def detect_shape(html: str) -> str:
    """Return the single most-specific platform/framework marker in ``html``.

    Order matters: SPA build-artefact markers (``__NEXT_DATA__``, ``_nuxt``)
    and the strict Wix/Webflow signatures beat the loose substring checks
    in :func:`companyctx.extract.detect_tech_stack`, because the loose
    checks trigger on any mention of the brand in prose — making Linear's
    Next.js homepage falsely read as Webflow when the word "webflow" shows
    up in a competitor tooltip.
    """
    tech = detect_tech_stack(html)
    # Strict platform signatures first.
    if _WIX_STRONG_RE.search(html) or "Wix" in tech and "wix-site" in html.lower():
        return "wix"
    if _WEBFLOW_STRONG_RE.search(html):
        return "webflow"
    if _NEXT_STRONG_RE.search(html):
        return "next"
    if _NUXT_STRONG_RE.search(html):
        return "nuxt"
    # Fall back to generic SPA-framework markers.
    if _VUE_RE.search(html):
        return "vue"
    if _REACT_RE.search(html):
        return "react"
    # Lastly the loose tech_stack — but only if a stricter signal didn't fire.
    if "Wix" in tech:
        return "wix"
    if "Webflow" in tech:
        return "webflow"
    if "WordPress" in tech:
        return "wordpress"
    if "Shopify" in tech:
        return "shopify"
    if "Squarespace" in tech:
        return "squarespace"
    return "other"


def _read_capped_body(resp: requests.Response) -> bytes:
    """Stream the response, refusing to exceed :data:`MAX_RESPONSE_BYTES`.

    Mirror of the guard in
    :func:`companyctx.providers.site_text_trafilatura._read_capped_body`
    so the probe cannot be weaponised as a gzip-bomb or
    resource-exhaustion vector via an attacker-controlled CSV entry.
    """
    declared = resp.headers.get("content-length") or resp.headers.get("Content-Length")
    if declared is not None:
        try:
            if int(declared) > MAX_RESPONSE_BYTES:
                raise _ProbeFetchError(
                    f"response_too_large: content-length {declared} exceeds {MAX_RESPONSE_BYTES}"
                )
        except ValueError:
            pass
    buf = bytearray()
    for chunk in resp.iter_content(chunk_size=8192):
        buf.extend(chunk)
        if len(buf) > MAX_RESPONSE_BYTES:
            raise _ProbeFetchError(f"response_too_large: exceeded {MAX_RESPONSE_BYTES} bytes")
    return bytes(buf)


class _ProbeFetchError(Exception):
    """Internal signal from the stealth-fetch path — same shape as the
    provider's private :class:`_BlockedError` but kept local to the
    harness so we never ``except`` production exceptions."""


def _stealth_fetch_guarded(url: str, timeout_s: float) -> tuple[int, str, int, int]:
    """Single fetch + SSRF + redirect + size-cap walk.

    Returns ``(status, body_text, body_bytes, redirects_followed)``.
    Raises :class:`_ProbeFetchError` on any guardrail trip (SSRF, redirect
    cap, over-size body, HTTP 4xx/5xx, transport error, decode error).
    """
    current = url
    hops = 0
    while True:
        try:
            validate_public_http_url(current)
        except UnsafeURLError as exc:
            raise _ProbeFetchError(f"unsafe_url: {exc}") from exc
        try:
            resp = requests.get(
                current,
                impersonate=IMPERSONATE,
                timeout=timeout_s,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestsError as exc:
            raise _ProbeFetchError(f"network: {exc.__class__.__name__}: {exc}") from exc

        if resp.status_code in _REDIRECT_STATUSES:
            location = resp.headers.get("location") or resp.headers.get("Location")
            resp.close()  # type: ignore[no-untyped-call]
            if not location:
                raise _ProbeFetchError(f"HTTP {resp.status_code} with no Location header")
            hops += 1
            if hops > MAX_REDIRECTS:
                raise _ProbeFetchError(f"redirect limit ({MAX_REDIRECTS}) exceeded")
            current = urljoin(current, location)
            continue

        status = resp.status_code
        if status in (401, 403):
            resp.close()  # type: ignore[no-untyped-call]
            raise _ProbeFetchError(f"blocked_by_antibot (HTTP {status})")
        if status >= 400:
            resp.close()  # type: ignore[no-untyped-call]
            raise _ProbeFetchError(f"HTTP {status}")
        try:
            body = _read_capped_body(resp)
        finally:
            resp.close()  # type: ignore[no-untyped-call]
        encoding = resp.encoding or "utf-8"
        text = body.decode(encoding, errors="replace")
        return status, text, len(body), hops


def probe_one(
    host: str,
    *,
    ignore_robots: bool = False,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict:
    """Single stealth-fetch probe.

    Applies the same guardrails the production zero-key provider does:
    SSRF pre-flight on every hop, ``MAX_REDIRECTS`` cap, streamed
    response capped at ``MAX_RESPONSE_BYTES``, ``DEFAULT_USER_AGENT`` for
    robots, ``DEFAULT_TIMEOUT_S`` per request.
    """
    url = _normalize_url(host)
    row: dict = {
        "host": host,
        "url": url,
        "impersonate": IMPERSONATE,
        "user_agent": user_agent,
        "timeout_s": timeout_s,
        "robots_allowed": None,
        "status": None,
        "redirects": 0,
        "bytes": 0,
        "extract_chars": 0,
        "extract_bytes": 0,
        "detected_shape": None,
        "tech_stack": [],
        "elapsed_ms": 0,
        "error": None,
        "outcome": None,
    }
    if not ignore_robots:
        try:
            allowed = is_allowed(url, user_agent=user_agent)
        except Exception as exc:  # pragma: no cover — defensive
            row["error"] = f"robots_check_error: {exc!r}"
            row["outcome"] = "robots_error"
            return row
        row["robots_allowed"] = allowed
        if not allowed:
            row["outcome"] = "blocked_by_robots"
            row["error"] = "blocked_by_robots"
            return row

    t0 = time.monotonic()
    try:
        status, html, body_bytes, hops = _stealth_fetch_guarded(url, timeout_s)
    except _ProbeFetchError as exc:
        row["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
        reason = str(exc)
        row["error"] = reason
        if reason.startswith("unsafe_url"):
            row["outcome"] = "unsafe_url"
        elif reason.startswith("blocked_by_antibot"):
            row["outcome"] = "blocked_by_antibot"
            row["status"] = 403 if "403" in reason else 401
        elif reason.startswith("redirect limit"):
            row["outcome"] = "redirect_loop"
        elif reason.startswith("response_too_large"):
            row["outcome"] = "response_too_large"
        elif reason.startswith("HTTP "):
            try:
                code = int(reason.split()[1])
                row["status"] = code
                row["outcome"] = f"http_{code}"
            except (IndexError, ValueError):
                row["outcome"] = "http_error"
        else:
            row["outcome"] = "network_error"
        return row

    row["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
    row["status"] = status
    row["bytes"] = body_bytes
    row["redirects"] = hops
    row["detected_shape"] = detect_shape(html)
    row["tech_stack"] = detect_tech_stack(html)
    extracted = extract_body_text(html) or ""
    row["extract_chars"] = len(extracted)
    row["extract_bytes"] = len(extracted.encode("utf-8"))
    row["outcome"] = "ok" if row["extract_bytes"] >= 1024 else "thin"
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidates", required=True, help="CSV: expected_shape,host,note")
    ap.add_argument(
        "--out",
        default=".context/cox-17-probe",
        help="output directory (default: .context/cox-17-probe)",
    )
    ap.add_argument("--ignore-robots", action="store_true", help="skip robots.txt check")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    with Path(args.candidates).open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    aggregate: list[dict] = []
    last_t = 0.0
    for i, row in enumerate(rows, 1):
        if last_t > 0:
            gap = time.monotonic() - last_t
            if gap < PACING_FLOOR_S:
                time.sleep(PACING_FLOOR_S - gap)
        last_t = time.monotonic()

        expected = row.get("expected_shape", "").strip()
        host = row.get("host", "").strip()
        note = row.get("note", "").strip()
        print(f"[{i:>2}/{len(rows)}] {expected:<8} {host}", flush=True)
        result = probe_one(host, ignore_robots=args.ignore_robots)
        result["expected_shape"] = expected
        result["note"] = note
        slug = re.sub(r"[^a-z0-9-]+", "-", host.lower()).strip("-") or "unknown"
        (runs_dir / f"{i:02d}-{slug}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        aggregate.append(result)
        print(
            f"    -> outcome={result['outcome']}  status={result['status']}  "
            f"bytes={result['bytes']}  extract={result['extract_bytes']}  "
            f"detected={result['detected_shape']}",
            flush=True,
        )

    (out_dir / "aggregate.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Shape-bucketed JSONL — hostnames and per-site notes included because the
    # probe sources (Wix/Webflow/made-in-webflow showcases, public SPA
    # marketing sites) are public. Contrast with the TLS spike's partner
    # CSV, which was private and so committed slug-only.
    public_rows = [
        {
            "expected_shape": r["expected_shape"],
            "host": r["host"],
            "detected_shape": r["detected_shape"],
            "outcome": r["outcome"],
            "status": r["status"],
            "bytes": r["bytes"],
            "extract_bytes": r["extract_bytes"],
            "elapsed_ms": r["elapsed_ms"],
            "redirects": r.get("redirects", 0),
            "error": r["error"],
            "tech_stack": r["tech_stack"],
        }
        for r in aggregate
    ]
    (out_dir / "probe-raw.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in public_rows) + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {len(aggregate)} rows -> {out_dir}/aggregate.json + probe-raw.jsonl")


if __name__ == "__main__":
    main()
