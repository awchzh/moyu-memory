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
VERSION = "2.4.8"

# Known SHA256 checksums for release zips, keyed by version tag.
# Verified before extracting updates.
# NOTE: Circular dependency — a version's own checksum cannot be embedded
# in that version (the updater.py is part of the zip). New versions leave
# their own checksum empty; it gets filled in the NEXT release.
# TOFU: first successful update auto-caches checksum locally.
_CHECKSUMS = {
    "2.4.8": "",  # To be filled in next release
    "2.4.7": "",  # To be filled in next release
    "2.4.6": "05159d27d96f23faaa1064d01e0000d8c3c16a077dbf972b7eb32f235e5cb5c1",  # Downloaded from GitHub
    "2.4.4": "190934a09513a1cefd70711ad6a690fa27b64eb3afab0bc123e7216859b56d9c",  # Downloaded from GitHub
    "2.4.3": "71354dd7b291b36aa2b461b7f4706168cfcfef34e2c2e8f81c2ccb4bba33fe0f",
    "2.4.2": "6a06b1065bd050b272307aae5247598334f4ade5f2b99c6ffaab6709c9bc0a1d",
    "2.4.0": "",
}

from moyu_toolkit._moyu_paths import get_package_dir, _is_installed_package
TOOLKIT_DIR = Path(get_package_dir())
REPO = "awchzh/moyu-memory"
GITHUB_API = f"https://api.github.com/repos/{REPO}/releases/latest"
EXCLUDE_DIRS = {"memory_data", "__pycache__"}
EXCLUDE_FILES = {".DS_Store", "*.pyc"}
_LOCAL_CHECKSUMS_PATH = TOOLKIT_DIR / ".moyu_checksums.json"  # TOFU: cache checksums after first successful update


def _current_version() -> str:
    return VERSION


def _parse_version(v: str) -> tuple:
    """Parse 'v1.3.1' or '1.3.1' into (1, 3, 1). Strips pre-release / build suffixes."""
    v = v.lstrip("v").strip()
    v = re.split(r"[-+]", v)[0]  # Strip -alpha, +build.123 etc.
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

    # ── Pip-installed mode: can't overwrite site-packages ──
    if _is_installed_package():
        return {
            "status": "ok",
            "message": f"v{info['latest']} available. Run: pip install --upgrade moyu",
            "version": info['latest'],
            "pip_upgrade": True,
        }

    # Download the zipball
    zip_url = f"https://github.com/{REPO}/archive/refs/tags/v{info['latest']}.zip"
    tmp_dir = Path(tempfile.mkdtemp(prefix="moyu_update_"))
    zip_path = tmp_dir / "update.zip"

    try:
        urllib.request.urlretrieve(zip_url, zip_path)
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"status": "error", "message": f"Download failed: {e}"}

    # ── SHA256 checksum verification ──
    import hashlib
    expected = _CHECKSUMS.get(info["latest"])

    # Also check local TOFU cache (populated after first successful update)
    if not expected and _LOCAL_CHECKSUMS_PATH.exists():
        try:
            with open(_LOCAL_CHECKSUMS_PATH) as f:
                local_cs = json.load(f)
            expected = local_cs.get(info["latest"], "")
        except Exception:
            pass

    if expected:
        sha = hashlib.sha256()
        with open(zip_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                sha.update(chunk)
        if sha.hexdigest() != expected:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {"status": "error", "message": f"Checksum mismatch for v{info['latest']}. Update aborted."}
    else:
        # No checksum available — refuse to update for safety
        url = info.get("release_url", "")
        if not url:
            url = f"https://github.com/{REPO}/releases/tag/v{info['latest']}"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"status": "error", "message": f"No checksum for v{info['latest']}. Download and verify manually from {url}."}

    # Extract — with zip slip protection
    extract_dir = tmp_dir / "extracted"
    extract_dir.mkdir()
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.namelist():
            dest = (extract_dir / member).resolve()
            if not str(dest).startswith(str(extract_dir.resolve())):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return {"status": "error", "message": f"Zip slip detected in update package: {member}"}
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

    # ── Apply update — with rollback capability ──
    # Backup entire toolkit before replacing
    toolkit_backup = tmp_dir / "toolkit_backup"
    shutil.copytree(TOOLKIT_DIR, toolkit_backup, ignore=shutil.ignore_patterns("memory_data", "__pycache__"))

    # Backup memory_data separately
    mem_data = TOOLKIT_DIR / "memory_data"
    mem_backup = None
    if mem_data.exists():
        mem_backup = tmp_dir / "memory_data_backup"
        shutil.copytree(mem_data, mem_backup)

    try:
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

        # ── Save checksum for next update (TOFU) ──
        if not _CHECKSUMS.get(info["latest"]) and zip_path.exists():
            sha = hashlib.sha256()
            with open(zip_path, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    sha.update(chunk)
            local_cs = {}
            if _LOCAL_CHECKSUMS_PATH.exists():
                try:
                    with open(_LOCAL_CHECKSUMS_PATH) as f:
                        local_cs = json.load(f)
                except Exception:
                    pass
            local_cs[info["latest"]] = sha.hexdigest()
            with open(_LOCAL_CHECKSUMS_PATH, 'w') as f:
                json.dump(local_cs, f)
    except Exception as e:
        # Rollback: restore from backup
        if toolkit_backup.exists():
            # Remove everything except memory_data
            for item in TOOLKIT_DIR.iterdir():
                if item.name in EXCLUDE_DIRS:
                    continue
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            # Restore from backup
            for item in toolkit_backup.iterdir():
                dest = TOOLKIT_DIR / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
        # Mark failed update state even after rollback (prevents silent mixed versions)
        _fail_marker = TOOLKIT_DIR / ".UPDATE_FAILED"
        try:
            _fail_marker.write_text(f"Update to v{info['latest']} failed and was rolled back at {datetime.now().isoformat()}")
        except Exception:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"status": "error", "message": f"Update failed, rolled back: {e}"}

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

  15 capabilities and growing.
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
