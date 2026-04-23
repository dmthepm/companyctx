#!/usr/bin/env python3
"""COX-58 §3 — cache-rerun analyzer.

Compares latency + cost between the first (live) run and the second
(cache-hit) run of the same subset. A cache-hit row is identified by
having its provenance entries report ``cost_incurred=0`` AND an
effectively zero latency budget (``wall_ms < 1000``) — the v0.4 cache
short-circuits every provider so total wall is dominated by subprocess
overhead, not network I/O.

Emits:
- ``.context/cox-58/summary-cache.json`` — hit rate, latency deltas, cost delta.
- ``research/2026-04-23-cox-58-cache-delta.jsonl`` — sanitized per-row deltas
  (niche + deltas only, no slug/host).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
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


def load_result(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def analyze(live_dir: Path, cache_dir: Path, sample_csv: Path) -> dict:
    with sample_csv.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    deltas = []
    for r in rows:
        slug = r["slug"]
        live_p = live_dir / f"{slug}.json"
        cache_p = cache_dir / f"{slug}.json"
        if not live_p.exists() or not cache_p.exists():
            continue
        live = load_result(live_p)
        cache = load_result(cache_p)
        live_env = live.get("envelope") or {}
        cache_env = cache.get("envelope") or {}
        live_prov = live_env.get("provenance") or {}
        cache_prov = cache_env.get("provenance") or {}
        live_cost = sum((m.get("cost_incurred") or 0) for m in live_prov.values())
        cache_cost = sum((m.get("cost_incurred") or 0) for m in cache_prov.values())
        deltas.append(
            {
                "niche": r["niche"],
                "slug": slug,
                "live_wall_ms": live.get("wall_ms"),
                "cache_wall_ms": cache.get("wall_ms"),
                "live_cost_cents": live_cost,
                "cache_cost_cents": cache_cost,
                "live_st_lat_ms": (live_prov.get("site_text_trafilatura") or {}).get("latency_ms")
                or 0,
                "cache_st_lat_ms": (cache_prov.get("site_text_trafilatura") or {}).get("latency_ms")
                or 0,
                "live_rv_lat_ms": (live_prov.get("reviews_google_places") or {}).get("latency_ms")
                or 0,
                "cache_rv_lat_ms": (cache_prov.get("reviews_google_places") or {}).get("latency_ms")
                or 0,
            }
        )

    # Hit detection — the provenance row's ``latency_ms`` + ``cost_incurred``
    # are HISTORICAL (replayed with the cached envelope). The live-vs-cache
    # signal lives in the SUBPROCESS wall clock: a cache read is SQLite +
    # Python startup (sub-second), a live fetch is multi-second provider
    # work. Threshold picked at 1000ms — empirical: cached rows here run
    # 200-400ms, live rows 3-9 seconds.
    HIT_WALL_MS = 1000
    hits = []
    for d in deltas:
        is_hit = (d["cache_wall_ms"] or 0) < HIT_WALL_MS
        d["is_hit"] = is_hit
        if is_hit:
            hits.append(d)

    summary = {
        "n": len(deltas),
        "hits": len(hits),
        "hit_rate_pct": round(100.0 * len(hits) / len(deltas), 1) if deltas else 0.0,
        "live_wall_ms": {
            "p50": int(_percentile([d["live_wall_ms"] for d in deltas], 0.5)),
            "p90": int(_percentile([d["live_wall_ms"] for d in deltas], 0.9)),
            "median": int(statistics.median([d["live_wall_ms"] for d in deltas])) if deltas else 0,
        },
        "cache_wall_ms": {
            "p50": int(_percentile([d["cache_wall_ms"] for d in deltas], 0.5)),
            "p90": int(_percentile([d["cache_wall_ms"] for d in deltas], 0.9)),
            "median": int(statistics.median([d["cache_wall_ms"] for d in deltas])) if deltas else 0,
        },
        "live_cost_cents_total": sum(d["live_cost_cents"] for d in deltas),
        "cache_cost_cents_total": sum(d["cache_cost_cents"] for d in deltas),
    }
    return {"summary": summary, "rows": deltas}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live-dir", default=".context/cox-58/runs-main")
    ap.add_argument("--cache-dir", default=".context/cox-58/runs-cached")
    ap.add_argument("--sample", default=".context/cox-58/sample-cache-subset.csv")
    ap.add_argument("--summary-out", default=".context/cox-58/summary-cache.json")
    ap.add_argument("--jsonl-out", default="research/2026-04-23-cox-58-cache-delta.jsonl")
    args = ap.parse_args()

    out = analyze(Path(args.live_dir), Path(args.cache_dir), Path(args.sample))
    Path(args.summary_out).write_text(json.dumps(out["summary"], indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out["summary"], indent=2))

    sanitized = Path(args.jsonl_out)
    sanitized.parent.mkdir(parents=True, exist_ok=True)
    with sanitized.open("w", encoding="utf-8") as f:
        for d in out["rows"]:
            row = {
                "niche": d["niche"],
                "is_hit": d["is_hit"],
                "live_wall_ms": d["live_wall_ms"],
                "cache_wall_ms": d["cache_wall_ms"],
                "live_cost_cents": d["live_cost_cents"],
                "cache_cost_cents": d["cache_cost_cents"],
                "live_st_lat_ms": d["live_st_lat_ms"],
                "cache_st_lat_ms": d["cache_st_lat_ms"],
                "live_rv_lat_ms": d["live_rv_lat_ms"],
                "cache_rv_lat_ms": d["cache_rv_lat_ms"],
            }
            f.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"wrote sanitized -> {sanitized}")


if __name__ == "__main__":
    main()
