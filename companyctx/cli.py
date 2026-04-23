"""Typer CLI surface for companyctx.

Exposes the public contract described in ``docs/SPEC.md``:

- ``fetch <site>`` — run the Deterministic Waterfall and emit one envelope.
- ``schema`` — print the envelope's JSON Schema (Draft 2020-12) to stdout.
- ``validate <path>`` — round-trip a JSON envelope through the schema.
- ``providers list`` — show registered providers with status + cost hint.
- ``cache list`` / ``cache clear`` — Vertical Memory plumbing (COX-6 / #9).
- ``batch <csv>`` — batch mode stub (still gated on the batch slice).

Several flags and subcommands are still stubs. They fail loudly rather
than silently accepting input and doing nothing — see issue #68 for the
honesty pass.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import typer
from pydantic import ValidationError

from companyctx import __version__, core
from companyctx.cache import (
    CACHE_DB_FILENAME,
    CacheEntry,
    FetchCache,
    parse_age,
)
from companyctx.config import default_cache_dir
from companyctx.providers import discover
from companyctx.providers.base import ProviderBase
from companyctx.schema import SCHEMA_VERSION, Envelope

app = typer.Typer(
    name="companyctx",
    help="Deterministic B2B company context router. Zero keys. Schema-locked JSON.",
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
# `batch` and the TOML `--config` loader still defer to the M3+ slice; the
# cache itself shipped in COX-6 / #9.
_BATCH_ISSUE = 9
_CONFIG_ISSUE = 9


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"companyctx {__version__}")
        raise typer.Exit()


def _reject_config_flag(value: Path | None) -> Path | None:
    """Reject ``--config <path>`` until the TOML loader lands."""
    if value is not None:
        raise typer.BadParameter(
            "--config is not implemented yet — "
            f"see https://github.com/dmthepm/companyctx/issues/{_CONFIG_ISSUE}"
        )
    return value


def _fail_stub(command: str, issue: int) -> None:
    """Print a loud stderr message and exit non-zero for a not-yet-wired command."""
    typer.secho(
        f"{command} is not implemented yet — "
        f"see https://github.com/dmthepm/companyctx/issues/{issue}",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=2)


def _open_cache() -> FetchCache:
    """Open the user's XDG-resolved fetch cache (creating dirs as needed)."""
    return FetchCache(default_cache_dir() / CACHE_DB_FILENAME)


def _try_open_cache(verbose: bool) -> FetchCache | None:
    """Open the cache, returning ``None`` (with a stderr warn) on failure.

    Cache outages — read-only home dir, locked DB, migration regression —
    must never crash a normal ``fetch``. The orchestrator runs without a
    cache when this returns ``None``; the ``--from-cache`` path handles
    its own hard-fail separately so the user gets a structured envelope
    instead of a Python traceback.
    """
    try:
        return _open_cache()
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        if verbose:
            typer.secho(
                f"warning: cache unavailable, continuing without: {exc.__class__.__name__}: {exc}",
                fg=typer.colors.YELLOW,
                err=True,
            )
        return None


def _cache_corrupted_envelope(site: str, *, message: str, when: datetime | None = None) -> Envelope:
    """Build a structured ``cache_corrupted`` envelope for the ``--from-cache`` path.

    Used when the cache opens but the cached row can't be deserialized
    (Pydantic ValidationError, JSON parse error, sqlite read error). The
    envelope carries an actionable suggestion pointing at
    ``cache clear --site``; the CLI exits non-zero so pipelines can still
    branch on the exit code, but they get a parseable envelope on stdout
    rather than a smear of Python tracebacks on stderr.
    """
    from companyctx.schema import CompanyContext, EnvelopeError

    return Envelope(
        schema_version=SCHEMA_VERSION,
        status="degraded",
        data=CompanyContext(
            site=site,
            fetched_at=when or datetime.now(timezone.utc),
        ),
        provenance={},
        error=EnvelopeError(
            code="cache_corrupted",
            message=message,
            suggestion=(f"run `companyctx cache clear --site {site}` to evict the stale entry"),
        ),
    )


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
        "--markdown is experimental and not implemented — "
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
    help="Bypass the cache read path; the fresh result is still written back.",
)
_CONFIG_OPT = typer.Option(
    None,
    "--config",
    help="TOML config path. (Not implemented yet — see issue #9.)",
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
    help="Ignore the cached read; force-write a fresh row (audit trail; old rows kept).",
)
_FROM_CACHE_OPT = typer.Option(
    False,
    "--from-cache",
    help=(
        "Return only the cached payload; never hit the network. "
        "Exits non-zero on miss / corrupted row (with a structured "
        "cache_corrupted envelope on stdout). Note: cache keys hash "
        "installed providers, not env-config — use --refresh after "
        "changing provider env vars to evict stale partials."
    ),
)
_CSV_ARG = typer.Argument(..., help="CSV of sites.")
_JSON_ARG = typer.Argument(..., help="Path to a companyctx JSON.")
_CACHE_SITE_OPT = typer.Option(None, "--site", help="Limit to one site.")
_CACHE_OLDER_OPT = typer.Option(None, "--older-than", help="Drop entries older than e.g. 7d.")
_CACHE_LIST_JSON_OPT = typer.Option(
    False,
    "--json",
    help="Emit the cache index as a JSON array (one dict per host).",
)


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
            "--markdown is not implemented; rerun with --json.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if from_cache and (refresh or no_cache):
        raise typer.BadParameter("--from-cache cannot be combined with --refresh or --no-cache")

    if from_cache:
        envelope, exit_code = _run_from_cache_only(site)
    else:
        cache = _try_open_cache(verbose=verbose)
        try:
            envelope = core.run(
                site,
                mock=mock,
                fixtures_dir=fixtures_dir if mock else None,
                ignore_robots=ignore_robots,
                cache=cache,
                read_cache=not (refresh or no_cache),
                write_cache=True,
            )
        finally:
            if cache is not None:
                cache.close()
        exit_code = 0

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

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


def _run_from_cache_only(site: str) -> tuple[Envelope, int]:
    """Read-only ``--from-cache`` path. Never raises at the boundary.

    Three outcomes, all surfaced as ``(envelope, exit_code)`` so the caller
    can emit the JSON envelope on stdout uniformly:

    - Hit: ``(cached_envelope, 0)``.
    - Miss: ``(degraded envelope with no_provider_succeeded, 2)`` —
      the user explicitly opted into cache-only and there's nothing to
      return.
    - Cache open failure or corrupted row: ``(degraded envelope with
      cache_corrupted, 2)`` — agents branch on ``error.code``, humans
      read ``error.message``.

    Exit code stays non-zero so existing pipelines that branch on the
    shell return code keep working; the new structured envelope is
    additive.
    """
    from companyctx.schema import CompanyContext, EnvelopeError

    cache: FetchCache | None = None
    try:
        cache = _open_cache()
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        return _cache_corrupted_envelope(
            site,
            message=f"cache open failed: {exc.__class__.__name__}: {exc}",
        ), 2

    try:
        try:
            envelope = cache.get_envelope(site, registry=discover())
        except Exception as exc:  # noqa: BLE001 - deliberate boundary
            return _cache_corrupted_envelope(
                site,
                message=f"cached row could not be deserialized: {exc.__class__.__name__}: {exc}",
            ), 2
    finally:
        cache.close()

    if envelope is not None:
        return envelope, 0

    miss = Envelope(
        schema_version=SCHEMA_VERSION,
        status="degraded",
        data=CompanyContext(site=site, fetched_at=datetime.now(timezone.utc)),
        provenance={},
        error=EnvelopeError(
            code="no_provider_succeeded",
            message=f"cache miss for {site}; --from-cache will not fall through to the network",
            suggestion=(
                "rerun without --from-cache, or prime the cache with `companyctx fetch <site>`"
            ),
        ),
    )
    return miss, 2


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
    """Run fetch over a CSV of sites. (Stub — see issue #9.)"""
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


def _cache_entry_row(entry: CacheEntry) -> dict[str, str]:
    return {
        "normalized_host": entry.normalized_host,
        "site": entry.site,
        "status": entry.status,
        "schema_version": entry.schema_version,
        "fetched_at": entry.fetched_at.isoformat(),
        "expires_at": entry.expires_at.isoformat(),
        "run_id": entry.run_id,
    }


def _open_cache_for_subcommand(subcommand: str) -> FetchCache:
    """Open the cache for a ``cache`` subcommand, exiting cleanly on failure.

    The ``cache list`` / ``cache clear`` subcommands have no degraded
    fallback — they exist to manage the cache itself, so an open
    failure is terminal. Print a one-line stderr message and exit 2
    rather than letting OSError / sqlite3.OperationalError bubble up
    as a Python traceback.
    """
    try:
        return _open_cache()
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        typer.secho(
            f"cache {subcommand} failed: cache unavailable — {exc.__class__.__name__}: {exc}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2) from exc


@cache_app.command("list")
def cache_list(json_out: bool = _CACHE_LIST_JSON_OPT) -> None:
    """List cached envelopes — one row per host (the latest run)."""
    with closing(_open_cache_for_subcommand("list")) as cache:
        entries = cache.list_entries()
    if json_out:
        sys.stdout.write(
            json.dumps([_cache_entry_row(e) for e in entries], indent=2, sort_keys=True) + "\n"
        )
        return
    if not entries:
        typer.echo("(empty cache)")
        return
    headers = ("HOST", "STATUS", "FETCHED_AT", "EXPIRES_AT")
    rows = [
        (e.normalized_host, e.status, e.fetched_at.isoformat(), e.expires_at.isoformat())
        for e in entries
    ]
    widths = [max(len(headers[i]), *(len(r[i]) for r in rows)) for i in range(len(headers))]
    typer.echo("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    for row in rows:
        typer.echo("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))


@cache_app.command("clear")
def cache_clear(
    site: str | None = _CACHE_SITE_OPT,
    older_than: str | None = _CACHE_OLDER_OPT,
) -> None:
    """Prune the cache. Requires at least one filter (``--site`` or ``--older-than``)."""
    if site is None and older_than is None:
        raise typer.BadParameter(
            "cache clear requires at least one filter — pass --site or --older-than. "
            "Wiping the whole cache is intentional friction; delete the DB file directly."
        )
    age = None
    if older_than is not None:
        try:
            age = parse_age(older_than)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    with closing(_open_cache_for_subcommand("clear")) as cache:
        removed = cache.clear(site=site, older_than=age)
    typer.echo(f"removed {removed} cached run(s)")


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
