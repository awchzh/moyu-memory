"""_moyu_paths.py — Centralized path resolution for MOYU toolkit.

Works both in development mode (files alongside code) and pip-installed mode.
"""
import os
import sys
from pathlib import Path

_PKG_DIR = Path(__file__).parent.resolve()


def _is_installed_package() -> bool:
    """Check if MOYU is running from a pip-installed location (vs. dev copy)."""
    # In dev mode, the parent dir has .git; in installed mode, it's site-packages
    try:
        return _PKG_DIR.parent.joinpath(".git").exists() is False
    except Exception:
        return True


def get_package_dir() -> Path:
    """Return the moYu_toolkit package directory (readable)."""
    return _PKG_DIR


def get_default_storage() -> str:
    """Return the default storage path for memory data.
    
    Priority:
    1. MOYU_STORAGE env var (user override)
    2. When pip-installed: ~/.moyu/memory_data/
    3. Otherwise: ./memory_data/ (dev mode, next to the toolkit)
    """
    env = os.environ.get("MOYU_STORAGE")
    if env:
        return env

    if _is_installed_package():
        default = Path.home() / ".moyu" / "memory_data"
    else:
        default = _PKG_DIR / "memory_data"
    return str(default)


def get_config_path() -> str:
    """Return the config.yaml path.
    
    Priority:
    1. MOYU_CONFIG env var (user override)
    2. config.yaml in the package directory (bundled default)
    """
    env = os.environ.get("MOYU_CONFIG")
    if env:
        return env
    return str(_PKG_DIR / "config.yaml")
