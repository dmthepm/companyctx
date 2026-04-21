"""Typer CLI surface for companyctx.

Milestone 1: command stubs only. Implementations land in M2–M4.
The CLI shape itself is part of the public contract — see docs/SPEC.md.
"""

from __future__ import annotations

from pathlib import Path

import typer

from companyctx import __version__

app = typer.Typer(
    name="companyctx",
    help="Deterministic B2B context router. Zero keys. Schema-locked JSON.",
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
        typer.echo(f"companyctx {__version__}")
        raise typer.Exit()


# Module-level Typer parameter singletons.
# Hoisted out of function defaults so ruff B008 (no function calls in defaults)
# stays strict for everything else while keeping Typer's idiomatic pattern.
_VERSION_OPT = typer.Option(
    None,
    "--version",
    callback=_version_callback,
    is_eager=True,
    help="Show version and exit.",
)

_SITE_ARG = typer.Argument(
    ..., help="The prospect site, e.g. example.com or https://example.com"
)
_OUT_OPT_FILE = typer.Option(None, "--out", help="Write JSON to this path.")
_OUT_OPT_DIR = typer.Option(..., "--out", help="Output directory.")
_FORMAT_OPT = typer.Option(True, "--json/--markdown", help="Output format.")
_NO_CACHE_OPT = typer.Option(False, "--no-cache", help="Bypass the fetch cache.")
_CONFIG_OPT = typer.Option(None, "--config", help="TOML config path.")
_MOCK_FETCH_OPT = typer.Option(
    False, "--mock", help="Load from fixtures/<site>/ instead of network."
)
_MOCK_BATCH_OPT = typer.Option(False, "--mock", help="Load from fixtures/.")
_VERBOSE_OPT = typer.Option(False, "--verbose", help="Verbose run-log to stderr.")
_IGNORE_ROBOTS_OPT = typer.Option(
    False,
    "--ignore-robots",
    help="Bypass robots.txt. Explicit CLI-only; not config-file-settable.",
)
_REFRESH_OPT = typer.Option(
    False,
    "--refresh",
    help="Ignore cache and re-fetch all providers; still write fresh results back.",
)
_FROM_CACHE_OPT = typer.Option(
    False,
    "--from-cache",
    help="Return only the cached payload; never hit the network. Exit non-zero on miss.",
)
_CSV_ARG = typer.Argument(..., help="CSV of sites.")
_JSON_ARG = typer.Argument(..., help="Path to a companyctx JSON.")
_CACHE_SITE_OPT = typer.Option(None, "--site", help="Limit to one site.")
_CACHE_OLDER_OPT = typer.Option(None, "--older-than", help="Drop entries older than e.g. 7d.")


@app.callback()
def _root(
    version: bool | None = _VERSION_OPT,  # noqa: ARG001 — eager callback handles it
) -> None:
    """companyctx — site in, schema-locked JSON out."""


@app.command()
def fetch(
    site: str = _SITE_ARG,
    out: Path | None = _OUT_OPT_FILE,
    json_out: bool = _FORMAT_OPT,
    no_cache: bool = _NO_CACHE_OPT,
    refresh: bool = _REFRESH_OPT,
    from_cache: bool = _FROM_CACHE_OPT,
    config: Path | None = _CONFIG_OPT,
    mock: bool = _MOCK_FETCH_OPT,
    verbose: bool = _VERBOSE_OPT,
    ignore_robots: bool = _IGNORE_ROBOTS_OPT,
) -> None:
    """Run all providers for one site. (Stub — implemented in M3/M4.)"""
    raise typer.Exit(code=2)


@app.command()
def batch(
    csv: Path = _CSV_ARG,
    out: Path = _OUT_OPT_DIR,
    json_out: bool = _FORMAT_OPT,
    no_cache: bool = _NO_CACHE_OPT,
    config: Path | None = _CONFIG_OPT,
    mock: bool = _MOCK_BATCH_OPT,
    verbose: bool = _VERBOSE_OPT,
) -> None:
    """Run fetch over a CSV of sites. (Stub — implemented in M4.)"""
    raise typer.Exit(code=2)


@app.command()
def validate(
    json_path: Path = _JSON_ARG,
) -> None:
    """Validate a JSON file against the pydantic schema. (Stub — implemented in M2/M4.)"""
    raise typer.Exit(code=2)


@cache_app.command("list")
def cache_list() -> None:
    """List cache entries. (Stub — implemented in M4.)"""
    raise typer.Exit(code=2)


@cache_app.command("clear")
def cache_clear(
    site: str | None = _CACHE_SITE_OPT,
    older_than: str | None = _CACHE_OLDER_OPT,
) -> None:
    """Prune the cache. (Stub — implemented in M4.)"""
    raise typer.Exit(code=2)


@providers_app.command("list")
def providers_list() -> None:
    """Show available providers, status, and cost-hint. (Stub — implemented in M2/M4.)"""
    raise typer.Exit(code=2)


if __name__ == "__main__":  # pragma: no cover
    app()
