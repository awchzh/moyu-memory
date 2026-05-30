#!/usr/bin/env python3
"""
active_context.py — MOYU Working Memory

Solves the problem of losing \"what is currently being done\" after context compression.
Stored as a standalone file, untouched by any compression mechanism.

Usage:
    python3 active_context.py status        # View current working memory
    python3 active_context.py start         # Start a new session
    python3 active_context.py set task ...  # Set the current task
    python3 active_context.py add ...       # Record key context
    python3 active_context.py todo add ...  # Add a todo item
    python3 active_context.py todo done ..  # Mark a todo as done
    python3 active_context.py context       # Get context format
"""

import json
import os
from datetime import datetime
from moyu_toolkit._storage import storage


def _default() -> dict:
    return {
        "session_start": datetime.now().isoformat(),
        "task": "",
        "contexts": [],
        "todos": [],
        "last_updated": datetime.now().isoformat()
    }


def start_session():
    storage.write("active_context.json", _default())
    print("✅ New session started")


def set_task(task: str):
    ctx = storage.read_or_default("active_context.json", _default())
    ctx["task"] = task
    ctx["last_updated"] = datetime.now().isoformat()
    storage.write("active_context.json", ctx)
    print(f"✅ Task: {task}")


def add_context(text: str):
    ctx = storage.read_or_default("active_context.json", _default())
    ctx["contexts"].append({"text": text[:200], "timestamp": datetime.now().isoformat()})
    if len(ctx["contexts"]) > 5:
        ctx["contexts"] = ctx["contexts"][-5:]
    ctx["last_updated"] = datetime.now().isoformat()
    storage.write("active_context.json", ctx)
    print(f"✅ Context recorded")


class Todo:
    @staticmethod
    def add(text: str):
        ctx = storage.read_or_default("active_context.json", _default())
        ctx["todos"].append({"id": len(ctx["todos"]) + 1, "text": text[:200], "done": False,
                             "created": datetime.now().isoformat()})
        ctx["last_updated"] = datetime.now().isoformat()
        storage.write("active_context.json", ctx)
        print(f"✅ Todo: {text[:60]}")

    @staticmethod
    def done(tid: str):
        if not tid:
            print("⚠️  Error: empty todo id")
            return
        ctx = storage.read_or_default("active_context.json", _default())
        found = False
        for t in ctx["todos"]:
            if str(t["id"]) == tid or t["text"].startswith(tid):
                t["done"] = True
                t["completed_at"] = datetime.now().isoformat()
                found = True
        ctx["last_updated"] = datetime.now().isoformat()
        storage.write("active_context.json", ctx)
        if found:
            print(f"✅ Completed: {tid}")
        else:
            print(f"⚠️  Todo not found: {tid}")


def format_context() -> str:
    ctx = storage.read_or_default("active_context.json", _default())
    lines = ["## [Working Memory — Current Session Context]\n"]
    if ctx["task"]:
        lines.append(f"**Current Task:** {ctx['task']}\n")
    if ctx["contexts"]:
        lines.append("**Key Context:**")
        for c in ctx["contexts"]:
            ts = c.get("timestamp", "")[:16]
            lines.append(f"- [{ts}] {c['text']}")
        lines.append("")
    pending = [t for t in ctx["todos"] if not t["done"]]
    if pending:
        lines.append("**Todos:**")
        for t in pending:
            lines.append(f"- [ ] {t['text']}")
        lines.append("")
    lines.append(f"*Started {ctx['session_start'][:19]}, last updated {ctx['last_updated'][:19]}*")
    return "\n".join(lines)


def status():
    ctx = storage.read_or_default("active_context.json", _default())
    print(f"\n📋 Working Memory")
    print("=" * 50)
    print(f"Session: {ctx['session_start'][:19]}")
    print(f"Task: {ctx['task'] or 'none'}")
    print(f"Contexts: {len(ctx['contexts'])}")
    print(f"Todos: {len(ctx['todos'])} items")
    for t in ctx['todos']:
        m = "✅" if t["done"] else "⬜"
        print(f"  {m} {t['text'][:80]}")


def demo() -> dict:
    """Return demo content for moyu_demo.py discovery engine."""
    return {
        "capability": 2,
        "title": "Working Memory",
        "output": """🧠 2/6  DEMO
────────────────────────────────────
  [Recovered Working Memory]
  Current task: Track smart photo frame MVP progress
  Todos:
    ✅ Confirm A/B roadmap decision
    ✅ Schedule first review meeting
    ⬜ Push weather plugin development
    ⬜ Prepare prototype demo by end of month

  Key context:
    • Zhang Yi is backend dev, building Flask API
    • Boss Li wants prototype by end of month

  Survives context compression. 100 rounds in, open working
  memory and you still know what you're doing.""",
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: status | start | set task | add | todo")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "status": status()
    elif cmd == "start": start_session()
    elif cmd == "set" and len(sys.argv) >= 4 and sys.argv[2] == "task":
        set_task(" ".join(sys.argv[3:]))
    elif cmd == "add":
        add_context(" ".join(sys.argv[2:]))
    elif cmd == "todo" and len(sys.argv) >= 4:
        Todo.add(" ".join(sys.argv[3:])) if sys.argv[2] == "add" else Todo.done(" ".join(sys.argv[3:]))
    elif cmd == "context":
        print(format_context())
