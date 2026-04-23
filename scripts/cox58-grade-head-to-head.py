#!/usr/bin/env python3
"""COX-58 head-to-head grader — structural re-grade of the six PR #90 §4
buckets against v0.4 envelopes.

**What this script does not do.** PR #90's grader was human-in-the-loop:
for each (site, bucket) pair Devon read the rendered research-brief.md and
the companyctx envelope side-by-side and issued a qualitative verdict.
That kind of judgment isn't fully automatable.

**What this script does.** Applies the PR #90 rubric (see
research/2026-04-22-v0.2-joel-integration-validation.md §2) as a structural
classifier over the v0.4 envelope + the extracted text. The outputs are:

- **reviews**: ``covered_now`` iff ``data.reviews.rating`` and
  ``data.reviews.count`` are both populated. Else ``out_of_scope``. This is
  the v0.2→v0.4 delta that matters most.
- **differentiator / audience / credentials**: raw-text muscle buckets.
  ``covered_via_LLM`` when extracted text is ≥ 1024 bytes. ``bug_thin_body``
  when envelope is ``degraded + empty_response`` (v0.4's FM-7 fix caught
  it). ``not_covered`` on unrecoverable failures. This matches PR #90 §2's
  "raw value lives directly on data.pages.* or at enough density that
  synthesis could derive it from homepage_text+about_text" criterion as
  applied to our zero-provider envelope.
- **content_social**: ``covered_now`` if a social handle / link surfaces in
  the extracted homepage_text. ``out_of_scope`` otherwise. Follower counts
  remain out of scope (no provider ships).
- **media_mentions**: always ``out_of_scope`` (FM-12 provider not shipped —
  tracked in #58).

Usage::

    python3 scripts/cox58-grade-head-to-head.py \
        --runs-dir .context/cox-58/runs-main \
        --intersect .context/cox-58/sample-with-briefs.csv \
        --pick 30 \
        --out-raw .context/cox-58/head-to-head-raw.json \
        --out-jsonl research/2026-04-23-cox-58-head-to-head.jsonl

The JSONL goes in research/ (sanitized: niche + verdict only, no slugs/
hosts). The raw JSON stays in .context/ (gitignored) for anyone wanting
to reproduce against the full envelope snapshots.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter
from pathlib import Path

SOCIAL_PATTERNS = [
    re.compile(r"instagram\.com/", re.I),
    re.compile(r"facebook\.com/", re.I),
    re.compile(r"youtube\.com/", re.I),
    re.compile(r"tiktok\.com/", re.I),
    re.compile(r"linkedin\.com/", re.I),
    re.compile(r"twitter\.com/", re.I),
    re.compile(r"x\.com/\w"),
    re.compile(r"@[A-Za-z0-9_.]{3,30}"),
]

BUCKETS = (
    "differentiator",
    "audience",
    "credentials",
    "content_social",
    "reviews",
    "media_mentions",
)


def _extracted_bytes(env: dict) -> int:
    pages = (env.get("data") or {}).get("pages") or {}
    return len((pages.get("homepage_text") or "").encode("utf-8"))


def _has_social(text: str) -> bool:
    return any(p.search(text) for p in SOCIAL_PATTERNS)


def _reviews_populated(env: dict) -> bool:
    reviews = (env.get("data") or {}).get("reviews")
    if not isinstance(reviews, dict):
        return False
    return reviews.get("rating") is not None and reviews.get("count") is not None


def grade_envelope(env: dict) -> dict[str, str]:
    """Return a verdict per bucket for one envelope."""
    status = env.get("status") or "crash"
    err_obj = env.get("error") or {}
    err_code = (err_obj.get("code") if isinstance(err_obj, dict) else "") or ""
    pages = (env.get("data") or {}).get("pages") or {}
    homepage_text = pages.get("homepage_text") or ""
    bytes_ = len(homepage_text.encode("utf-8"))

    # Raw-text muscle buckets collapse into the same verdict because they're
    # all derived from the same pages_text field. The v0.2 report split
    # them by reviewer judgment; the structural grader collapses them.
    #
    # Important v0.4 nuance: when the reviews provider succeeds and the
    # site-text provider flags empty_response, the composite envelope
    # status is "partial", not "degraded" (the issue body's §4 expected
    # "degraded + empty_response" — measurement contradicts the expectation).
    # bug_thin_body fires on either composite so the reclassification count
    # is honest.
    if err_code == "empty_response" and status in ("partial", "degraded"):
        rich = "bug_thin_body"
    elif status == "ok" and bytes_ >= 1024:
        rich = "covered_via_LLM"
    elif status == "ok" and bytes_ > 0:
        # v0.4's FM-7 floor should have caught this, but if for some reason
        # a thin-body ok slipped through, call it partial.
        rich = "partial_via_LLM"
    elif status in ("partial", "degraded"):
        rich = "not_covered"
    else:
        rich = "not_covered"

    content_social = (
        "covered_now"
        if (status == "ok" and bytes_ >= 1024 and _has_social(homepage_text))
        else "out_of_scope"
    )

    reviews = "covered_now" if _reviews_populated(env) else "out_of_scope"

    return {
        "differentiator": rich,
        "audience": rich,
        "credentials": rich,
        "content_social": content_social,
        "reviews": reviews,
        "media_mentions": "out_of_scope",
    }


def pick_pairs(
    intersect: list[dict[str, str]],
    runs_dir: Path,
    n: int,
    seed: int = 42,
) -> list[dict[str, object]]:
    """Pick n rows from the intersection that also have an envelope on disk."""
    rng = random.Random(seed)
    rows_by_niche: dict[str, list[dict[str, str]]] = {}
    for r in intersect:
        env_path = runs_dir / f"{r['slug']}.json"
        if not env_path.exists():
            continue
        rows_by_niche.setdefault(r["niche"], []).append(r)

    # Proportional draw — same niche-weighting as the intersection supplied.
    total = sum(len(v) for v in rows_by_niche.values())
    if total < n:
        n = total
    plan: dict[str, int] = {}
    remainder = n
    for niche, rs in rows_by_niche.items():
        target = max(1, round(len(rs) * n / total))
        plan[niche] = min(target, len(rs))
        remainder -= plan[niche]
    # Fix drift.
    if remainder != 0:
        keys = (
            sorted(plan.keys(), key=lambda k: -plan[k])
            if remainder < 0
            else sorted(plan.keys(), key=lambda k: plan[k])
        )
        i = 0
        while remainder != 0 and keys:
            k = keys[i % len(keys)]
            if remainder > 0 and plan[k] < len(rows_by_niche[k]):
                plan[k] += 1
                remainder -= 1
            elif remainder < 0 and plan[k] > 1:
                plan[k] -= 1
                remainder += 1
            else:
                keys = [kk for kk in keys if kk != k]
                continue
            i += 1

    picked: list[dict[str, object]] = []
    for niche, count in plan.items():
        picked_rows = rng.sample(rows_by_niche[niche], count)
        for r in picked_rows:
            env_path = runs_dir / f"{r['slug']}.json"
            result = json.loads(env_path.read_text(encoding="utf-8"))
            envelope = result.get("envelope")
            if envelope is None:
                continue
            picked.append(
                {
                    "slug": r["slug"],
                    "niche": niche,
                    "host": r["host"],
                    "brief_path": r["brief_path"],
                    "envelope": envelope,
                }
            )
    return picked


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs-dir", default=".context/cox-58/runs-main")
    ap.add_argument("--intersect", default=".context/cox-58/sample-with-briefs.csv")
    ap.add_argument("--pick", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-raw", default=".context/cox-58/head-to-head-raw.json")
    ap.add_argument(
        "--out-jsonl",
        default="research/2026-04-23-cox-58-head-to-head.jsonl",
    )
    args = ap.parse_args()

    with Path(args.intersect).open(encoding="utf-8") as f:
        intersect = list(csv.DictReader(f))

    picked = pick_pairs(intersect, Path(args.runs_dir), args.pick, seed=args.seed)
    print(f"picked {len(picked)} pairs for grading")

    verdicts: list[dict[str, object]] = []
    for p in picked:
        v = grade_envelope(p["envelope"])
        verdicts.append(
            {
                "slug": p["slug"],
                "niche": p["niche"],
                "host": p["host"],
                **{f"v_{k}": v[k] for k in BUCKETS},
            }
        )

    raw = Path(args.out_raw)
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(json.dumps(verdicts, indent=2) + "\n", encoding="utf-8")
    print(f"wrote raw -> {raw}")

    # Sanitized JSONL (no slugs, no hosts) for the committed research/ dir.
    sanitized = Path(args.out_jsonl)
    sanitized.parent.mkdir(parents=True, exist_ok=True)
    with sanitized.open("w", encoding="utf-8") as f:
        for v in verdicts:
            row = {"niche": v["niche"]}
            for b in BUCKETS:
                row[f"v_{b}"] = v[f"v_{b}"]
            f.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"wrote sanitized -> {sanitized}")

    # Print the per-bucket verdict table.
    print("\nper-bucket verdicts:")
    for b in BUCKETS:
        c = Counter(v[f"v_{b}"] for v in verdicts)
        line = "  ".join(f"{k}={n}" for k, n in c.most_common())
        print(f"  {b:18s} {line}")


if __name__ == "__main__":
    main()
