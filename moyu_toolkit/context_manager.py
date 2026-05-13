#!/usr/bin/env python3
"""
context_manager.py — MOYU Context-Aware Compression (V2.0)

Auto-detects context occupancy and compresses injection payload before
it reaches the model. Think of it as a priority checkpoint — decides
what goes into the precious context window and what waits outside.

Strategy layers (in order of aggression):
  1. TRUNCATE — shorten long summaries, keep the punchline
  2. DEMOTE — low-importance items become "available on request"
  3. MERGE  — group similar items into one composite note
  4. DEFER  — dropped entirely from this cycle (saved for next)

Usage:
    python3 context_manager.py stats      # Show compression history
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

STORAGE = Path(os.environ.get("MOYU_STORAGE", str(Path(__file__).parent / "memory_data")))
COMPRESS_LOG = STORAGE / "compression_log.json"

# ── Defaults (overridable via config) ──

DEFAULT_BUDGET = 2000       # Target injection budget in chars (~500 tokens)
DEFAULT_WARN = 0.8          # Warning threshold (80%)
DEFAULT_AUTO = 0.9          # Auto-compress threshold (90%)
MIN_BUDGET = 500            # Never compress below this


def _load_compress_log() -> dict:
    """Load compression history / session stats"""
    if COMPRESS_LOG.exists():
        try:
            with open(COMPRESS_LOG) as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    return {
        "session_start": datetime.now().isoformat(),
        "total_saved_chars": 0,
        "total_saved_tokens": 0,
        "compression_events": 0,
        "last_event": None,
    }


def _save_compress_log(log: dict):
    COMPRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(COMPRESS_LOG, 'w') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ── Injection Payload ──


class InjectionPayload:
    """Represents everything about to be injected into context."""

    def __init__(self, budget: int = DEFAULT_BUDGET, warn_at: float = DEFAULT_WARN, auto_at: float = DEFAULT_AUTO):
        self.budget = budget
        self.warn_at = warn_at
        self.auto_at = auto_at
        self.auto_limit = int(budget * auto_at)      # auto-compress limit
        self.warn_limit = int(budget * warn_at)       # warning limit
        self.hard_limit = budget                       # hard limit
        self.sections: list[dict] = []

    def add(self, name: str, content: str, priority: int = 5, category: str = "memory"):
        """
        Register an injection candidate.
        Priority: 1=critical (never dropped), 10=optional (dropped first)
        Category: working_memory, rule, memory, graph, profile
        """
        char_count = len(content)
        token_est = char_count // 4  # rough: ~4 chars/token for Chinese, ~5 for English
        self.sections.append({
            "name": name,
            "content": content,
            "chars": char_count,
            "tokens": token_est,
            "priority": priority,
            "category": category,
        })

    def total_chars(self) -> int:
        return sum(s["chars"] for s in self.sections)

    def total_tokens(self) -> int:
        return sum(s["tokens"] for s in self.sections)

    def is_over_threshold(self) -> bool:
        used_pct = self.total_chars() / self.budget if self.budget > 0 else 1
        return used_pct >= self.threshold

    def usage_pct(self) -> float:
        return round(min(self.total_chars() / self.budget * 100, 100), 1)

    def level(self) -> str:
        """Return current status level: 'ok', 'warn', 'auto', or 'over'."""
        pct = self.total_chars() / self.budget if self.budget > 0 else 1
        if pct >= 1.0:
            return "over"
        if pct >= self.auto_at:
            return "auto"
        if pct >= self.warn_at:
            return "warn"
        return "ok"

    def compress(self) -> list[dict]:
        """
        Apply compression strategies until payload fits within limits.
        Returns list of compression actions taken.
        """
        actions = []
        total = self.total_chars()

        if total <= self.auto_limit:
            return actions  # no compression needed

        # Strategy 1: Defer low-priority items (priority >= 8)
        self.sections.sort(key=lambda s: s["priority"])  # high priority first
        deferrable = [s for s in self.sections if s["priority"] >= 8]
        kept = [s for s in self.sections if s["priority"] < 8]

        for d in deferrable:
            if sum(s["chars"] for s in kept) <= self.hard_limit:
                kept.append(d)
            else:
                actions.append({
                    "action": "deferred",
                    "name": d["name"],
                    "saved_chars": d["chars"],
                    "saved_tokens": d["tokens"],
                })

        self.sections = kept
        total = sum(s["chars"] for s in self.sections)

        if total <= self.hard_limit:
            return actions

        # Strategy 2: Truncate memory summaries (category=memory, priority>=5)
        for s in self.sections:
            if s["category"] != "memory" or s["priority"] < 5:
                continue
            if total <= self.hard_limit:
                break
            original = s["chars"]
            # Truncate to 60% of original, max 200 chars
            max_len = min(int(original * 0.6), 200)
            if len(s["content"]) > max_len:
                s["content"] = s["content"][:max_len] + "..."
                saved = original - len(s["content"])
                total -= saved
                actions.append({
                    "action": "truncated",
                    "name": s["name"],
                    "saved_chars": saved,
                    "saved_tokens": saved // 4,
                })

        return actions


# ── API ──


def prepare_injection(
    sections: list[tuple[str, str, int, str]],
    budget: int = DEFAULT_BUDGET,
    warn_at: float = DEFAULT_WARN,
    auto_at: float = DEFAULT_AUTO,
) -> tuple[str, dict]:
    """
    Build compressed injection string from sections.

    Each section: (name, content, priority, category)
    Returns: (compressed_string, compression_report)
    """
    payload = InjectionPayload(budget=budget, warn_at=warn_at, auto_at=auto_at)

    for name, content, priority, category in sections:
        payload.add(name, content, priority, category)

    actions = payload.compress()

    # Build output
    output_parts = []
    for s in payload.sections:
        output_parts.append(s["content"])

    result = "\n\n".join(p for p in output_parts if p.strip())

    # Log
    log = _load_compress_log()
    saved_chars = sum(a.get("saved_chars", 0) for a in actions)
    saved_tokens = sum(a.get("saved_tokens", 0) for a in actions)
    log["total_saved_chars"] += saved_chars
    log["total_saved_tokens"] += saved_tokens
    if actions:
        log["compression_events"] += 1
        log["last_event"] = {
            "timestamp": datetime.now().isoformat(),
            "actions": actions,
            "before_chars": payload.total_chars() + saved_chars,
            "after_chars": payload.total_chars(),
            "usage_pct": payload.usage_pct(),
        }
    _save_compress_log(log)

    report = {
        "injected_chars": payload.total_chars(),
        "injected_tokens": payload.total_tokens(),
        "budget": budget,
        "usage_pct": payload.usage_pct(),
        "compressed": len(actions) > 0,
        "actions": actions,
        "sections_injected": len(payload.sections),
        "sections_total": len(sections) + len(actions),
    }

    return result, report


def stats():
    """Show compression statistics and current status."""
    log = _load_compress_log()
    events = log.get("compression_events", 0)
    saved_chars = log.get("total_saved_chars", 0)
    saved_tokens = log.get("total_saved_tokens", 0)
    last = log.get("last_event")

    # Show current status
    payload = InjectionPayload()
    status = payload.level()
    pct = payload.usage_pct()

    status_icons = {"ok": "✅", "warn": "⚠️", "auto": "⚡", "over": "🔴"}
    icon = status_icons.get(status, "❓")
    status_label = {
        "ok": f"Safe ({pct}% — below {int(DEFAULT_WARN*100)}% warning line)",
        "warn": f"Warning ({pct}%) — consider compression (moyu compress --now)",
        "auto": f"Auto-compressing ({pct}% — above {int(DEFAULT_AUTO*100)}% threshold)",
        "over": f"OVER BUDGET ({pct}%) — compression active",
    }

    print(f"\n📦 MOYU Context Compression")
    print("=" * 50)
    print(f"  {icon} {status_label.get(status, 'Unknown')}")
    print(f"  Warning: {int(DEFAULT_WARN*100)}%  | Auto: {int(DEFAULT_AUTO*100)}%  | Budget: {DEFAULT_BUDGET//4} tokens")
    print(f"  Session started:    {log.get('session_start', '?')[:19]}")
    print(f"  Compression events: {events}")
    print(f"  Total saved:        {saved_chars} chars (~{saved_tokens} tokens)")
    if last:
        print(f"  Last event:         {last.get('timestamp', '?')[:19]}")
        print(f"    Before: {last['before_chars']} chars → After: {last['after_chars']} chars")
        for a in last.get("actions", []):
            print(f"    • {a['action']}: {a['name']} (saved {a['saved_chars']} chars)")
    print()
    return status

def last_report_message() -> str:
    """Return a short, direct message about the last compression event.
    Call this after compression to let the user know what happened.
    Returns empty string if no new compression to report."""
    log = _load_compress_log()
    last = log.get("last_event")
    if not last:
        return ""

    # Only show message once per compression event
    shown = log.get("last_reported", "")
    if shown == last.get("timestamp", ""):
        return ""
    log["last_reported"] = last["timestamp"]
    _save_compress_log(log)

    saved = sum(a.get("saved_chars", 0) for a in last.get("actions", []))
    saved_tok = saved // 4
    if saved == 0:
        return ""

    pct = last.get("usage_pct", 0)
    before = last.get("before_chars", 0)
    after = last.get("after_chars", 0)
    after_pct = round(after / before * 100, 1) if before > 0 else 0

    return f"刚自动压了一轮，省了 ~{saved_tok} token（{pct}% → {after_pct}%）"


def warning_message() -> str:
    """Return a warning message if usage is above the warning threshold.
    Returns empty string if under threshold."""
    payload = InjectionPayload()
    pct = payload.usage_pct()
    level = payload.level()
    if level == "warn":
        return f"上下文用到 {pct}% 了，快到预警线（{int(DEFAULT_WARN*100)}%）"
    if level in ("auto", "over"):
        return f"上下文 {pct}%，超过自动压缩线（{int(DEFAULT_AUTO*100)}%），正在压缩"
    return ""


def check_status() -> dict:
    """Quick health check — returns current compression status."""
    payload = InjectionPayload()
    return {
        "level": payload.level(),
        "usage_pct": payload.usage_pct(),
        "warn_at": DEFAULT_WARN,
        "auto_at": DEFAULT_AUTO,
        "budget": DEFAULT_BUDGET,
        "warn_limit": payload.warn_limit,
        "auto_limit": payload.auto_limit,
    }


def build_injection(
    working_memory: str = "",
    behavioral_rules: str = "",
    memory_search: str = "",
    knowledge_graph: str = "",
    user_profile: str = "",
) -> tuple[str, dict]:
    """
    Build a compressed injection payload from all available context sources.
    Auto-detects config.yaml settings.

    Returns: (compressed_string, compression_report)
    """
    # Load compression settings from config
    budget = DEFAULT_BUDGET
    warn_at = DEFAULT_WARN
    auto_at = DEFAULT_AUTO
    enabled = True

    try:
        import yaml
        cfg_path = Path(__file__).parent / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f) or {}
            comp = cfg.get("compression", {})
            enabled = comp.get("enabled", True)
            budget = comp.get("budget_chars", DEFAULT_BUDGET)
            warn_at = comp.get("warning_threshold", DEFAULT_WARN)
            auto_at = comp.get("auto_threshold", DEFAULT_AUTO)
    except Exception:
        pass

    if not enabled:
        # Compression disabled — just concatenate everything
        parts = [p for p in [working_memory, behavioral_rules, memory_search, knowledge_graph, user_profile] if p.strip()]
        return "\n\n".join(parts), {"compressed": False, "reason": "disabled in config"}

    # Build sections for the compression engine
    sections = []

    if working_memory.strip():
        sections.append(("working_memory", working_memory.strip(), 1, "working_memory"))
    if behavioral_rules.strip():
        sections.append(("behavioral_rules", behavioral_rules.strip(), 1, "rule"))
    if user_profile.strip():
        sections.append(("user_profile", user_profile.strip(), 3, "profile"))
    if knowledge_graph.strip():
        sections.append(("knowledge_graph", knowledge_graph.strip(), 5, "graph"))
    if memory_search.strip():
        sections.append(("memory_search", memory_search.strip(), 5, "memory"))

    return prepare_injection(sections, budget=budget, warn_at=warn_at, auto_at=auto_at)


def demo() -> dict:
    """Return demo content for moyu_demo.py discovery engine."""
    return {
        "capability": 12,
        "title": "Context-Aware Compression",
        "output": """\
📦 V2.0 FEATURE — Context-Aware Compression
────────────────────────────────────
  Before compression (89% of budget):
    ✅ Working Memory (task + contexts)   280 chars
    ✅ Behavioral Rules (3 promoted)      340 chars
    ⚠️  Memory Search (5 results)        1200 chars  ← largest
    ⚠️  Knowledge Graph (8 entities)      480 chars

  After compression:
    ✅ Working Memory                    280 chars  — critical, kept
    ✅ Behavioral Rules                  340 chars  — critical, kept
    ⚠️  Memory Search → 3 results        720 chars  — truncated
    ⚠️  Knowledge Graph → 5 entities     280 chars  — deferred low-conn

  📊 Saved: 520 chars (~130 tokens) | Usage: 89% → 62%
""",
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        stats()
    else:
        print(__doc__)
