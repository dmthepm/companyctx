"""Real golden corpus — 5 hand-curated oracles from external brief artifacts.

Closes the gap flagged as HIGH by the Codex review on PR #19 and tracked in
issue #24. Five fixtures are marked ``.hand-curated``: the HTML under each
is a **sanitized snapshot** of the real site the external brief pipeline
observed (not synthetic templates), the per-fixture
``raw_observations.json`` captures the review/rating/social signals the
brief recorded verbatim, and ``expected.json`` is the frozen envelope
shape companyctx must produce against the sanitized HTML.

What this suite enforces (gated on every PR):

1. **Envelope shape drift.** ``companyctx fetch <slug>.example --mock
   --json`` must produce bytes equal to the committed
   ``expected.json`` modulo ``fetched_at``. Any extractor or envelope
   change that shifts the output against real sanitized markup trips
   this immediately.
2. **Observation/provider-fixture parity.** The review counts, ratings,
   and social follower counts in ``raw_observations.json`` must match
   what the sibling provider JSON fixtures encode. When a future
   provider wires up and starts surfacing these fields in the envelope,
   the regenerated ``expected.json`` will continue to need to match the
   observations — preserving the external-pipeline gate across provider
   additions.
3. **Marker integrity.** Every real-golden fixture carries the
   ``.hand-curated`` marker, and ``scripts/build-fixtures.py`` refuses
   to overwrite any directory that carries it.

The five slugs + their external artifact dates / opaque ids live in
``fixtures/<slug>/SOURCE.md`` and are summarized in ``fixtures/README.md``.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from companyctx.cli import app

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FETCHED_AT_RE = re.compile(rb'"fetched_at":\s*"[^"]+"')

REAL_GOLDEN_SLUGS = (
    "northarlington-pharmacy-01",
    "cary-hormone-02",
    "hinsdale-derm-03",
    "birmingham-iv-04",
    "charleston-medspa-05",
)


def _scrub_fetched_at(raw: bytes) -> bytes:
    return FETCHED_AT_RE.sub(b'"fetched_at": "<scrubbed>"', raw)


def _load_json(path: Path) -> dict[str, Any]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), path
    return payload


def _load_observations(slug: str) -> dict[str, Any]:
    return _load_json(FIXTURES_DIR / slug / "raw_observations.json")


def _load_provider_json(slug: str, name: str) -> dict[str, Any]:
    return _load_json(FIXTURES_DIR / slug / name)


@pytest.mark.parametrize("slug", REAL_GOLDEN_SLUGS)
def test_envelope_matches_hand_curated_oracle(slug: str) -> None:
    fixture_dir = FIXTURES_DIR / slug
    assert (fixture_dir / ".hand-curated").exists(), (
        f"{fixture_dir}/.hand-curated is missing — real-golden fixtures must "
        "carry the marker so scripts/build-fixtures.py refuses to regenerate them"
    )
    assert (fixture_dir / "SOURCE.md").exists(), (
        f"{fixture_dir}/SOURCE.md is missing — every real-golden fixture must "
        "cite the external brief artifact it was sanitized from"
    )
    assert (fixture_dir / "raw_observations.json").exists(), (
        f"{fixture_dir}/raw_observations.json is missing — the external "
        "pipeline's review/rating/social observations live there"
    )

    expected = _scrub_fetched_at((fixture_dir / "expected.json").read_bytes())

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            f"{slug}.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert _scrub_fetched_at(result.stdout.encode("utf-8")) == expected, slug


@pytest.mark.parametrize("slug", REAL_GOLDEN_SLUGS)
def test_google_places_fixture_matches_observations(slug: str) -> None:
    obs = _load_observations(slug)
    gp = _load_provider_json(slug, "google_places.json")
    expected_rating = obs["reviews"]["google"]["rating"]
    expected_count = obs["reviews"]["google"]["review_count"]

    result = gp.get("result", {})
    if expected_rating is None:
        assert "rating" not in result, (slug, "unexpected Google rating in fixture")
    else:
        assert result.get("rating") == expected_rating, slug

    if expected_count is None:
        assert "user_ratings_total" not in result, (
            slug,
            "unexpected Google review count in fixture",
        )
    else:
        assert result.get("user_ratings_total") == expected_count, slug


@pytest.mark.parametrize("slug", REAL_GOLDEN_SLUGS)
def test_yelp_fixture_matches_observations(slug: str) -> None:
    obs = _load_observations(slug)
    y = _load_provider_json(slug, "yelp.json")
    expected_rating = obs["reviews"]["yelp"]["rating"]
    expected_count = obs["reviews"]["yelp"]["review_count"]

    if expected_rating is None:
        assert "rating" not in y, (slug, "unexpected Yelp rating in fixture")
    else:
        assert y.get("rating") == expected_rating, slug

    if expected_count is None:
        assert "review_count" not in y, (slug, "unexpected Yelp review count in fixture")
    else:
        assert y.get("review_count") == expected_count, slug


@pytest.mark.parametrize("slug", REAL_GOLDEN_SLUGS)
def test_youtube_fixture_matches_observations(slug: str) -> None:
    obs = _load_observations(slug)
    yt = _load_provider_json(slug, "youtube.json")
    channel_exists = obs["social"]["youtube"]["channel_exists"]
    subscribers = obs["social"]["youtube"]["subscribers"]

    items = yt.get("items", [])
    if not channel_exists:
        assert items == [], (slug, "observation says no channel but fixture has items")
        return

    assert items, (slug, "observation says channel exists but fixture is empty")
    stats = items[0].get("statistics", {})
    if subscribers is None:
        # Channel exists but subscribers hidden — fixture must reflect that.
        assert stats.get("hiddenSubscriberCount") is True, slug
        assert "subscriberCount" not in stats, slug
    else:
        assert stats.get("subscriberCount") == str(subscribers), slug


@pytest.mark.parametrize("slug", REAL_GOLDEN_SLUGS)
def test_observation_identifiers_are_consistent(slug: str) -> None:
    """The slug in raw_observations.json matches the directory slug, and
    the artifact date + id are the same values the SOURCE.md cites."""
    obs = _load_observations(slug)
    assert obs["slug"] == slug
    artifact = obs["artifact"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", artifact["date"]), artifact
    assert re.match(r"^brief-[0-9a-f]{12}$", artifact["id"]), artifact

    source = (FIXTURES_DIR / slug / "SOURCE.md").read_text(encoding="utf-8")
    assert artifact["date"] in source, slug
    assert artifact["id"] in source, slug


def _load_build_fixtures_module() -> object:
    """Import ``scripts/build-fixtures.py`` dynamically.

    The file is named with a hyphen, so the normal ``import`` machinery
    does not find it; we load it via ``importlib.util`` instead. Caching
    on ``sys.modules`` keeps later calls cheap.
    """
    mod_name = "scripts_build_fixtures"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "build-fixtures.py"
    spec = importlib.util.spec_from_file_location(mod_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def test_build_fixtures_refuses_to_overwrite_hand_curated(tmp_path: Path) -> None:
    """Guard invariant: any fixture with a ``.hand-curated`` marker must not
    be regenerated by ``scripts/build-fixtures.py``, regardless of mode."""
    module = _load_build_fixtures_module()

    synthetic_prospects = module.build_synthetic_prospects()  # type: ignore[attr-defined]
    target = synthetic_prospects[0]

    site_dir = tmp_path / target.slug
    site_dir.mkdir()
    marker = site_dir / module.HAND_CURATED_MARKER  # type: ignore[attr-defined]
    marker.write_text("hand-curated — do not regenerate\n", encoding="utf-8")

    with pytest.raises(module.HandCuratedFixtureError) as excinfo:  # type: ignore[attr-defined]
        module.write_prospect(target, tmp_path)  # type: ignore[attr-defined]
    assert target.slug in str(excinfo.value)
    assert marker.exists()
    assert not (site_dir / "homepage.html").exists()


def test_every_real_golden_fixture_carries_the_marker() -> None:
    """Sanity: the marker is the only thing that prevents regeneration."""
    for slug in REAL_GOLDEN_SLUGS:
        marker = FIXTURES_DIR / slug / ".hand-curated"
        assert marker.exists(), f"{slug} is missing the .hand-curated marker"
