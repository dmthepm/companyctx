"""Provider plugin discovery via Python entry points.

Day-one providers register under the ``research_pack.providers`` entry-point
group in pyproject.toml; entries are commented out at M1 and uncommented as
each provider lands in M3.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from research_pack.providers.base import ProviderBase

ENTRY_POINT_GROUP = "research_pack.providers"


def discover() -> dict[str, type[ProviderBase]]:
    """Return registered providers keyed by their entry-point slug.

    M1 returns an empty dict because no providers are yet registered;
    `providers list` will show the empty surface until M3.
    """
    found: dict[str, type[ProviderBase]] = {}
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        found[ep.name] = ep.load()
    return found


__all__ = ["ENTRY_POINT_GROUP", "discover"]
