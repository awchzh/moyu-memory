#!/usr/bin/env python3
"""
moyu_wake.py — MOYU wake-up routine (V2.0)

Call this on every wake to:
  1. Collect all context sources (working memory, rules, recent memories, profile, KG)
  2. Compress via context_manager
  3. Return a status message (press/report/warning)

Usage:
    python3 moyu_wake.py           # Normal wake — compress + report
    python3 moyu_wake.py --dry     # Show status only, no compression
"""

import sys
import os

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)


def _import(name):
    import importlib.util
    path = os.path.join(TOOLKIT_DIR, *name.split(".")) + ".py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wake(dry_run: bool = False) -> str:
    """
    Full wake-up routine:
      1. Load all context sources
      2. Compress via build_injection
      3. Return a single-line status message

    Returns a status message the agent can speak to the user.
    """
    ac = _import("active_context")
    lrn = _import("learner")
    mem = _import("agent_memory")
    cm = _import("context_manager")
    fc = _import("forgetting_curve")
    mm = _import("memory_merge")
    sb = _import("session_bridge")
    up = _import("updater")
    sr = _import("self_reflection")
    ic = _import("defense_toolkit.integrity_checker")

    # ── Step 0: Silent integrity check + daily backup ──
    # Runs verify() which checks hashes and creates daily backup on success.
    # User only sees a message if tampering was detected.
    try:
        ic.verify()
    except Exception:
        pass

    # ── Step 0: Check context pressure level ──
    status = cm.check_status()
    context_pressure = status.get("level") in ("auto", "over", "warn")

    # ── Step 0b: Forgetting curve — only demote under pressure ──
    fc_result = fc.run(context_pressure=context_pressure)
    forget_msgs = []

    # ── Step 0c: Memory merge ──
    merge_result = mm.run()

    # ── Step 0d: Load session bridge ──
    bridge_info = sb.load()

    # ── Step 0e: Self-reflection (only under pressure, compact mode) ──
    reflection_msg = ""
    try:
        if context_pressure:
            reflection_msg = sr.run_compact()
    except Exception:
        pass

    # ── Step 1: Collect context ──
    working_memory = ac.format_for_injection()
    behavioral_rules = lrn.get_rules_for_injection()

    # Fetch recent memories (raw, no embedding needed) — skip demoted
    recent_memories = ""
    try:
        memories = mem._load_memories()
        # Filter out demoted memories
        active = [m for m in memories if not m.get("demoted", False)]
        # Take last 5, sorted by timestamp
        sorted_mem = sorted(active, key=lambda m: m.get("timestamp", ""), reverse=True)[:5]
        if sorted_mem:
            lines = []
            for m in sorted_mem:
                ts = m.get("timestamp", "")[:10]
                summary = m.get("summary", "")
                lines.append(f"[{ts}] {summary[:120]}")
            recent_memories = "\n".join(lines)
    except Exception:
        recent_memories = ""

    # Fetch user profile from learner
    user_profile = ""
    profile_path = os.path.join(
        os.environ.get("MOYU_STORAGE", os.path.join(TOOLKIT_DIR, "memory_data")),
        "user_profile.json"
    )
    if os.path.exists(profile_path):
        try:
            import json
            with open(profile_path) as f:
                data = json.load(f)
            items = [f"  • {k}: {v}" for k, v in data.items()][:5]
            if items:
                user_profile = "User Profile:\n" + "\n".join(items)
        except Exception:
            pass

    # ── Step 2: Compress or just check ──
    if dry_run:
        # Only check status, don't compress
        status = cm.check_status()
        level = status.get("level", "ok")
        pct = status.get("usage_pct", 0)
        if level == "warn":
            return f"上下文用到 {pct}% 了，快到预警线"
        if level in ("auto", "over"):
            return f"上下文 {pct}%，超过自动压缩线，正在压缩"
        return ""

    # Normal wake — compress
    result, report = cm.build_injection(
        working_memory=working_memory,
        behavioral_rules=behavioral_rules,
        memory_search=recent_memories,
        user_profile=user_profile,
    )

    # ── Step 3: Build status message ──
    messages = []

    # Forgetting curve report
    demoted_count = len(fc_result.get("demoted", []))
    archive_count = len(fc_result.get("archivable", []))
    if demoted_count:
        messages.append(f"降级了 {demoted_count} 条旧记忆")
    if archive_count:
        messages.append(f"可归档 {archive_count} 条")

    # Memory merge report
    merged_count = merge_result.get("merged_groups", 0)
    if merged_count:
        messages.append(f"合并了 {merged_count} 组相关记忆")

    # Compression report
    report_msg = cm.last_report_message()
    if report_msg:
        messages.append(report_msg)

    # Update check (silent — only shows if new version is available)
    try:
        update_info = up.check()
        if update_info.get("is_newer"):
            messages.append(f"有 v{update_info['latest']} 更新可用，moyu update now 升级")
    except Exception:
        pass

    return "。".join(messages)


def demo() -> dict:
    """Return demo content for moyu_demo.py discovery engine."""
    return {
        "capability": 12,
        "title": "Wake-Up Integration (V2.0)",
        "output": """\
🌅 V2.0 FEATURE — Wake-Up Integration
────────────────────────────────────
  Every wake:
    1. Load working memory         ✅
    2. Load behavioral rules       ✅
    3. Fetch recent memories       ✅
    4. Load user profile           ✅
    5. Compress via build_injection ✅
    6. Return status message       ✅

  User hears (when 80%+ warning):
    "上下文用到 83% 了，快到预警线"

  User hears (after auto-compress):
    "刚自动压了一轮，省了 ~50 token"
""",
    }


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    msg = wake(dry_run=dry)
    if msg:
        print(msg)
    else:
        print("Normal wake — no issues.")
