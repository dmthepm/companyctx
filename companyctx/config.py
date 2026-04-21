"""Settings + XDG-compliant paths.

Milestone 1: skeleton only. TOML + env loader and per-provider settings land
in Milestone 4.
"""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "companyctx"


def default_config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))


def default_cache_dir() -> Path:
    return Path(user_cache_dir(APP_NAME))


class Settings(BaseSettings):
    """Global runtime settings.

    `--ignore-robots` is intentionally omitted: per spec, it must be a CLI-only
    flag and never settable via TOML or env.
    """

    model_config = SettingsConfigDict(
        env_prefix="COMPANYCTX_",
        extra="ignore",
    )

    cache_enabled: bool = False
    cache_dir: Path = default_cache_dir()
    config_dir: Path = default_config_dir()
    verbose: bool = False


__all__ = ["APP_NAME", "Settings", "default_cache_dir", "default_config_dir"]
