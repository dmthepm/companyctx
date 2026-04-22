"""Typer CLI surface for companyctx.

Exposes the public contract described in ``docs/SPEC.md``:

- ``fetch <site>`` — run the Deterministic Waterfall and emit one envelope.
- ``schema`` — print the envelope's JSON Schema (Draft 2020-12) to stdout.
- ``validate <path>`` — round-trip a JSON envelope through the schema.
- ``providers list`` — show registered providers with status + cost hint.
- ``cache list`` / ``cache clear`` — Vertical Memory plumbing (see issue #37).
- ``batch <csv>`` — batch mode (see issue #38).

Several flags and subcommands in v0.2 are stubs. They fail loudly rather than
silently accepting input and doing nothing — see issue #68 for the honesty
pass.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from companyctx import __version__, core
from companyctx.providers import discover
from companyctx.providers.base import ProviderBase
from companyctx.schema import Envelope

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


# Tracking-issue links for honesty-mode rejections. Each stub command / flag
# carries its own issue so users who hit the wall can follow progress.
_CACHE_ISSUE = 37
_BATCH_ISSUE = 38
_CONFIG_ISSUE = 37


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"companyctx {__version__}")
        raise typer.Exit()


def _reject_cache_flag(flag: str, issue: int) -> Any:
    """Typer callback that rejects a cache-related flag if the user set it.

    Cache flags exist in the CLI surface as first-class options (per v0.1
    SPEC) but the cache itself is still unwired. Silently ignoring them used
    to be the behavior; v0.2 rejects them loudly so agents don't build on a
    contract we don't honour yet. See issue #68 Part A.
    """

    def _callback(value: bool) -> bool:
        if value:
            raise typer.BadParameter(
                f"{flag} is not implemented in v0.2.0 — "
                f"see https://github.com/dmthepm/companyctx/issues/{issue}"
            )
        return value

    return _callback


def _reject_config_flag(value: Path | None) -> Path | None:
    """Reject ``--config <path>`` until the TOML loader lands."""
    if value is not None:
        raise typer.BadParameter(
            "--config is not implemented in v0.2.0 — "
            f"see https://github.com/dmthepm/companyctx/issues/{_CONFIG_ISSUE}"
        )
    return value


def _fail_stub(command: str, issue: int) -> None:
    """Print a loud stderr message and exit non-zero for a not-yet-wired command."""
    typer.secho(
        f"{command} is not implemented in v0.2.0 — "
        f"see https://github.com/dmthepm/companyctx/issues/{issue}",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=2)


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

_SITE_ARG = typer.Argument(..., help="The prospect site, e.g. example.com or https://example.com")
_OUT_OPT_FILE = typer.Option(None, "--out", help="Write JSON to this path.")
_OUT_OPT_DIR = typer.Option(..., "--out", help="Output directory.")
_FORMAT_OPT = typer.Option(
    True,
    "--json/--markdown",
    help=(
        "Output format. --json is the supported contract. "
        "--markdown is experimental and not implemented in v0.2.0 — "
        "runs fail fast (see issue #68)."
    ),
)
_PROVIDERS_JSON_OPT = typer.Option(
    False,
    "--json",
    help="Emit the registry as a JSON array (one dict per provider).",
)
_NO_CACHE_OPT = typer.Option(
    False,
    "--no-cache",
    help="Bypass the fetch cache. (Not implemented in v0.2.0 — see issue #37.)",
    callback=_reject_cache_flag("--no-cache", _CACHE_ISSUE),
)
_CONFIG_OPT = typer.Option(
    None,
    "--config",
    help="TOML config path. (Not implemented in v0.2.0 — see issue #37.)",
    callback=_reject_config_flag,
)
_MOCK_FETCH_OPT = typer.Option(
    False, "--mock", help="Load from fixtures/<site>/ instead of network."
)
_FIXTURES_DIR_OPT = typer.Option(
    Path("fixtures"),
    "--fixtures-dir",
    help="Directory holding the --mock fixture tree (default: ./fixtures).",
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
    help="Ignore cache and re-fetch. (Not implemented in v0.2.0 — see issue #37.)",
    callback=_reject_cache_flag("--refresh", _CACHE_ISSUE),
)
_FROM_CACHE_OPT = typer.Option(
    False,
    "--from-cache",
    help="Return only the cached payload. (Not implemented in v0.2.0 — see issue #37.)",
    callback=_reject_cache_flag("--from-cache", _CACHE_ISSUE),
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
    no_cache: bool = _NO_CACHE_OPT,  # noqa: ARG001 — callback rejects if set
    refresh: bool = _REFRESH_OPT,  # noqa: ARG001 — callback rejects if set
    from_cache: bool = _FROM_CACHE_OPT,  # noqa: ARG001 — callback rejects if set
    config: Path | None = _CONFIG_OPT,  # noqa: ARG001 — callback rejects if set
    mock: bool = _MOCK_FETCH_OPT,
    verbose: bool = _VERBOSE_OPT,
    ignore_robots: bool = _IGNORE_ROBOTS_OPT,
    fixtures_dir: Path = _FIXTURES_DIR_OPT,
) -> None:
    """Run every registered provider for ``site`` and emit one envelope."""
    if not json_out:
        # Markdown output belongs in a downstream synthesis layer, not here.
        typer.secho(
            "--markdown is not implemented in v0.2.0; rerun with --json.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    envelope = core.run(
        site,
        mock=mock,
        fixtures_dir=fixtures_dir if mock else None,
        ignore_robots=ignore_robots,
    )

    payload = envelope.model_dump(mode="json")
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    if verbose:
        typer.secho(
            f"companyctx {__version__} — {site} → status={envelope.status}",
            fg=typer.colors.CYAN,
            err=True,
        )
        for slug, meta in sorted(envelope.provenance.items()):
            typer.secho(
                f"  {slug}: {meta.status} ({meta.latency_ms}ms)",
                fg=typer.colors.CYAN,
                err=True,
            )

    if out is None:
        sys.stdout.write(text)
    else:
        out.write_text(text, encoding="utf-8")


@app.command()
def schema() -> None:
    """Emit the envelope's JSON Schema (Draft 2020-12) to stdout.

    Consumers can validate envelopes without importing ``companyctx`` — the
    schema is self-describing and carries ``$defs`` for every nested model.
    """
    payload = Envelope.model_json_schema()
    # Pydantic v2 targets Draft 2020-12 but omits the ``$schema`` key by
    # default. Stamp it so downstream validators (``jsonschema.validate`` and
    # friends) pick the right dialect without probing the payload.
    payload.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


@app.command()
def batch(
    csv: Path = _CSV_ARG,  # noqa: ARG001 — stub
    out: Path = _OUT_OPT_DIR,  # noqa: ARG001 — stub
    json_out: bool = _FORMAT_OPT,  # noqa: ARG001 — stub
    no_cache: bool = _NO_CACHE_OPT,  # noqa: ARG001 — stub
    config: Path | None = _CONFIG_OPT,  # noqa: ARG001 — stub
    mock: bool = _MOCK_BATCH_OPT,  # noqa: ARG001 — stub
    verbose: bool = _VERBOSE_OPT,  # noqa: ARG001 — stub
) -> None:
    """Run fetch over a CSV of sites. (Stub — see issue #38.)"""
    _fail_stub("batch", _BATCH_ISSUE)


@app.command()
def validate(
    json_path: Path = _JSON_ARG,
) -> None:
    """Validate a JSON file against the pydantic schema."""
    try:
        raw = json_path.read_text(encoding="utf-8")
    except OSError as exc:
        typer.secho(f"cannot read {json_path}: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    try:
        Envelope.model_validate_json(raw)
    except ValidationError as exc:
        typer.secho(f"invalid envelope: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"ok: {json_path}")


@cache_app.command("list")
def cache_list() -> None:
    """List cache entries. (Stub — see issue #37.)"""
    _fail_stub("cache list", _CACHE_ISSUE)


@cache_app.command("clear")
def cache_clear(
    site: str | None = _CACHE_SITE_OPT,  # noqa: ARG001 — stub
    older_than: str | None = _CACHE_OLDER_OPT,  # noqa: ARG001 — stub
) -> None:
    """Prune the cache. (Stub — see issue #37.)"""
    _fail_stub("cache clear", _CACHE_ISSUE)


# Waterfall-tier mapping for the provider registry. The orchestrator runs
# providers in three bands — zero-key (Attempt 1), smart-proxy (Attempt 2),
# and direct-API (Attempt 3) — and ``providers list`` surfaces the band next
# to each slug so users can see the waterfall shape without reading the code.
_TIER_BY_CATEGORY: dict[str, str] = {
    "site_text": "zero-key",
    "site_meta": "zero-key",
    "social_discovery": "zero-key",
    "signals": "zero-key",
    "smart_proxy": "smart-proxy",
    "reviews": "direct-api",
    "social_counts": "direct-api",
    "mentions": "direct-api",
}


def _provider_config_status(cls: type[ProviderBase]) -> tuple[str, str | None]:
    """Return ``(status, reason)`` for a provider's runtime configuration.

    A provider declares runtime-required env vars via the optional
    ``required_env: ClassVar[tuple[str, ...]]`` attribute. Missing entries
    surface as ``not_configured`` with a human-readable reason; zero-key
    providers with no declared env vars report ``ready``.
    """
    required_env = tuple(getattr(cls, "required_env", ()))
    if not required_env:
        return "ready", None
    missing = [name for name in required_env if not os.environ.get(name, "").strip()]
    if not missing:
        return "ready", None
    return "not_configured", f"missing env: {', '.join(missing)}"


def _provider_row(slug: str, cls: type[ProviderBase]) -> dict[str, str | None]:
    category = str(getattr(cls, "category", "?"))
    status, reason = _provider_config_status(cls)
    return {
        "slug": slug,
        "tier": _TIER_BY_CATEGORY.get(category, "unknown"),
        "category": category,
        "cost_hint": str(getattr(cls, "cost_hint", "?")),
        "status": status,
        "reason": reason,
    }


@providers_app.command("list")
def providers_list(json_out: bool = _PROVIDERS_JSON_OPT) -> None:
    """Show registered providers with waterfall tier, config status, and reason.

    The text table is the human-first shape. ``--json`` emits a JSON array of
    ``{slug, tier, category, cost_hint, status, reason}`` dicts — agents and
    scripts should consume the JSON form.
    """
    registry = discover()
    if json_out:
        payload = [_provider_row(slug, registry[slug]) for slug in sorted(registry)]
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    if not registry:
        typer.echo("(no providers registered)")
        return
    rows = [_provider_row(slug, registry[slug]) for slug in sorted(registry)]
    headers = {
        "slug": "SLUG",
        "tier": "TIER",
        "category": "CATEGORY",
        "cost_hint": "COST",
        "status": "STATUS",
        "reason": "REASON",
    }
    widths = {
        key: max(len(headers[key]), *(len(str(row[key] or "-")) for row in rows)) for key in headers
    }
    typer.echo(
        "  ".join(headers[key].ljust(widths[key]) for key in ("slug", "tier", "category"))
        + "  "
        + "  ".join(headers[key].ljust(widths[key]) for key in ("cost_hint", "status", "reason"))
    )
    for row in rows:
        typer.echo(
            "  ".join(
                str(row[key] or "-").ljust(widths[key])
                for key in ("slug", "tier", "category", "cost_hint", "status", "reason")
            )
        )


if __name__ == "__main__":  # pragma: no cover
    app()
