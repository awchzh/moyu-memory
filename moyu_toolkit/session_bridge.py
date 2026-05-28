#!/usr/bin/env python3
"""
session_bridge.py — MOYU Session Bridge (V2.2)

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

from moyu_toolkit._moyu_paths import get_default_storage
STORAGE = Path(get_default_storage())
BRIDGE_PATH = STORAGE / "session_bridge.json"

# ── Sync targets ──
DEFAULT_PREFILL = Path.home() / ".hermes" / "prefill.json"
DEFAULT_CONTEXT_MD = Path.home() / "Documents" / "MoBai" / "current_context.md"

MAX_ROUNDS = 3
MAX_TURNS = 10

# ── Pseudo-signal injection blacklist ──
# Cheap patterns that indicate fake system directives or signal pollution
_PSEUDO_SIGNAL_PATTERNS = [
    "<artificial>",
    "<|im_start|>",
    "<|im_end|>",
    "[system]",
    "[/system]",
    "[END OF CONTEXT]",
    "[START OF CONTEXT]",
]


def _filter_pseudo_signals(text: str) -> str:
    """Strip common pseudo-signal injection markers from prefill content."""
    import re
    for pattern in _PSEUDO_SIGNAL_PATTERNS:
        text = text.replace(pattern, "[blocked]")
    # Strip lines with 3+ identical emoji (pollution attempts)
    text = re.sub(
        r'^([\U0001F300-\U0001F9FF])\1{2,}$',
        '',
        text,
        flags=re.MULTILINE,
    )
    return text


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
        "decisions": [],
        "pending": [],
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
            if "decisions" not in data:
                data["decisions"] = []
            if "pending" not in data:
                data["pending"] = []
            return data
        except (json.JSONDecodeError, Exception):
            pass
    return _default_data()


def _save(data: dict):
    STORAGE.mkdir(parents=True, exist_ok=True)
    # 原子写入：先写临时文件，再替换
    tmp_path = BRIDGE_PATH.with_suffix('.json.tmp')
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, BRIDGE_PATH)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


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


def format_context_summary() -> str:
    """Returns a short string for context snippet (legacy format)."""
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


def _generate_next_points(data: dict) -> str:
    """Generate compact behavioral points (≤3 items) for next-session prefill."""
    parts = []
    for d in (data.get("decisions") or [])[-3:]:
        parts.append(f"决定：{d[:80]}")
        if len(parts) >= 2:
            break
    for p in (data.get("pending") or [])[:2]:
        if len(parts) < 3:
            parts.append(f"待办：{p[:80]}")
    topic = data.get("topic", "")
    if topic and not parts:
        parts.append(f"上次：{topic[:80]}")
    return " | ".join(parts) if parts else ""


MAX_STATE_ITEMS = 10


def add_decision(text: str):
    """Append a decision. Capped at MAX_STATE_ITEMS."""
    data = _load()
    if "decisions" not in data:
        data["decisions"] = []
    data["decisions"].append(text)
    if len(data["decisions"]) > MAX_STATE_ITEMS:
        data["decisions"] = data["decisions"][-MAX_STATE_ITEMS:]
    data["last_updated"] = datetime.now().isoformat()
    _save(data)
    _sync_to_state_file(data)


def add_pending(text: str):
    """Append a pending item. Capped at MAX_STATE_ITEMS."""
    data = _load()
    if "pending" not in data:
        data["pending"] = []
    data["pending"].append(text)
    if len(data["pending"]) > MAX_STATE_ITEMS:
        data["pending"] = data["pending"][-MAX_STATE_ITEMS:]
    data["last_updated"] = datetime.now().isoformat()
    _save(data)
    _sync_to_state_file(data)


def remove_pending(text: str):
    """Remove a pending item by exact text match."""
    data = _load()
    if "pending" not in data:
        return
    data["pending"] = [p for p in data["pending"] if p != text]
    data["last_updated"] = datetime.now().isoformat()
    _save(data)
    _sync_to_state_file(data)


def format_state_summary() -> str:
    """Return a one-line state summary: topic, decisions, pending.
    Self-contained, reads from bridge data only."""
    data = _load()
    parts = []

    if data.get("topic"):
        parts.append(f"上次聊到「{data['topic']}」")

    decisions = data.get("decisions", [])
    if decisions:
        parts.append(f"已有决定：{'；'.join(decisions[-3:])}")

    pending = data.get("pending", [])
    if pending:
        pending_str = "、".join(pending[:3])
        if len(pending) > 3:
            pending_str += f" 等{len(pending)}项"
        parts.append(f"待办：{pending_str}")

    if parts:
        return "🧠 " + " | ".join(parts)
    return ""


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
    _sync_to_state_file(data)


def _sync_to_state_file(data: dict):
    """Write ~/.moyu/session_state.json — generic, Agent-agnostic state file.
    
    Any Agent that reads this file at startup can pick up the last session state.
    This is the foundation of the "prompt injection" approach.
    """
    state_path = Path.home() / ".moyu" / "session_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "topic": data.get("topic"),
        "decisions": data.get("decisions", []),
        "pending": data.get("pending", []),
        "round_count": data.get("conversation_count", 0),
        "last_updated": data.get("last_updated"),
    }
    state_summary = format_state_summary()

    with open(state_path, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    # Also write an easy-to-read summary
    summary_path = Path.home() / ".moyu" / "session_summary.txt"
    with open(summary_path, "w") as f:
        f.write(state_summary or "")


def generate_session_prompt() -> str:
    """Generate a system prompt snippet that users can paste into their Agent's
    system prompt configuration.

    The prompt tells the Agent to read ~/.moyu/session_state.json at startup
    and use its content to continue the conversation from where it left off.

    Returns the prompt text as a string.
    """
    prompt = r"""## Session Continuation (MOYU)

When starting a new conversation, read ~/.moyu/session_state.json at the very beginning.
If the file exists and has content, use it to understand the context of the previous session.

The file contains:
- "topic": what the previous conversation was about
- "decisions": key decisions made during previous sessions (most recent first)
- "pending": items still waiting to be addressed or completed
- "round_count": total number of conversation rounds across all sessions

If the file exists, start your first response by naturally acknowledging the
previous session's context — mention the topic, any relevant decisions, and
any pending items that should be followed up.

If the file does not exist or is empty, proceed as a normal first conversation.
"""
    return prompt.strip()


def write_session_prompt():
    """Write the generated session prompt to ~/.moyu/session_prompt.md.
    
    Users can read this file and paste its content into their Agent's
    system prompt configuration for automatic session continuation.
    """
    prompt_path = Path.home() / ".moyu" / "session_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(generate_session_prompt() + "\n")


def _sync_to_prefill(data: dict):
    """
    Write ~/.hermes/prefill.json in Hermes native format.

    Structure:
      [0] system — state summary + 10-turn summary
      [1..] user/assistant — 3-round conversation (user text verbatim, asst compressed)
    """
    lines = []

    # State summary (V2.2)
    try:
        summary = format_state_summary()
        if summary:
            lines.append(summary)
            lines.append("")
    except Exception:
        pass

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

    # Next-session behavioral points (compact, ≤3 items)
    try:
        next_pts = _generate_next_points(data)
        if next_pts:
            lines.append("")
            lines.append(f"🧠 {next_pts}")
    except Exception:
        pass

    prefill = [{"role": "system", "content": "\n".join(lines)}]

    # User/assistant: 3 complete rounds
    rounds = data.get("rounds", [])
    for r in rounds:
        if r.get("user"):
            prefill.append({"role": "user", "content": r["user"]})
        if r.get("assistant"):
            prefill.append({"role": "assistant", "content": r["assistant"]})

    # Also filter user/assistant content through pseudo-signal filter
    for m in prefill:
        if m.get("content"):
            m["content"] = _filter_pseudo_signals(m["content"])

    # Write — with content security gate
    prefill_path = _prefill_path()
    prefill_path.parent.mkdir(parents=True, exist_ok=True)

    # Scan all user and assistant messages for injection patterns before writing
    try:
        from moyu_toolkit.defense_toolkit.integrity_checker import content_scan
        clean_rounds = []
        for r in rounds:
            user_text = r.get("user", "")
            assistant_text = r.get("assistant", "")
            blocked = False
            if user_text:
                hits = content_scan(user_text)
                if hits:
                    print(f"🔴 Prefill Security Gate: blocked injection in user message — detected: {', '.join(hits)}", file=sys.stderr)
                    blocked = True
            if assistant_text and not blocked:
                hits = content_scan(assistant_text)
                if hits:
                    print(f"🔴 Prefill Security Gate: blocked injection in assistant summary — detected: {', '.join(hits)}", file=sys.stderr)
                    blocked = True
            if not blocked:
                clean_rounds.append(r)
            else:
                print(f"⚠️ Skipping round due to injection pattern", file=sys.stderr)
        # Rebuild prefill with clean rounds only
        prefill = [prefill[0]]  # keep system message
        for r in clean_rounds:
            if r.get("user"):
                prefill.append({"role": "user", "content": r["user"]})
            if r.get("assistant"):
                prefill.append({"role": "assistant", "content": r["assistant"]})
        if not clean_rounds:
            print(f"⚠️ Prefill: all rounds blocked by security gate — prefill will only contain system message", file=sys.stderr)
    except ImportError:
        pass
    except Exception:
        print(f"⚠️ Prefill Security Gate: content_scan failed — writing prefill without security scan", file=sys.stderr)

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
        try:
            path = Path(env).resolve()
            home = Path.home().resolve()
            project = Path(__file__).parent.parent.resolve()
            if path.is_relative_to(home) or path.is_relative_to(project):
                return path
            else:
                print(f"⚠️ MOYU_PREFILL_PATH 路径不在允许范围内，使用默认路径 {DEFAULT_PREFILL}", file=sys.stderr)
        except Exception:
            print(f"⚠️ MOYU_PREFILL_PATH 解析失败，使用默认路径 {DEFAULT_PREFILL}", file=sys.stderr)
    return DEFAULT_PREFILL


def _context_md_path() -> Path:
    env = os.environ.get("MOYU_CONTEXT_MD_PATH")
    if env:
        try:
            path = Path(env).resolve()
            home = Path.home().resolve()
            project = Path(__file__).parent.parent.resolve()
            if path.is_relative_to(home) or path.is_relative_to(project):
                return path
            else:
                print(f"⚠️ MOYU_CONTEXT_MD_PATH 路径不在允许范围内，使用默认路径 {DEFAULT_CONTEXT_MD}", file=sys.stderr)
        except Exception:
            print(f"⚠️ MOYU_CONTEXT_MD_PATH 解析失败，使用默认路径 {DEFAULT_CONTEXT_MD}", file=sys.stderr)
    return DEFAULT_CONTEXT_MD


# ==================== Display ====================

def status():
    """Print readable status."""
    data = _load()
    print(f"\n🌉 MOYU Session Bridge  V2.2")
    print("=" * 50)
    print(f"  Session count:  {data.get('conversation_count', 0)}")
    last_up = data.get('last_updated')
    print(f"  Last updated:   {last_up[:16] if last_up else 'never'}")
    print(f"  Topic:          {data.get('topic', '—') or '—'}")

    decisions = data.get("decisions", [])
    if decisions:
        latest = decisions[-1][:40] if decisions[-1] else "(empty)"
        print(f"  Decisions:      {len(decisions)} (latest: {latest})")
    pending = data.get("pending", [])
    if pending:
        print(f"  Pending:        {len(pending)} items")

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
        "title": "Session Bridge V2.2",
        "output": """\\
🌉 V2.2 FEATURE — Session Bridge
────────────────────────────────────
  log_round(user_text, assistant_summary) → 3-round storage + prefill + context.md
  log_turn(summary) → 10-turn legacy storage
  add_decision(text) / add_pending(text) / remove_pending(text) → state tracking
  format_state_summary() → one-line topic + decisions + pending
  Auto-syncs to ~/.hermes/prefill.json for system-level injection
  New window sees conversation and state as if it never ended.""",
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
        topic = input("Topic: ") if sys.stdin.isatty() else "MOYU V2.2"
        update(topic=topic)
        print("✅ Session bridge updated")

    elif cmd == "sync":
        data = _load()
        _sync_all(data)
        print("✅ Re-synced all outputs")

    elif cmd == "state":
        print(format_state_summary() or "（暂无状态）")

    elif cmd == "decision":
        add_decision(" ".join(args[1:]))
        print(f"✅ Decision recorded")

    elif cmd in ("pending", "add_pending"):
        add_pending(" ".join(args[1:]))
        print(f"✅ Pending added")

    elif cmd == "remove_pending":
        remove_pending(" ".join(args[1:]))
        print(f"✅ Pending removed")

    elif cmd == "prompt":
        prompt = generate_session_prompt()
        print(prompt)
        print()
        print("---")
        print("要保存到文件，运行：python3 session_bridge.py write-prompt")
        print("或将以上内容粘贴到你的 Agent 的 system prompt 配置中。")

    elif cmd in ("write-prompt", "init-prompt"):
        write_session_prompt()
        prompt_path = Path.home() / ".moyu" / "session_prompt.md"
        print(f"✅ Session prompt 已写入 {prompt_path}")
        print("将文件内容粘贴到你的 Agent 的 system prompt 配置中即可。")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
