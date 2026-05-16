#!/usr/bin/env python3
"""
session_bridge.py — MOYU Session Bridge (V2.1)

Bridges conversations across sessions with TWO coordinated approaches:
  1. Round-based logging (user text + assistant summary, max 3 rounds)
  2. Turn-based logging (summary only, max 10 turns, legacy)

Auto-syncs to:
  - prefill.json (Hermes system injection — highest reliability)
  - current_context.md (readable fallback)

Usage:
    python3 session_bridge.py status              # Show current bridge state
    python3 session_bridge.py round <user> <asst>  # Manually log a round
    python3 session_bridge.py log <summary>        # (legacy) log a turn
    python3 session_bridge.py sync                 # Force re-sync all outputs
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

STORAGE = Path(os.environ.get(
    "MOYU_STORAGE", str(Path(__file__).parent / "memory_data")))
BRIDGE_PATH = STORAGE / "session_bridge.json"

# ── Sync targets ──
DEFAULT_PREFILL = Path.home() / ".hermes" / "prefill.json"
DEFAULT_CONTEXT_MD = Path.home() / "Documents" / "MoBai" / "current_context.md"

MAX_ROUNDS = 3
MAX_TURNS = 10


# ==================== Internal Helpers ====================

def _default_data() -> dict:
    return {
        "last_session_id": None,
        "last_updated": None,
        "topic": None,
        "key_points": [],
        "user_intent": None,
        "pending_tasks": [],
        "conversation_count": 0,
        "rounds": [],
        "turns": [],
    }


def _load() -> dict:
    if BRIDGE_PATH.exists():
        try:
            with open(BRIDGE_PATH) as f:
                data = json.load(f)
            # Ensure new keys exist
            if "rounds" not in data:
                data["rounds"] = []
            if "turns" not in data:
                data["turns"] = []
            return data
        except (json.JSONDecodeError, Exception):
            pass
    return _default_data()


def _save(data: dict):
    STORAGE.mkdir(parents=True, exist_ok=True)
    with open(BRIDGE_PATH, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==================== Core API (backward compat) ====================

def update(topic: str = None, key_points: list = None,
           user_intent: str = None, pending_tasks: list = None):
    """Save a snapshot of the current session (legacy API)."""
    data = _load()
    data["last_session_id"] = f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    data["last_updated"] = datetime.now().isoformat()
    data["conversation_count"] = data.get("conversation_count", 0) + 1
    if topic:
        data["topic"] = topic
    if key_points:
        data["key_points"] = key_points[:5]
    if user_intent:
        data["user_intent"] = user_intent
    if pending_tasks is not None:
        data["pending_tasks"] = pending_tasks[:3]
    _save(data)


def load() -> dict:
    return _load()


def inject_format() -> str:
    """Returns a short string for context injection (legacy format)."""
    data = _load()
    if not data.get("topic"):
        return ""
    lines = [f"上次会话主题：{data['topic']}"]
    if data.get("key_points"):
        lines.append("关键内容：")
        for kp in data["key_points"]:
            lines.append(f"  • {kp}")
    if data.get("pending_tasks"):
        lines.append(f"待办：{'、'.join(data['pending_tasks'])}")
    if data.get("user_intent"):
        lines.append(f"意向：{data['user_intent']}")
    return "\n".join(lines)


# ==================== V2.1: Round-based logging ====================

def log_round(user_text: str, assistant_summary: str,
              snapshot: dict = None):
    """
    Log one conversation round. Appends to rounds array (max MAX_ROUNDS),
    syncs to prefill.json and current_context.md.

    Call this at the end of every conversation turn.
    """
    data = _load()

    _ts = datetime.now().isoformat(timespec="minutes")

    round_entry = {
        "ts": _ts,
        "user": user_text,
        "assistant": assistant_summary,
    }
    if snapshot:
        round_entry["snapshot"] = snapshot

    rounds = data.get("rounds", [])
    rounds.append(round_entry)
    if len(rounds) > MAX_ROUNDS:
        rounds = rounds[-MAX_ROUNDS:]
    data["rounds"] = rounds

    # Also update legacy topic/key_points from last round
    data["topic"] = data.get("topic") or (
        user_text[:60] + "…" if len(user_text) > 60 else user_text)
    data["last_updated"] = _ts
    data["conversation_count"] = data.get("conversation_count", 0) + 1

    _save(data)

    # Sync all output formats
    _sync_all(data)


def log_turn(summary: str):
    """Legacy: log a turn summary (max 10)."""
    data = _load()
    _ts = datetime.now().isoformat()
    turns = data.get("turns", [])
    turns.append({"ts": _ts, "summary": summary})
    if len(turns) > MAX_TURNS:
        turns = turns[-MAX_TURNS:]
    data["turns"] = turns
    data["last_updated"] = _ts
    _save(data)
    _sync_all(data)


# ==================== Sync to external formats ====================

def _sync_all(data: dict):
    """Sync bridge data to all external targets."""
    _sync_to_prefill(data)
    _sync_to_context_md(data)


def _sync_to_prefill(data: dict):
    """
    Write ~/.hermes/prefill.json in Hermes native format.

    Structure:
      [0] system — 10-turn summary
      [1..] user/assistant — 3-round conversation (user text verbatim, asst compressed)
    """
    lines = []

    # System: 10-turn summary
    turns = data.get("turns", [])
    if turns:
        lines.append("📋 跨会话摘要（最近10轮）")
        for t in turns[-MAX_TURNS:]:
            ts = t.get("ts", "")[5:16] if t.get("ts") else ""
            summary = t.get("summary", "")
            lines.append(f"  ({ts}) {summary[:120]}")
    else:
        lines.append("📋 跨会话摘要")
        lines.append("  （暂无）")

    prefill = [{"role": "system", "content": "\n".join(lines)}]

    # User/assistant: 3 complete rounds
    rounds = data.get("rounds", [])
    for r in rounds:
        if r.get("user"):
            prefill.append({"role": "user", "content": r["user"]})
        if r.get("assistant"):
            prefill.append({"role": "assistant", "content": r["assistant"]})

    # Write
    prefill_path = _prefill_path()
    prefill_path.parent.mkdir(parents=True, exist_ok=True)
    with open(prefill_path, 'w') as f:
        json.dump(prefill, f, ensure_ascii=False, indent=2)


def _sync_to_context_md(data: dict):
    """Write ~/Documents/MoBai/current_context.md as readable conversation log."""
    rounds = data.get("rounds", [])
    if not rounds:
        return

    lines = [
        "📜 前置对话（最近3轮，用户消息原文保留，墨白回复已压缩）",
        "──────────────────────────────────────────────────",
    ]
    for r in rounds:
        ts = r.get("ts", "")
        if r.get("user"):
            lines.append(f"[{ts}] 用户：{r['user']}")
        if r.get("assistant"):
            lines.append(f"[{ts}] 墨白：{r['assistant']}")
        lines.append("")

    lines.append("---")
    lines.append(f"_最后更新: {data.get('last_updated', '')}_")

    md_path = _context_md_path()
    md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, 'w') as f:
        f.write("\n".join(lines) + "\n")


def _prefill_path() -> Path:
    env = os.environ.get("MOYU_PREFILL_PATH")
    if env:
        return Path(env)
    return DEFAULT_PREFILL


def _context_md_path() -> Path:
    env = os.environ.get("MOYU_CONTEXT_MD_PATH")
    if env:
        return Path(env)
    return DEFAULT_CONTEXT_MD


# ==================== Display ====================

def status():
    """Print readable status."""
    data = _load()
    print(f"\n🌉 MOYU Session Bridge  V2.1")
    print("=" * 50)
    print(f"  Session count:  {data.get('conversation_count', 0)}")
    last_up = data.get('last_updated')
    print(f"  Last updated:   {last_up[:16] if last_up else 'never'}")
    print(f"  Topic:          {data.get('topic', '—') or '—'}")

    rounds = data.get("rounds", [])
    print(f"  Rounds:         {len(rounds)} / {MAX_ROUNDS}")
    if rounds:
        for r in rounds:
            ts = r.get("ts", "")
            user_preview = r.get("user", "")[:50]
            asst_preview = r.get("assistant", "")[:50]
            print(f"    [{ts}] U: {user_preview}…" if len(user_preview) == 50 else
                  f"    [{ts}] U: {user_preview}")
            print(f"          A: {asst_preview}…" if len(asst_preview) == 50 else
                  f"          A: {asst_preview}")
            if r.get("snapshot"):
                print(f"          📸 snapshot: {list(r['snapshot'].keys())}")

    turns = data.get("turns", [])
    if turns:
        print(f"  Turns (legacy): {len(turns)} / {MAX_TURNS}")

    # Check sync targets
    prefill = _prefill_path()
    ctx = _context_md_path()
    print(f"  prefill.json:   {'✅' if prefill.exists() else '❌'} {prefill}")
    print(f"  current_context: {'✅' if ctx.exists() else '❌'} {ctx}")
    print()


def demo() -> dict:
    return {
        "capability": 15,
        "title": "Session Bridge (V2.1)",
        "output": """\
🌉 V2.1 FEATURE — Session Bridge
────────────────────────────────────
  log_round(user_text, assistant_summary) → 3-round storage + prefill + context.md
  log_turn(summary) → 10-turn legacy storage
  Auto-syncs to ~/.hermes/prefill.json for system-level injection
  Auto-syncs to ~/Documents/MoBai/current_context.md for readable fallback
  New window sees conversation as if it never ended.""",
    }


# ==================== CLI ====================

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "status":
        status()

    elif cmd == "round":
        # round "<user>" "<assistant>"
        user = args[1] if len(args) > 1 else ""
        asst = args[2] if len(args) > 2 else ""
        log_round(user, asst)
        print("✅ Round logged")

    elif cmd == "log":
        summary = " ".join(args[1:]) if len(args) > 1 else ""
        log_turn(summary)
        print("✅ Turn logged (legacy)")

    elif cmd == "save":
        topic = input("Topic: ") if sys.stdin.isatty() else "MOYU V2.1"
        update(topic=topic)
        print("✅ Session bridge updated")

    elif cmd == "sync":
        data = _load()
        _sync_all(data)
        print("✅ Re-synced all outputs")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
