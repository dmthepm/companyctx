"""Pytest fixtures shared across the suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to the repo's fixtures/ directory."""
    return Path(__file__).resolve().parent.parent / "fixtures"
