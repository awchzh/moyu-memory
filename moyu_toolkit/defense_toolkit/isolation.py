#!/usr/bin/env python3
"""
isolation.py — MOYU User Isolation Module

Optional layer: when enabled in config.yaml, each user gets their own
storage directory (memory_data/{user_id}/) instead of a shared pool.

Usage:
    from defense_toolkit.isolation import get_storage_path, set_user, get_user

    path = get_storage_path("memory_data")  # -> "memory_data/" or "memory_data/alice/"
"""

import os
import yaml
from pathlib import Path

_CONFIG_PATH = None
_USER_CACHE = None  # cached user_id


def _load_config() -> dict:
    """Load isolation config from config.yaml. Cached after first read."""
    global _CONFIG_PATH
    if _CONFIG_PATH is None:
        from moyu_toolkit._moyu_paths import get_package_dir
        toolkit = Path(get_package_dir())
        _CONFIG_PATH = toolkit / "config.yaml"

    try:
        with open(_CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("security", {}).get("isolation", {})
    except Exception:
        return {}


def _get_active_user() -> str:
    """Return the current active user_id, or empty string if isolation is disabled."""
    global _USER_CACHE
    if _USER_CACHE is not None:
        return _USER_CACHE

    cfg = _load_config()
    if not cfg.get("enabled", False):
        _USER_CACHE = ""
        return ""

    user_id = cfg.get("default_user", "").strip()
    if not user_id:
        # If isolation is enabled but no user specified, use a fallback
        user_id = "default"
    _USER_CACHE = user_id
    return user_id


def set_user(user_id: str):
    """Temporarily switch to a different user (runtime only, not persisted to config).

    Call with empty string or None to reset to the config default.
    """
    global _USER_CACHE
    _USER_CACHE = user_id.strip() if user_id else None
    # Force re-read on next call to _get_active_user
    if not user_id:
        _USER_CACHE = None


def get_user() -> str:
    """Get current active user_id (empty string = isolation disabled)."""
    return _get_active_user()


def get_storage_path(base_path: str) -> str:
    """Get the storage path for the current user.

    When isolation is disabled, returns base_path unchanged.
    When isolation is enabled, returns base_path/{user_id}/.

    Creates the user directory if it doesn't exist.
    """
    user_id = _get_active_user()
    if not user_id:
        return base_path

    # Sanitize: only allow alphanumeric, underscore, hyphen
    import re
    safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', user_id)
    if safe_id != user_id:
        safe_id = safe_id or "default"

    user_path = os.path.join(base_path, safe_id)
    os.makedirs(user_path, exist_ok=True)
    return user_path
