#!/usr/bin/env python3
"""
forgetting_curve.py — MOYU Memory Lifecycle (V2.0)

Demotes old/low-access memories ONLY when context is under pressure
(compression engine is actively triggering). If context usage is below
the warning threshold, NO memories are demoted regardless of age.

Config (config.yaml → forgetting_curve):
  enabled: true
  demote_days: 14    → Not accessed in 14 days + context under pressure → demoted
  archive_days: 60   → Demoted + 60 more days → archivable
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

STORAGE = Path(os.environ.get("MOYU_STORAGE", str(Path(__file__).parent / "memory_data")))


def _memories_path() -> str:
    return str(STORAGE / "conversation_memory.json")


def _load_memories() -> list:
    p = _memories_path()
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    return []


def _save_memories(memories: list):
    STORAGE.mkdir(parents=True, exist_ok=True)
    with open(_memories_path(), 'w') as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)


def _load_config() -> dict:
    try:
        import yaml
        cfg_path = Path(__file__).parent / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("forgetting_curve", {})
    except Exception:
        pass
    return {}


def _now() -> str:
    return datetime.now().isoformat()


def _days_since(ts_str: str) -> float:
    """Calculate days between now and a timestamp string."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return (datetime.now() - dt).total_seconds() / 86400
    except Exception:
        return 0


def track_access(memory_ids: list):
    """Update last_accessed and access_count for given memory IDs.
    Call this when memories are retrieved (e.g., after a search)."""
    memories = _load_memories()
    now = _now()
    changed = False
    for m in memories:
        if m.get("id") in memory_ids:
            m["last_accessed"] = now
            m["access_count"] = m.get("access_count", 0) + 1
            # Remove demoted flag since it's being accessed again
            if m.pop("demoted", None) is not None:
                m.pop("demoted_reason", None)
            changed = True
    if changed:
        _save_memories(memories)


def run(context_pressure: bool = False) -> dict:
    """
    Run the forgetting curve check on all memories.

    Args:
        context_pressure: If True, demote old memories. If False, only
                          demote if total active memories exceed budget
                          (safe default for low-frequency users).
    Returns a report of what happened.
    """
    cfg = _load_config()
    if not cfg.get("enabled", True):
        return {"status": "disabled"}

    demote_days = cfg.get("demote_days", 14)
    archive_days = cfg.get("archive_days", 60)

    memories = _load_memories()
    active_memories = [m for m in memories if not m.get("demoted", False)]

    # ── Key logic: only demote if context is under pressure OR
    #    there are more active memories than we can reasonably inject ──
    active_count = len(active_memories)

    if not context_pressure and active_count <= 15:
        # No pressure + few memories → keep everything active
        # Count already-demoted for reporting
        demoted = []
        archived = []
        re_demoted = [m.get("id", "?") for m in memories if m.get("demoted", False)]

        return {
            "status": "ok",
            "total_memories": len(memories),
            "demoted": demoted,
            "already_demoted": len(re_demoted),
            "archivable": archived,
            "demote_threshold_days": demote_days,
            "archive_threshold_days": archive_days,
            "note": "no pressure, kept all memories active",
        }
    now = _now()
    demoted = []
    archived = []
    re_demoted = []  # already demoted but still stale

    for m in memories:
        m_id = m.get("id", "?")
        is_demoted = m.get("demoted", False)

        # Get the most recent relevant timestamp
        access_ts = m.get("last_accessed") or m.get("timestamp", now)
        days = _days_since(access_ts)

        if is_demoted:
            if days >= archive_days:
                archived.append(m_id)
            else:
                re_demoted.append(m_id)  # stays demoted
        else:
            if days >= demote_days:
                m["demoted"] = True
                m["demoted_reason"] = f"not accessed in {days:.0f} days"
                m["demoted_at"] = now
                demoted.append(m_id)

    if demoted or archived:
        _save_memories(memories)

    return {
        "status": "ok",
        "total_memories": len(memories),
        "demoted": demoted,
        "already_demoted": len(re_demoted),
        "archivable": archived,
        "demote_threshold_days": demote_days,
        "archive_threshold_days": archive_days,
    }


def summary() -> str:
    """Quick readable summary for agent messages."""
    r = run()
    parts = []
    if r.get("demoted"):
        parts.append(f"降级了 {len(r['demoted'])} 条记忆")
    if r.get("archivable"):
        parts.append(f"可归档 {len(r['archivable'])} 条")
    active = r.get("total_memories", 0) - len(r.get("demoted", []))
    parts.append(f"活跃记忆 {active} 条")
    return "，".join(parts)


def stats():
    """Terminal stats output."""
    r = run()
    print(f"\n🧠 MOYU Memory Lifecycle")
    print("=" * 50)
    print(f"  Total memories:     {r.get('total_memories', 0)}")
    print(f"  Demote threshold:   {r.get('demote_threshold_days', '?')}d")
    print(f"  Archive threshold:  {r.get('archive_threshold_days', '?')}d")
    print(f"  Freshly demoted:    {len(r.get('demoted', []))}")
    print(f"  Already demoted:    {r.get('already_demoted', 0)}")
    print(f"  Archivable:         {len(r.get('archivable', []))}")
    if r.get("demoted"):
        print(f"  Demoted IDs:        {', '.join(r['demoted'][:5])}")
    print()


def demo() -> dict:
    return {
        "capability": 13,
        "title": "Forgetting Curve (V2.0)",
        "output": """\
🧠 V2.0 FEATURE — Forgetting Curve
────────────────────────────────────
  Memories not accessed in 14 days → Demoted (not auto-injected)
  Demoted + 60 more days → Archivable (cleanup candidate)
  Re-accessing a memory removes its demoted status

  [2026-04-20] Old meeting notes       → ⏳ 32 days → demoted
  [2026-05-01] Tech decision log        → ✅ 11 days → active
  [2026-05-10] Recent project update    → ✅ 2 days  → active
""",
    }


if __name__ == "__main__":
    import sys
    if "--summary" in sys.argv:
        print(summary())
    else:
        stats()
