"""Tests for the ``reviews_google_places`` direct-API provider (COX-5).

Covers the COX-5 acceptance:

- No key → ``not_configured`` with actionable suggestion.
- Bad key (HTTP 401/403) → ``failed`` with ``blocked_by_antibot``-classified error.
- Site with no Places result (``ZERO_RESULTS``) → ``failed`` with structured error.
- Multiple candidates → the picker takes Google's first Text Search
  result (legacy Text Search doesn't return ``website`` so domain
  matching isn't an option without an extra Details billing hit).
- ``REQUEST_DENIED`` / ``OVER_QUERY_LIMIT`` → ``failed`` with classifiable errors.
- Fixture parity with the zero-key-only run: the envelope's ``data.reviews``
  slot populates deterministically when the Places provider is registered.
- Happy-path network call charges the published Text Search + Place Details
  rate in integer US cents via ``ProviderRunMetadata.cost_incurred``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest
from curl_cffi import requests

from companyctx import core
from companyctx.http import DEFAULT_TIMEOUT_S, DEFAULT_USER_AGENT
from companyctx.providers.base import FetchContext, ProviderBase
from companyctx.providers.reviews_google_places import (
    _DETAILS_BASIC_ATMOSPHERE_TENTHS,
    _TEXT_SEARCH_TENTHS,
    ENV_KEY,
    NOT_CONFIGURED_SUGGESTION,
    SOURCE_SLUG,
    Provider,
    _cost_cents,
)
from companyctx.providers.site_text_trafilatura import Provider as TrafilaturaProvider

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FIXED_WHEN = datetime(2026, 4, 22, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeResponse:
    """``curl_cffi.requests.Response`` stand-in for the synchronous get()."""

    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.text = json.dumps(payload or {})

    def close(self) -> None:
        return None


def _ctx(*, mock: bool = False, fixtures_dir: str | None = None) -> FetchContext:
    return FetchContext(
        user_agent=DEFAULT_USER_AGENT,
        timeout_s=DEFAULT_TIMEOUT_S,
        mock=mock,
        fixtures_dir=fixtures_dir,
    )


def _fake_get_factory(
    responses: dict[str, _FakeResponse],
) -> Any:
    """Dispatch ``requests.get(url, ...)`` to the mapped ``_FakeResponse``.

    The URL returned by the provider includes the query string, so we match
    on the path prefix (``/textsearch/`` vs ``/details/``) rather than the
    full URL — that keeps the test fixtures decoupled from the exact
    param-encoding order.
    """

    def _get(url: str, *_args: object, **_kwargs: object) -> _FakeResponse:
        if "/textsearch/" in url:
            return responses["textsearch"]
        if "/details/" in url:
            return responses["details"]
        raise AssertionError(f"unexpected places URL: {url}")

    return _get


# ---------------------------------------------------------------------------
# Provider contract
# ---------------------------------------------------------------------------


def test_slug_category_cost_hint() -> None:
    assert Provider.slug == SOURCE_SLUG == "reviews_google_places"
    assert Provider.category == "reviews"
    assert Provider.cost_hint == "per-1k"
    assert ENV_KEY in Provider.required_env


def test_no_key_returns_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_KEY, raising=False)
    signals, meta = Provider().fetch("acme-bakery.example", ctx=_ctx())
    assert signals is None
    assert meta.status == "not_configured"
    assert meta.error is not None
    assert ENV_KEY in meta.error
    assert NOT_CONFIGURED_SUGGESTION in meta.error
    assert meta.cost_incurred == 0


def test_empty_string_key_is_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, "   ")
    _, meta = Provider().fetch("acme-bakery.example", ctx=_ctx())
    assert meta.status == "not_configured"


# ---------------------------------------------------------------------------
# Happy path + candidate picker
# ---------------------------------------------------------------------------


def test_happy_path_populates_reviews_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, "test-key")
    responses = {
        "textsearch": _FakeResponse(
            200,
            {
                "status": "OK",
                "results": [{"place_id": "pid-correct", "name": "Acme Bakery"}],
            },
        ),
        "details": _FakeResponse(
            200,
            {
                "status": "OK",
                "result": {
                    "place_id": "pid-correct",
                    "rating": 4.4,
                    "user_ratings_total": 128,
                },
            },
        ),
    }
    monkeypatch.setattr(
        "companyctx.providers.reviews_google_places.requests.get",
        _fake_get_factory(responses),
    )
    signals, meta = Provider().fetch("acme-bakery.example", ctx=_ctx())

    assert meta.status == "ok"
    assert meta.error is None
    # Happy path = Text Search Basic + Details Basic+Atmosphere,
    # ceil-summed to integer cents.
    assert meta.cost_incurred == _cost_cents(_TEXT_SEARCH_TENTHS, _DETAILS_BASIC_ATMOSPHERE_TENTHS)
    assert signals is not None
    assert signals.count == 128
    assert signals.rating == pytest.approx(4.4)
    assert signals.source == SOURCE_SLUG


def test_picker_takes_first_text_search_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy Text Search doesn't return ``website``; we take Google's prominence-
    ordered first result and the Place Details call must carry THAT ``place_id``.

    An earlier draft picked by matching a fabricated ``website`` field on
    Text Search results, but that field isn't returned by the legacy API
    per Google's "Place Data Fields (Legacy)" docs. This regression
    keeps the picker honest: first result wins, period.
    """
    monkeypatch.setenv(ENV_KEY, "test-key")
    captured: list[str] = []

    def _capture(url: str, *_args: object, **_kwargs: object) -> _FakeResponse:
        captured.append(url)
        if "/textsearch/" in url:
            return _FakeResponse(
                200,
                {
                    "status": "OK",
                    "results": [
                        {"place_id": "pid-first", "name": "First"},
                        {"place_id": "pid-second", "name": "Second"},
                        {"place_id": "pid-third", "name": "Third"},
                    ],
                },
            )
        return _FakeResponse(
            200,
            {
                "status": "OK",
                "result": {
                    "place_id": "pid-first",
                    "rating": 4.8,
                    "user_ratings_total": 42,
                },
            },
        )

    monkeypatch.setattr("companyctx.providers.reviews_google_places.requests.get", _capture)

    signals, meta = Provider().fetch("acme-bakery.example", ctx=_ctx())
    assert meta.status == "ok"
    assert signals is not None
    assert signals.count == 42
    details_url = next(u for u in captured if "/details/" in u)
    assert "place_id=pid-first" in details_url


def test_details_request_does_not_ask_for_website_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requesting ``website`` would pull in the Contact billing bundle for
    no benefit (we don't use it). The Details URL's ``fields`` param must
    stay at ``place_id,rating,user_ratings_total``.
    """
    monkeypatch.setenv(ENV_KEY, "test-key")
    captured: list[str] = []

    def _capture(url: str, *_args: object, **_kwargs: object) -> _FakeResponse:
        captured.append(url)
        if "/textsearch/" in url:
            return _FakeResponse(
                200, {"status": "OK", "results": [{"place_id": "pid", "name": "x"}]}
            )
        return _FakeResponse(
            200,
            {"status": "OK", "result": {"place_id": "pid", "rating": 4.0, "user_ratings_total": 1}},
        )

    monkeypatch.setattr("companyctx.providers.reviews_google_places.requests.get", _capture)
    Provider().fetch("acme-bakery.example", ctx=_ctx())
    details_url = next(u for u in captured if "/details/" in u)
    assert "website" not in details_url


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [401, 403])
def test_bad_key_maps_to_failed_with_antibot_prefix(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    monkeypatch.setenv(ENV_KEY, "invalid-key")
    monkeypatch.setattr(
        "companyctx.providers.reviews_google_places.requests.get",
        lambda *args, **kwargs: _FakeResponse(status_code=status_code),
    )
    signals, meta = Provider().fetch("acme-bakery.example", ctx=_ctx())
    assert signals is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "blocked_by_antibot" in meta.error
    assert str(status_code) in meta.error
    # Text-Search leg still bills.
    assert meta.cost_incurred == _cost_cents(_TEXT_SEARCH_TENTHS)


def test_zero_results_maps_to_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, "test-key")
    monkeypatch.setattr(
        "companyctx.providers.reviews_google_places.requests.get",
        lambda *args, **kwargs: _FakeResponse(200, {"status": "ZERO_RESULTS", "results": []}),
    )
    signals, meta = Provider().fetch("ghost-biz.example", ctx=_ctx())
    assert signals is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "no places result" in meta.error
    assert meta.cost_incurred == _cost_cents(_TEXT_SEARCH_TENTHS)


def test_request_denied_maps_to_failed_with_antibot_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_KEY, "test-key")
    monkeypatch.setattr(
        "companyctx.providers.reviews_google_places.requests.get",
        lambda *args, **kwargs: _FakeResponse(
            200,
            {"status": "REQUEST_DENIED", "error_message": "API key not valid"},
        ),
    )
    signals, meta = Provider().fetch("acme-bakery.example", ctx=_ctx())
    assert signals is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "blocked_by_antibot" in meta.error
    assert "REQUEST_DENIED" in meta.error


def test_over_query_limit_maps_to_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, "test-key")
    monkeypatch.setattr(
        "companyctx.providers.reviews_google_places.requests.get",
        lambda *args, **kwargs: _FakeResponse(
            200, {"status": "OVER_QUERY_LIMIT", "error_message": "daily quota"}
        ),
    )
    signals, meta = Provider().fetch("acme-bakery.example", ctx=_ctx())
    assert meta.status == "failed"
    assert meta.error is not None
    assert "blocked_by_antibot" in meta.error
    assert "OVER_QUERY_LIMIT" in meta.error


def test_network_raise_maps_to_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, "test-key")

    def _boom(*_args: object, **_kwargs: object) -> _FakeResponse:
        raise requests.RequestsError("connection reset")

    monkeypatch.setattr("companyctx.providers.reviews_google_places.requests.get", _boom)
    signals, meta = Provider().fetch("acme-bakery.example", ctx=_ctx())
    assert signals is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "network error" in meta.error


def test_api_key_is_redacted_from_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key in the error message would leak into provenance logs — it must not."""
    monkeypatch.setenv(ENV_KEY, "SECRET-ABC-123")

    def _boom(url: str, *_args: object, **_kwargs: object) -> _FakeResponse:
        # Even though we don't inject the key into the exception, make sure
        # the redactor runs unconditionally so future code paths can't leak.
        assert "SECRET-ABC-123" in url
        raise requests.RequestsError("boom SECRET-ABC-123 bad")

    monkeypatch.setattr("companyctx.providers.reviews_google_places.requests.get", _boom)
    _, meta = Provider().fetch("acme-bakery.example", ctx=_ctx())
    assert meta.error is not None
    assert "SECRET-ABC-123" not in meta.error


def test_invalid_site_maps_to_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, "test-key")

    def _boom(*_args: object, **_kwargs: object) -> _FakeResponse:
        raise AssertionError("invalid site must not hit the network")

    monkeypatch.setattr("companyctx.providers.reviews_google_places.requests.get", _boom)
    signals, meta = Provider().fetch("", ctx=_ctx())
    assert signals is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "invalid site" in meta.error


def test_details_missing_user_ratings_total_maps_to_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_KEY, "test-key")
    responses = {
        "textsearch": _FakeResponse(
            200,
            {"status": "OK", "results": [{"place_id": "pid-x", "name": "x"}]},
        ),
        # Place exists in Google Maps but has never been rated; omit the
        # aggregate fields entirely (real observed Places API behavior).
        "details": _FakeResponse(200, {"status": "OK", "result": {"place_id": "pid-x"}}),
    }
    monkeypatch.setattr(
        "companyctx.providers.reviews_google_places.requests.get",
        _fake_get_factory(responses),
    )
    signals, meta = Provider().fetch("acme-bakery.example", ctx=_ctx())
    assert signals is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "user_ratings_total" in meta.error


# ---------------------------------------------------------------------------
# --mock fixture path (deterministic)
# ---------------------------------------------------------------------------


def test_mock_reads_existing_details_only_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The existing ``fixtures/acme-bakery/google_places.json`` is Details-only."""
    monkeypatch.setenv(ENV_KEY, "test-key")
    signals, meta = Provider().fetch(
        "acme-bakery.example",
        ctx=_ctx(mock=True, fixtures_dir=str(FIXTURES_DIR)),
    )
    assert meta.status == "ok"
    assert meta.cost_incurred == 0  # mock mode never bills
    assert meta.latency_ms == 0
    assert signals is not None
    assert signals.count == 40
    assert signals.rating == pytest.approx(4.0)
    assert signals.source == SOURCE_SLUG


def test_mock_missing_fixture_returns_failed(tmp_path: Path) -> None:
    import os

    os.environ["GOOGLE_PLACES_API_KEY"] = "test-key"
    try:
        signals, meta = Provider().fetch(
            "ghost.example",
            ctx=_ctx(mock=True, fixtures_dir=str(tmp_path)),
        )
        assert signals is None
        assert meta.status == "failed"
        assert meta.error is not None
        assert "fixture not found" in meta.error
    finally:
        os.environ.pop("GOOGLE_PLACES_API_KEY", None)


def test_mock_full_fixture_shape_works(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    slug = "acmemulti"
    site_dir = tmp_path / slug
    site_dir.mkdir()
    (site_dir / "google_places.json").write_text(
        json.dumps(
            {
                "text_search": {
                    "status": "OK",
                    "results": [
                        {"place_id": "pid-right", "name": "right"},
                        {"place_id": "pid-wrong", "name": "wrong"},
                    ],
                },
                "details": {
                    "status": "OK",
                    "result": {
                        "place_id": "pid-right",
                        "rating": 5.0,
                        "user_ratings_total": 314,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv(ENV_KEY, "test-key")
    signals, meta = Provider().fetch(
        f"{slug}.example",
        ctx=_ctx(mock=True, fixtures_dir=str(tmp_path)),
    )
    assert meta.status == "ok"
    assert signals is not None
    assert signals.count == 314
    assert signals.rating == pytest.approx(5.0)


def test_mock_bad_fixture_slug_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_KEY, "test-key")
    signals, meta = Provider().fetch(
        "../evil",
        ctx=_ctx(mock=True, fixtures_dir=str(tmp_path)),
    )
    assert signals is None
    assert meta.status == "failed"
    assert meta.error is not None


# ---------------------------------------------------------------------------
# Orchestrator integration — the "fixture comparison" acceptance check
# ---------------------------------------------------------------------------


def test_envelope_comparison_zero_key_only_vs_with_places(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registering the Places provider populates ``data.reviews`` deterministically.

    Zero-key-only run leaves ``data.reviews = null``. With the Places
    provider registered and a key present, ``data.reviews`` fills with
    ``{count, rating, source="reviews_google_places"}``.
    """
    monkeypatch.setenv(ENV_KEY, "test-key")

    # Zero-key only — no reviews signal.
    env_zero_only = core.run(
        "acme-bakery.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=cast(
            "dict[str, type[ProviderBase]]",
            {"site_text_trafilatura": TrafilaturaProvider},
        ),
        fetched_at=FIXED_WHEN,
    )
    assert env_zero_only.status == "ok"
    assert env_zero_only.data.reviews is None

    # Zero-key + Places — reviews slot fills from the fixture.
    env_with_places = core.run(
        "acme-bakery.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=cast(
            "dict[str, type[ProviderBase]]",
            {
                "site_text_trafilatura": TrafilaturaProvider,
                "reviews_google_places": Provider,
            },
        ),
        fetched_at=FIXED_WHEN,
    )
    assert env_with_places.status == "ok"
    assert env_with_places.data.reviews is not None
    assert env_with_places.data.reviews.count == 40
    assert env_with_places.data.reviews.rating == pytest.approx(4.0)
    assert env_with_places.data.reviews.source == SOURCE_SLUG


def test_places_unconfigured_does_not_downgrade_zero_key_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ``GOOGLE_PLACES_API_KEY`` must NOT flip a successful zero-key
    run to ``partial``. The orchestrator skips invocation of a primary
    provider whose ``required_env`` is unmet — no provenance row, no
    envelope-status downgrade. Mirrors the README's "Zero keys on the
    default path" promise.
    """
    monkeypatch.delenv(ENV_KEY, raising=False)
    env = core.run(
        "acme-bakery.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=cast(
            "dict[str, type[ProviderBase]]",
            {
                "site_text_trafilatura": TrafilaturaProvider,
                "reviews_google_places": Provider,
            },
        ),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "ok"
    assert env.error is None
    assert "reviews_google_places" not in env.provenance
    assert env.provenance["site_text_trafilatura"].status == "ok"
    assert env.data.reviews is None
