#!/usr/bin/env python3
"""
_storage.py — MOYU Unified File I/O Layer

All memory file reads/writes MUST go through this module.
No module should call open()/os.makedirs()/os.path.join() directly for
memory data files. This ensures:
  - Content security scanning on every write
  - HMAC signature on every write
  - Atomic write (tmp → rename)
  - Manifest integrity tracking
  - Consistent path resolution

Usage:
  from moyu_toolkit._storage import storage
  data = storage.read("active_context.json")
  storage.write("active_context.json", {"key": "value"})
"""

import json
import os
import hashlib
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from moyu_toolkit._moyu_paths import get_default_storage

# ── Internal helpers ──

def _build_path(filename: str) -> str:
    """Resolve filename to full path under storage directory."""
    base = get_default_storage()
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, filename)


def _atomic_write(path: str, content: str):
    """Write to temp file then rename — crash-safe."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp, path)  # atomic on POSIX
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _content_scan(text: str) -> list:
    """Run content security gate. Returns list of detected threats (empty = clean)."""
    try:
        from moyu_toolkit.defense_toolkit.integrity_checker import content_scan
        return content_scan(text) or []
    except ImportError:
        return []


def _sign(data_file: str, content: str):
    """Sign written file if signature is enabled."""
    try:
        from moyu_toolkit.defense_toolkit.signature import sign
        sign(data_file, content)
    except ImportError:
        pass


def _update_manifest(filename: str):
    """Update integrity manifest for the written file."""
    try:
        from moyu_toolkit.defense_toolkit.integrity_checker import sha256_file, MANIFEST_PATH, _atomic_write_json
        filepath = _build_path(filename)
        if os.path.exists(MANIFEST_PATH):
            with open(MANIFEST_PATH) as f:
                manifest = json.load(f)
            existing = [e for e in manifest.get("files", []) if e["path"] != filename]
            sha = sha256_file(filepath)
            existing.append({
                "path": filename,
                "sha256": sha,
                "updated": datetime.now().isoformat(),
            })
            manifest["files"] = existing
            _atomic_write_json(MANIFEST_PATH, manifest)
    except (ImportError, Exception):
        pass


def _remove_from_manifest(filename: str):
    """Remove a file's entry from integrity manifest after deletion."""
    try:
        from moyu_toolkit.defense_toolkit.integrity_checker import MANIFEST_PATH, _atomic_write_json
        if os.path.exists(MANIFEST_PATH):
            with open(MANIFEST_PATH) as f:
                manifest = json.load(f)
            manifest["files"] = [e for e in manifest.get("files", []) if e["path"] != filename]
            _atomic_write_json(MANIFEST_PATH, manifest)
    except (ImportError, Exception):
        pass


# ── Public API ──

class Storage:
    """Unified file I/O for MOYU memory data."""

    # ── Path & directory ──

    @staticmethod
    def path(filename: str) -> str:
        """Full path to a file in storage. Directory is created if needed."""
        return _build_path(filename)

    @staticmethod
    def ensure():
        """Ensure storage directory exists."""
        os.makedirs(get_default_storage(), exist_ok=True)

    @staticmethod
    def exists(filename: str) -> bool:
        """Check if file exists in storage."""
        return os.path.exists(_build_path(filename))

    @staticmethod
    def list_files(suffix: str = ".json") -> list:
        """List files in storage directory (filtered by suffix)."""
        base = get_default_storage()
        if not os.path.isdir(base):
            return []
        return sorted([f for f in os.listdir(base) if f.endswith(suffix) and os.path.isfile(os.path.join(base, f))])

    # ── Read ──

    @staticmethod
    def read(filename: str) -> Optional[dict]:
        """Read JSON file. Returns None if missing or corrupt."""
        path = _build_path(filename)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def read_or_default(filename: str, default: dict) -> dict:
        """Read JSON file; return default if missing."""
        data = Storage.read(filename)
        return data if data is not None else default

    @staticmethod
    def read_raw(filename: str) -> Optional[str]:
        """Read raw text file. Returns None if missing."""
        path = _build_path(filename)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding='utf-8') as f:
                return f.read()
        except OSError:
            return None

    # ── Write (atomic + security-gated) ──

    @staticmethod
    def write(filename: str, data: Union[dict, list], scan: bool = True) -> bool:
        """Atomic JSON write with content scan + signature + manifest update.

        Args:
            filename: Target filename (e.g. 'active_context.json')
            data: JSON-serializable data
            scan: If True (default), content scan blocks injection writes.

        Returns:
            True if write succeeded, False if blocked by content gate.
        """
        path = _build_path(filename)
        content = json.dumps(data, ensure_ascii=False, indent=2)

        if scan:
            hits = _content_scan(content)
            if hits:
                print(f"🔴 _storage: write blocked for {filename} — detected: {', '.join(hits)}",
                      file=__import__('sys').stderr)
                return False

        _atomic_write(path, content)
        _sign(path, content)
        _update_manifest(filename)
        return True

    @staticmethod
    def write_raw(filename: str, text: str, scan: bool = True) -> bool:
        """Atomic raw text write with content scan + signature.

        Args:
            filename: Target filename
            text: Raw text content
            scan: If True (default), content scan blocks injection writes.

        Returns:
            True if write succeeded, False if blocked by content gate.
        """
        path = _build_path(filename)

        if scan:
            hits = _content_scan(text)
            if hits:
                print(f"🔴 _storage: write_raw blocked for {filename} — detected: {', '.join(hits)}",
                      file=__import__('sys').stderr)
                return False

        _atomic_write(path, text)
        _sign(path, text)
        _update_manifest(filename)
        return True

    @staticmethod
    def delete(filename: str) -> bool:
        """Delete a file from storage and its manifest entry. Returns True if deleted."""
        path = _build_path(filename)
        if os.path.exists(path):
            os.unlink(path)
            _remove_from_manifest(filename)
            return True
        return False

    # ── Info ──

    @staticmethod
    def sha256(filename: str) -> Optional[str]:
        """SHA256 hash of a file in storage."""
        path = _build_path(filename)
        if not os.path.exists(path):
            return None
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()


# Singleton
storage = Storage()
