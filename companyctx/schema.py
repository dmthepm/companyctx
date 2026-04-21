"""Pydantic v2 schema for the companyctx JSON contract.

Milestone 1: minimal placeholder so the package imports cleanly. The full
schema (per docs/SPEC.md) is implemented in Milestone 2.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyContext(BaseModel):
    """Top-level envelope. Full schema lands in M2."""

    model_config = ConfigDict(extra="forbid")

    site: str = Field(..., description="Prospect site, e.g. example.com or https://example.com")
    fetched_at: datetime = Field(..., description="UTC timestamp of the run.")


__all__ = ["CompanyContext"]
