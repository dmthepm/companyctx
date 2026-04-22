"""Public-API surface tests — the re-export contract.

Downstream ``pipx install companyctx`` users write ``from companyctx import
Envelope`` and expect mypy to see concrete Pydantic types, not ``Any``. This
module pins that contract. See issue #56 and docs/OSS-HYGIENE.md §1.
"""

from __future__ import annotations

import importlib.resources

import companyctx


def test_top_level_reexports_are_importable() -> None:
    from companyctx import (
        SCHEMA_VERSION,
        CompanyContext,
        Envelope,
        EnvelopeError,
        EnvelopeErrorCode,  # noqa: F401 — typing Literal, importability is the test
        EnvelopeStatus,  # noqa: F401 — typing Literal, importability is the test
        FundingRound,
        HeuristicSignals,
        MediaMention,
        MentionKind,  # noqa: F401 — typing Literal, importability is the test
        MentionsSignals,
        ProviderRunMetadata,
        ProviderStatus,  # noqa: F401 — typing Literal, importability is the test
        ReviewsSignals,
        SiteSignals,
        SocialSignals,
    )

    assert SCHEMA_VERSION == "0.2.0"
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


def test_package_version_is_020() -> None:
    assert companyctx.__version__ == "0.2.0"


def test_py_typed_marker_ships_with_package() -> None:
    """PEP 561 marker must exist at ``companyctx/py.typed`` for downstream mypy."""
    root = importlib.resources.files("companyctx")
    marker = root.joinpath("py.typed")
    assert marker.is_file(), "py.typed marker missing — downstream mypy sees Any"
