"""Tests for the 30-prospect fixtures corpus + the generator script.

Covers the acceptance gates on issue #5:
- 30 normalized prospect directories exist under fixtures/
- Zero PII leakage (email/phone/contact-name regex sweep)
- Determinism: re-running the generator produces byte-identical output
- scripts/build-fixtures.py is reproducible from a briefs dump
"""

from __future__ import annotations

import filecmp
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"
SCRIPT_PATH = REPO_ROOT / "scripts" / "build-fixtures.py"

EXPECTED_FILES = (
    "homepage.html",
    "about.html",
    "services.html",
    "google_places.json",
    "yelp.json",
    "youtube.json",
    "expected.json",
)

# Regexes used to audit fixture bytes for PII. These are stricter than the
# sanitizer's input regexes — if any of these match committed fixtures, the
# sanitizer let something through.
REAL_EMAIL_RE = re.compile(
    r"(?i)[A-Za-z0-9._%+-]+@(?!example\.test\b|example\.com\b|schema\.org\b)"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
REAL_PHONE_RE = re.compile(
    r"(?:\+?1[\s\-.]?)?\(?(?!555\))\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"
)


@pytest.fixture(scope="module")
def builder():
    """Load scripts/build-fixtures.py as an importable module."""
    spec = importlib.util.spec_from_file_location("build_fixtures", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_fixtures"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_corpus_has_exactly_thirty_prospect_dirs() -> None:
    dirs = sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir())
    assert len(dirs) == 30, [p.name for p in dirs]


def test_each_prospect_has_expected_files() -> None:
    for site_dir in (p for p in FIXTURES_DIR.iterdir() if p.is_dir()):
        missing = [f for f in EXPECTED_FILES if not (site_dir / f).exists()]
        assert not missing, f"{site_dir.name} missing {missing}"


def test_seeds_csv_lists_every_site() -> None:
    seeds = (FIXTURES_DIR / "seeds.csv").read_text(encoding="utf-8").splitlines()
    assert seeds[0] == "site"
    assert len(seeds) == 31  # header + 30


def test_every_expected_json_parses_and_has_schema_shape() -> None:
    for site_dir in (p for p in FIXTURES_DIR.iterdir() if p.is_dir()):
        payload = json.loads((site_dir / "expected.json").read_text())
        assert payload["status"] in {"ok", "partial", "degraded"}
        assert "data" in payload
        assert payload["data"]["site"].endswith(".example")
        assert "fetched_at" in payload["data"]
        assert "provenance" in payload


def test_no_pii_in_any_fixture_bytes() -> None:
    offenders: list[tuple[str, str]] = []
    for path in FIXTURES_DIR.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for email in REAL_EMAIL_RE.findall(text):
            offenders.append((str(path.relative_to(REPO_ROOT)), email))
        for phone in REAL_PHONE_RE.findall(text):
            offenders.append((str(path.relative_to(REPO_ROOT)), phone))
    assert not offenders, offenders


def test_generator_is_deterministic(builder, tmp_path: Path) -> None:
    run1 = tmp_path / "run1"
    run2 = tmp_path / "run2"
    rc1 = builder.main(["--synthetic", "--out", str(run1)])
    rc2 = builder.main(["--synthetic", "--out", str(run2)])
    assert rc1 == 0 and rc2 == 0

    cmp = filecmp.dircmp(run1, run2)
    _assert_no_diff(cmp)


def _assert_no_diff(cmp: filecmp.dircmp[str]) -> None:
    assert not cmp.diff_files, cmp.diff_files
    assert not cmp.left_only, cmp.left_only
    assert not cmp.right_only, cmp.right_only
    for sub in cmp.subdirs.values():
        _assert_no_diff(sub)


def test_generator_matches_committed_corpus(builder, tmp_path: Path) -> None:
    """The committed fixtures/ must equal a fresh --synthetic run."""
    out = tmp_path / "regen"
    rc = builder.main(["--synthetic", "--out", str(out)])
    assert rc == 0

    for site_dir in (p for p in FIXTURES_DIR.iterdir() if p.is_dir()):
        mirror = out / site_dir.name
        assert mirror.is_dir(), site_dir.name
        for name in EXPECTED_FILES:
            left = (site_dir / name).read_bytes()
            right = (mirror / name).read_bytes()
            assert left == right, f"{site_dir.name}/{name} drifted"


def test_sanitizer_masks_emails(builder) -> None:
    out = builder.sanitize_text("ping jane@acme.co if needed")
    assert "jane@acme.co" not in out
    assert builder.PLACEHOLDER_EMAIL in out


def test_sanitizer_masks_phones(builder) -> None:
    for raw in (
        "(503) 555-1234",
        "503-555-1234",
        "503.555.1234",
        "+1 503 555 1234",
        "5035551234",
    ):
        out = builder.sanitize_text(f"call {raw}")
        assert raw not in out, raw
        assert builder.PLACEHOLDER_PHONE in out


def test_sanitizer_masks_contact_context_names(builder) -> None:
    cases = (
        "Contact: Jane Smith",
        "Founder — John Doe",
        "Owner: Priya Patel",
        "CEO, Marcus Lee",
    )
    for raw in cases:
        out = builder.sanitize_text(raw)
        assert builder.PLACEHOLDER_PERSON in out, raw
        # The raw name tokens should be gone.
        tail = raw.split(":", 1)[-1].split("—", 1)[-1].split(",", 1)[-1]
        for token in tail.strip().split():
            assert token not in out or token == builder.PLACEHOLDER_PERSON.split()[-1]


def test_sanitizer_preserves_non_person_text(builder) -> None:
    # Business names that look like "First Last" must NOT be masked when they
    # appear without a person-signalling prefix.
    text = "Acme Bakery makes great bread."
    assert builder.sanitize_text(text) == text


def test_brief_mode_extracts_front_matter(builder, tmp_path: Path) -> None:
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    (briefs / "01-example.md").write_text(
        "---\n"
        "site: real-biz.test\n"
        "name: Real Biz\n"
        "niche: bakery\n"
        "stack: wordpress\n"
        "founded: 2015\n"
        "team_claim: team of 11\n"
        "---\n"
        "\n"
        "Contact: Jane Smith at jane@realbiz.test or (503) 555-9876.\n",
        encoding="utf-8",
    )

    out = tmp_path / "out"
    rc = builder.main(["--source", str(briefs), "--out", str(out)])
    assert rc == 0

    site_dir = out / "real-biz"
    assert site_dir.is_dir()
    expected = json.loads((site_dir / "expected.json").read_text())
    assert expected["data"]["site"] == "real-biz.test"
    assert expected["data"]["signals"]["team_size_claim"] == "team of 11"


def test_brief_mode_fills_missing_fields_from_synthetic(
    builder, tmp_path: Path
) -> None:
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    (briefs / "01.md").write_text(
        "---\nsite: minimal.test\n---\nbody\n", encoding="utf-8"
    )
    out = tmp_path / "out"
    rc = builder.main(["--source", str(briefs), "--out", str(out)])
    assert rc == 0
    assert (out / "minimal" / "homepage.html").exists()
