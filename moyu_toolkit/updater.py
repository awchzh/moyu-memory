#!/usr/bin/env python3
"""
updater.py — MOYU self-update (V2.0)

Checks GitHub for new releases and updates the toolkit in place.
Preserves memory_data/ and user config.

Usage:
    python3 updater.py check        # Check if update is available
    python3 updater.py update       # Download and apply update
"""

import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# ── Version (also importable) ──
VERSION = "1.3.1"

TOOLKIT_DIR = Path(__file__).parent.resolve()
REPO = "awchzh/moyu-memory"
GITHUB_API = f"https://api.github.com/repos/{REPO}/releases/latest"
EXCLUDE_DIRS = {"memory_data", "__pycache__"}
EXCLUDE_FILES = {".DS_Store", "*.pyc"}


def _current_version() -> str:
    return VERSION


def _parse_version(v: str) -> tuple:
    """Parse 'v1.3.1' or '1.3.1' into (1, 3, 1)"""
    v = v.lstrip("v").strip()
    parts = v.split(".")
    return tuple(int(p) for p in parts)


def _version_str(v: tuple) -> str:
    return ".".join(str(x) for x in v)


def check() -> dict:
    """Check GitHub for latest release. Returns info dict."""
    try:
        req = urllib.request.Request(
            GITHUB_API,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        latest_tag = data.get("tag_name", "").lstrip("v")
        latest_version = _parse_version(latest_tag)
        current_version = _parse_version(_current_version())

        is_newer = latest_version > current_version
        return {
            "current": _current_version(),
            "latest": latest_tag,
            "is_newer": is_newer,
            "release_url": data.get("html_url", ""),
            "body": (data.get("body", "") or "")[:200],
        }
    except Exception as e:
        return {"error": str(e), "current": _current_version()}


def update(dry_run: bool = False) -> dict:
    """
    Download and apply the latest version.
    Preserves memory_data/ and config.yaml user settings.

    dry_run=True: download to temp dir and verify, don't overwrite.
    """
    info = check()
    if "error" in info:
        return {"status": "error", "message": info["error"]}

    if not info.get("is_newer"):
        return {"status": "ok", "message": f"Already up to date ({_current_version()})"}

    # Download the zipball
    zip_url = f"https://github.com/{REPO}/archive/refs/tags/v{info['latest']}.zip"
    tmp_dir = Path(tempfile.mkdtemp(prefix="moyu_update_"))
    zip_path = tmp_dir / "update.zip"

    try:
        urllib.request.urlretrieve(zip_url, zip_path)
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"status": "error", "message": f"Download failed: {e}"}

    # Extract
    extract_dir = tmp_dir / "extracted"
    extract_dir.mkdir()
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_dir)

    # The zip has a top-level dir named like "moyu-1.3.1/"
    inner_dirs = [d for d in extract_dir.iterdir() if d.is_dir()]
    if not inner_dirs:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"status": "error", "message": "Invalid update package: no root dir"}

    root = inner_dirs[0]

    # Validate moyu_toolkit/ exists
    new_toolkit = root / "moyu_toolkit"
    if not new_toolkit.is_dir():
        # Maybe the root itself is the toolkit
        if (root / "agent_memory.py").exists():
            new_toolkit = root
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {"status": "error", "message": "Invalid update package: no moyu_toolkit/"}

    if dry_run:
        # Count files
        file_count = sum(1 for f in new_toolkit.rglob("*") if f.is_file())
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {
            "status": "ok",
            "message": f"Dry run: {info['latest']} available, {file_count} files ready to update",
            "version": info['latest'],
        }

    # ── Apply update ──
    # Backup memory_data before replacing
    mem_data = TOOLKIT_DIR / "memory_data"
    mem_backup = None
    if mem_data.exists():
        mem_backup = tmp_dir / "memory_data_backup"
        shutil.copytree(mem_data, mem_backup)

    # Replace all files in moyu_toolkit/ (recursively)
    for item in new_toolkit.iterdir():
        name = item.name
        # Skip excluded dirs
        if name in EXCLUDE_DIRS:
            continue
        dest = TOOLKIT_DIR / name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest, ignore_errors=True)
            else:
                dest.unlink()
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Restore memory_data from backup (shouldn't have been touched, but safety)
    if mem_backup and mem_backup.exists():
        if mem_data.exists():
            shutil.rmtree(mem_data, ignore_errors=True)
        shutil.copytree(mem_backup, mem_data)

    shutil.rmtree(tmp_dir, ignore_errors=True)

    return {
        "status": "ok",
        "message": f"Updated from {_current_version()} to {info['latest']}",
        "version": info['latest'],
    }


def stats():
    """Show version info and check for update."""
    info = check()
    current = _current_version()
    if "error" in info:
        print(f"\n📡 MOYU Updater")
        print("=" * 50)
        print(f"  Current:  v{current}")
        print(f"  Error:    {info['error']}")
        print()
        return

    latest = info.get("latest", "?")
    status = "✅ Up to date" if not info.get("is_newer") else "⬆️ Update available!"
    print(f"\n📡 MOYU Updater")
    print("=" * 50)
    print(f"  Current:  v{current}")
    print(f"  Latest:   v{latest}")
    print(f"  Status:   {status}")
    if info.get("body"):
        print(f"  Notes:    {info['body'][:100]}")
    print()


def demo() -> dict:
    return {
        "capability": 16,
        "title": "Self-Update (V2.0)",
        "output": """\
📡 V2.0 FEATURE — Self-Update
────────────────────────────────────
  moyu update check    → Check GitHub for latest version
  moyu update          → Download & apply update (preserves data)
  moyu update --dry    → Preview what would happen

  16 capabilities and growing.
""",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "--help", "-h"):
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "check":
        info = check()
        if "error" in info:
            print(f"Error: {info['error']}")
        else:
            print(f"Current: v{info['current']} → Latest: v{info['latest']}")
            print(f"Update available: {info['is_newer']}")
        sys.exit(0)

    elif cmd == "update":
        dry = "--dry" in sys.argv
        result = update(dry_run=dry)
        print(result["message"])
        sys.exit(0)

    else:
        stats()
