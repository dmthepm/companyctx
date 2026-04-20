"""Milestone 1 smoke tests.

Verify the package imports cleanly and the CLI surface is wired. Behavior
tests for providers, schema round-trip, robots enforcement, cache TTL,
and `--mock` determinism land in M2–M5 per docs/SPEC.md test gates.
"""

from __future__ import annotations

from typer.testing import CliRunner

import research_pack
from research_pack.cli import app


def test_version_string_present() -> None:
    assert isinstance(research_pack.__version__, str)
    assert research_pack.__version__


def test_cli_help_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "research-pack" in result.stdout


def test_cli_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert research_pack.__version__ in result.stdout


def test_subcommands_registered() -> None:
    runner = CliRunner()
    for cmd in ("fetch", "batch", "validate", "cache", "providers"):
        result = runner.invoke(app, [cmd, "--help"])
        assert result.exit_code == 0, f"{cmd} --help failed: {result.stdout}"
