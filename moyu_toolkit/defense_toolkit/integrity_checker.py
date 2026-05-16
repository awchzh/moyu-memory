#!/usr/bin/env python3
"""
integrity_checker.py — MOYU File Integrity Checker

Two independent functions:
  1. Daily backup — snapshots all JSON files once per day, keeps 3 days.
  2. Integrity check — verifies manifest.json hashes, recovers from backup
     if tampered. Skips files that are expected to change daily.

Usage:
    python3 integrity_checker.py              # Run verification + backup
    python3 integrity_checker.py init         # Initialize manifest
"""

import json, os, hashlib, sys, shutil
from datetime import datetime

BASE = os.environ.get("MOYU_STORAGE", os.path.join(os.path.dirname(__file__), "..", "memory_data"))
MANIFEST_PATH = os.path.join(BASE, "manifest.json")
BACKUP_DIR = os.path.join(BASE, "backups")
LOG_PATH = os.path.join(BASE, "integrity_log.json")

# Files that change daily — backed up, integrity-check skipped (hash change expected)
_DATA_FILES = {
    "conversation_memory.json", "vector_index.json", "kb_index.json",
    "compression_log.json", "knowledge_graph.json", "user_profile.json",
    "session_bridge.json", "active_context.json", "knowledge_base_index.json",
    "scene_checkpoint.json", "manifest.json",
}


def sha256_file(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return "FILE_NOT_FOUND"


def log(msg, level="INFO"):
    ts = datetime.now().isoformat()
    print(f"[{ts}] [{level}] {msg}")


def init_manifest():
    """Scan memory_data files and generate manifest"""
    manifest = {"version": "1.0", "created": datetime.now().isoformat(), "files": []}
    for fname in os.listdir(BASE):
        fpath = os.path.join(BASE, fname)
        if os.path.isfile(fpath) and fname.endswith(".json"):
            manifest["files"].append({
                "path": fname,
                "sha256": sha256_file(fpath),
                "description": fname
            })
    with open(MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log(f"Manifest initialized ({len(manifest['files'])} files)", "PASS")


# ── Daily snapshot backup (completely independent of verification) ──

def _daily_backup_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _daily_backup_exists() -> bool:
    today = _daily_backup_key()
    if not os.path.isdir(BACKUP_DIR):
        return False
    for fname in os.listdir(BACKUP_DIR):
        if fname.startswith(f"daily_{today}"):
            return True
    return False


def _prune_old_backups():
    """Keep only 3 most recent days of backup."""
    if not os.path.isdir(BACKUP_DIR):
        return
    daily = {}
    for fname in os.listdir(BACKUP_DIR):
        if fname.startswith("daily_"):
            parts = fname.split("_", 2)
            if len(parts) >= 2:
                date_key = parts[1]
                daily.setdefault(date_key, []).append(fname)
    for old_date in sorted(daily.keys(), reverse=True)[3:]:
        for fname in daily[old_date]:
            try:
                os.remove(os.path.join(BACKUP_DIR, fname))
            except Exception:
                pass


def daily_backup():
    """Snapshot all JSON files once per day. Keeps 3 days.
    Completely independent of integrity verification."""
    if _daily_backup_exists():
        return False
    os.makedirs(BACKUP_DIR, exist_ok=True)
    today = _daily_backup_key()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backed_up = 0
    for fname in os.listdir(BASE):
        if not fname.endswith(".json"):
            continue
        src = os.path.join(BASE, fname)
        if not os.path.exists(src):
            continue
        name, ext = os.path.splitext(fname)
        bak_name = f"daily_{today}_{name}_{ts}.json"
        try:
            shutil.copy2(src, os.path.join(BACKUP_DIR, bak_name))
            backed_up += 1
        except Exception:
            pass
    _prune_old_backups()
    if backed_up:
        log(f"Daily backup: {backed_up} files ({today})", "PASS")
    return backed_up > 0


# ── Last-known-good hash snapshot (for data files) ──

SNAPSHOT_PATH = os.path.join(BACKUP_DIR, "last_hash_snapshot.json")
HASH_LOG_PATH = os.path.join(BASE, "hash_change_log.json")


def _load_snapshot() -> dict:
    if os.path.exists(SNAPSHOT_PATH):
        with open(SNAPSHOT_PATH) as f:
            return json.load(f)
    return {}


def _save_snapshot(snapshot: dict):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    with open(SNAPSHOT_PATH, 'w') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def _log_hash_change(filepath: str, old_hash: str, new_hash: str, file_size_diff: int):
    """Append a hash change entry to the change log."""
    entries = []
    if os.path.exists(HASH_LOG_PATH):
        try:
            with open(HASH_LOG_PATH) as f:
                entries = json.load(f)
        except Exception:
            entries = []
    entries.append({
        "timestamp": datetime.now().isoformat(),
        "file": filepath,
        "hash_before": old_hash,
        "hash_after": new_hash,
        "size_diff_bytes": file_size_diff,
    })
    entries = entries[-200:]  # keep last 200
    with open(HASH_LOG_PATH, 'w') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def hash_change_log() -> list:
    """Return recent hash change entries for audit display."""
    if not os.path.exists(HASH_LOG_PATH):
        return []
    with open(HASH_LOG_PATH) as f:
        return json.load(f)


# ── Integrity verification ──

def verify():
    if not os.path.exists(MANIFEST_PATH):
        log("manifest.json not found. Run 'init' first.", "CRITICAL")
        return False

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    # First: daily backup (always, regardless of what happens next)
    daily_backup()

    # Load the hash snapshot for data file tracking
    snapshot = _load_snapshot()

    # Then: integrity check
    all_ok = True
    needs_reinit = False
    data_changes = 0
    critical_changes = 0

    for entry in manifest["files"]:
        fpath = os.path.join(BASE, entry["path"])
        actual = sha256_file(fpath)
        expected = entry["sha256"]

        if actual == "FILE_NOT_FOUND":
            log(f"File missing: {entry['path']}", "CRITICAL")
            all_ok = False
            critical_changes += 1
        elif actual != expected:
            if entry["path"] in _DATA_FILES:
                # Data files: track change, don't alarm
                # Skip manifest.json — it updates on every verify()
                if entry["path"] == "manifest.json":
                    snapshot[entry["path"]] = actual
                else:
                    old_snapshot = snapshot.get(entry["path"])
                    if old_snapshot and old_snapshot != actual:
                        log(f"📝 {entry['path']} (hash changed)", "INFO")
                        _log_hash_change(entry["path"], old_snapshot, actual, 0)
                        data_changes += 1
                    snapshot[entry["path"]] = actual
            else:
                log(f"File tampered: {entry['path']}", "CRITICAL")
                all_ok = False
                critical_changes += 1
                needs_reinit = True
                _auto_recover(entry["path"], manifest)
        else:
            log(f"✓ {entry['path']}", "PASS")

    # Save updated snapshot
    _save_snapshot(snapshot)

    # Summary
    if data_changes:
        log(f"{data_changes} data file(s) changed since last check", "INFO")
    if all_ok:
        log("All checks passed ✓", "PASS")
    else:
        log(f"{critical_changes} critical issue(s) detected", "CRITICAL")

    # Add hash_change_log to manifest for audit display
    manifest["_data_changes_since_init"] = data_changes
    manifest["_checked_at"] = datetime.now().isoformat()
    with open(MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return all_ok


def _auto_recover(fpath, manifest):
    """Restore static file from the most recent daily backup."""
    if not os.path.isdir(BACKUP_DIR):
        log(f"  No backup directory", "WARN")
        return
    name_stub = fpath.replace(".json", "")
    candidates = []
    for fname in os.listdir(BACKUP_DIR):
        if fname.startswith("daily_") and name_stub in fname and fname.endswith(".json"):
            candidates.append(fname)
    candidates.sort(reverse=True)
    for bak_name in candidates:
        bak_path = os.path.join(BACKUP_DIR, bak_name)
        target = os.path.join(BASE, fpath)
        try:
            shutil.copy2(bak_path, target)
            new_hash = sha256_file(target)
            for e in manifest.get("files", []):
                if e["path"] == fpath:
                    e["sha256"] = new_hash
            with open(MANIFEST_PATH, 'w') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            log(f"  ✅ Restored from {bak_name}", "PASS")
            return
        except Exception:
            pass
    log(f"  ❌ All backups failed", "CRITICAL")


def forensic_analysis(tampered_file: str):
    """Forensic analysis: compare current file with latest backup,
    detect attack patterns and format anomalies."""
    if not os.path.isdir(BACKUP_DIR):
        return "No backup directory"
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".json")], reverse=True)
    if not backups:
        return "No backup available"
    current = os.path.join(BASE, tampered_file)
    latest = os.path.join(BACKUP_DIR, backups[0])
    if not os.path.exists(current) or not os.path.exists(latest):
        return "File not found"
    cur_size = os.path.getsize(current)
    bak_size = os.path.getsize(latest)
    diff = cur_size - bak_size
    report = f"File size changed by {diff:+d} bytes"
    if diff > 500:
        report += " — possible injection of new content"
    elif diff < -500:
        report += " — possible deletion of content"

    with open(current, errors='replace') as f:
        content = f.read()

    FORENSIC_PATTERNS = [
        ("ignore all previous instructions", "Instruction override"),
        ("ignore previous", "Instruction override"),
        ("forget everything", "Instruction override"),
        ("forget all previous", "Instruction override"),
        ("override all instructions", "Instruction override"),
        ("override previous", "Instruction override"),
        ("disregard previous", "Instruction override"),
        ("disregard all instructions", "Instruction override"),
        ("discard previous", "Instruction override"),
        ("from now on you are", "Role rewrite"),
        ("you are now", "Role rewrite"),
        ("your new role is", "Role rewrite"),
        ("your new identity is", "Role rewrite"),
        ("pretend you are", "Role rewrite"),
        ("act as if", "Role rewrite"),
        ("you will now act as", "Role rewrite"),
        ("this is your top priority", "Rule injection"),
        ("most important instruction", "Rule injection"),
        ("new rule", "Rule injection"),
        ("this overrides everything", "Rule injection"),
        ("you must obey", "Rule injection"),
        ("under no circumstances", "Rule injection"),
        ("ignore all safety rules", "Rule injection"),
        ("override safety", "Rule injection"),
        ("delete your memory", "Memory manipulation"),
        ("erase your memory", "Memory manipulation"),
        ("clear your memory", "Memory manipulation"),
        ("modify your memory", "Memory manipulation"),
        ("override memory", "Memory manipulation"),
        ("forget what you know", "Memory manipulation"),
        ("reset your settings", "Memory manipulation"),
        ("--end--", "Injection marker"),
        ("===END===", "Injection marker"),
        ("[END]", "Injection marker"),
    ]

    detected_labels = set()
    for pattern, label in FORENSIC_PATTERNS:
        if pattern in content.lower():
            if label not in detected_labels:
                report += f"\n  🔴 Detected {label}"
                detected_labels.add(label)

    try:
        json.loads(content)
    except (json.JSONDecodeError, ValueError) as e:
        report += f"\n  ⚠️ JSON structure corrupted: {str(e)[:60]}"

    return report


def demo() -> dict:
    return {
        "capability": 6,
        "title": "Integrity Check + Auto Recovery + Forensic Analysis",
        "output": """💡 6/7  DEMO
────────────────────────────────────
  [Wake Check]
  ✅ conversation_memory.json — OK
  ❌ security_config.json — TAMPERED!
     → Auto-recovered from backup
     → Forensic analysis: file size +2048 bytes

  Triple-layer defense:
  • Before operation 🔒 Memory Self-Defense (security.py)
  • On wake      ✅ Integrity Check + Auto Recovery
  • Post-fact    🔍 Forensic Analysis""",
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_manifest()
    else:
        verify()
