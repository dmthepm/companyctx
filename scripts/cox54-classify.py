#!/usr/bin/env python3
"""COX-54 — classify the threshold-fit probe results into buckets.

Reads the per-row envelopes written by
``scripts/run-durability-batch.py`` and emits a sanitized
classification CSV. The output drops hostnames (slug + niche carry
all the signal) so the CSV is safe to commit alongside the research
doc.

Buckets:

    good-catch     — v0.4.0 correctly flagged thin/empty content
                     (status=degraded, error.code=empty_response).
                     NOTE: being in this bucket means "the provider
                     reported 0 bytes of extractable text" — it does
                     NOT mean "the site is thin." A human reviewer
                     (or LLM-assisted browser fetch) must confirm
                     the site's actual content before declaring
                     this a true FM-7.
    too-aggressive — site has real usable content but got flagged
                     (bytes just under 1024 with coherent text).
                     Decided by human review, not byte count alone.
    clean-ok       — status=ok and bytes >= 1024.
    clean-ok-borderline
                   — ok at 700-1200 B (near-threshold zone).
    antibot        — status=degraded with error.code=blocked_by_antibot.
    crash / timeout / other-error.

Usage:

    python3 scripts/cox54-classify.py \\
        --runs-dir .context/cox-54/runs-cox-54 \\
        --sample .context/cox-54/sample.csv \\
        --out research/2026-04-23-cox-54-classification.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def bucket(envelope: dict, bytes_: int) -> tuple[str, str]:
    """Return (bucket, error_code_or_note)."""
    status = envelope.get("status")
    err = envelope.get("error") or {}
    code = err.get("code") if isinstance(err, dict) else None

    if status == "ok":
        if bytes_ >= 1024:
            if 700 <= bytes_ <= 1200:
                return "clean-ok-borderline", "ok"
            return "clean-ok", "ok"
        return "CONTRACT-VIOLATION", f"ok but {bytes_}B"

    if code == "empty_response":
        if bytes_ >= 700:
            return "good-catch-review", f"{bytes_}B"
        return "good-catch", f"{bytes_}B"
    if code == "blocked_by_antibot":
        return "antibot", code
    if code == "network_timeout":
        return "timeout", code
    if code is None:
        return "unclassified", "no error code"
    return "other-error", code


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--runs-dir",
        type=Path,
        default=Path(".context/cox-54/runs-cox-54"),
        help="per-row envelope JSON directory (default: .context/cox-54/runs-cox-54)",
    )
    ap.add_argument(
        "--sample",
        type=Path,
        default=Path(".context/cox-54/sample.csv"),
        help="sample CSV used for the run (default: .context/cox-54/sample.csv)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("research/2026-04-23-cox-54-classification.csv"),
        help="sanitized output CSV (default: research/2026-04-23-cox-54-classification.csv)",
    )
    args = ap.parse_args()

    with args.sample.open(encoding="utf-8") as f:
        sample = {r["slug"]: r for r in csv.DictReader(f)}

    rows: list[dict] = []
    for p in sorted(args.runs_dir.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        slug = d.get("slug") or p.stem
        env = d.get("envelope")
        if env is None:
            rows.append(
                {
                    "slug": slug,
                    "niche": sample.get(slug, {}).get("niche", ""),
                    "status": "crash",
                    "error_code": "",
                    "bytes": 0,
                    "bucket": "crash",
                    "note": d.get("crash", ""),
                }
            )
            continue
        pages = (env.get("data") or {}).get("pages") or {}
        text = pages.get("homepage_text") or ""
        bytes_ = len(text.encode("utf-8"))
        b, note = bucket(env, bytes_)
        err = env.get("error")
        rows.append(
            {
                "slug": slug,
                "niche": sample.get(slug, {}).get("niche", ""),
                "status": env.get("status"),
                "error_code": err.get("code", "") if isinstance(err, dict) else "",
                "bytes": bytes_,
                "bucket": b,
                "note": note,
            }
        )

    rows.sort(key=lambda r: (r["bucket"], r["niche"], r["slug"]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "slug",
                "niche",
                "status",
                "error_code",
                "bytes",
                "bucket",
                "note",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    counts = Counter(r["bucket"] for r in rows)
    print(f"wrote {args.out}")
    print("\nbucket counts:")
    for b, n in counts.most_common():
        print(f"  {b:30s} {n}")
    print(f"  {'TOTAL':30s} {len(rows)}")


if __name__ == "__main__":
    main()
