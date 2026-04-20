"""Pydantic v2 schema for the research-pack JSON contract.

Milestone 1: minimal placeholder so the package imports cleanly. The full
schema (per docs/SPEC.md) is implemented in Milestone 2.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResearchPack(BaseModel):
    """Top-level research-pack envelope. Full schema lands in M2."""

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(..., description="Prospect domain, e.g. example.com")
    fetched_at: datetime = Field(..., description="UTC timestamp of the run.")


__all__ = ["ResearchPack"]
