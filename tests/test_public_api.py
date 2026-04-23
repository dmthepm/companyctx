"""Public-API surface tests — the re-export contract.

Downstream ``pipx install companyctx`` users write ``from companyctx import
Envelope`` and expect mypy to see concrete Pydantic types, not ``Any``. This
module pins that contract. See issue #56 and docs/OSS-HYGIENE.md §1.
"""

from __future__ import annotations

import importlib.resources
from typing import get_args

from companyctx import (
    SCHEMA_VERSION,
    CompanyContext,
    Envelope,
    EnvelopeError,
    EnvelopeErrorCode,
    EnvelopeStatus,
    FundingRound,
    HeuristicSignals,
    MediaMention,
    MentionKind,
    MentionsSignals,
    ProviderRunMetadata,
    ProviderStatus,
    ReviewsSignals,
    SiteSignals,
    SocialSignals,
    __version__,
)


def test_top_level_reexports_are_importable() -> None:
    assert SCHEMA_VERSION == "0.3.0"
    assert Envelope.__name__ == "Envelope"
    assert EnvelopeError.__name__ == "EnvelopeError"
    for cls in (
        CompanyContext,
        FundingRound,
        HeuristicSignals,
        MediaMention,
        MentionsSignals,
        ProviderRunMetadata,
        ReviewsSignals,
        SiteSignals,
        SocialSignals,
    ):
        assert hasattr(cls, "model_fields"), cls.__name__


def test_top_level_literal_aliases_expose_expected_members() -> None:
    """Lock the Literal alias membership so downstream consumers can branch on it."""
    assert "ok" in get_args(EnvelopeStatus)
    assert "partial" in get_args(EnvelopeStatus)
    assert "degraded" in get_args(EnvelopeStatus)
    assert "ok" in get_args(ProviderStatus)
    assert "not_configured" in get_args(ProviderStatus)
    assert "press" in get_args(MentionKind)
    assert "award" in get_args(MentionKind)
    # Every v0.3 error code must stay re-exported. ``empty_response`` is
    # the v0.3 addition — COX-44 / #79.
    for code in (
        "ssrf_rejected",
        "network_timeout",
        "blocked_by_antibot",
        "path_traversal_rejected",
        "response_too_large",
        "no_provider_succeeded",
        "misconfigured_provider",
        "empty_response",
    ):
        assert code in get_args(EnvelopeErrorCode), code


def test_package_version_is_current() -> None:
    """Pinned to current release — bump in the version-bump PR."""
    assert __version__ == "0.3.1"


def test_py_typed_marker_ships_with_package() -> None:
    """PEP 561 marker must exist at ``companyctx/py.typed`` for downstream mypy."""
    root = importlib.resources.files("companyctx")
    marker = root.joinpath("py.typed")
    assert marker.is_file(), "py.typed marker missing — downstream mypy sees Any"
