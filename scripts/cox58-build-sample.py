#!/usr/bin/env python3
"""COX-58 corpus builder — stratified draw of ~100 sites from the partner's
Dream-100 trackers for the v0.4 partner-integration re-validation.

Reads ``new-signal-studio/outputs/dream100-<niche>-tracker.md`` markdown tables
(columns include ``First``, ``Last``, ``Business``, ``Website``), extracts one
row per tracker entry, and emits a CSV matching the shape
``scripts/run-durability-batch.py`` expects:

    niche,position,slug,host,heading

Stratification matches PR #90 §3 shape (17 niches; 10-15 per heavy, 5-8 per
minor). Two niches from PR #90 don't have a current tracker with a ``Website``
column (``window-door-replacement`` has no tracker; ``business-immigration``
tracker uses a Google-Docs-per-prospect shape, no ``Website`` column) — both
are excluded and the shape reshuffles to 16 niches × (7 heavy / 5 minor) =
70 + 30 = 100. This drift is documented in the research report.

Deterministic: ``seed=42`` matches PR #90's round-1 convention.

Output goes to ``.context/cox-58/sample.csv`` (gitignored); raw host data
never lands in the committed repo.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import re
from pathlib import Path
from urllib.parse import urlparse

# Stratification target for the v0.4 re-validation. Must sum to 100.
HEAVY_NICHES = {
    "bariatric-surgery": 7,
    "chiropractic-practices": 7,
    "cosmetic-dentistry": 7,
    "dermatology-aesthetic": 7,
    "gutter-installation-repair": 7,
    "iv-therapy-wellness": 7,
    "laser-hair-removal": 7,
    "medical-aesthetics-botox-fillers": 7,
    "orthodontics": 7,
    "plastic-surgery": 7,
}
MINOR_NICHES = {
    "med-spa-services": 5,
    "property-inspection-services": 5,
    "real-estate-photography": 5,
    "real-estate-staging-services": 5,
    "virtual-staging-services": 5,
    "waste-management-services": 5,
}
TARGET = {**HEAVY_NICHES, **MINOR_NICHES}
assert sum(TARGET.values()) == 100

SLUG_RE = re.compile(r"[^a-z0-9]+")

# Email domains that never represent the prospect's own website. Used when
# a tracker uses the legacy "Google Docs" shape (Prospect / Practice / Email
# columns only — no Website column) and we fall back to email-domain as the
# host-derivation signal. Gmail and yahoo would steer fetch into the wrong
# domain entirely.
_GENERIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "hotmail.com",
        "outlook.com",
        "aol.com",
        "icloud.com",
        "protonmail.com",
        "me.com",
        "msn.com",
        "live.com",
        "comcast.net",
        "sbcglobal.net",
    }
)


def _slugify(s: str) -> str:
    return SLUG_RE.sub("-", s.lower()).strip("-")


def _host_from_email(raw: str) -> str | None:
    raw = raw.strip().lower()
    if "@" not in raw:
        return None
    domain = raw.split("@", 1)[1].strip()
    domain = domain.strip(".,);>]")
    if not domain or domain in _GENERIC_EMAIL_DOMAINS:
        return None
    if not re.match(r"^[a-z0-9.-]+$", domain):
        return None
    if "." not in domain:
        return None
    return domain


def _hostname(raw: str) -> str | None:
    raw = raw.strip().strip("`").strip()
    if not raw:
        return None
    # Strip markdown link shells: [text](url) or [url](url)
    m = re.match(r"\[.*?\]\((.*?)\)", raw)
    if m:
        raw = m.group(1)
    # Add scheme for urlparse
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    host = (parsed.netloc or parsed.path).lower().strip("/")
    if not host or "/" in host or " " in host:
        return None
    if host.startswith("www."):
        host = host[4:]
    # Very permissive sanity check — at least one dot, valid chars only.
    if "." not in host or not re.match(r"^[a-z0-9.-]+$", host):
        return None
    return host


def parse_tracker(path: Path, niche: str) -> list[dict[str, str]]:
    """Parse a dream100-<niche>-tracker.md markdown table. Returns one dict
    per data row with keys: position, first, last, business, website."""
    text = path.read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in text.splitlines():
        line = line.rstrip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # Skip the separator row like |---|---|...
        if all(re.fullmatch(r"-{2,}:?", c) or c == "" for c in cells):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if len(cells) < len(header):
            continue
        row = dict(zip(header, cells, strict=False))
        pos = row.get("#", "").strip()
        # First data row has a digit in column 1; skip non-data rows.
        if not pos.isdigit():
            continue
        # Two tracker shapes:
        #   (a) full table with Website column (gutter, chiropractic, ...)
        #   (b) legacy "Google Docs" shape with only Email (bariatric,
        #       cosmetic-dentistry, orthodontics, plastic-surgery) — fall
        #       back to the email domain when it's not a generic provider.
        host: str | None = None
        website = row.get("website", "")
        if website:
            host = _hostname(website)
        if host is None:
            email = row.get("email", "")
            host = _host_from_email(email)
        if host is None:
            continue
        first = row.get("first", "")
        last = row.get("last", "")
        business = row.get("business") or row.get("practice") or row.get("prospect", "")
        # Legacy shape: "Prospect" holds the name, "Practice" holds the business.
        if not first and not last and row.get("prospect"):
            # Best-effort split: first token is usually "Dr." or the first name.
            prospect = row.get("prospect", "").strip()
            # Strip "Dr." / "Dr" honorific if present.
            prospect = re.sub(r"^(dr\.?|mr\.?|ms\.?|mrs\.?)\s+", "", prospect, flags=re.I)
            parts = prospect.split(None, 1)
            first = parts[0] if parts else ""
            last = parts[1] if len(parts) > 1 else ""
            business = row.get("practice") or business
        rows.append(
            {
                "position": pos,
                "first": first,
                "last": last,
                "business": business,
                "host": host,
            }
        )
    return rows


def build(trackers_dir: Path, out_path: Path, seed: int = 42) -> None:
    rng = random.Random(seed)
    out_rows: list[dict[str, str]] = []
    missing: list[str] = []

    for niche, n in TARGET.items():
        tracker_path = trackers_dir / f"dream100-{niche}-tracker.md"
        if not tracker_path.exists():
            missing.append(niche)
            continue
        rows = parse_tracker(tracker_path, niche)
        if len(rows) < n:
            print(f"  warn: {niche} has {len(rows)} rows, target {n} — taking all")
            n = len(rows)
        picked = rng.sample(rows, n)
        for p in picked:
            # Slug is a compact identifier derived from the business+host; it's
            # used as the per-run JSON filename. Kept local-only via .context/.
            business_slug = _slugify(p["business"])[:48] or _slugify(p["host"])
            slug = f"{niche}--{p['position']:>02}-{business_slug}"
            heading = f"{p['first']} {p['last']} - {p['business']}".strip(" -")
            out_rows.append(
                {
                    "niche": niche,
                    "position": p["position"],
                    "slug": slug,
                    "host": p["host"],
                    "heading": heading,
                }
            )
        print(f"  {niche}: sampled {n}/{len(rows)}")

    if missing:
        print(f"  warn: missing trackers for: {', '.join(missing)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["niche", "position", "slug", "host", "heading"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"\nwrote {len(out_rows)} rows -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # --trackers-dir must be provided either via the flag or the
    # COX58_PARTNER_OUTPUTS_DIR env var. No hardcoded default so the script
    # stays portable (this repo is public; the partner repo is not, and the
    # path is contributor-specific).
    ap.add_argument(
        "--trackers-dir",
        default=os.environ.get("COX58_PARTNER_OUTPUTS_DIR"),
        help="Dir containing dream100-<niche>-tracker.md files. "
        "Defaults to $COX58_PARTNER_OUTPUTS_DIR.",
    )
    ap.add_argument(
        "--out",
        default=".context/cox-58/sample.csv",
        help="Output CSV path (gitignored)",
    )
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if not args.trackers_dir:
        ap.error(
            "--trackers-dir is required (or set COX58_PARTNER_OUTPUTS_DIR). "
            "Point it at your new-signal-studio/outputs directory."
        )
    build(Path(args.trackers_dir), Path(args.out), seed=args.seed)


if __name__ == "__main__":
    main()
