#!/usr/bin/env python3
"""COX-58 brief discovery — map partner's rendered research-brief.md files
to the hosts in our sample.

For each ``outputs/<date>-dream100-<name>/research-brief.md`` in the partner
repo, parses the ``**Website:** <host>`` line and emits a lookup
``.context/cox-58/brief-map.json`` of the shape::

    {"host-name.com": "/abs/path/to/research-brief.md", ...}

Also intersects with the sample CSV (from cox58-build-sample.py) and prints a
count of how many sample rows have a matching rendered brief available —
that's the upper bound on the head-to-head n.

No PII / raw hostnames leave this script in committed artifacts; the
brief-map.json lives under .context/ (gitignored).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

WEBSITE_RE = re.compile(r"^\*\*Website:\*\*\s*(.+?)\s*$", re.MULTILINE)


def _normalize(raw: str) -> str | None:
    raw = raw.strip().rstrip(".,);")
    if not raw:
        return None
    # Strip markdown shell [text](url).
    m = re.match(r"\[.*?\]\((.*?)\)", raw)
    if m:
        raw = m.group(1)
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        host = urlparse(candidate).netloc or urlparse(candidate).path
    except ValueError:
        return None
    host = host.lower().strip("/")
    if host.startswith("www."):
        host = host[4:]
    if "." not in host or "/" in host or " " in host:
        return None
    return host or None


def build_map(outputs_dir: Path, out_json: Path) -> dict[str, str]:
    hmap: dict[str, str] = {}
    briefs = list(outputs_dir.glob("*/research-brief.md"))
    for path in briefs:
        text = path.read_text(encoding="utf-8", errors="ignore")
        m = WEBSITE_RE.search(text)
        if not m:
            continue
        host = _normalize(m.group(1))
        if host is None:
            continue
        # If the same host appears in multiple briefs (unlikely but possible),
        # prefer the most recently modified brief — partner may have re-run.
        prior = hmap.get(host)
        if prior and Path(prior).stat().st_mtime > path.stat().st_mtime:
            continue
        hmap[host] = str(path)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(hmap, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return hmap


def intersect_sample(sample_csv: Path, brief_map: dict[str, str]) -> list[dict[str, str]]:
    with sample_csv.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    hits: list[dict[str, str]] = []
    for r in rows:
        host = r["host"].lower()
        if host in brief_map:
            hits.append({**r, "brief_path": brief_map[host]})
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # Same portability rule as cox58-build-sample.py — no committed hard
    # path to the private partner repo. Require --outputs-dir or env var.
    ap.add_argument(
        "--outputs-dir",
        default=os.environ.get("COX58_PARTNER_OUTPUTS_DIR"),
        help="Dir with <date>-dream100-<name>/research-brief.md trees. "
        "Defaults to $COX58_PARTNER_OUTPUTS_DIR.",
    )
    ap.add_argument("--sample", default=".context/cox-58/sample.csv")
    ap.add_argument("--out-map", default=".context/cox-58/brief-map.json")
    ap.add_argument("--out-intersect", default=".context/cox-58/sample-with-briefs.csv")
    args = ap.parse_args()
    if not args.outputs_dir:
        ap.error(
            "--outputs-dir is required (or set COX58_PARTNER_OUTPUTS_DIR). "
            "Point it at your new-signal-studio/outputs directory."
        )
    hmap = build_map(Path(args.outputs_dir), Path(args.out_map))
    print(f"indexed {len(hmap)} briefs -> {args.out_map}")
    if Path(args.sample).exists():
        hits = intersect_sample(Path(args.sample), hmap)
        by_niche: dict[str, int] = {}
        for h in hits:
            by_niche[h["niche"]] = by_niche.get(h["niche"], 0) + 1
        print(f"sample intersection: {len(hits)} / rows have a matching brief")
        for niche, n in sorted(by_niche.items()):
            print(f"  {niche}: {n}")
        with Path(args.out_intersect).open("w", newline="", encoding="utf-8") as f:
            fields = ["niche", "position", "slug", "host", "heading", "brief_path"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(hits)
        print(f"wrote intersection -> {args.out_intersect}")


if __name__ == "__main__":
    main()
