"""Inbound-lead webhook enrichment handler.

Drop ``handle_inbound_lead`` into any runtime you like:

- AWS Lambda: wrap as the ``lambda_handler`` (return ``dict``).
- n8n / Make: paste the function body into a Code node.
- FastAPI / Flask: wire it behind your webhook route.
- CLI / cron: run this file directly — the ``__main__`` block shows the shape.

The handler itself is sync and dependency-free beyond ``companyctx``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from companyctx.core import run

FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
    }
)


def handle_inbound_lead(event: dict[str, Any], *, mock: bool = False) -> dict[str, Any]:
    """Enrich an inbound-lead webhook event.

    Returns a dict with either a ``crm_payload`` ready to push, or a
    ``status`` explaining why we skipped (free email, invalid domain,
    or a non-ok envelope with an actionable suggestion).
    """
    email = (event.get("email") or "").strip().lower()
    if "@" not in email:
        return {"status": "ignored", "reason": "missing or malformed email"}

    domain = email.split("@", 1)[1]
    if domain in FREE_EMAIL_DOMAINS:
        return {"status": "ignored", "reason": "free email provider"}

    fixtures_dir = Path("fixtures") if mock else None
    envelope = run(domain, mock=mock, fixtures_dir=fixtures_dir)

    if envelope.status != "ok":
        return {
            "status": "degraded",
            "reason": envelope.error or "envelope not ok",
            "suggestion": envelope.suggestion,
            "domain": domain,
        }

    data = envelope.data
    crm_payload: dict[str, Any] = {
        "company_domain": domain,
        "primary_services": data.pages.services if data.pages else [],
        "tech_stack_detected": data.pages.tech_stack if data.pages else [],
        "review_rating": data.reviews.rating if data.reviews else None,
        "review_count": data.reviews.count if data.reviews else None,
        "review_source": data.reviews.source if data.reviews else None,
        "social_handles": dict(data.social.handles) if data.social else {},
        "copyright_year": data.signals.copyright_year if data.signals else None,
        "team_size_claim": data.signals.team_size_claim if data.signals else None,
        "context_fetched_at": data.fetched_at.isoformat(),
    }

    return {
        "status": "enriched",
        "domain": domain,
        "crm_payload": crm_payload,
    }


def _demo_event() -> dict[str, Any]:
    return {"email": "josh@acme-bakery"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Inbound webhook enrichment demo")
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read a JSON webhook event from stdin instead of using the demo event.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use the fixtures corpus instead of a live fetch.",
    )
    args = parser.parse_args()

    event = json.load(sys.stdin) if args.stdin else _demo_event()

    result = handle_inbound_lead(event, mock=args.mock or not args.stdin)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()


# --- EXPECTED OUTPUT (demo event with --mock) ---
# {
#   "crm_payload": {
#     "company_domain": "acme-bakery",
#     "context_fetched_at": "2026-04-21T14:44:59.314842Z",
#     "copyright_year": 2024,
#     "primary_services": ["Custom cakes", "Catering", "Wholesale bread", "Pastry boxes"],
#     "review_count": 142,
#     "review_rating": 4.6,
#     "review_source": "reviews_google_places",
#     "social_handles": {"instagram": "@acmebakery"},
#     "team_size_claim": "team of 3",
#     "tech_stack_detected": ["WordPress", "Elementor"]
#   },
#   "domain": "acme-bakery",
#   "status": "enriched"
# }
