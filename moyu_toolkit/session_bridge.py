#!/usr/bin/env python3
"""
session_bridge.py — MOYU Session Bridge (V2.0)

Bridges conversations across sessions. On wake, the agent reads
this file to know what was happening last time. If the user wants
to continue, key points are injected into context.

Usage:
    python3 session_bridge.py status       # Show current bridge state
    python3 session_bridge.py save         # Save snapshot from active context
"""

import json
import os
from datetime import datetime
from pathlib import Path

STORAGE = Path(os.environ.get("MOYU_STORAGE", str(Path(__file__).parent / "memory_data")))
BRIDGE_PATH = STORAGE / "session_bridge.json"


def _load() -> dict:
    if BRIDGE_PATH.exists():
        try:
            with open(BRIDGE_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    return {
        "last_session_id": None,
        "last_updated": None,
        "topic": None,
        "key_points": [],
        "user_intent": None,
        "pending_tasks": [],
        "conversation_count": 0,
    }


def _save(data: dict):
    STORAGE.mkdir(parents=True, exist_ok=True)
    with open(BRIDGE_PATH, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update(topic: str = None, key_points: list = None,
           user_intent: str = None, pending_tasks: list = None):
    """
    Save a snapshot of the current session. Call this before session ends.
    """
    data = _load()
    data["last_session_id"] = f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    data["last_updated"] = datetime.now().isoformat()
    data["conversation_count"] = data.get("conversation_count", 0) + 1
    if topic:
        data["topic"] = topic
    if key_points:
        data["key_points"] = key_points[:5]  # keep max 5
    if user_intent:
        data["user_intent"] = user_intent
    if pending_tasks is not None:
        data["pending_tasks"] = pending_tasks[:3]
    _save(data)


def load() -> dict:
    """Load bridge data. Returns dict with last session info or empty defaults."""
    return _load()


def inject_format() -> str:
    """Returns a short string for context injection if there's an active bridge."""
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


def status():
    """Print readable status."""
    data = _load()
    print(f"\n🌉 MOYU Session Bridge")
    print("=" * 50)
    print(f"  Session count:  {data.get('conversation_count', 0)}")
    last_up = data.get('last_updated')
    print(f"  Last updated:   {last_up[:16] if last_up else 'never'}")
    print(f"  Topic:          {data.get('topic', '—') or '—'}")
    if data.get("key_points"):
        print(f"  Key points:")
        for kp in data["key_points"]:
            print(f"    • {kp}")
    if data.get("pending_tasks"):
        print(f"  Pending:        {', '.join(data['pending_tasks'])}")
    print()


def demo() -> dict:
    return {
        "capability": 15,
        "title": "Session Bridge (V2.0)",
        "output": """\
🌉 V2.0 FEATURE — Session Bridge
────────────────────────────────────
  New session → reads last session context
  If user says "continue" → inject key points
  If user says fresh topic → ignore, no overhead

  Last session:
    Topic: MOYU V2.0 development
    Key points:
      • Forgetting curve is context-pressure driven
      • Memory merge uses keyword overlap
    Pending: finish merge integration
""",
    }


if __name__ == "__main__":
    import sys
    if "status" in sys.argv:
        status()
    elif "save" in sys.argv:
        topic = input("Topic: ") if sys.stdin.isatty() else "MOYU V2.0"
        update(topic=topic)
        print("✅ Session bridge updated")
    else:
        print(__doc__)
