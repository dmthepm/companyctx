"""Tests for ``companyctx schema`` verb and CLI honesty-pass behaviors.

Covers the v0.2 additions driven by COX-37:

- ``companyctx schema`` dumps Draft 2020-12 JSON Schema on stdout.
- The schema validates every regression-fixture envelope.
- ``--from-cache`` / ``--refresh`` / ``--no-cache`` / ``--config`` raise
  ``typer.BadParameter`` with an issue-link message (was silent-ignore).
- ``batch`` / ``cache list`` / ``cache clear`` print a loud "not implemented"
  message on stderr + exit non-zero (was silent exit 2).
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from typer.testing import CliRunner

from companyctx.cli import app

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


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


@pytest.mark.parametrize(
    "flag",
    ["--from-cache", "--refresh", "--no-cache"],
)
def test_fetch_rejects_silent_cache_flag(flag: str) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            "acme-bakery.example",
            flag,
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    assert result.exit_code != 0
    assert flag in result.output
    assert "not implemented" in result.output or "issues/37" in result.output


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
    assert "--config" in result.output
    assert "not implemented" in result.output or "issues/37" in result.output


@pytest.mark.parametrize(
    ("argv", "needle"),
    [
        (
            ["batch", "fixtures/seeds.csv", "--out", "/tmp/companyctx-batch", "--mock"],
            "batch",
        ),
        (["cache", "list"], "cache list"),
        (["cache", "clear"], "cache clear"),
    ],
)
def test_stubs_fail_loudly(argv: list[str], needle: str) -> None:
    runner = CliRunner()
    result = runner.invoke(app, argv)
    assert result.exit_code == 2
    # Click/Typer 0.12+: stderr is separated; ``result.output`` is the merged
    # stream, ``result.stderr`` the stderr-only view. The stub writes its
    # "not implemented" banner via ``typer.secho(..., err=True)``.
    assert needle in result.output
    assert "not implemented in v0.2.0" in result.output
