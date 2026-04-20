"""Typer CLI surface for research-pack.

Milestone 1: command stubs only. Implementations land in M2–M4.
The CLI shape itself is part of the public contract — see docs/SPEC.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from research_pack import __version__

app = typer.Typer(
    name="research-pack",
    help="Deterministic research-pack collector for outreach pipelines.",
    no_args_is_help=True,
    add_completion=False,
)

cache_app = typer.Typer(
    name="cache",
    help="Inspect or prune the fetch cache.",
    no_args_is_help=True,
)
app.add_typer(cache_app, name="cache")

providers_app = typer.Typer(
    name="providers",
    help="Inspect available providers.",
    no_args_is_help=True,
)
app.add_typer(providers_app, name="providers")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"research-pack {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Optional[bool] = typer.Option(  # noqa: UP007 — Typer needs Optional
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """research-pack — domain in, JSON out."""


@app.command()
def fetch(
    domain: str = typer.Argument(..., help="The prospect domain, e.g. example.com"),
    out: Optional[Path] = typer.Option(None, "--out", help="Write JSON to this path."),
    json_out: bool = typer.Option(True, "--json/--markdown", help="Output format."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the fetch cache."),
    config: Optional[Path] = typer.Option(None, "--config", help="TOML config path."),
    mock: bool = typer.Option(
        False, "--mock", help="Load from fixtures/<domain>/ instead of network."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose run-log to stderr."),
    ignore_robots: bool = typer.Option(
        False,
        "--ignore-robots",
        help="Bypass robots.txt. Explicit CLI-only; not config-file-settable.",
    ),
) -> None:
    """Run all providers for one domain. (Stub — implemented in M3/M4.)"""
    raise typer.Exit(code=2)


@app.command()
def batch(
    csv: Path = typer.Argument(..., help="CSV of domains."),
    out: Path = typer.Option(..., "--out", help="Output directory."),
    json_out: bool = typer.Option(True, "--json/--markdown", help="Output format."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the fetch cache."),
    config: Optional[Path] = typer.Option(None, "--config", help="TOML config path."),
    mock: bool = typer.Option(False, "--mock", help="Load from fixtures/."),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose run-log."),
) -> None:
    """Run fetch over a CSV of domains. (Stub — implemented in M4.)"""
    raise typer.Exit(code=2)


@app.command()
def validate(
    json_path: Path = typer.Argument(..., help="Path to a research-pack JSON."),
) -> None:
    """Validate a JSON file against the pydantic schema. (Stub — implemented in M2/M4.)"""
    raise typer.Exit(code=2)


@cache_app.command("list")
def cache_list() -> None:
    """List cache entries. (Stub — implemented in M4.)"""
    raise typer.Exit(code=2)


@cache_app.command("clear")
def cache_clear(
    domain: Optional[str] = typer.Option(None, "--domain", help="Limit to one domain."),
    older_than: Optional[str] = typer.Option(
        None, "--older-than", help="Drop entries older than e.g. 7d."
    ),
) -> None:
    """Prune the cache. (Stub — implemented in M4.)"""
    raise typer.Exit(code=2)


@providers_app.command("list")
def providers_list() -> None:
    """Show available providers, status, and cost-hint. (Stub — implemented in M2/M4.)"""
    raise typer.Exit(code=2)


if __name__ == "__main__":  # pragma: no cover
    app()
