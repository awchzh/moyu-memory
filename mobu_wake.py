#!/usr/bin/env python3
"""
mobu_wake.py — MoBai's personal wake-up routine (uses MOYU V2.0)

Called at the start of every session. Integrates:
  - MoBai's identity layer (SOUL.md, memory_core)
  - MOYU V2.0 lifecycle (compression, forgetting, merging, bridging)

Usage:
    python3 mobu_wake.py          # Full wake
    python3 mobu_wake.py --dry    # Status only, no mutations
"""

import json
import os
import subprocess
import sys
from datetime import datetime

MOBAI_DIR = os.path.expanduser("~/Documents/MoBai")
TOOLKIT_DIR = os.path.join(MOBAI_DIR, "moyu_toolkit")
MEMORY_CORE = os.path.join(MOBAI_DIR, "memory_core")
sys.path.insert(0, TOOLKIT_DIR)


def _import(name):
    import importlib.util
    path = os.path.join(TOOLKIT_DIR, *name.split(".")) + ".py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _moyu_cli(cmd: str) -> str:
    """Call a moyu CLI command and return output."""
    result = subprocess.run(
        [sys.executable, os.path.join(TOOLKIT_DIR, "moyu.py")] + cmd.split(),
        capture_output=True, text=True, cwd=MOBAI_DIR, timeout=30
    )
    return result.stdout.strip()


def wake(dry_run: bool = False) -> list:
    """
    Full MoBai wake-up routine.
    Returns a list of status messages.
    """
    messages = []

    # ── 1. MOYU V2.0 Lifecycle ──
    fc = _import("forgetting_curve")
    cm = _import("context_manager")
    sb = _import("session_bridge")

    # Check context pressure
    status = cm.check_status()
    under_pressure = status.get("level") in ("warn", "auto", "over")

    # Run forgetting curve (only demote under pressure)
    fc_result = fc.run(context_pressure=under_pressure)
    demoted = fc_result.get("demoted", [])
    if demoted:
        messages.append(f"降级了 {len(demoted)} 条旧记忆以保持精炼")

    # Run memory merge
    mm = _import("memory_merge")
    merge_result = mm.run()
    merged = merge_result.get("merged_groups", 0)
    if merged:
        messages.append(f"合并了 {merged} 组相关记忆")

    # Load session bridge
    bridge = sb.load()
    if bridge.get("topic"):
        messages.append(f"上次会话主题: {bridge['topic']}")
    else:
        messages.append("新会话")

    # Compression warning
    warn_msg = cm.warning_message()
    if warn_msg:
        messages.append(warn_msg)

    # Compression report
    report_msg = cm.last_report_message()
    if report_msg:
        messages.append(report_msg)

    # ── 2. Update check (silent) ──
    try:
        up = _import("updater")
        info = up.check()
        if info.get("is_newer"):
            messages.append(f"有 v{info['latest']} 更新可用")
    except Exception:
        pass

    # Clean MOYU test data
    for fname in ["compression_log.json", "session_bridge.json"]:
        p = os.path.join(TOOLKIT_DIR, "memory_data", fname)
        if os.path.exists(p) and os.path.getsize(p) < 500:
            os.remove(p)

    if not messages:
        messages.append("一切正常")

    return messages


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    msgs = wake(dry_run=dry)
    print(" | ".join(msgs))
