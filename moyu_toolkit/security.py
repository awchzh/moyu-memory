#!/usr/bin/env python3
"""security.py -- MOYU Memory Self-Defense (First Line of Defense)

Intercepts and verifies password before operations such as file deletion,
configuration modification, security rule changes, and external script execution
**reach the memory files**. On verification failure, logs forensic evidence and locks.

Works alongside integrity_checker.py (post-event tamper detection + auto-restore)
to form a complete defense chain: "pre-event prevention -> post-event detection -> auto-recovery".

Usage (terminal):
    python3 security.py setup         # Set password for the first time
    python3 security.py verify <op_type> [context]
    python3 security.py unlock         # Enter password to unlock
    python3 security.py status         # View security status

Usage (in code):
    from security import verify_operation
    if verify_operation("delete_file", "delete memory_data/config.json"):
        # Proceed with dangerous operation
    else:
        # Verification failed, do not execute
"""

import json, os, sys, hashlib, time
from datetime import datetime
from pathlib import Path

BASE = Path(os.environ.get("MOYU_STORAGE", str(Path(__file__).parent / "memory_data")))
CONFIG_PATH = Path(os.environ.get("MOYU_CONFIG", str(Path(__file__).parent / "config.yaml")))
SECURITY_LOG = BASE / "security_log.json"
LOCK_FILE = BASE / "security_lock.json"

# Defaults
DEFAULT_LOCKOUT_THRESHOLD = 3  # Failed attempts before lockout
DEFAULT_LOCKOUT_MINUTES = 30   # Lockout duration in minutes


# ── Utility Functions ─────────────────────────────────────


def _timestamp():
    return datetime.now().isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _read_config() -> dict:
    """Read config.yaml and return the security section"""
    if not CONFIG_PATH.exists():
        return {}
    try:
        import yaml
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("security", {})
    except ImportError:
        return {}
    except Exception:
        return {}


def _write_config_section(section: dict):
    """Update the security section in config.yaml"""
    try:
        import yaml
        # Read full config
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                cfg = yaml.safe_load(f) or {}
        else:
            cfg = {}
        # Write security section
        cfg["security"] = section
        with open(CONFIG_PATH, 'w') as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True
    except ImportError:
        return False


def _log_failure(op_type: str, context: str):
    """Log a verification failure for forensic evidence"""
    entry = {
        "timestamp": _timestamp(),
        "operation": op_type,
        "context": context,
        "status": "DENIED",
    }
    logs = []
    if SECURITY_LOG.exists():
        try:
            with open(SECURITY_LOG) as f:
                logs = json.load(f)
        except (json.JSONDecodeError, Exception):
            logs = []
    logs.append(entry)
    # Keep last 100 entries
    logs = logs[-100:]
    SECURITY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SECURITY_LOG, 'w') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
    _alert(op_type, context)


def _alert(op_type: str, context: str):
    """Active alert (stderr output + returns alert info to caller)"""
    ts = _timestamp()
    msg = (
        f"\n⚠️ Security Alert [{ts}]\n"
        f"   Operation: {op_type}\n"
        f"   Context:   {context}\n"
        f"   Status:    Verification failed, evidence logged\n"
        f"   Log file:  {SECURITY_LOG}\n"
    )
    print(msg, file=sys.stderr)


def _check_lock() -> dict:
    """Check if the system is in locked state. Returns lock info or empty dict"""
    if not LOCK_FILE.exists():
        return {}
    try:
        with open(LOCK_FILE) as f:
            lock = json.load(f)
        elapsed = time.time() - lock.get("locked_at", 0)
        duration = lock.get("duration_minutes", DEFAULT_LOCKOUT_MINUTES) * 60
        if elapsed < duration:
            remain = int((duration - elapsed) / 60)
            return {
                "locked": True,
                "reason": lock.get("reason", ""),
                "remaining_minutes": remain,
                "locked_at": lock.get("locked_at"),
            }
        else:
            # Lock expired, auto-release
            LOCK_FILE.unlink(missing_ok=True)
            return {}
    except Exception:
        return {}


def _record_failure(op_type: str):
    """Track failure count, lock if threshold exceeded"""
    # Track failures using a persistent failure count file
    fail_file = BASE / "security_failures.json"
    failures = []
    now = time.time()
    window = 10 * 60  # 10-minute sliding window

    if fail_file.exists():
        try:
            with open(fail_file) as f:
                failures = json.load(f)
        except Exception:
            failures = []

    # Prune entries outside the window
    failures = [f for f in failures if f["ts"] > now - window]
    failures.append({"ts": now, "operation": op_type})

    ts = _timestamp()
    threshold = DEFAULT_LOCKOUT_THRESHOLD
    sec = _read_config()
    if sec:
        threshold = sec.get("lockout_threshold", DEFAULT_LOCKOUT_THRESHOLD)

    if len(failures) >= threshold:
        # Trigger lockout
        duration = sec.get("lockout_minutes", DEFAULT_LOCKOUT_MINUTES) if sec else DEFAULT_LOCKOUT_MINUTES
        lock_data = {
            "locked_at": now,
            "duration_minutes": duration,
            "reason": f"Failed {threshold} verification attempts (last: {op_type})",
            "timestamp": ts,
        }
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOCK_FILE, 'w') as f:
            json.dump(lock_data, f, ensure_ascii=False, indent=2)
        print(f"\n🔒 Security Locked! {threshold} failed attempts, locked for {duration} minutes.", file=sys.stderr)

    # Write back
    with open(fail_file, 'w') as f:
        json.dump(failures, f, ensure_ascii=False, indent=2)


def _clear_failures():
    """Clear failure count"""
    fail_file = BASE / "security_failures.json"
    if fail_file.exists():
        fail_file.unlink(missing_ok=True)


# ── Public API ────────────────────────────────────────────


def setup():
    """
    Set the security password for the first time.
    Runs interactively in the terminal.
    """
    sec = _read_config()
    if sec.get("safe_word_hash"):
        print("Security password already set. To change it, manually delete security.safe_word_hash from config.yaml and re-run setup.")
        return

    print("\n🔐 MOYU Security Password Setup")
    print("=" * 40)
    print("After setting, dangerous operations (delete file, modify config, etc.) require password confirmation.")
    print("Password is stored locally as a SHA256 hash only. It is NOT uploaded anywhere.")
    print()

    pw1 = input("Enter a security password (leave empty to skip verification): ").strip()
    if not pw1:
        print("⚠️  No password set. Verification will be skipped. (Re-run setup to set one later.)")
        return

    pw2 = input("Enter the same password again to confirm: ").strip()
    if pw1 != pw2:
        print("❌ Passwords do not match. Setup failed.")
        return

    if len(pw1) < 4:
        print("❌ Password must be at least 4 characters long.")
        return

    sec_config = {
        "safe_word_hash": _sha256(pw1),
        "lockout_threshold": DEFAULT_LOCKOUT_THRESHOLD,
        "lockout_minutes": DEFAULT_LOCKOUT_MINUTES,
    }
    ok = _write_config_section(sec_config)
    if ok:
        SECURITY_LOG.parent.mkdir(parents=True, exist_ok=True)
        print("✅ Security password set successfully!")
        print(f"   {DEFAULT_LOCKOUT_THRESHOLD} consecutive wrong attempts will lock for {DEFAULT_LOCKOUT_MINUTES} minutes.")
        print(f"   Forensic logs saved at: {SECURITY_LOG}")
    else:
        print("⚠️  Setup completed, but could not write to config.yaml (missing PyYAML library).")
        print("   Please manually add the following to config.yaml:")
        print(f"  security:")
        print(f"    safe_word_hash: {_sha256(pw1)}")
        print(f"    lockout_threshold: {DEFAULT_LOCKOUT_THRESHOLD}")
        print(f"    lockout_minutes: {DEFAULT_LOCKOUT_MINUTES}")


def verify_operation(op_type: str, context: str = "") -> bool:
    """
    Verify a dangerous operation.
    Returns True (allow) or False (deny).

    Args:
        op_type: Operation type (delete_file, modify_config, modify_security, run_script)
        context: Description of the operation
    """
    # Check lock
    lock = _check_lock()
    if lock:
        print(f"\n🔒 System is locked. Auto-unlocks in {lock['remaining_minutes']} minutes.")
        print(f"   Reason: {lock['reason']}")
        print(f"   Or run: python3 security.py unlock")
        return False

    sec = _read_config()
    safe_word_hash = sec.get("safe_word_hash", "")

    if not safe_word_hash:
        # No password set, skip verification
        print(f"⚠️  Security password not set, skipping verification (run `python3 security.py setup` to set one)")
        return True

    # Verify password (terminal interactive mode)
    # For non-terminal environments (e.g., agent calls), use environment variable MOYU_SAFE_WORD
    env_pw = os.environ.get("MOYU_SAFE_WORD", "")

    if env_pw:
        # Environment variable mode (agent internal call)
        if _sha256(env_pw) == safe_word_hash:
            return True
        else:
            pass  # Failed, fall through to terminal mode

    # Terminal interactive mode
    print(f"\n🔐 An operation may threaten memory integrity. Password required to confirm")
    print(f"   ═══════════════════════════════════════")
    print(f"   Operation: {op_type}")
    if context:
        print(f"   Context:   {context}")
    print(f"   Note: This operation may cause memory data loss or corruption")
    print(f"   Enter password to confirm identity (or type 'q' to cancel):")
    try:
        pw = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        pw = ""
        print()

    if pw.lower() == 'q':
        _log_failure(op_type, context or "User cancelled")
        print("⏹  Operation cancelled.")
        return False

    if _sha256(pw) == safe_word_hash:
        _clear_failures()
        return True
    else:
        _log_failure(op_type, context or "Wrong password")
        _record_failure(op_type)
        print("❌ Wrong password. Operation denied.")
        return False


def unlock():
    """
    Unlock the system by verifying the password.
    """
    lock = _check_lock()
    if not lock:
        print("System is not locked. No need to unlock.")
        return True

    sec = _read_config()
    safe_word_hash = sec.get("safe_word_hash", "")
    if not safe_word_hash:
        # No password set, just remove the lock
        LOCK_FILE.unlink(missing_ok=True)
        _clear_failures()
        print("✅ Lock removed (no password set)")
        return True

    print(f"🔓 Enter security password to unlock (remaining lock: {lock['remaining_minutes']} min):")
    try:
        pw = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n⏹  Cancelled.")
        return False

    if _sha256(pw) == safe_word_hash:
        LOCK_FILE.unlink(missing_ok=True)
        _clear_failures()
        print("✅ Lock removed")
        return True
    else:
        print("❌ Wrong password. Lock remains active.")
        return False




def check_password_set() -> bool:
    """Silently check if a password is set (no print output)."""
    sec = _read_config()
    return bool(sec.get("safe_word_hash", ""))


def _is_password_set() -> bool:
    """(deprecated, use check_password_set)"""
    return check_password_set()


# ==================== Public API ====================

def status() -> dict:
    sec = _read_config()
    lock = _check_lock()
    has_pw = bool(sec.get("safe_word_hash", ""))

    # Count failures
    failures = 0
    fail_file = BASE / "security_failures.json"
    if fail_file.exists():
        try:
            with open(fail_file) as f:
                failures = len(json.load(f))
        except Exception:
            failures = 0

    # Read log statistics
    log_count = 0
    if SECURITY_LOG.exists():
        try:
            with open(SECURITY_LOG) as f:
                log_count = len(json.load(f))
        except Exception:
            log_count = 0

    info = {
        "password_set": has_pw,
        "locked": bool(lock),
        "lock_remaining_minutes": lock.get("remaining_minutes", 0) if lock else 0,
        "recent_failures": failures,
        "total_logged_events": log_count,
        "lockout_threshold": sec.get("lockout_threshold", DEFAULT_LOCKOUT_THRESHOLD),
        "lockout_minutes": sec.get("lockout_minutes", DEFAULT_LOCKOUT_MINUTES),
        "log_path": str(SECURITY_LOG),
    }

    print(f"\n🔐 MOYU Security Status")
    print("=" * 40)
    print(f"   Password set:    {'✅ Yes' if has_pw else '❌ No'}")
    print(f"   System locked:   {'🔒 Yes (' + str(info['lock_remaining_minutes']) + ' min remaining)' if lock else '✅ No'}")
    print(f"   Recent failures: {failures}")
    print(f"   Audit log count: {log_count}")
    print(f"   Lock threshold:  {info['lockout_threshold']} tries/{info['lockout_minutes']} min")
    print(f"   Log file path:   {info['log_path']}")
    print()

    return info


def demo() -> dict:
    """Return demo content for moyu_demo.py discovery engine."""
    return {
        "capability": 7,
        "title": "Memory Self-Defense",
        "output": """🛡️ 7/7  DEMO
────────────────────────────────────
  [Before: Direct file access]  [After: Protected]

  Agent: \"delete config.yaml\"   Agent: \"delete config.yaml\"
  → Done. 🗑️                   → 🔐 Password required!
                                  User: ***
                                  ✅ Identity verified
                                  ⏹ Operation logged

  First line of defense — stops dangerous operations
  BEFORE they reach your memory files.
  • 3 failed attempts → 30min auto-lockout
  • Every attempt logged for forensic audit""",
    }


# ── CLI ────────────────────────────────────────────────────


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "setup":
        setup()

    elif cmd == "verify":
        op_type = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        context = sys.argv[3] if len(sys.argv) > 3 else ""
        allowed = verify_operation(op_type, context)
        sys.exit(0 if allowed else 1)

    elif cmd == "unlock":
        unlock()
        sys.exit(0 if not _check_lock() else 1)

    elif cmd == "status":
        status()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
