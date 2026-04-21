#!/usr/bin/env python3
"""Durability harness — run ``companyctx fetch`` over a CSV of real sites.

Purpose. Power the 100-site durability-report measurement (see
[issue #22](https://github.com/dmthepm/companyctx/issues/22) and
``fixtures/durability-report-2026-04-XX.md``). Reads a private sample CSV,
shells out to ``python -m companyctx.cli fetch <host> --json`` for each row,
classifies the envelope against the FM taxonomy in ``docs/RISK-REGISTER.md``,
and writes:

- ``runs-<label>/<slug>.json`` — one per-row envelope + wall-clock timing.
- ``aggregate-<label>.csv`` — flat table suitable for reporting.

``robots.txt`` is honored throughout (no ``--ignore-robots``). 2-second
pacing floor between requests. 45-second subprocess timeout.

Input CSV columns (header required):

    niche,position,slug,host,heading

Only ``slug``, ``host``, and ``niche`` are used. ``heading`` (business name)
is ignored by the harness and stays out of committed artifacts — see
fixtures/durability-report-*.md for the sanitization rationale.

Usage:

    python3 scripts/run-durability-batch.py --sample my-sample.csv \
        --label pilot-25 --out-dir .context/durability
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

PACING_FLOOR_S = 2.0
SUBPROCESS_TIMEOUT_S = 45.0


def classify(envelope: dict, homepage_bytes: int) -> tuple[str, str]:
    """Return (outcome, fm_code) from an envelope + extracted byte count.

    Outcomes: ``ok`` | ``ok-empty`` | ``partial`` | ``degraded`` | ``crash``.
    FM codes track ``docs/RISK-REGISTER.md``; two extensions (RB-blocked,
    HTTP-4xx/5xx) capture observed shapes the register did not enumerate.
    """
    status = envelope.get("status", "crash")

    if status == "ok":
        if homepage_bytes < 50:
            return "ok-empty", "FM-6"
        return "ok", "none"

    prov = envelope.get("provenance") or {}
    err = ""
    for meta in prov.values():
        if meta.get("status") in ("failed", "degraded", "not_configured"):
            err = (meta.get("error") or "").lower()
            break
    err = err or (envelope.get("error") or "").lower()

    if "blocked_by_robots" in err:
        fm = "RB-blocked"
    elif "blocked_by_antibot" in err or "http 403" in err or "http 401" in err:
        fm = "FM-1"
    elif "http 4" in err:
        fm = "HTTP-4xx"
    elif "http 5" in err:
        fm = "HTTP-5xx"
    elif "timed out" in err or "timeout" in err:
        fm = "FM-13"
    elif any(k in err for k in ("nxdomain", "name or service not known", "resolve", "dnserror")):
        fm = "DNS"
    elif "network error" in err or "connection" in err:
        fm = "network"
    else:
        fm = "unclassified"

    return ("partial" if status == "partial" else "degraded"), fm


def run_one(slug: str, host: str, *, repo_root: Path) -> dict:
    """Invoke the CLI, capture the envelope JSON and wall-clock timing."""
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "companyctx.cli", "fetch", host, "--json"],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_S,
            cwd=str(repo_root),
            check=False,
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
            "crash": f"rc={proc.returncode}; stderr={proc.stderr[:500]}",
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
    ap.add_argument("--sample", required=True, help="CSV with niche,slug,host columns")
    ap.add_argument("--label", required=True, help="run label (e.g. pilot-25, full-100)")
    ap.add_argument(
        "--out-dir",
        default=".context/durability",
        help="directory for per-run JSON + aggregate CSV (default: .context/durability)",
    )
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    out_dir = Path(args.out_dir)
    runs_dir = out_dir / f"runs-{args.label}"
    runs_dir.mkdir(parents=True, exist_ok=True)

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
        result = run_one(row["slug"], row["host"], repo_root=repo_root)

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
                    "status": "crash",
                    "fm_code": "crash",
                    "outcome": "crash",
                    "homepage_bytes": 0,
                    "latency_ms": 0,
                    "wall_ms": result["wall_ms"],
                    "provider_status": "crash",
                    "provider_error": result.get("crash", ""),
                }
            )
            print(f"    -> CRASH: {result.get('crash')}", flush=True)
            continue

        pages = (env.get("data") or {}).get("pages") or {}
        homepage_text = pages.get("homepage_text") or ""
        homepage_bytes = len(homepage_text.encode("utf-8"))

        outcome, fm = classify(env, homepage_bytes)
        prov = env.get("provenance") or {}
        first = next(iter(prov.values()), {}) if prov else {}
        aggregate.append(
            {
                "slug": row["slug"],
                "niche": row.get("niche", ""),
                "host": row["host"],
                "status": env.get("status"),
                "fm_code": fm,
                "outcome": outcome,
                "homepage_bytes": homepage_bytes,
                "latency_ms": first.get("latency_ms", 0),
                "wall_ms": result["wall_ms"],
                "provider_status": first.get("status", ""),
                "provider_error": first.get("error") or "",
            }
        )
        print(
            f"    -> status={env.get('status')}  fm={fm}  "
            f"bytes={homepage_bytes}  lat={first.get('latency_ms', 0)}ms",
            flush=True,
        )

    out_path = out_dir / f"aggregate-{args.label}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "slug",
                "niche",
                "host",
                "status",
                "fm_code",
                "outcome",
                "homepage_bytes",
                "latency_ms",
                "wall_ms",
                "provider_status",
                "provider_error",
            ],
        )
        writer.writeheader()
        writer.writerows(aggregate)
    print(f"\nwrote aggregate -> {out_path}")


if __name__ == "__main__":
    main()
