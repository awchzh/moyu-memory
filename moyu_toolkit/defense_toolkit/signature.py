#!/usr/bin/env python3
"""
signature.py — MOYU Memory Digital Signature Module (V1.0)

HMAC-SHA256 signing for memory integrity verification.

Design:
- Disabled by default (zero-config priority). Enable via MOYU_SIGN_KEY env var.
- Signs each memory entry on write (add_memory / _save_memories).
- Signatures stored separately in signatures/ directory (not with content files).
- Verification: periodic scan + on-read check + full scan via moyu doctor.
- Auto-recovery: if verification fails, try to restore from signed backup.

Key management:
- Key source: MOYU_SIGN_KEY environment variable only.
- No TPM support — pragmatic env-var approach.
- If key changes, all existing signatures become invalid.
- Signature purpose: detect silent corruption / accidental modification,
  NOT root-level attack prevention.

Storage layout:
    memory_data/
    ├── conversation_memory.json
    ├── vector_index.json
    ├── signatures/
    │   ├── conversation_memory.json.sig
    │   └── vector_index.json.sig
    └── backups/
        ├── daily_20260525_conversation_memory.json
        └── daily_20260525_vector_index.json
"""

import hmac
import hashlib
import json
import os
import time
from datetime import datetime

# ── Config ──
_ENV_KEY = "MOYU_SIGN_KEY"
_SIG_DIR = "signatures"
_HASH_ALGO = "sha256"

# ── Status tracking ──
_last_scan_result = {}  # {"timestamp": ..., "checked": N, "failed": N, "recovered": N}


def _get_storage_path() -> str:
    """Get the base storage directory."""
    base = os.environ.get("MOYU_STORAGE", "")
    if not base:
        try:
            from moyu_toolkit._moyu_paths import get_default_storage
            base = get_default_storage()
        except Exception:
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memory_data")
    return base


def _sig_dir() -> str:
    """Get or create the signatures directory."""
    path = os.path.join(_get_storage_path(), _SIG_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def _sig_path(data_file: str) -> str:
    """Get the signature file path for a given data file."""
    basename = os.path.basename(data_file)
    return os.path.join(_sig_dir(), basename + ".sig")


def _get_key() -> bytes:
    """Get the HMAC signing key from environment variable."""
    key = os.environ.get(_ENV_KEY, "")
    if not key:
        return b""
    return key.encode("utf-8")


def is_enabled() -> bool:
    """Check if memory signing is enabled (MOYU_SIGN_KEY set)."""
    return bool(os.environ.get(_ENV_KEY, ""))


def _compute(data: bytes, key: bytes) -> str:
    """Compute HMAC-SHA256 of data."""
    h = hmac.new(key, data, _HASH_ALGO)
    return h.hexdigest()


# ── Sign ──


def sign(data_file: str, content: str) -> bool:
    """
    Sign a memory data file.

    Args:
        data_file: Absolute path to the data file (e.g., memory_data/conversation_memory.json)
        content: The JSON content string to sign.

    Returns:
        True if signed successfully, False if signing is disabled.
    """
    key = _get_key()
    if not key:
        return False

    sig = _compute(content.encode("utf-8"), key)
    sig_path = _sig_path(data_file)

    # Signatures file format: { "file": ..., "sig": ..., "timestamp": ..., "algo": "hmac-sha256" }
    sig_entry = {
        "file": os.path.basename(data_file),
        "sig": sig,
        "timestamp": datetime.now().isoformat(),
        "algo": "hmac-sha256",
    }
    try:
        with open(sig_path, "w") as f:
            json.dump(sig_entry, f, ensure_ascii=False)
        return True
    except (OSError, IOError):
        return False


def sign_memory_file() -> bool:
    """Sign the current conversation_memory.json and vector_index.json."""
    storage = _get_storage_path()
    files = ["conversation_memory.json", "vector_index.json"]
    ok = True
    for fname in files:
        path = os.path.join(storage, fname)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r") as f:
                content = f.read()
            if not sign(path, content):
                ok = False
        except Exception:
            ok = False
    return ok


# ── Verify ──


def verify(data_file: str) -> dict:
    """
    Verify a single memory data file against its signature.

    Args:
        data_file: Absolute path to the data file.

    Returns:
        {"status": "ok"|"fail"|"no_sig"|"disabled",
         "file": basename,
         "message": str}
    """
    result = {"file": os.path.basename(data_file), "status": "disabled", "message": "Signing disabled"}

    key = _get_key()
    if not key:
        return result

    sig_path = _sig_path(data_file)
    if not os.path.exists(sig_path):
        result["status"] = "no_sig"
        result["message"] = "No signature file found"
        return result

    try:
        # Read current content
        with open(data_file, "r") as f:
            content = f.read()

        # Read stored signature
        with open(sig_path) as f:
            sig_entry = json.load(f)

        # Recompute
        expected_sig = _compute(content.encode("utf-8"), key)
        stored_sig = sig_entry.get("sig", "")

        if expected_sig == stored_sig:
            result["status"] = "ok"
            result["message"] = "Signature matches"
        else:
            result["status"] = "fail"
            result["message"] = "Signature mismatch — content has changed since signing"
            # Report to defense log
            try:
                from moyu_toolkit.defense_toolkit.defense_log import report as _dl_report
                _dl_report("signature", "red", {
                    "event": f"{os.path.basename(data_file)} 签名校验失败",
                    "source": "磁盘读取",
                    "detail": f"HMAC-SHA256 校验失败，{result['message']}",
                    "auto_resolved": False,
                })
            except Exception:
                pass

    except (json.JSONDecodeError, OSError) as e:
        result["status"] = "error"
        result["message"] = f"Verification error: {e}"

    return result


def verify_memory_files() -> dict:
    """Verify all memory data files. Returns summary."""
    storage = _get_storage_path()
    files = ["conversation_memory.json", "vector_index.json"]
    results = []
    for fname in files:
        path = os.path.join(storage, fname)
        if os.path.exists(path):
            r = verify(path)
            results.append(r)

    failed = [r for r in results if r["status"] == "fail"]
    ok_count = sum(1 for r in results if r["status"] == "ok")
    no_sig = sum(1 for r in results if r["status"] == "no_sig")
    disabled = sum(1 for r in results if r["status"] == "disabled")

    summary = {
        "enabled": is_enabled(),
        "checked": len(results),
        "ok": ok_count,
        "failed": len(failed),
        "no_sig": no_sig,
        "disabled_files": disabled,
        "details": results,
    }

    # Update scan status
    global _last_scan_result
    _last_scan_result = {
        "timestamp": time.time(),
        "checked": len(results),
        "failed": len(failed),
        "recovered": 0,
    }

    return summary


def verify_sample(sample_pct: float = 0.01) -> dict:
    """
    Verify a random sample of memories (not whole files).
    For future use when per-entry signatures are implemented.
    Currently delegates to file-level verify_memory_files.
    """
    return verify_memory_files()


# ── Auto-recovery ──


def verify_and_recover() -> dict:
    """
    Verify all memory files. If signature fails, try to recover from backup.

    Recovery strategy:
    1. Verify all files
    2. For each failed file, look for daily backup in backups/ dir
    3. If backup has valid signature, restore from backup
    4. If no signed backup found, report failure

    Returns:
        {"status": "ok"|"partial"|"fail",
         "checked": N, "recovered": N, "unrecoverable": N,
         "details": [...]}
    """
    if not is_enabled():
        return {"status": "disabled", "message": "Signing disabled"}

    summary = verify_memory_files()
    storage = _get_storage_path()
    backup_dir = os.path.join(storage, "backups")

    recovered = 0
    unrecoverable = 0
    details = summary.get("details", [])

    for r in details:
        if r["status"] != "fail":
            continue

        fname = r["file"]
        data_path = os.path.join(storage, fname)

        # Look for the most recent backup
        best_backup = None
        best_time = 0

        if os.path.isdir(backup_dir):
            for bf in os.listdir(backup_dir):
                if bf.endswith(fname):
                    bpath = os.path.join(backup_dir, bf)
                    mtime = os.path.getmtime(bpath)
                    if mtime > best_time:
                        best_backup = bpath
                        best_time = mtime

        if best_backup:
            # Verify backup's own signature
            backup_sig = verify(best_backup)
            if backup_sig["status"] == "ok":
                # Backup is clean — restore it
                try:
                    import shutil
                    shutil.copy2(best_backup, data_path)
                    # Re-sign after restore
                    with open(data_path, "r") as f:
                        content = f.read()
                    sign(data_path, content)
                    r["status"] = "recovered"
                    r["message"] = f"Recovered from backup: {os.path.basename(best_backup)}"
                    recovered += 1
                    # Report recovery to defense log
                    try:
                        from moyu_toolkit.defense_toolkit.defense_log import report as _dl_report
                        _dl_report("signature", "yellow", {
                            "event": f"{fname} 自动恢复成功",
                            "source": f"备份: {os.path.basename(best_backup)}",
                            "detail": "签名校验失败后自动从签名通过的备份恢复，用户零感知",
                            "auto_resolved": True,
                        })
                    except Exception:
                        pass
                except Exception as e:
                    r["message"] += f"; recovery failed: {e}"
                    unrecoverable += 1
            else:
                r["message"] += f"; backup {os.path.basename(best_backup)} also has invalid signature"
                unrecoverable += 1
                try:
                    from moyu_toolkit.defense_toolkit.defense_log import report as _dl_report
                    _dl_report("signature", "red", {
                        "event": f"{fname} 恢复失败 — 备份也签名不匹配",
                        "source": f"备份: {os.path.basename(best_backup)}",
                        "detail": "签名校验失败，备份文件同样签名不匹配，无法自动恢复，需人工介入",
                        "auto_resolved": False,
                    })
                except Exception:
                    pass
        else:
            r["message"] += "; no backup found for recovery"
            unrecoverable += 1
            try:
                from moyu_toolkit.defense_toolkit.defense_log import report as _dl_report
                _dl_report("signature", "red", {
                    "event": f"{fname} 恢复失败 — 无可用备份",
                    "source": "磁盘读取",
                    "detail": "签名校验失败但未找到可用的备份文件，无法自动恢复",
                    "auto_resolved": False,
                })
            except Exception:
                pass

    global _last_scan_result
    _last_scan_result = {
        "timestamp": time.time(),
        "checked": summary["checked"],
        "failed": summary["failed"],
        "recovered": recovered,
    }

    status = "ok"
    if unrecoverable > 0:
        status = "partial" if recovered > 0 else "fail"
    elif recovered > 0:
        status = "ok"

    return {
        "status": status,
        "checked": summary["checked"],
        "recovered": recovered,
        "unrecoverable": unrecoverable,
        "details": details,
    }


# ── Status ──


def get_status() -> dict:
    """Get current signing status for display."""
    global _last_scan_result
    return {
        "enabled": is_enabled(),
        "key_set": bool(_get_key()),
        "key_env": _ENV_KEY,
        "sig_dir": _sig_dir(),
        "last_scan": _last_scan_result,
    }


def demo() -> dict:
    """Quick demo for moyu_demo.py discovery engine."""
    enabled = is_enabled()
    status = "🟢 Signatures ON" if enabled else "🔴 Signatures OFF"
    if enabled:
        r = verify_memory_files()
        status += f" — {r['ok']}/{r['checked']} files OK"
        if r['failed']:
            status += f", ⚠️ {r['failed']} failed"
    return {
        "capability": 3,
        "title": "Memory Integrity",
        "output": f"🧠 Memory Signature{' (disabled, set MOYU_SIGN_KEY)' if not enabled else ' (HMAC-SHA256)'}",
        "status": status,
    }
