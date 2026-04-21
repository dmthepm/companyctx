#!/usr/bin/env python3
"""Build the 30-prospect fixtures corpus.

Two modes:

1. ``--source <dir>`` — read Joel's private research-brief.md dump, extract
   prospect site + public web snippets, sanitize PII, write per-site fixtures.
   Brief files must have YAML-ish front-matter with at minimum a ``site:``
   key, then free-form markdown body. The body is scanned for
   sanitizable public content (homepage/about/services snippets). Everything
   that looks like a contact name / email / phone is masked.
2. ``--synthetic`` — no corpus required. Produces the same 30 prospect
   directories from a deterministic taxonomy (6 niches × 5 tech stacks).
   Used by contributors without access to Joel's corpus, by CI, and as the
   starter corpus committed to the repo.

The two modes emit the **same per-site layout** per ``fixtures/README.md``:

    fixtures/<slug>/
      homepage.html
      about.html
      services.html
      google_places.json
      yelp.json
      youtube.json
      expected.json
    fixtures/seeds.csv

Determinism: re-runs are byte-identical. The ``expected.json`` payload
carries a pinned ``fetched_at`` placeholder so the file content is stable;
tests compare modulo that field per the determinism rule in
``fixtures/README.md``.

Usage:

    python scripts/build-fixtures.py --synthetic
    python scripts/build-fixtures.py --source ~/briefs --out fixtures/
    python scripts/build-fixtures.py --synthetic --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "fixtures"

# IANA-reserved TLD for documentation / examples; safe from real collisions.
FIXTURE_TLD = "example"

# Pinned placeholder. The determinism rule lets tests ignore this field.
PLACEHOLDER_FETCHED_AT = "2026-04-20T00:00:00+00:00"

PLACEHOLDER_EMAIL = "hello@example.test"
PLACEHOLDER_PHONE = "(555) 555-0100"
PLACEHOLDER_PERSON = "the Owner"

CORPUS_TARGET_SIZE = 30


# ---------------------------------------------------------------------------
# PII sanitization
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"
)
# Masks person names that appear in a person-signalling context
# ("contact: Jane Doe", "— Founder Jane Doe"). Deliberately narrow to avoid
# nuking business names that happen to read like "First Last".
PERSON_CONTEXT_RE = re.compile(
    r"(?i)\b(contact|founder|owner|ceo|cto|coo|director|manager|principal|"
    r"president|partner|head)\b[\s:,\-—]+"
    r"(?P<name>[A-Z][a-z]+(?:\s[A-Z]\.?)?\s[A-Z][a-z]+)"
)


def sanitize_text(text: str) -> str:
    """Mask emails, phones, and contact-context person names."""
    text = EMAIL_RE.sub(PLACEHOLDER_EMAIL, text)
    text = PHONE_RE.sub(PLACEHOLDER_PHONE, text)

    def _mask_name(match: re.Match[str]) -> str:
        return match.group(0).replace(match.group("name"), PLACEHOLDER_PERSON)

    text = PERSON_CONTEXT_RE.sub(_mask_name, text)
    return text


# ---------------------------------------------------------------------------
# Synthetic taxonomy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Niche:
    slug: str
    label: str
    services: tuple[str, ...]
    city: str
    region: str


NICHES: tuple[Niche, ...] = (
    Niche(
        slug="bakery",
        label="Bakery",
        services=("Custom cakes", "Catering", "Wholesale bread", "Pastry boxes"),
        city="Portland",
        region="OR",
    ),
    Niche(
        slug="contractor",
        label="Home Contractor",
        services=(
            "Kitchen remodels",
            "Bathroom remodels",
            "Additions",
            "Deck & patio",
        ),
        city="Denver",
        region="CO",
    ),
    Niche(
        slug="dental",
        label="Dental Clinic",
        services=(
            "General dentistry",
            "Invisalign",
            "Teeth whitening",
            "Pediatric dentistry",
        ),
        city="Austin",
        region="TX",
    ),
    Niche(
        slug="agency",
        label="Marketing Agency",
        services=(
            "Brand strategy",
            "Web design",
            "Paid social",
            "Content production",
        ),
        city="Brooklyn",
        region="NY",
    ),
    Niche(
        slug="auto",
        label="Auto Repair",
        services=(
            "Oil changes",
            "Brake service",
            "Transmission repair",
            "State inspections",
        ),
        city="Raleigh",
        region="NC",
    ),
    Niche(
        slug="fitness",
        label="Boutique Fitness",
        services=(
            "Small-group strength",
            "Private training",
            "Mobility classes",
            "Corporate wellness",
        ),
        city="Seattle",
        region="WA",
    ),
)


@dataclass(frozen=True)
class Stack:
    slug: str
    label: str
    generator_meta: str
    theme_class: str
    tech_stack: tuple[str, ...]


STACKS: tuple[Stack, ...] = (
    Stack(
        slug="wordpress",
        label="WordPress + Elementor",
        generator_meta='<meta name="generator" content="WordPress 6.4">',
        theme_class='class="wp-elementor"',
        tech_stack=("WordPress", "Elementor"),
    ),
    Stack(
        slug="squarespace",
        label="Squarespace",
        generator_meta='<meta name="generator" content="Squarespace 7.1">',
        theme_class='class="sqs-site"',
        tech_stack=("Squarespace",),
    ),
    Stack(
        slug="wix",
        label="Wix",
        generator_meta='<meta name="generator" content="Wix.com Website Builder">',
        theme_class='class="wix-site"',
        tech_stack=("Wix",),
    ),
    Stack(
        slug="webflow",
        label="Webflow",
        generator_meta='<meta name="generator" content="Webflow">',
        theme_class='class="w-body" data-wf-site="synthetic"',
        tech_stack=("Webflow",),
    ),
    Stack(
        slug="custom",
        label="Custom",
        generator_meta="<!-- hand-rolled static build -->",
        theme_class='class="site-root"',
        tech_stack=("Custom",),
    ),
)

# Deterministic name prefixes per niche. Five prefixes × five stacks; we pair
# them by index so each (niche, stack) maps to exactly one prospect.
NAME_PREFIXES: dict[str, tuple[str, ...]] = {
    "bakery": ("acme", "brooklyn-loaves", "sunrise", "cornerstone", "oakleaf"),
    "contractor": ("hilltop", "ironworks", "keystone", "mapleridge", "redwood"),
    "dental": ("brightsmile", "cedarpark", "elmwood", "northridge", "seaside"),
    "agency": ("bluepeak", "canopy", "northlight", "pinewood", "riverstone"),
    "auto": ("apex", "goldengate", "midtown", "rustic", "summit"),
    "fitness": ("anchor", "coastal", "forge", "greenfield", "ironbell"),
}


@dataclass(frozen=True)
class Prospect:
    slug: str
    site: str
    name: str
    niche: Niche
    stack: Stack
    founded: int
    team_claim: str
    copyright_year: int
    last_blog_at: str
    google_place_id: str
    yelp_business_id: str
    youtube_channel_id: str
    review_count: int
    review_rating: float
    ig_handle: str
    yt_handle: str
    yt_subscribers: int


def build_synthetic_prospects() -> list[Prospect]:
    """Produce the 30 synthetic prospects deterministically."""
    prospects: list[Prospect] = []
    for niche in NICHES:
        prefixes = NAME_PREFIXES[niche.slug]
        assert len(prefixes) == len(STACKS), niche.slug
        for i, stack in enumerate(STACKS):
            prefix = prefixes[i]
            slug = f"{prefix}-{niche.slug}"
            site = f"{slug}.{FIXTURE_TLD}"
            name = _humanize_name(prefix, niche.label)
            founded = 2010 + ((len(prospects) * 3) % 14)
            team_size = 3 + (len(prospects) % 18)
            prospects.append(
                Prospect(
                    slug=slug,
                    site=site,
                    name=name,
                    niche=niche,
                    stack=stack,
                    founded=founded,
                    team_claim=f"team of {team_size}",
                    copyright_year=2024 - (len(prospects) % 3),
                    last_blog_at=_pinned_blog_date(len(prospects)),
                    google_place_id=f"ChIJ-synthetic-{slug}",
                    yelp_business_id=f"yelp-{slug}",
                    youtube_channel_id=f"UCsynthetic{len(prospects):02d}",
                    review_count=40 + (len(prospects) * 7) % 260,
                    review_rating=round(4.0 + ((len(prospects) * 0.03) % 1.0), 1),
                    ig_handle=f"@{slug.replace('-', '')}",
                    yt_handle=f"@{slug}",
                    yt_subscribers=150 + (len(prospects) * 37) % 9000,
                )
            )
    assert len(prospects) == CORPUS_TARGET_SIZE, len(prospects)
    return prospects


def _humanize_name(prefix: str, niche_label: str) -> str:
    parts = [p.capitalize() for p in prefix.split("-")]
    return f"{' '.join(parts)} {niche_label}"


def _pinned_blog_date(idx: int) -> str:
    # Month varies deterministically across the corpus; year pinned.
    month = 1 + (idx % 12)
    day = 1 + (idx * 2 % 27)
    return f"2026-{month:02d}-{day:02d}T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def render_homepage(p: Prospect) -> str:
    services_li = "\n".join(
        f'      <li>{svc}</li>' for svc in p.niche.services
    )
    sameas = json.dumps(
        [
            f"https://instagram.com/{p.ig_handle.lstrip('@')}",
            f"https://youtube.com/{p.yt_handle}",
        ]
    )
    jsonld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": p.name,
            "url": f"https://{p.site}",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": p.niche.city,
                "addressRegion": p.niche.region,
            },
            "sameAs": json.loads(sameas),
        },
        sort_keys=True,
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  {p.stack.generator_meta}
  <title>{p.name} — {p.niche.label} in {p.niche.city}, {p.niche.region}</title>
  <meta property="og:site_name" content="{p.name}">
  <meta property="og:url" content="https://{p.site}">
  <script type="application/ld+json">{jsonld}</script>
</head>
<body {p.stack.theme_class}>
  <header><h1>{p.name}</h1></header>
  <main>
    <p>
      {p.name} is a {p.niche.label.lower()} in {p.niche.city}, {p.niche.region}.
      Founded {p.founded}. We're a {p.team_claim}.
    </p>
    <h2>What we do</h2>
    <ul class="services">
{services_li}
    </ul>
    <h2>Get in touch</h2>
    <p>Email: {PLACEHOLDER_EMAIL} · Phone: {PLACEHOLDER_PHONE}</p>
  </main>
  <footer>© {p.copyright_year} {p.name}. All rights reserved.</footer>
</body>
</html>
"""


def render_about(p: Prospect) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>About — {p.name}</title>
</head>
<body {p.stack.theme_class}>
  <h1>About {p.name}</h1>
  <p>
    {p.name} has served {p.niche.city}, {p.niche.region} since {p.founded}.
    Today we're a {p.team_claim}.
  </p>
  <p>Contact: {PLACEHOLDER_PERSON}. Reach us at {PLACEHOLDER_EMAIL}.</p>
  <p>Our last post went up on {p.last_blog_at[:10]}.</p>
</body>
</html>
"""


def render_services(p: Prospect) -> str:
    items = "\n".join(
        f"  <li><strong>{svc}.</strong> {_service_blurb(svc, p)}</li>"
        for svc in p.niche.services
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Services — {p.name}</title>
</head>
<body {p.stack.theme_class}>
  <h1>Services</h1>
  <ul>
{items}
  </ul>
</body>
</html>
"""


def _service_blurb(svc: str, p: Prospect) -> str:
    return f"Delivered by our {p.team_claim} in {p.niche.city}."


def render_google_places(p: Prospect) -> dict[str, object]:
    return {
        "status": "OK",
        "result": {
            "place_id": p.google_place_id,
            "name": p.name,
            "user_ratings_total": p.review_count,
            "rating": p.review_rating,
            "formatted_address": (
                f"100 Main St, {p.niche.city}, {p.niche.region} 00000, USA"
            ),
            "website": f"https://{p.site}",
            "types": ["establishment", "point_of_interest"],
        },
    }


def render_yelp(p: Prospect) -> dict[str, object]:
    return {
        "id": p.yelp_business_id,
        "name": p.name,
        "url": f"https://yelp.com/biz/{p.yelp_business_id}",
        "rating": p.review_rating,
        "review_count": max(5, p.review_count // 2),
        "categories": [{"alias": p.niche.slug, "title": p.niche.label}],
        "location": {
            "city": p.niche.city,
            "state": p.niche.region,
            "country": "US",
        },
    }


def render_youtube(p: Prospect) -> dict[str, object]:
    return {
        "kind": "youtube#channelListResponse",
        "items": [
            {
                "kind": "youtube#channel",
                "id": p.youtube_channel_id,
                "snippet": {
                    "title": p.name,
                    "customUrl": p.yt_handle,
                },
                "statistics": {
                    "subscriberCount": str(p.yt_subscribers),
                    "hiddenSubscriberCount": False,
                },
            }
        ],
    }


def render_expected(p: Prospect) -> dict[str, object]:
    homepage_text = (
        f"{p.name} is a {p.niche.label.lower()} in {p.niche.city}, "
        f"{p.niche.region}. Founded {p.founded}. We're a {p.team_claim}."
    )
    about_text = (
        f"{p.name} has served {p.niche.city}, {p.niche.region} since "
        f"{p.founded}. Today we're a {p.team_claim}."
    )
    return {
        "status": "ok",
        "data": {
            "site": p.site,
            "fetched_at": PLACEHOLDER_FETCHED_AT,
            "pages": {
                "homepage_text": homepage_text,
                "about_text": about_text,
                "services": list(p.niche.services),
                "tech_stack": list(p.stack.tech_stack),
            },
            "reviews": {
                "count": p.review_count,
                "rating": p.review_rating,
                "source": "reviews_google_places",
            },
            "social": {
                "handles": {
                    "instagram": p.ig_handle,
                    "youtube": p.yt_handle,
                },
                "follower_counts": {"youtube": p.yt_subscribers},
            },
            "mentions": [],
            "signals": {
                "team_size_claim": p.team_claim,
                "linkedin_employee_count": None,
                "hiring_page_active": None,
                "last_funding_round": None,
                "copyright_year": p.copyright_year,
                "last_blog_post_at": p.last_blog_at,
                "tech_vs_claim_mismatches": [],
            },
        },
        "provenance": {
            "site_text_trafilatura": {
                "status": "ok",
                "latency_ms": 0,
                "error": None,
                "provider_version": "0.1.0",
            },
            "site_meta_extruct": {
                "status": "ok",
                "latency_ms": 0,
                "error": None,
                "provider_version": "0.1.0",
            },
            "reviews_google_places": {
                "status": "ok",
                "latency_ms": 0,
                "error": None,
                "provider_version": "0.1.0",
            },
            "reviews_yelp_fusion": {
                "status": "ok",
                "latency_ms": 0,
                "error": None,
                "provider_version": "0.1.0",
            },
            "social_counts_youtube": {
                "status": "ok",
                "latency_ms": 0,
                "error": None,
                "provider_version": "0.1.0",
            },
        },
        "error": None,
        "suggestion": None,
    }


# ---------------------------------------------------------------------------
# Brief-dump mode
# ---------------------------------------------------------------------------


FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SECTION_RE = re.compile(r"(?m)^##\s+(?P<title>.+?)\s*$")


def extract_prospect_from_brief(
    brief_path: Path, synthetic_fallback: Prospect
) -> Prospect:
    """Extract a Prospect from a research-brief.md file.

    The brief is expected to carry YAML-ish front-matter; missing keys fall
    back to the synthetic prospect at the same corpus index so the per-site
    layout stays uniform. Fails soft by design — a malformed brief becomes
    a "mostly synthetic" fixture rather than crashing the run.
    """
    text = brief_path.read_text(encoding="utf-8", errors="replace")
    front: dict[str, str] = {}
    fm = FRONT_MATTER_RE.match(text)
    if fm:
        for line in fm.group(1).splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                front[key.strip().lower()] = val.strip().strip('"').strip("'")

    site = front.get("site") or synthetic_fallback.site
    site = site.replace("http://", "").replace("https://", "").strip("/ ")

    name = front.get("name") or synthetic_fallback.name
    niche_slug = (front.get("niche") or synthetic_fallback.niche.slug).lower()
    niche = next((n for n in NICHES if n.slug == niche_slug), synthetic_fallback.niche)
    stack_slug = (front.get("stack") or synthetic_fallback.stack.slug).lower()
    stack = next((s for s in STACKS if s.slug == stack_slug), synthetic_fallback.stack)

    # Slug is derived from the site so the fixture dir is stable even when
    # the brief uses a different filename.
    slug = re.sub(r"[^a-z0-9]+", "-", site.lower().split(".")[0]).strip("-")
    if not slug:
        slug = synthetic_fallback.slug

    return Prospect(
        slug=slug,
        site=site,
        name=name,
        niche=niche,
        stack=stack,
        founded=int(front.get("founded") or synthetic_fallback.founded),
        team_claim=front.get("team_claim") or synthetic_fallback.team_claim,
        copyright_year=int(
            front.get("copyright_year") or synthetic_fallback.copyright_year
        ),
        last_blog_at=front.get("last_blog_at") or synthetic_fallback.last_blog_at,
        google_place_id=front.get("google_place_id")
        or synthetic_fallback.google_place_id,
        yelp_business_id=front.get("yelp_business_id")
        or synthetic_fallback.yelp_business_id,
        youtube_channel_id=front.get("youtube_channel_id")
        or synthetic_fallback.youtube_channel_id,
        review_count=int(front.get("review_count") or synthetic_fallback.review_count),
        review_rating=float(
            front.get("review_rating") or synthetic_fallback.review_rating
        ),
        ig_handle=front.get("ig_handle") or synthetic_fallback.ig_handle,
        yt_handle=front.get("yt_handle") or synthetic_fallback.yt_handle,
        yt_subscribers=int(
            front.get("yt_subscribers") or synthetic_fallback.yt_subscribers
        ),
    )


def load_prospects_from_briefs(source: Path) -> list[Prospect]:
    """Sample up to ``CORPUS_TARGET_SIZE`` prospects from a briefs dir.

    Briefs are sorted alphabetically for determinism. Each brief is paired
    with the synthetic prospect at the same index as its fallback source.
    """
    briefs = sorted(source.glob("*.md"))
    if not briefs:
        raise SystemExit(f"no *.md briefs found in {source}")
    synthetic = build_synthetic_prospects()
    prospects: list[Prospect] = []
    for idx, path in enumerate(briefs[:CORPUS_TARGET_SIZE]):
        fallback = synthetic[idx % len(synthetic)]
        prospects.append(extract_prospect_from_brief(path, fallback))
    return prospects


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_prospect(p: Prospect, out_root: Path) -> None:
    site_dir = out_root / p.slug
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "homepage.html").write_text(
        sanitize_text(render_homepage(p)), encoding="utf-8"
    )
    (site_dir / "about.html").write_text(
        sanitize_text(render_about(p)), encoding="utf-8"
    )
    (site_dir / "services.html").write_text(
        sanitize_text(render_services(p)), encoding="utf-8"
    )
    write_json(site_dir / "google_places.json", render_google_places(p))
    write_json(site_dir / "yelp.json", render_yelp(p))
    write_json(site_dir / "youtube.json", render_youtube(p))
    write_json(site_dir / "expected.json", render_expected(p))


def write_seeds(prospects: Iterable[Prospect], out_root: Path) -> None:
    lines = ["site"] + [p.site for p in prospects]
    (out_root / "seeds.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the 30-prospect fixtures corpus from a briefs dump or a "
            "deterministic synthetic taxonomy."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--source",
        type=Path,
        help="Directory of research-brief.md files (Joel's private corpus).",
    )
    mode.add_argument(
        "--synthetic",
        action="store_true",
        help="Emit the deterministic 30-prospect synthetic taxonomy.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory (default: fixtures/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be written; do not touch disk.",
    )
    args = parser.parse_args(argv)

    if args.synthetic:
        prospects = build_synthetic_prospects()
    else:
        prospects = load_prospects_from_briefs(args.source)

    if args.dry_run:
        for p in prospects:
            print(f"{p.slug}\t{p.site}\t{p.niche.slug}/{p.stack.slug}")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    for p in prospects:
        write_prospect(p, args.out)
    write_seeds(prospects, args.out)
    print(f"wrote {len(prospects)} prospects under {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
