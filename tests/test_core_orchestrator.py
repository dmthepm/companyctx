"""Orchestrator behavior: status aggregation, graceful-partial, determinism."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Literal, cast

from typer.testing import CliRunner

from companyctx import core
from companyctx.cli import app
from companyctx.providers.base import FetchContext, ProviderBase
from companyctx.providers.site_text_trafilatura import Provider as TrafilaturaProvider
from companyctx.schema import (
    Envelope,
    ProviderRunMetadata,
    SiteSignals,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FIXED_WHEN = datetime(2026, 4, 20, tzinfo=timezone.utc)


def _reg(**mapping: type) -> dict[str, type[ProviderBase]]:
    """Narrow test-provider classes to the ProviderBase Protocol for mypy.

    Every class passed here is runtime-checkable against ``ProviderBase``; the
    cast is just a typing convenience so ``core.run(providers=...)`` accepts
    them without each test growing its own cast boilerplate.
    """
    return cast("dict[str, type[ProviderBase]]", dict(mapping))


class _AlwaysOk:
    slug: ClassVar[str] = "always_ok"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self, site: str, *, ctx: FetchContext
    ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
        return (
            SiteSignals(homepage_text=f"hello {site}"),
            ProviderRunMetadata(status="ok", latency_ms=0, provider_version=self.version),
        )


class _AlwaysFail:
    slug: ClassVar[str] = "always_fail"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self, site: str, *, ctx: FetchContext
    ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
        return None, ProviderRunMetadata(
            status="failed",
            latency_ms=42,
            error="blocked_by_antibot (HTTP 403)",
            provider_version=self.version,
        )


class _Explodes:
    """Provider that raises — the orchestrator must wrap it into a failed row."""

    slug: ClassVar[str] = "explodes"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self, site: str, *, ctx: FetchContext
    ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
        raise RuntimeError("provider internals misbehaved")


def test_orchestrator_status_ok_when_all_providers_ok() -> None:
    env = core.run(
        "example.com",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(always_ok=_AlwaysOk),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "ok"
    assert env.error is None
    assert env.suggestion is None
    assert env.provenance["always_ok"].status == "ok"


def test_orchestrator_status_partial_when_some_fail() -> None:
    env = core.run(
        "example.com",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(always_ok=_AlwaysOk, always_fail=_AlwaysFail),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "partial"
    assert env.error is not None
    assert env.suggestion is not None
    assert env.provenance["always_ok"].status == "ok"
    assert env.provenance["always_fail"].status == "failed"


def test_orchestrator_status_degraded_when_all_fail() -> None:
    env = core.run(
        "example.com",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(always_fail=_AlwaysFail),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    assert env.error is not None
    assert env.suggestion is not None


def test_orchestrator_never_raises_when_provider_explodes() -> None:
    env = core.run(
        "example.com",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(explodes=_Explodes),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    row = env.provenance["explodes"]
    assert row.status == "failed"
    assert row.error is not None
    assert "RuntimeError" in row.error


def test_orchestrator_graceful_partial_on_missing_fixture() -> None:
    """A slug with no fixture dir → provider returns failed; envelope stays well-formed."""
    env = core.run(
        "no-such-site.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    assert env.data.pages is None
    assert env.error is not None
    provider_error = env.provenance["site_text_trafilatura"].error
    assert provider_error is not None
    assert "fixture" in provider_error


def test_mock_mode_populates_pages_homepage_text() -> None:
    env = core.run(
        "acme-bakery.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "ok"
    assert env.data.pages is not None
    assert "Acme Bakery" in env.data.pages.homepage_text
    assert env.data.pages.services == [
        "Custom cakes",
        "Catering",
        "Wholesale bread",
        "Pastry boxes",
    ]
    assert "WordPress" in env.data.pages.tech_stack


def test_mock_mode_is_deterministic_modulo_fetched_at() -> None:
    providers = _reg(site_text_trafilatura=TrafilaturaProvider)
    env1 = core.run(
        "acme-bakery.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=providers,
        fetched_at=FIXED_WHEN,
    ).model_dump(mode="json")
    env2 = core.run(
        "acme-bakery.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=providers,
        fetched_at=FIXED_WHEN,
    ).model_dump(mode="json")
    # fetched_at is pinned in both runs; with that fixed, JSON should match.
    assert env1 == env2


def test_cli_fetch_emits_schema_valid_envelope() -> None:
    runner = CliRunner()
    result = runner.invoke(
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
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    # Round-trip the stdout JSON through the envelope to prove schema validity.
    env = Envelope.model_validate(payload)
    assert env.status == "ok"
    assert env.data.pages is not None
    assert env.data.pages.homepage_text


def test_cli_fetch_graceful_partial_exits_zero() -> None:
    """Missing fixture → envelope still emitted, exit 0 (downstream branches on status)."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            "nonexistent-site.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    env = Envelope.model_validate(payload)
    assert env.status in ("partial", "degraded")
    assert env.error is not None
    assert env.suggestion is not None


def test_cli_validate_accepts_round_tripped_envelope(tmp_path: Path) -> None:
    env = core.run(
        "acme-bakery.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    path = tmp_path / "env.json"
    path.write_text(env.model_dump_json(indent=2), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0, result.stdout


def test_cli_validate_rejects_extra_field(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "status": "ok",
                "data": {"site": "x", "fetched_at": FIXED_WHEN.isoformat(), "bogus": 1},
                "provenance": {},
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 1


def test_cli_providers_list_shows_registered_provider() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0, result.stdout
    assert "site_text_trafilatura" in result.stdout
