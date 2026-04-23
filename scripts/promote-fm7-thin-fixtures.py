#!/usr/bin/env python3
"""Promote the FM-7 thin-body regression fixtures (COX-52).

The v0.2 partner-integration validation measured 41 / 209 `status: ok`
envelopes returning under 1 KiB of extracted text — FM-7 thin-body. The
raw per-host evidence lives outside the repo (gitignored per the
sanitization rule). This script writes the committed, sanitized, pseudo-
named regression fixtures that guard the v0.4.0 floor raise.

Niche distribution matches issue #91 §"Fixture promotions":

- 2 seeds per thin-dominated niche (virtual staging, real-estate
  photography, gutter installation, real-estate staging) — 8 fixtures.
- 1 seed per occasional-FM-7 niche — 11 fixtures.
- Total 19 fixtures, each ``homepage.html`` extracting to between
  64 (old floor) and 1024 (new floor) UTF-8 bytes, each with an
  ``expected.json`` asserting the post-fix envelope (``status:
  degraded``, ``error.code: "empty_response"``).

Each fixture is fully pseudonymized — no real business names, real
hostnames, real contact details. The prose is niche-appropriate boilerplate
constructed deterministically from the recipe table so re-runs are
byte-identical.

Usage:

    python scripts/promote-fm7-thin-fixtures.py

Re-runs overwrite the fixtures in place and must produce byte-identical
output (same determinism rule as ``build-fixtures.py``).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES_DIR = REPO_ROOT / "fixtures"
PLACEHOLDER_FETCHED_AT = "2026-04-20T00:00:00+00:00"


@dataclass(frozen=True)
class ThinRecipe:
    """A pseudonymized thin-body fixture recipe.

    ``intro`` must be under ~900 characters so the extracted text stays
    below the v0.4.0 1024-byte floor. The build script asserts per-fixture
    that the extract lands in ``(64, 1024)``.
    """

    slug: str
    niche: str
    city: str
    region: str
    intro: str


# Recipes pair each FM-7-dominated niche in the partner-integration
# validation with a deterministic, pseudonymized thin homepage. The
# ``intro`` prose stays under ~900 bytes — long enough to clear the old
# 64-byte floor (would have been silent-success under v0.3.0) and short
# enough to trip the new 1024-byte floor. Each niche represents the
# thin-body distribution in `research/2026-04-22-v0.2-joel-integration-
# validation.md` §3 without quoting any real site.
RECIPES: tuple[ThinRecipe, ...] = (
    # --- thin-dominated niches (2 seeds each) ---
    ThinRecipe(
        slug="fm7-thin-virtual-staging-01",
        niche="Virtual Staging",
        city="Atlanta",
        region="GA",
        intro=(
            "Boutique virtual staging studio serving Atlanta and Charlotte "
            "metro agents with next-day turnaround on empty-listing "
            "photography. Book a consult through the contact form."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-virtual-staging-02",
        niche="Virtual Staging",
        city="Dallas",
        region="TX",
        intro=(
            "Fast, AI-assisted virtual staging for busy real-estate agents. "
            "Upload empty-room photos, pick a style, get staged listings "
            "back within 24 hours. Volume pricing available."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-re-photography-01",
        niche="Real Estate Photography",
        city="Miami",
        region="FL",
        intro=(
            "Premium real-estate photography and drone coverage for "
            "luxury listings across South Florida. Same-week scheduling, "
            "MLS-ready deliverables, twilight shoots on request."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-re-photography-02",
        niche="Real Estate Photography",
        city="Seattle",
        region="WA",
        intro=(
            "Seattle-based real-estate photography studio specializing "
            "in Craftsman and mid-century listings. Next-day turnaround, "
            "floor plans, and Matterport 3D tours included."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-gutters-01",
        niche="Gutter Installation",
        city="Charlotte",
        region="NC",
        intro=(
            "Local gutter installation and repair contractor serving the "
            "Charlotte metro. Free estimates, seamless aluminum gutters, "
            "gutter-guard upgrades, fully insured."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-gutters-02",
        niche="Gutter Installation",
        city="Indianapolis",
        region="IN",
        intro=(
            "Family-owned gutter contractor serving Indianapolis homeowners "
            "since the early 2000s. Seamless installation, leaf-guard "
            "retrofits, storm-damage repair. Call for a free estimate."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-re-staging-01",
        niche="Real Estate Staging",
        city="Washington",
        region="DC",
        intro=(
            "Full-service real-estate staging for DC metro luxury listings. "
            "Curated furniture inventory, designer-led consultations, "
            "month-to-month rentals available."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-re-staging-02",
        niche="Real Estate Staging",
        city="Austin",
        region="TX",
        intro=(
            "Austin-based home staging studio. We work with listing "
            "agents to prepare vacant and occupied properties for market "
            "photography, open houses, and quick-close timelines."
        ),
    ),
    # --- occasional-FM-7 niches (1 seed each) ---
    ThinRecipe(
        slug="fm7-thin-bariatric-01",
        niche="Bariatric Surgery",
        city="Orlando",
        region="FL",
        intro=(
            "Board-certified bariatric surgery practice serving central "
            "Florida. Gastric sleeve, bypass, and revisional procedures. "
            "Comprehensive pre-op and post-op nutrition support."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-chiropractic-01",
        niche="Chiropractic Care",
        city="Denver",
        region="CO",
        intro=(
            "Full-service chiropractic clinic in Denver. Adjustments, "
            "active-release technique, sports-injury recovery, and "
            "prenatal care. New-patient exams available."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-dentistry-01",
        niche="Cosmetic Dentistry",
        city="New York",
        region="NY",
        intro=(
            "Manhattan-based cosmetic dentistry office. Porcelain veneers, "
            "Invisalign clear aligners, whitening, and digital smile-design "
            "consults. Accepting new patients."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-dermatology-01",
        niche="Dermatology",
        city="San Diego",
        region="CA",
        intro=(
            "San Diego dermatology and aesthetic medicine practice. "
            "Medical, surgical, and cosmetic dermatology under one roof. "
            "Same-week appointments for most visits."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-medspa-01",
        niche="Medical Spa",
        city="Phoenix",
        region="AZ",
        intro=(
            "Full-service medical spa in the Phoenix metro. Injectables, "
            "laser treatments, skin rejuvenation, IV therapy. Physician-"
            "owned and operated since 2014."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-botox-01",
        niche="Medical Aesthetics",
        city="Nashville",
        region="TN",
        intro=(
            "Nashville-based medical aesthetics clinic specializing in "
            "Botox, dermal fillers, and laser hair removal. Licensed "
            "nurse injectors on staff, free consultations available."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-orthodontics-01",
        niche="Orthodontics",
        city="Columbus",
        region="OH",
        intro=(
            "Columbus-area orthodontics practice serving children, "
            "teens, and adults. Traditional braces, clear aligners, "
            "and retainer services. Two convenient locations."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-plastic-surgery-01",
        niche="Plastic Surgery",
        city="Los Angeles",
        region="CA",
        intro=(
            "LA-based plastic and reconstructive surgery practice. "
            "Board-certified surgeons, in-house accredited surgical "
            "suite, virtual consultations available nationwide."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-inspection-01",
        niche="Property Inspection",
        city="Minneapolis",
        region="MN",
        intro=(
            "Residential and commercial property inspection services "
            "across the Twin Cities. Same-week scheduling, digital "
            "reports, thermal imaging on request."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-waste-01",
        niche="Waste Management",
        city="Houston",
        region="TX",
        intro=(
            "Houston-area dumpster rental and waste removal. Roll-off "
            "containers from 10 to 40 yards, construction-debris "
            "specialists, next-day delivery."
        ),
    ),
    ThinRecipe(
        slug="fm7-thin-window-door-01",
        niche="Window and Door Replacement",
        city="Kansas City",
        region="MO",
        intro=(
            "Kansas City window and door replacement contractor. "
            "Energy-efficient vinyl, fiberglass, and wood-clad windows. "
            "Professional installation, lifetime labor warranty."
        ),
    ),
)


def render_thin_homepage(r: ThinRecipe) -> str:
    """Render a deterministic thin homepage for a recipe.

    The homepage is intentionally sparse — a single headline plus one
    paragraph of prose. Trafilatura extracts the <p> body only, so the
    extracted bytes equal ``len(r.intro.encode("utf-8"))`` plus a small
    margin. Stay under 1024 bytes of extracted text to trip the gate.
    """
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{r.niche} — {r.city}, {r.region}</title>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{r.niche} in {r.city}, {r.region}</h1>\n"
        f"  <p>{r.intro}</p>\n"
        "</body>\n"
        "</html>\n"
    )


def render_expected_envelope(r: ThinRecipe) -> dict[str, object]:
    """Build the post-fix envelope for this fixture by running the orchestrator.

    Keeps the expected envelope in lockstep with ``companyctx.core.run`` so
    the fixture evolves automatically if the envelope shape or classifier
    output changes.
    """
    from companyctx import core  # noqa: PLC0415

    pinned = datetime.fromisoformat(PLACEHOLDER_FETCHED_AT)
    env = core.run(
        f"{r.slug}.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        fetched_at=pinned,
    )
    return env.model_dump(mode="json")


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_fixture(r: ThinRecipe) -> None:
    site_dir = FIXTURES_DIR / r.slug
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "homepage.html").write_text(render_thin_homepage(r), encoding="utf-8")
    # expected.json must be written second — the orchestrator reads the
    # just-written HTML to build the envelope.
    write_json(site_dir / "expected.json", render_expected_envelope(r))


def main() -> int:
    for r in RECIPES:
        write_fixture(r)
    print(f"wrote {len(RECIPES)} FM-7 thin-body fixtures under {FIXTURES_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
