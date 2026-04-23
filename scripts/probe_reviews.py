#!/usr/bin/env python3
"""COX-64 Slice B — reviews-provider probe harness.

Runs one call per ``(slug, provider)`` cell against the three finalists
named in ``research/2026-04-23-reviews-extraction-method-survey.md`` and
appends one JSONL row per cell to a raw-evidence file.

Slice A (this PR) ships the harness scaffolding and the adapter
interfaces — no network calls, no spend. Slice B (follow-up) provisions
the API keys + Apify token + residential-proxy allocation and runs the
harness for real.

Usage (Slice B, once keys are provisioned)::

    export GOOGLE_PLACES_NEW_API_KEY=...
    export YELP_FUSION_API_KEY=...
    export APIFY_TOKEN=...
    python scripts/probe_reviews.py \\
        --slugs research/.slug-map-cox64.local.csv \\
        --providers google_places_new_enterprise yelp_fusion_plus apify_compass_crawler \\
        --output research/2026-04-23-reviews-probe-raw.jsonl \\
        --confirm-spend-usd 15

Until ``--confirm-spend-usd`` is passed (with a value at least as large
as the estimated cost), the harness prints the estimated spend and
exits without making any network calls. This is the safety gate that
keeps Slice A from accidentally spending partner money.

The slug map CSV is ``slug,host,query_name`` — ``query_name`` is the
business display-name string used for Text Search / Yelp business-match
(the harness does **not** resolve hostnames to business names itself —
that's the operator's job, done once when building the slug map).

Output row schema (one per cell) is documented in
``research/2026-04-23-reviews-extraction-method-survey.md#measurement-harness``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol

PROVIDER_IDS = (
    "google_places_new_enterprise",
    "apify_compass_crawler",
    "websearch_llm_parse",
    "dataforseo_reviews",
    "yelp_fusion_plus",
)
ProviderId = Literal[
    "google_places_new_enterprise",
    "apify_compass_crawler",
    "websearch_llm_parse",
    "dataforseo_reviews",
    "yelp_fusion_plus",
]


# Pre-probe cost estimates (cents) used only for the --confirm-spend gate.
# These come from the desktop survey and are replaced by measured
# ``cost_incurred_cents`` in the JSONL rows the harness emits.
ESTIMATED_CENTS_PER_CALL: dict[str, int] = {
    # Text Search Enterprise $35/1k = 3.5c + Place Details Enterprise (rating,
    # userRatingCount, websiteUri — no Atmosphere) $20/1k = 2c = 5.5c/site.
    # 1k/mo free on each SKU, so the first 1k cells per SKU are $0. Round to
    # 6 for probe-budget safety margin.
    "google_places_new_enterprise": 6,
    "apify_compass_crawler": 5,  # ~$2.10/1k nominal + residential proxy
    "websearch_llm_parse": 2,  # ~1.5c WebSearch + agent tokens
    "dataforseo_reviews": 1,  # Claimed ~$0.00075/10 reviews — round up to 1c for safety
    "yelp_fusion_plus": 1,  # $9.99/1k = 1c, free during trial
}


@dataclass
class ProbeRow:
    """One row of the probe JSONL. Shape is stable across all providers."""

    slug: str
    provider: str
    run_id: str
    run_date: str
    status: Literal["ok", "zero_results", "blocked", "error"]
    rating: float | None
    review_count: int | None
    data_source_name: str | None
    latency_ms: int
    cost_incurred_cents: int
    proxy_used: Literal["residential", "none"] = "none"
    raw_response_hash: str | None = None
    notes: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ProviderAdapter(Protocol):
    """Common interface every finalist provider adapter implements.

    ``fetch`` never raises — the adapter maps all failure modes to a
    ``ProbeRow`` with the appropriate ``status`` and ``error_*`` fields,
    mirroring the ``ProviderBase`` contract of the runtime providers.
    """

    provider_id: str

    def fetch(self, slug: str, host: str, query_name: str) -> ProbeRow: ...


def _hash_response(obj: object) -> str:
    """Deterministic content hash for raw-response pinning in the JSONL."""
    payload = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _row(
    *,
    slug: str,
    provider: str,
    status: str,
    latency_ms: int,
    cost_incurred_cents: int,
    rating: float | None = None,
    review_count: int | None = None,
    data_source_name: str | None = None,
    proxy_used: str = "none",
    raw_response_hash: str | None = None,
    notes: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> ProbeRow:
    return ProbeRow(
        slug=slug,
        provider=provider,
        run_id=str(uuid.uuid4()),
        run_date=time.strftime("%Y-%m-%d"),
        status=status,  # type: ignore[arg-type]
        rating=rating,
        review_count=review_count,
        data_source_name=data_source_name,
        latency_ms=latency_ms,
        cost_incurred_cents=cost_incurred_cents,
        proxy_used=proxy_used,  # type: ignore[arg-type]
        raw_response_hash=raw_response_hash,
        notes=notes,
        error_code=error_code,
        error_message=error_message,
    )


class GooglePlacesNewEnterpriseAdapter:
    """Slice B — real implementation wires Places API (New) Text Search +
    Place Details with an Enterprise-tier field mask that **explicitly
    excludes Atmosphere-tier fields**.

    Exact field mask for Place Details (New):
    ``id,displayName,rating,userRatingCount,websiteUri``.

    Requesting ``reviews`` or ``reviewSummary`` would escalate to the
    Atmosphere SKU at $25/1k instead of Enterprise at $20/1k. The
    partner's downstream consumes rating + count only; we pay
    Enterprise, not Atmosphere.

    Expected billed cost per successful cell: Text Search Enterprise
    $0.035 + Place Details Enterprise $0.020 = $0.055 (5.5c). First 1k
    cells/mo per SKU are free. The adapter must record the actual
    billed cost from response headers / billing console, not the
    estimate.
    """

    provider_id = "google_places_new_enterprise"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch(self, slug: str, host: str, query_name: str) -> ProbeRow:
        # Slice-B TODO: Text Search (New) -> Place Details (New).
        # Lock field mask to ``id,displayName,rating,userRatingCount,websiteUri``.
        # Fail-fast if a future edit tries to add ``reviews`` or
        # ``reviewSummary`` (that would silently move billing to Atmosphere).
        raise NotImplementedError(
            "Slice B implementation pending key provisioning — see "
            "decisions/2026-04-23-reviews-provider-selection.md"
        )


class YelpFusionPlusAdapter:
    """Slice B — real implementation wires /v3/businesses/search with
    ``term`` and ``location`` derived from query_name, then the
    /v3/businesses/{id} detail endpoint to pin rating+review_count.

    The Plus tier returns 3 review excerpts; we ignore them (richness
    weight = 1× per ADR).
    """

    provider_id = "yelp_fusion_plus"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch(self, slug: str, host: str, query_name: str) -> ProbeRow:
        raise NotImplementedError(
            "Slice B implementation pending key provisioning — see "
            "decisions/2026-04-23-reviews-provider-selection.md"
        )


class ApifyCompassCrawlerAdapter:
    """Slice B — real implementation runs the
    ``compass/crawler-google-places`` actor in sync mode with a
    residential-proxy configuration and extracts
    ``reviewsCount`` + ``totalScore`` from the first result.

    Cost accounting must **include** proxy units — nominal $2.10/1k
    Apify cost is misleading without them after the Feb-2026 Google Maps
    limited-view event.
    """

    provider_id = "apify_compass_crawler"

    def __init__(self, token: str) -> None:
        self.token = token

    def fetch(self, slug: str, host: str, query_name: str) -> ProbeRow:
        raise NotImplementedError(
            "Slice B implementation pending token provisioning — see "
            "decisions/2026-04-23-reviews-provider-selection.md"
        )


class WebSearchLlmParseAdapter:
    """Slice B — the agentic alternative.

    Structurally different from the other adapters: there is no billable
    REST endpoint to call. The operator runs the agentic probe
    out-of-band — one prompt per slug, driving Claude through its own
    WebSearch tool surface — and appends JSONL rows matching this
    harness's schema. See the "WebSearch + LLM parsing: agentic-probe
    protocol" subsection in
    ``research/2026-04-23-reviews-extraction-method-survey.md`` for the
    exact prompt template, token-accounting rules, and the determinism
    caveat (one trial per slug, not a distribution).

    This adapter exists so the provider_id is first-class in the probe
    config and the row schema stays uniform; ``fetch`` deliberately
    raises to force the operator into the documented out-of-band
    workflow instead of accidentally running the harness against a non-
    existent HTTP endpoint.
    """

    provider_id = "websearch_llm_parse"

    def fetch(self, slug: str, host: str, query_name: str) -> ProbeRow:
        raise NotImplementedError(
            "websearch_llm_parse is an agentic probe — see "
            "research/2026-04-23-reviews-extraction-method-survey.md "
            "for the out-of-band protocol. Append the operator-produced "
            "rows directly to the probe JSONL."
        )


class DataForSeoReviewsAdapter:
    """Slice B — real implementation wires the DataForSEO Google
    Reviews API (``/v3/business_data/google/reviews/task_post`` +
    ``/task_get``) with HTTP Basic auth on the login / password pair.

    **First Slice B task on this slot is to verify the 2026 pricing
    claim** (~$0.00075/10 reviews) against DataForSEO's current pricing
    page. The ``cost_incurred_cents`` emitted by this adapter must be
    the actual billed cost from the task-post response's ``cost`` field,
    not a pre-registered estimate.
    """

    provider_id = "dataforseo_reviews"

    def __init__(self, login: str, password: str) -> None:
        self.login = login
        self.password = password

    def fetch(self, slug: str, host: str, query_name: str) -> ProbeRow:
        raise NotImplementedError(
            "Slice B implementation pending credential provisioning — "
            "see decisions/2026-04-23-reviews-provider-selection.md"
        )


def build_adapter(provider_id: str) -> ProviderAdapter:
    """Instantiate the adapter for ``provider_id`` from its env var.

    Env vars required (loaded by the operator before running the harness):

    - ``GOOGLE_PLACES_NEW_API_KEY`` for ``google_places_new_enterprise``
    - ``APIFY_TOKEN`` for ``apify_compass_crawler``
    - ``DATAFORSEO_LOGIN`` + ``DATAFORSEO_PASSWORD`` for ``dataforseo_reviews``
    - ``YELP_FUSION_API_KEY`` for ``yelp_fusion_plus``
    - (no env for ``websearch_llm_parse`` — that slot is an agentic
      out-of-band probe; the adapter raises to redirect the operator
      to the documented protocol)
    """
    if provider_id == "google_places_new_enterprise":
        key = os.environ.get("GOOGLE_PLACES_NEW_API_KEY")
        if not key:
            raise SystemExit(
                "GOOGLE_PLACES_NEW_API_KEY is not set — "
                "provision via Google Cloud Console and re-run"
            )
        return GooglePlacesNewEnterpriseAdapter(api_key=key)
    if provider_id == "yelp_fusion_plus":
        key = os.environ.get("YELP_FUSION_API_KEY")
        if not key:
            raise SystemExit(
                "YELP_FUSION_API_KEY is not set — "
                "provision via Yelp Data Licensing signup and re-run"
            )
        return YelpFusionPlusAdapter(api_key=key)
    if provider_id == "apify_compass_crawler":
        token = os.environ.get("APIFY_TOKEN")
        if not token:
            raise SystemExit("APIFY_TOKEN is not set — provision via Apify console and re-run")
        return ApifyCompassCrawlerAdapter(token=token)
    if provider_id == "websearch_llm_parse":
        return WebSearchLlmParseAdapter()
    if provider_id == "dataforseo_reviews":
        login = os.environ.get("DATAFORSEO_LOGIN")
        password = os.environ.get("DATAFORSEO_PASSWORD")
        if not login or not password:
            raise SystemExit(
                "DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must both be set — "
                "provision via dataforseo.com signup and re-run"
            )
        return DataForSeoReviewsAdapter(login=login, password=password)
    raise SystemExit(f"unknown provider_id: {provider_id}")


def load_slug_map(path: Path) -> list[tuple[str, str, str]]:
    """Parse the gitignored ``slug,host,query_name`` CSV.

    The map lives at ``research/.slug-map-cox64.local.csv`` by convention
    so it never leaks the partner's seed list into public git history.
    """
    if not path.exists():
        raise SystemExit(
            f"slug map not found at {path}. Build it by sampling "
            "deterministically from the 209-site v0.4 corpus "
            "(4 medical-aesthetic, 3 home-services, "
            "2 no-website-just-Facebook, 1 obscure)."
        )
    rows: list[tuple[str, str, str]] = []
    with path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append((row["slug"], row["host"], row["query_name"]))
    return rows


def estimate_spend_cents(
    slugs: list[tuple[str, str, str]],
    providers: list[str],
) -> int:
    """Conservative pre-flight estimate. Replaced by measured billed
    ``cost_incurred_cents`` after the probe runs."""
    per_cell = sum(ESTIMATED_CENTS_PER_CALL[p] for p in providers)
    return per_cell * len(slugs)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--slugs",
        type=Path,
        required=True,
        help="CSV with columns slug,host,query_name (gitignored .local.*)",
    )
    ap.add_argument(
        "--providers",
        nargs="+",
        default=list(PROVIDER_IDS),
        choices=list(PROVIDER_IDS),
        help="Provider subset to probe",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=Path("research/2026-04-23-reviews-probe-raw.jsonl"),
        help="JSONL output path",
    )
    ap.add_argument(
        "--confirm-spend-usd",
        type=float,
        default=0.0,
        help=(
            "Confirm authorization to spend up to $N on this probe. "
            "Harness refuses to make network calls until this equals or "
            "exceeds the pre-flight estimate. Default 0 = dry-run."
        ),
    )
    ap.add_argument(
        "--pacing-s",
        type=float,
        default=2.0,
        help="Sleep between cells to avoid rate-limit surprises",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    slugs = load_slug_map(args.slugs)
    providers: list[str] = args.providers
    estimated_cents = estimate_spend_cents(slugs, providers)
    estimated_usd = estimated_cents / 100.0
    print(
        f"Probe preflight: {len(slugs)} slugs × {len(providers)} providers "
        f"= {len(slugs) * len(providers)} cells, "
        f"estimated spend ${estimated_usd:.2f}",
        file=sys.stderr,
    )
    if args.confirm_spend_usd < estimated_usd:
        print(
            f"Dry-run: --confirm-spend-usd={args.confirm_spend_usd:.2f} < "
            f"estimated ${estimated_usd:.2f}. No network calls made.",
            file=sys.stderr,
        )
        return 0
    adapters = [build_adapter(pid) for pid in providers]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a") as out:
        for slug, host, query_name in slugs:
            for adapter in adapters:
                row = adapter.fetch(slug=slug, host=host, query_name=query_name)
                out.write(json.dumps(asdict(row)) + "\n")
                time.sleep(args.pacing_s)
    print(f"Probe complete — rows appended to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
