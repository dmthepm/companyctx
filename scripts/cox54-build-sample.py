#!/usr/bin/env python3
"""COX-54 — assemble a niche-weighted fresh sample for the threshold-fit probe.

Reads partner dream100-*-tracker.md trackers (local-only on Devon's
machine; see noontide CLAUDE.md for the repo path convention) and emits
a CSV with `niche,position,slug,host,heading` columns that
`scripts/run-durability-batch.py` accepts.

The output CSV contains partner hostnames and therefore **stays under
.context/** by default — it cannot be committed. The script itself is
the durable artifact; the CSV it produces is scratch.

Weighting biases toward niches with the highest pre-fix FM-7 rates
from the archived 209-site COX-46 corpus, per
`research/2026-04-23-cox-52-post-fix-reclassification.md`:

    real-estate-photography        45.5% FM-7  -> sample 5
    gutter-installation-repair     42.9% FM-7  -> sample 5
    virtual-staging-services       36.4% FM-7  -> sample 4
    real-estate-staging-services   27.3% FM-7  -> sample 4
    chiropractic-practices         20.0% FM-7  -> sample 3
    waste-management-services      20.0% FM-7  -> sample 3
    property-inspection-services   18.2% FM-7  -> sample 2
    med-spa-services               20.0% FM-7  -> sample 2
    iv-therapy-wellness             0.0% FM-7  -> sample 2

Total: 30. Picks a deterministic stride across each tracker (positions
1, 5, 9, ...) so re-running is reproducible.

Usage:

    python3 scripts/cox54-build-sample.py \\
        --trackers-dir /path/to/new-signal-studio/outputs \\
        --out .context/cox-54/sample.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

NICHE_BUDGET = [
    ("real-estate-photography", 5),
    ("gutter-installation-repair", 5),
    ("virtual-staging-services", 4),
    ("real-estate-staging-services", 4),
    ("chiropractic-practices", 3),
    ("waste-management-services", 3),
    ("property-inspection-services", 2),
    ("med-spa-services", 2),
    ("iv-therapy-wellness", 2),
]


def parse_tracker(path: Path) -> list[dict[str, str]]:
    """Return one dict per row with keys position, host, business."""
    text = path.read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []

    lines = text.splitlines()
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.lstrip().startswith("| #")),
        None,
    )
    if header_idx is None:
        return rows
    header = [c.strip().lower() for c in lines[header_idx].strip("|").split("|")]
    try:
        col_position = header.index("#")
        col_website = header.index("website")
    except ValueError:
        return rows
    col_business = next(
        (header.index(k) for k in ("business", "company", "org") if k in header),
        None,
    )
    if col_business is None:
        return rows

    for ln in lines[header_idx + 2 :]:
        if not ln.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) <= max(col_position, col_website, col_business):
            continue
        pos = cells[col_position]
        web = cells[col_website]
        biz = cells[col_business]
        if not pos.isdigit() or not web:
            continue
        web = re.sub(r"^https?://", "", web).strip().rstrip("/")
        web = re.sub(r"^www\.", "", web)
        web = web.split()[0]
        rows.append({"position": pos, "host": web, "business": biz})
    return rows


def pick(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    """Evenly-spaced stride across the tracker — deterministic."""
    if not rows or count == 0:
        return []
    step = max(1, len(rows) // count)
    return rows[::step][:count]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--trackers-dir",
        required=True,
        type=Path,
        help="path to new-signal-studio/outputs (contains dream100-*-tracker.md)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(".context/cox-54/sample.csv"),
        help="output CSV path (default: .context/cox-54/sample.csv)",
    )
    args = ap.parse_args()

    sample: list[dict[str, str]] = []
    for niche, budget in NICHE_BUDGET:
        path = args.trackers_dir / f"dream100-{niche}-tracker.md"
        if not path.exists():
            print(f"skip (no tracker): {niche}")
            continue
        rows = parse_tracker(path)
        picks = pick(rows, budget)
        for row in picks:
            sample.append(
                {
                    "niche": niche,
                    "position": row["position"],
                    "slug": f"{niche}-{row['position']}",
                    "host": row["host"],
                    "heading": row["business"],
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["niche", "position", "slug", "host", "heading"])
        w.writeheader()
        w.writerows(sample)

    print(f"wrote {len(sample)} rows -> {args.out}")


if __name__ == "__main__":
    main()
