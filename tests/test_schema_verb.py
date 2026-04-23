"""Tests for ``companyctx schema`` verb and remaining CLI honesty-pass behaviors.

Covers the v0.2 additions driven by COX-37 plus the v0.3 cache wiring (#9):

- ``companyctx schema`` dumps Draft 2020-12 JSON Schema on stdout.
- The schema validates every regression-fixture envelope.
- ``--config`` still raises ``typer.BadParameter`` (TOML loader deferred).
- ``batch`` still prints a loud "not implemented" banner.

The ``--from-cache`` / ``--refresh`` / ``--no-cache`` / ``cache list`` /
``cache clear`` honesty-pass tests retired with the cache wiring — those
flags and subcommands ship in v0.3, so behavior tests live in
``test_cache.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
from typer.testing import CliRunner

from companyctx.cli import app

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# Typer renders ``typer.BadParameter`` messages through Rich, which wraps
# flag names (``--from-cache``) in per-character ANSI color codes. The escape
# sequences split ``--from-cache`` into ``-`` + ``-from`` + ``-cache`` in
# ``result.output``, so a literal substring match fails on CI even though the
# visible output is correct. Strip ANSI before asserting.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _plain(output: str) -> str:
    return _ANSI_RE.sub("", output)


def test_schema_verb_emits_draft_2020_12_json_schema() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    # Draft 2020-12 publishes both ``$schema`` and a ``$defs`` block when the
    # root model composes nested Pydantic models. The schema URL is the one
    # pydantic v2 emits by default; check containment rather than equality so
    # a future Pydantic pin-bump doesn't silently rot this test.
    assert "2020-12" in payload.get("$schema", "")
    assert payload.get("title") == "Envelope"
    # Essential envelope fields live under ``properties``.
    props = payload.get("properties", {})
    for field in ("schema_version", "status", "data", "provenance", "error"):
        assert field in props, field
    # COX-47: schema_version MUST be in the ``required`` array. A missing
    # ``required`` entry lets a v0.1 envelope (no ``schema_version``) pass as
    # v0.2 — the honesty bug this issue fixes at the Pydantic layer must also
    # show up in the externally-published JSON Schema.
    required = payload.get("required", [])
    assert "schema_version" in required, required


def test_schema_verb_validates_regression_fixture_envelope() -> None:
    schema_runner = CliRunner()
    schema_result = schema_runner.invoke(app, ["schema"])
    assert schema_result.exit_code == 0, schema_result.stdout
    envelope_schema = json.loads(schema_result.stdout)

    fetch_runner = CliRunner()
    fetch_result = fetch_runner.invoke(
        app,
        [
            "fetch",
            "acme-bakery.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    assert fetch_result.exit_code == 0, fetch_result.stdout
    envelope = json.loads(fetch_result.stdout)
    # jsonschema.validate raises on drift; a green assertion is a pass.
    jsonschema.validate(instance=envelope, schema=envelope_schema)


def test_fetch_rejects_silent_config_flag(tmp_path: Path) -> None:
    runner = CliRunner()
    config_path = tmp_path / "settings.toml"
    config_path.write_text("", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "fetch",
            "acme-bakery.example",
            "--config",
            str(config_path),
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    assert result.exit_code != 0
    plain = _plain(result.output)
    assert "--config" in plain
    assert "not implemented" in plain or "issues/9" in plain


def test_batch_stub_fails_loudly() -> None:
    """``batch`` is still deferred — it must exit non-zero with an issue link."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["batch", "fixtures/seeds.csv", "--out", "/tmp/companyctx-batch", "--mock"],
    )
    assert result.exit_code == 2
    plain = _plain(result.output)
    assert "batch" in plain
    assert "not implemented" in plain
