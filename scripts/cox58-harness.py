#!/usr/bin/env python3
"""COX-58 live harness — v0.4.0 partner-integration re-validation.

Difference from ``scripts/run-durability-batch.py``:

1. Shells out to the pipx-installed ``~/.local/bin/companyctx`` binary (real
   PyPI install at v0.4.0) rather than ``python -m companyctx.cli`` against
   the editable worktree. Issue #108 scope §1 explicitly asks for the PyPI
   install so the run mirrors what a partner sees.
2. Captures ALL provenance rows (``site_text_trafilatura`` AND
   ``reviews_google_places``), surfaces per-row ``cost_incurred`` in cents,
   and carries an ``empty_response_floor`` column for §4 FM-7
   reclassification accounting.
3. Honors ``--refresh`` on the first pass so cache state from prior smoke
   tests cannot bleed into the live measurement.

Input CSV columns (from ``cox58-build-sample.py``): ``niche,position,slug,
host,heading``.

Output:
- ``<out-dir>/runs/<slug>.json`` — full envelope + wall-clock timing.
- ``<out-dir>/aggregate.csv`` — flat table suitable for §1/§2/§3/§4 rollups.

Cost accounting convention: ``cost_incurred`` is integer US cents as emitted
by the providers themselves — the aggregate sums them and the report
converts to dollars at write time.

The ``GOOGLE_PLACES_API_KEY`` env var is expected to be set by the caller
(``set -a; source .env.local; set +a`` upstream). The harness does not read
``.env.local`` itself — env propagation is the caller's job.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from pathlib import Path

PACING_FLOOR_S = 2.0
SUBPROCESS_TIMEOUT_S = 60.0  # Bumped from 45s — reviews leg adds up to ~10s.
FM7_THIN_BYTES = 1024
CCX_BIN_DEFAULT = str(Path.home() / ".local" / "bin" / "companyctx")


def classify(env: dict, bytes_: int) -> tuple[str, str]:
    """Return (outcome, fm_code) for reporting.

    Outcomes: ok | thin_ok | partial | degraded | crash.

    On v0.4, the 1024-byte floor in the provider's extraction path now
    reclassifies thin-body successes to ``status=degraded`` +
    ``error.code=empty_response``. So ``thin_ok`` (<1024 bytes + status=ok)
    should be rare — if it shows up it's a v0.4 regression, not FM-7.
    """
    status = env.get("status", "crash")
    if status == "ok":
        if bytes_ < FM7_THIN_BYTES:
            # Would be a regression on v0.4 — flag it.
            return "thin_ok", "FM-7-regress"
        return "ok", "none"
    err_obj = env.get("error") or {}
    err_code = (err_obj.get("code") if isinstance(err_obj, dict) else "") or ""
    # Prefer the structured error.code — v0.4 makes this first-class.
    # Composite status may be "partial" (reviews succeeded) or "degraded"
    # (nothing succeeded); bucket both into FM-7 for reclassification
    # accounting. Tracking the surrounding status in the outcome column
    # preserves the detail.
    if err_code == "empty_response":
        return (status if status in ("partial", "degraded") else "degraded"), "FM-7"
    if err_code == "no_provider_succeeded":
        return status, "FM-no-provider"
    if err_code == "network_timeout":
        return status, "FM-13"
    if err_code == "blocked_by_antibot":
        return status, "FM-1"
    if err_code == "ssrf_rejected":
        return status, "FM-ssrf"
    if err_code:
        return status, f"FM-{err_code}"
    # Fall back to provenance sniffing if error.code isn't populated.
    prov = env.get("provenance") or {}
    err_str = ""
    for meta in prov.values():
        if meta.get("status") in ("failed", "degraded", "not_configured"):
            err_str = (meta.get("error") or "").lower()
            break
    if "http 4" in err_str:
        return status, "HTTP-4xx"
    if "http 5" in err_str:
        return status, "HTTP-5xx"
    if "timeout" in err_str:
        return status, "FM-13"
    if any(k in err_str for k in ("nxdomain", "name or service", "resolve", "dnserror")):
        return status, "DNS"
    if "network error" in err_str or "connection" in err_str:
        return status, "network"
    return status, "unclassified"


def summarise(env: dict, bytes_: int) -> dict:
    """Compress an envelope into aggregate-row columns."""
    prov = env.get("provenance") or {}
    site_text = prov.get("site_text_trafilatura") or {}
    reviews = prov.get("reviews_google_places") or {}
    data = env.get("data") or {}
    reviews_payload = data.get("reviews") or {}
    err_obj = env.get("error") or {}
    err_code = (err_obj.get("code") if isinstance(err_obj, dict) else "") or ""
    outcome, fm = classify(env, bytes_)
    return {
        "status": env.get("status") or "",
        "error_code": err_code,
        "outcome": outcome,
        "fm_code": fm,
        "homepage_bytes": bytes_,
        "site_text_status": site_text.get("status") or "",
        "site_text_latency_ms": site_text.get("latency_ms") or 0,
        "site_text_cost_cents": site_text.get("cost_incurred") or 0,
        "reviews_status": reviews.get("status") or "",
        "reviews_latency_ms": reviews.get("latency_ms") or 0,
        "reviews_cost_cents": reviews.get("cost_incurred") or 0,
        "reviews_rating": reviews_payload.get("rating")
        if isinstance(reviews_payload, dict)
        else None,
        "reviews_count": reviews_payload.get("count")
        if isinstance(reviews_payload, dict)
        else None,
        "schema_version": env.get("schema_version") or "",
    }


def run_one(slug: str, host: str, *, ccx_bin: str, extra_flags: list[str]) -> dict:
    cmd = [ccx_bin, "fetch", host, "--json", *extra_flags]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_S,
            check=False,
            # IMPORTANT: inherit parent env so GOOGLE_PLACES_API_KEY
            # propagates into the pipx venv's os.environ.get call.
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return {
            "slug": slug,
            "host": host,
            "wall_ms": int((time.monotonic() - t0) * 1000),
            "envelope": None,
            "crash": "subprocess_timeout",
        }
    wall_ms = int((time.monotonic() - t0) * 1000)
    if proc.returncode != 0 or not proc.stdout:
        return {
            "slug": slug,
            "host": host,
            "wall_ms": wall_ms,
            "envelope": None,
            "crash": f"rc={proc.returncode}; stderr={proc.stderr[:400]}",
        }
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "slug": slug,
            "host": host,
            "wall_ms": wall_ms,
            "envelope": None,
            "crash": f"bad_json: {exc}",
        }
    return {
        "slug": slug,
        "host": host,
        "wall_ms": wall_ms,
        "envelope": envelope,
        "crash": None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out-dir", default=".context/cox-58")
    ap.add_argument("--ccx-bin", default=CCX_BIN_DEFAULT)
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="Pass --refresh to companyctx fetch (force live, write fresh row).",
    )
    ap.add_argument(
        "--from-cache",
        action="store_true",
        help="Pass --from-cache (cache-only, §3 measurement).",
    )
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    runs_dir = out_dir / f"runs-{args.label}"
    runs_dir.mkdir(parents=True, exist_ok=True)

    extra_flags: list[str] = []
    if args.refresh:
        extra_flags.append("--refresh")
    if args.from_cache:
        extra_flags.append("--from-cache")

    # Sanity: require the Places key for a run labelled "main" so we don't
    # silently ship a zero-reviews run. Cache-re-runs are fine without it.
    if not args.from_cache and not os.environ.get("GOOGLE_PLACES_API_KEY"):
        print("ERROR: GOOGLE_PLACES_API_KEY not set — refusing live run.")
        raise SystemExit(2)

    with Path(args.sample).open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    aggregate: list[dict] = []
    last_t = 0.0
    for i, row in enumerate(rows, 1):
        gap = time.monotonic() - last_t
        if gap < PACING_FLOOR_S and last_t > 0:
            time.sleep(PACING_FLOOR_S - gap)
        last_t = time.monotonic()

        print(f"[{i}/{len(rows)}] {row['slug']}  {row['host']}", flush=True)
        result = run_one(
            row["slug"],
            row["host"],
            ccx_bin=args.ccx_bin,
            extra_flags=extra_flags,
        )
        (runs_dir / f"{row['slug']}.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        env = result["envelope"]
        if env is None:
            aggregate.append(
                {
                    "slug": row["slug"],
                    "niche": row.get("niche", ""),
                    "host": row["host"],
                    "wall_ms": result["wall_ms"],
                    "status": "crash",
                    "error_code": "",
                    "outcome": "crash",
                    "fm_code": "crash",
                    "homepage_bytes": 0,
                    "site_text_status": "",
                    "site_text_latency_ms": 0,
                    "site_text_cost_cents": 0,
                    "reviews_status": "",
                    "reviews_latency_ms": 0,
                    "reviews_cost_cents": 0,
                    "reviews_rating": None,
                    "reviews_count": None,
                    "schema_version": "",
                    "crash_reason": result.get("crash", ""),
                }
            )
            print(f"    -> CRASH {result.get('crash')}", flush=True)
            continue

        pages = (env.get("data") or {}).get("pages") or {}
        homepage_text = pages.get("homepage_text") or ""
        homepage_bytes = len(homepage_text.encode("utf-8"))
        summary = summarise(env, homepage_bytes)
        row_out = {
            "slug": row["slug"],
            "niche": row.get("niche", ""),
            "host": row["host"],
            "wall_ms": result["wall_ms"],
            **summary,
            "crash_reason": "",
        }
        aggregate.append(row_out)
        print(
            f"    -> status={summary['status']} err={summary['error_code'] or '-'} "
            f"fm={summary['fm_code']} bytes={homepage_bytes} "
            f"st_lat={summary['site_text_latency_ms']}ms "
            f"rv={summary['reviews_status'] or '-'}({summary['reviews_cost_cents']}c) "
            f"rating={summary['reviews_rating']}",
            flush=True,
        )

    fieldnames = [
        "slug",
        "niche",
        "host",
        "wall_ms",
        "status",
        "error_code",
        "outcome",
        "fm_code",
        "homepage_bytes",
        "site_text_status",
        "site_text_latency_ms",
        "site_text_cost_cents",
        "reviews_status",
        "reviews_latency_ms",
        "reviews_cost_cents",
        "reviews_rating",
        "reviews_count",
        "schema_version",
        "crash_reason",
    ]
    out_path = out_dir / f"aggregate-{args.label}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(aggregate)
    print(f"\nwrote aggregate -> {out_path}")


if __name__ == "__main__":
    main()
