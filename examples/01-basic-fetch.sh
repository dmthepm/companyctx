#!/usr/bin/env bash
# 01-basic-fetch.sh — the hello-world recipe.
#
# Fetches one domain, pretty-prints the JSON envelope. Nothing else.
# This is the shape every other recipe in the gallery builds on.
#
# Uses --mock to stay self-contained: runs against the fixture corpus
# shipped in the repo, so no network, no keys, byte-identical output
# modulo fetched_at.
#
# Usage:
#   ./01-basic-fetch.sh
#   ./01-basic-fetch.sh acme-bakery          # any fixture slug
#   ./01-basic-fetch.sh acme-bakery.com --live   # real fetch, zero-key path

set -euo pipefail

SITE="${1:-acme-bakery}"
MODE="${2:---mock}"

if [ "$MODE" = "--live" ]; then
  companyctx fetch "$SITE" --json
else
  companyctx fetch "$SITE" --mock --json
fi

# --- EXPECTED OUTPUT (abbreviated, v0.2 envelope) ---
# {
#   "schema_version": "0.2.0",
#   "status": "ok",
#   "data": {
#     "site": "acme-bakery",
#     "fetched_at": "2026-04-21T14:44:59.314842Z",
#     "pages": {
#       "homepage_text": "Acme Bakery is a bakery in Portland, OR. ...",
#       "about_text": "Acme Bakery has served Portland, OR since 2010. ...",
#       "services": ["Custom cakes", "Catering", "Wholesale bread", "Pastry boxes"],
#       "tech_stack": ["WordPress", "Elementor"]
#     },
#     "reviews": { "count": 142, "rating": 4.6, "source": "reviews_google_places" },
#     "social": { "handles": { "instagram": "@acmebakery" }, "follower_counts": {} },
#     "signals": { "copyright_year": 2024, "team_size_claim": "team of 3" },
#     "mentions": null
#   },
#   "provenance": {
#     "site_text_trafilatura":  { "status": "ok", "latency_ms": 0,   "error": null, "provider_version": "0.2.0" },
#     "reviews_google_places":  { "status": "ok", "latency_ms": 312, "error": null, "provider_version": "0.1.0" }
#   },
#   "error": null
# }
