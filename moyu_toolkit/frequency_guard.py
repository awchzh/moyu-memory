#!/usr/bin/env python3
"""
frequency_guard.py — MOYU Frequency Guard (V1.0)

Generic sliding window frequency monitor with configurable rules.
Replaces the hard-coded write burst protection with a unified framework.

Supports:
  - Write burst: >30 writes/60s → rollback + auto-lock
  - Read burst:  >100 reads/60s  → alert log (not blocking)
  - Custom rules can be added by config

Usage:
    from frequency_guard import FrequencyGuard
    guard = FrequencyGuard()
    guard.record("write")  # records a write event
    guard.record("read")   # records a read event
    if guard.is_locked("write"):
        print("writes are locked due to burst")
"""

import json
import os
import time
from collections import defaultdict
from datetime import datetime

STORAGE_PATH = os.environ.get(
    "MOYU_STORAGE",
    os.path.join(os.path.dirname(__file__), "memory_data")
)

# ── Default rules ──
# Each rule: name, threshold (events within window), window (seconds), action, lock_minutes (if rollback)
DEFAULT_RULES = {
    "write": {
        "threshold": 30,
        "window": 60,
        "action": "rollback",
        "lock_minutes": 5,
        "description": "Write burst protection: >30 writes in 60s triggers rollback + 5min lock",
    },
    "read": {
        "threshold": 100,
        "window": 60,
        "action": "alert",
        "lock_minutes": 0,
        "description": "Read burst monitoring: >100 reads in 60s triggers alert",
    },
}

# ── Lock file paths (shared with agent_memory for backward compat) ──
_LOCK_FILES = {}
_FREQ_FILES = {}
_FLOCK_FILES = {}


def _ensure_paths(rule_name: str):
    """Ensure storage paths for a given rule."""
    if rule_name not in _LOCK_FILES:
        os.makedirs(STORAGE_PATH, exist_ok=True)
        _LOCK_FILES[rule_name] = os.path.join(STORAGE_PATH, f"{rule_name}_lock.json")
        _FREQ_FILES[rule_name] = os.path.join(STORAGE_PATH, f"{rule_name}_freq.json")
        _FLOCK_FILES[rule_name] = os.path.join(STORAGE_PATH, f"{rule_name}_flock.lock")


# ============================================================
#  Timestamp helpers
# ============================================================

def _ts_to_unix(ts_str: str) -> float:
    """Parse ISO timestamp string to unix timestamp. Handles missing/partial microseconds."""
    if not ts_str:
        return 0.0
    try:
        # Try with microseconds first, then without
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(ts_str, fmt).timestamp()
            except ValueError:
                continue
        return 0.0
    except Exception:
        return 0.0


# ============================================================
#  Flock (file-level locking for thread/process safety)
# ============================================================

class _Flock:
    """Simple file lock via fcntl.flock. Prevents concurrent writes."""
    def __init__(self, path: str):
        self.path = path
        self.fp = None

    def __enter__(self):
        import fcntl
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.fp = open(self.path, 'w')
        fcntl.flock(self.fp, fcntl.LOCK_EX)
        return self

    def __exit__(self, *args):
        import fcntl
        if self.fp:
            fcntl.flock(self.fp, fcntl.LOCK_UN)
            self.fp.close()
            self.fp = None


# ============================================================
#  FrequencyGuard
# ============================================================

class FrequencyGuard:
    """Sliding window frequency monitor.

    Usage:
        guard = FrequencyGuard()
        guard.record("write")
        guard.record("read")
        guard.is_locked("write")  # → True/False
        guard.stats()             # → {"write": {...}, "read": {...}}
    """

    def __init__(self, rules: dict = None):
        self.rules = rules or DEFAULT_RULES.copy()

    # ── Record an event ──

    def record(self, rule_name: str) -> dict:
        """Record an event for the given rule. Returns the rule result.

        Returns:
            {"triggered": False} or
            {"triggered": True, "action": "rollback|alert", "count": N, "window": N}
        """
        rule = self.rules.get(rule_name)
        if not rule:
            return {"triggered": False, "error": f"Unknown rule: {rule_name}"}

        _ensure_paths(rule_name)
        freq_path = _FREQ_FILES[rule_name]
        flock_path = _FLOCK_FILES[rule_name]

        with _Flock(flock_path):
            now = time.time()
            records = self._load_records(freq_path)
            cutoff = now - rule["window"]
            records = [t for t in records if t > cutoff]
            records.append(now)

            if len(records) > rule["threshold"]:
                # Burst detected
                burst_records = list(records)
                self._clear_records(freq_path)
                return self._handle_burst(rule_name, rule, burst_records)

            # Normal: save and return
            self._save_records(freq_path, records)
            return {"triggered": False}

    # ── Check lock status ──

    def is_locked(self, rule_name: str) -> bool:
        """Check if the given rule currently has a lock active."""
        _ensure_paths(rule_name)
        lock_path = _LOCK_FILES[rule_name]
        if not os.path.exists(lock_path):
            return False
        try:
            with open(lock_path) as f:
                lock = json.load(f)
            elapsed = time.time() - lock.get("locked_at", 0)
            lock_minutes = lock.get("lock_minutes", 0)
            if elapsed < lock_minutes * 60:
                return True
            else:
                os.remove(lock_path)
                return False
        except Exception:
            # Corrupted lock file — treat as locked to be safe
            return True

    def lock_remaining(self, rule_name: str) -> float:
        """Get remaining lock time in seconds. Returns 0 if not locked."""
        _ensure_paths(rule_name)
        lock_path = _LOCK_FILES[rule_name]
        if not os.path.exists(lock_path):
            return 0
        try:
            with open(lock_path) as f:
                lock = json.load(f)
            elapsed = time.time() - lock.get("locked_at", 0)
            lock_minutes = lock.get("lock_minutes", 0)
            remaining = (lock_minutes * 60) - elapsed
            return max(0, remaining)
        except Exception:
            return 0

    def unlock(self, rule_name: str):
        """Manually unlock a rule."""
        _ensure_paths(rule_name)
        lock_path = _LOCK_FILES[rule_name]
        if os.path.exists(lock_path):
            os.remove(lock_path)

    # ── Stats ──

    def stats(self) -> dict:
        """Return current stats for all rules."""
        result = {}
        for name, rule in self.rules.items():
            _ensure_paths(name)
            freq_path = _FREQ_FILES[name]
            records = self._load_records(freq_path)
            now = time.time()
            cutoff = now - rule["window"]
            active = [t for t in records if t > cutoff]
            result[name] = {
                "recent_count": len(active),
                "threshold": rule["threshold"],
                "window": rule["window"],
                "action": rule["action"],
                "locked": self.is_locked(name),
                "description": rule.get("description", ""),
            }
        return result

    # ── Internal helpers ──

    def _load_records(self, path: str) -> list:
        """Load timestamp records from file."""
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_records(self, path: str, records: list):
        """Save timestamp records to file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(records, f)

    def _clear_records(self, path: str):
        """Clear frequency records."""
        with open(path, 'w') as f:
            json.dump([], f)

    def _handle_burst(self, rule_name: str, rule: dict, burst_records: list) -> dict:
        """Handle a burst event. Returns result dict."""
        action = rule.get("action", "alert")
        lock_minutes = rule.get("lock_minutes", 0)
        window = rule.get("window", 60)
        result = {
            "triggered": True,
            "action": action,
            "count": len(burst_records),
            "window": window,
        }

        # Lock if configured
        if lock_minutes > 0:
            _ensure_paths(rule_name)
            lock_path = _LOCK_FILES[rule_name]
            lock_data = {
                "locked_at": time.time(),
                "lock_minutes": lock_minutes,
                "reason": f"Burst: >{rule['threshold']} {rule_name}s in {window}s",
                "timestamp": datetime.now().isoformat(),
            }
            with open(lock_path, 'w') as f:
                json.dump(lock_data, f, ensure_ascii=False, indent=2)
            result["lock_minutes"] = lock_minutes

        # Rollback if action is rollback
        if action == "rollback":
            removed = self._rollback_burst(burst_records)
            result["removed"] = removed
            # Report to defense log
            try:
                from defense_toolkit.defense_log import report as _dl_report
                _dl_report("burst", "yellow", {
                    "event": f"写入暴风 — {config.get('threshold')}次/{config.get('window')}秒",
                    "source": f"规则: {rule_name}",
                    "detail": f"回滚了 {removed} 条写入，锁定 {config.get('lock_minutes', 0)} 分钟",
                    "auto_resolved": True,
                })
            except Exception:
                pass

        # Send alert
        self._send_alert(rule_name, rule, result)

        return result

    def _rollback_burst(self, burst_records: list) -> int:
        """Rollback entries written during the burst window. Returns count removed."""
        min_unix = min(burst_records)
        removed_count = 0

        # conversation_memory.json — direct file ops, no cross-module import
        mem_path = os.path.join(STORAGE_PATH, "conversation_memory.json")
        if os.path.exists(mem_path):
            try:
                with open(mem_path) as f:
                    memories = json.load(f)
                before = len(memories)
                memories = [m for m in memories if _ts_to_unix(m.get("timestamp", "")) < min_unix]
                removed = before - len(memories)
                if removed:
                    with open(mem_path, 'w') as f:
                        json.dump(memories, f, ensure_ascii=False, indent=2)
                    removed_count += removed
            except Exception:
                pass

        # vector_index.json — direct file ops
        vec_path = os.path.join(STORAGE_PATH, "vector_index.json")
        if os.path.exists(vec_path):
            try:
                with open(vec_path) as f:
                    idx = json.load(f)
                before = len(idx.get("vectors", []))
                idx["vectors"] = [v for v in idx.get("vectors", []) if _ts_to_unix(v.get("timestamp", "")) < min_unix]
                removed = before - len(idx["vectors"])
                if removed:
                    with open(vec_path, 'w') as f:
                        json.dump(idx, f, ensure_ascii=False, indent=2)
                    removed_count += removed
            except Exception:
                pass

        if removed_count:
            try:
                from defense_toolkit.integrity_checker import log
                log(f"Frequency Guard: removed {removed_count} entries after burst", "CRITICAL")
            except Exception:
                pass

        return removed_count

    def _send_alert(self, rule_name: str, rule: dict, result: dict):
        """Send alert for burst event."""
        try:
            from defense_toolkit.integrity_checker import _send_alert
            action = result.get("action", "alert")
            count = result.get("count", 0)
            window = result.get("window", 60)
            threshold = rule.get("threshold", 0)
            lock_info = f", locked {result.get('lock_minutes', 0)}min" if result.get("lock_minutes") else ""
            _send_alert(
                f"🔴 MOYU {rule_name.upper()} Burst Alert{lock_info}",
                f"Detected >{threshold} {rule_name}s in {window}s\n"
                f"Actual: {count} events{lock_info}"
            )
        except Exception:
            pass


# ============================================================
#  Module-level convenience (backward compat with agent_memory)
# ============================================================

_guard = None


def get_guard() -> FrequencyGuard:
    """Get the singleton FrequencyGuard instance."""
    global _guard
    if _guard is None:
        _guard = FrequencyGuard()
    return _guard


def record_write() -> dict:
    """Record a write event (backward compat)."""
    return get_guard().record("write")


def record_read() -> dict:
    """Record a read event."""
    return get_guard().record("read")


def is_write_locked() -> bool:
    """Check if writes are locked (backward compat)."""
    return get_guard().is_locked("write")


def write_lock_remaining() -> float:
    """Get remaining write lock time in seconds."""
    return get_guard().lock_remaining("write")


def unlock_writes():
    """Manually unlock writes."""
    return get_guard().unlock("write")


def guard_stats() -> dict:
    """Get guard stats for all rules."""
    return get_guard().stats()


# ============================================================
#  CLI
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "stats":
        s = guard_stats()
        for name, info in s.items():
            status = "🔒 LOCKED" if info["locked"] else "✅ OK"
            print(f"  [{name}] {info['recent_count']}/{info['threshold']} in {info['window']}s — {status}")
            print(f"           {info['description']}")
            if info["locked"]:
                remaining = get_guard().lock_remaining(name)
                print(f"           Lock expires in {remaining:.0f}s")

    elif len(sys.argv) >= 3 and sys.argv[1] == "record":
        result = get_guard().record(sys.argv[2])
        if result.get("triggered"):
            print(f"⚠️  Burst triggered! action={result.get('action')}")
        else:
            print(f"✅ Recorded ({sys.argv[2]})")

    elif len(sys.argv) >= 3 and sys.argv[1] == "unlock":
        get_guard().unlock(sys.argv[2])
        print(f"✅ Unlocked ({sys.argv[2]})")

    else:
        print("Usage:")
        print("  python3 frequency_guard.py stats              # Show guard stats")
        print("  python3 frequency_guard.py record <name>       # Record an event")
        print("  python3 frequency_guard.py unlock <name>       # Unlock a rule")
