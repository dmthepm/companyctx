#!/usr/bin/env python3
"""COX-58 analyze — aggregate roll-ups for the v0.4 re-validation report.

Reads the per-site JSON envelopes under ``.context/cox-58/runs-<label>/*.json``
and computes every statistic the research report needs in one pass:

§1 headline — status histogram, FM-7 rate at 1024 bytes, error-code
histogram, per-niche outcome table, latency percentiles.

§2 reviews — population rate, rating + count distributions, per-site cost
histogram, total run cost.

§3 is handled by re-running the harness on a cached subset (see
``cox58-cache-rerun.sh``); analysis of the resulting aggregate happens in
this same script via ``--cache-aggregate``.

§4 FM-7 reclassification — lists the slugs that came back
``partial|degraded + empty_response`` so four can be picked by hand /
automation for the deeper-dive.

Output: JSON document on stdout (easy to splice into the report) plus a
few sanitized JSONLs for research/.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _homepage_bytes(env: dict) -> int:
    pages = (env.get("data") or {}).get("pages") or {}
    return len((pages.get("homepage_text") or "").encode("utf-8"))


def _rating_and_count(env: dict) -> tuple[float | None, int | None]:
    reviews = (env.get("data") or {}).get("reviews") or {}
    if not isinstance(reviews, dict):
        return None, None
    r = reviews.get("rating")
    c = reviews.get("count")
    return (r if isinstance(r, (int, float)) else None, c if isinstance(c, int) else None)


def load_rows(runs_dir: Path) -> list[dict]:
    rows = []
    for p in sorted(runs_dir.glob("*.json")):
        result = json.loads(p.read_text(encoding="utf-8"))
        env = result.get("envelope")
        if env is None:
            rows.append(
                {
                    "slug": result.get("slug"),
                    "host": result.get("host"),
                    "wall_ms": result.get("wall_ms"),
                    "envelope": None,
                    "crash": result.get("crash"),
                }
            )
            continue
        prov = env.get("provenance") or {}
        st = prov.get("site_text_trafilatura") or {}
        rv = prov.get("reviews_google_places") or {}
        rating, count = _rating_and_count(env)
        err_obj = env.get("error") or {}
        err_code = (err_obj.get("code") if isinstance(err_obj, dict) else "") or ""
        rows.append(
            {
                "slug": result.get("slug"),
                "host": result.get("host"),
                "wall_ms": result.get("wall_ms"),
                "envelope": env,
                "status": env.get("status"),
                "error_code": err_code,
                "homepage_bytes": _homepage_bytes(env),
                "site_text_status": st.get("status"),
                "site_text_latency_ms": st.get("latency_ms") or 0,
                "reviews_status": rv.get("status"),
                "reviews_latency_ms": rv.get("latency_ms") or 0,
                "reviews_cost_cents": rv.get("cost_incurred") or 0,
                "reviews_rating": rating,
                "reviews_count": count,
                "schema_version": env.get("schema_version"),
            }
        )
    return rows


def load_niche_map(sample_csv: Path) -> dict[str, str]:
    with sample_csv.open(encoding="utf-8") as f:
        return {r["slug"]: r["niche"] for r in csv.DictReader(f)}


def analyze(rows: list[dict], niche_by_slug: dict[str, str]) -> dict:
    total = len(rows)
    non_crash = [r for r in rows if r.get("envelope") is not None]
    status_counts = Counter(r.get("status") for r in non_crash)
    status_counts["crash"] = total - len(non_crash)

    err_counts = Counter(
        r.get("error_code") or "" for r in non_crash if (r.get("error_code") or "")
    )

    # FM-7 at the 1024-byte floor = status ∈ {partial, degraded} + error.code == empty_response.
    fm7 = [
        r
        for r in non_crash
        if r.get("error_code") == "empty_response" and r.get("status") in ("partial", "degraded")
    ]

    # Reviews population = reviews_status == ok AND rating/count populated.
    reviews_ok = [
        r
        for r in non_crash
        if r.get("reviews_status") == "ok"
        and r.get("reviews_rating") is not None
        and r.get("reviews_count") is not None
    ]
    reviews_failed = [r for r in non_crash if r.get("reviews_status") == "failed"]
    reviews_not_run = [
        r for r in non_crash if r.get("reviews_status") in (None, "", "not_configured")
    ]

    total_cost_cents = sum(r.get("reviews_cost_cents") or 0 for r in non_crash) + sum(
        (r.get("envelope") or {})
        .get("provenance", {})
        .get("site_text_trafilatura", {})
        .get("cost_incurred")
        or 0
        for r in non_crash
    )

    # Latency (site_text leg only — matches PR #90's Attempt-1 column).
    latencies = [r.get("site_text_latency_ms") or 0 for r in non_crash]
    review_latencies = [
        r.get("reviews_latency_ms") or 0
        for r in non_crash
        if r.get("reviews_status") in ("ok", "failed")
    ]
    wall_ms = [r.get("wall_ms") or 0 for r in non_crash]

    # Bytes distribution (non-zero only).
    bytes_non_zero = [
        r.get("homepage_bytes") or 0 for r in non_crash if (r.get("homepage_bytes") or 0) > 0
    ]

    # Per-niche histogram.
    by_niche: dict[str, Counter[str]] = {}
    bytes_by_niche: dict[str, list[int]] = {}
    lat_by_niche: dict[str, list[int]] = {}
    fm7_by_niche: dict[str, int] = {}
    ok_fat_by_niche: dict[str, int] = {}
    n_by_niche: dict[str, int] = {}
    for r in rows:
        niche = niche_by_slug.get(r.get("slug") or "", "unknown")
        n_by_niche[niche] = n_by_niche.get(niche, 0) + 1
        if r.get("envelope") is None:
            by_niche.setdefault(niche, Counter())["crash"] += 1
            continue
        status = r.get("status") or ""
        ec = r.get("error_code") or ""
        bytes_ = r.get("homepage_bytes") or 0
        bytes_by_niche.setdefault(niche, []).append(bytes_)
        lat_by_niche.setdefault(niche, []).append(r.get("site_text_latency_ms") or 0)
        if ec == "empty_response":
            fm7_by_niche[niche] = fm7_by_niche.get(niche, 0) + 1
            by_niche.setdefault(niche, Counter())["fm7"] += 1
        elif status == "ok" and bytes_ >= 1024:
            ok_fat_by_niche[niche] = ok_fat_by_niche.get(niche, 0) + 1
            by_niche.setdefault(niche, Counter())["ok_fat"] += 1
        elif status == "ok":
            by_niche.setdefault(niche, Counter())["ok_thin"] += 1
        elif status == "partial":
            by_niche.setdefault(niche, Counter())["partial"] += 1
        elif status == "degraded":
            by_niche.setdefault(niche, Counter())["degraded"] += 1
        else:
            by_niche.setdefault(niche, Counter())[status or "other"] += 1

    summary = {
        "n": total,
        "status": dict(status_counts),
        "error_codes": dict(err_counts),
        "fm7_count": len(fm7),
        "fm7_pct": round(100.0 * len(fm7) / total, 1) if total else 0.0,
        "reviews": {
            "ok": len(reviews_ok),
            "failed": len(reviews_failed),
            "not_run": len(reviews_not_run),
            "ok_pct": round(100.0 * len(reviews_ok) / total, 1) if total else 0.0,
        },
        "reviews_rating_distribution": {
            "median": round(statistics.median([r["reviews_rating"] for r in reviews_ok]), 2)
            if reviews_ok
            else None,
            "min": min((r["reviews_rating"] for r in reviews_ok), default=None),
            "max": max((r["reviews_rating"] for r in reviews_ok), default=None),
        },
        "reviews_count_distribution": {
            "median": int(statistics.median([r["reviews_count"] for r in reviews_ok]))
            if reviews_ok
            else None,
            "min": min((r["reviews_count"] for r in reviews_ok), default=None),
            "max": max((r["reviews_count"] for r in reviews_ok), default=None),
        },
        "cost_cents_total": total_cost_cents,
        "cost_usd_total": round(total_cost_cents / 100.0, 2),
        "latency_site_text_ms": {
            "p50": int(_percentile(latencies, 0.50)),
            "p90": int(_percentile(latencies, 0.90)),
            "p99": int(_percentile(latencies, 0.99)),
        },
        "latency_reviews_ms": {
            "p50": int(_percentile(review_latencies, 0.50)),
            "p90": int(_percentile(review_latencies, 0.90)),
            "p99": int(_percentile(review_latencies, 0.99)),
        },
        "wall_ms": {
            "p50": int(_percentile(wall_ms, 0.50)),
            "p90": int(_percentile(wall_ms, 0.90)),
            "p99": int(_percentile(wall_ms, 0.99)),
        },
        "bytes_non_zero": {
            "p50": int(_percentile(bytes_non_zero, 0.50)),
            "p90": int(_percentile(bytes_non_zero, 0.90)),
        },
        "niches": sorted(n_by_niche.keys()),
        "per_niche": {
            niche: {
                "n": n_by_niche[niche],
                "fm7": fm7_by_niche.get(niche, 0),
                "ok_fat": ok_fat_by_niche.get(niche, 0),
                "p50_bytes": int(_percentile(bytes_by_niche.get(niche, []), 0.50)),
                "p50_latency_ms": int(_percentile(lat_by_niche.get(niche, []), 0.50)),
                "histogram": dict(by_niche.get(niche, Counter())),
            }
            for niche in sorted(n_by_niche.keys())
        },
        "fm7_slugs": [r["slug"] for r in fm7],
    }
    return summary


def write_sanitized_jsonl(rows: list[dict], niche_by_slug: dict[str, str], out: Path) -> None:
    """One row per site — niche + envelope stats, no slug / host committed."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            niche = niche_by_slug.get(r.get("slug") or "", "unknown")
            env = r.get("envelope")
            if env is None:
                row = {
                    "niche": niche,
                    "status": "crash",
                    "error_code": "",
                    "homepage_bytes": 0,
                    "site_text_latency_ms": 0,
                    "reviews_status": "",
                    "reviews_cost_cents": 0,
                    "reviews_rating": None,
                    "reviews_count": None,
                    "crash_reason": r.get("crash") or "",
                }
            else:
                row = {
                    "niche": niche,
                    "status": r.get("status"),
                    "error_code": r.get("error_code") or "",
                    "homepage_bytes": r.get("homepage_bytes"),
                    "site_text_latency_ms": r.get("site_text_latency_ms"),
                    "reviews_status": r.get("reviews_status") or "",
                    "reviews_cost_cents": r.get("reviews_cost_cents"),
                    "reviews_rating": r.get("reviews_rating"),
                    "reviews_count": r.get("reviews_count"),
                    "crash_reason": "",
                }
            f.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs-dir", default=".context/cox-58/runs-main")
    ap.add_argument("--sample", default=".context/cox-58/sample.csv")
    ap.add_argument("--sanitized-jsonl", default="research/2026-04-23-cox-58-v0.4-raw.jsonl")
    ap.add_argument("--summary-out", default=".context/cox-58/summary-main.json")
    args = ap.parse_args()
    rows = load_rows(Path(args.runs_dir))
    niche_by_slug = load_niche_map(Path(args.sample))
    summary = analyze(rows, niche_by_slug)
    print(json.dumps(summary, indent=2, default=str))
    Path(args.summary_out).write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    write_sanitized_jsonl(rows, niche_by_slug, Path(args.sanitized_jsonl))


if __name__ == "__main__":
    main()
