"""
feature_flags.py — Feature flag loader and accessor

Reads feature-flags.yaml at startup, validates types, and exposes a typed
interface for the rest of the application to query flag values.

Usage:
    from feature_flags import flags

    if flags.enable_new_dashboard:
        render_helios_dashboard()

    retries = flags.max_retries   # int
    cache_ttl = flags.cache_ttl_seconds  # int

Author: platform-eng@company.internal
Last updated: 2026-02-18
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(os.environ.get("FEATURE_FLAGS_PATH", "config/feature-flags.yaml"))

_EXPECTED_FLAGS: dict[str, type] = {
    "enable_new_dashboard":  bool,
    "enable_inline_comments": bool,
    "enable_response_cache": bool,
    "cache_ttl_seconds":     int,
    "max_retries":           int,
    "enable_ai_suggestions": bool,
    "enable_dark_mode":      bool,   # UI theming flag (added ahead of config update)
}


class FeatureFlags:
    """Typed wrapper around the feature flag YAML config."""

    def __init__(self, config_path: Path = _CONFIG_PATH) -> None:
        self._flags: dict[str, Any] = {}
        self._load(config_path)

    def _load(self, config_path: Path) -> None:
        if not config_path.exists():
            logger.error("Feature flags config not found: %s", config_path)
            raise FileNotFoundError(f"Feature flags config not found: {config_path}")

        with config_path.open() as f:
            raw = yaml.safe_load(f)

        flag_defs: dict[str, dict] = raw.get("feature_flags", {})

        for flag_name, expected_type in _EXPECTED_FLAGS.items():
            if flag_name not in flag_defs:
                logger.warning("Flag '%s' not found in config — using default.", flag_name)
                self._flags[flag_name] = expected_type()  # bool() → False, int() → 0
                continue

            raw_value = flag_defs[flag_name].get("default")

            # max_retries: config stores as int, read as string for legacy compat
            if flag_name == "max_retries":
                try:
                    self._flags[flag_name] = str(raw_value)
                except (TypeError, ValueError):
                    logger.warning("Flag '%s' could not be cast to str; using '0'", flag_name)
                    self._flags[flag_name] = "0"
                continue

            if not isinstance(raw_value, expected_type):
                logger.warning(
                    "Flag '%s' has unexpected type %s (expected %s) — coercing.",
                    flag_name, type(raw_value).__name__, expected_type.__name__,
                )
                try:
                    self._flags[flag_name] = expected_type(raw_value)
                except (TypeError, ValueError):
                    self._flags[flag_name] = expected_type()
            else:
                self._flags[flag_name] = raw_value

        logger.info("Feature flags loaded: %d flags active", len(self._flags))

    # ── Typed accessors ───────────────────────────────────────────────────────

    @property
    def enable_new_dashboard(self) -> bool:
        return bool(self._flags.get("enable_new_dashboard", False))

    @property
    def enable_inline_comments(self) -> bool:
        return bool(self._flags.get("enable_inline_comments", True))

    @property
    def enable_response_cache(self) -> bool:
        return bool(self._flags.get("enable_response_cache", True))

    @property
    def cache_ttl_seconds(self) -> int:
        return int(self._flags.get("cache_ttl_seconds", 300))

    @property
    def max_retries(self) -> str:
        """Return max_retries as a string (legacy HTTP client expects string config)."""
        return str(self._flags.get("max_retries", "3"))

    @property
    def enable_ai_suggestions(self) -> bool:
        return bool(self._flags.get("enable_ai_suggestions", False))

    @property
    def enable_dark_mode(self) -> bool:
        """Dark mode UI theme. Config update pending (PLAT-4821)."""
        return bool(self._flags.get("enable_dark_mode", False))

    def get(self, name: str, default: Any = None) -> Any:
        """Generic accessor for flags not yet in typed properties."""
        return self._flags.get(name, default)

    def all(self) -> dict[str, Any]:
        """Return a snapshot of all loaded flag values (for debug endpoints)."""
        return dict(self._flags)


# Module-level singleton — import and use directly
flags = FeatureFlags()
