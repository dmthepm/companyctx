#!/usr/bin/env python3
"""COX-58 — export a grading pack for qualitative brief-vs-envelope re-grade.

Takes ``.context/cox-58/head-to-head-raw.json`` (30 pairs with envelope +
brief_path) and produces a JSONL where each line is one pair with:

- niche, slug, host
- envelope.homepage_text (the raw extracted text companyctx returned)
- envelope.about_text (if any)
- envelope.reviews (rating + count or null)
- envelope.status + error.code
- brief_path (absolute path on this machine)
- structural_verdict (from the existing head-to-head-raw.json grader output)

The human grader (or subagent) reads each pair and returns per-bucket
qualitative verdicts per the PR #90 rubric. Writes to
``.context/cox-58/grade-pack.jsonl`` — gitignored.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


def main() -> None:
    verdicts = json.loads(Path(".context/cox-58/head-to-head-raw.json").read_text())
    with Path(".context/cox-58/sample-with-briefs.csv").open(encoding="utf-8") as f:
        brief_by_slug = {r["slug"]: r["brief_path"] for r in csv.DictReader(f)}

    runs_dir = Path(".context/cox-58/runs-main")
    out_path = Path(".context/cox-58/grade-pack.jsonl")
    with out_path.open("w", encoding="utf-8") as f:
        for v in verdicts:
            slug = v["slug"]
            env_path = runs_dir / f"{slug}.json"
            if not env_path.exists():
                continue
            result = json.loads(env_path.read_text())
            env = result.get("envelope") or {}
            pages = (env.get("data") or {}).get("pages") or {}
            data = env.get("data") or {}
            err_obj = env.get("error") or {}
            reviews = data.get("reviews") if isinstance(data.get("reviews"), dict) else None
            row = {
                "slug": slug,
                "niche": v["niche"],
                "host": v["host"],
                "brief_path": brief_by_slug.get(slug, ""),
                "envelope_status": env.get("status"),
                "envelope_error_code": (err_obj.get("code") if isinstance(err_obj, dict) else None),
                "homepage_text": pages.get("homepage_text") or "",
                "about_text": pages.get("about_text") or "",
                "homepage_bytes": len((pages.get("homepage_text") or "").encode("utf-8")),
                "reviews": reviews,
                "structural_verdict": {
                    "differentiator": v["v_differentiator"],
                    "audience": v["v_audience"],
                    "credentials": v["v_credentials"],
                    "content_social": v["v_content_social"],
                    "reviews": v["v_reviews"],
                    "media_mentions": v["v_media_mentions"],
                },
            }
            f.write(json.dumps(row) + "\n")
    print(f"wrote {len(verdicts)} pairs -> {out_path}")


if __name__ == "__main__":
    main()
