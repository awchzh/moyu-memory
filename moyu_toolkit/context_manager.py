#!/usr/bin/env python3
"""
context_manager.py — MOYU Context-Aware Compression (V2.2)

Two-tier graduated compression:
  Mild (70%+)  — truncate long memories, defer low-priority items
  Auto (85%+)  — aggressive: demote non-critical, aggressive truncate

Provider context warning:
  Auto-detects the user's Agent (Hermes/Claude Code/OpenClaw/Cursor/Continue).
  Reads its local session data (SQLite/JSONL) to determine real context usage.
  When usage exceeds warn_threshold (default 70%), warning_message() returns an
  alert that gets auto-appended to behavioral_rules via build_injection().

Config (config.yaml → compression):
  enabled: true
  budget_chars: 2000
  mild_threshold: 0.7
  auto_threshold: 0.85
  warn_threshold: 0.7   → warn user when Hermes window reaches 70%

Usage:
    python3 context_manager.py stats      # Show compression history
    python3 context_manager.py config     # Show current config
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

STORAGE = Path(os.environ.get("MOYU_STORAGE", str(Path(__file__).parent / "memory_data")))
REFS_DIR = STORAGE / "refs"           # Truncated original content, for drill-down
COMPRESS_LOG = STORAGE / "compression_log.json"

# ── Defaults (overridable via config) ──

DEFAULT_BUDGET = 2000       # Target injection budget in chars (~500 tokens)
DEFAULT_WARN = 0.7          # Warning threshold (70%) — display only
DEFAULT_MILD = 0.7          # Mild compression (70%) — truncate/defer
DEFAULT_AUTO = 0.85         # Aggressive compression (85%) — demote/truncate hard
MIN_BUDGET = 500            # Never compress below this

ALLOWED_KEYS = {"mild_threshold", "auto_threshold", "budget_chars", "enabled", "warn_threshold", "warn_language"}


# ── Refs (compression→traceability drill-down) ──


DELETE_REF_DAYS = 7  # Auto-clean refs older than this


def _save_ref(name: str, content: str):
    """Save original content before truncation, so agent can drill down."""
    safe_name = name.replace("/", "_").replace("\\", "_").replace(" ", "_")
    path = REFS_DIR / f"{safe_name}.ref"
    with open(path, "w") as f:
        f.write(content)
    return str(path)


def _list_refs() -> list[str]:
    """List available ref files."""
    if not REFS_DIR.exists():
        return []
    return sorted(f.name for f in REFS_DIR.iterdir() if f.suffix == ".ref")


def read_ref(name: str):
    """Read a ref file by name (with or without .ref suffix). Returns content or None."""
    safe_name = name.replace("/", "_").replace("\\", "_").replace(" ", "_")
    if not safe_name.endswith(".ref"):
        safe_name += ".ref"
    path = REFS_DIR / safe_name
    if path.exists():
        return path.read_text()
    return None


def delete_ref(name: str):
    """Delete a ref file."""
    safe_name = name.replace("/", "_").replace("\\", "_").replace(" ", "_")
    if not safe_name.endswith(".ref"):
        safe_name += ".ref"
    path = REFS_DIR / safe_name
    if path.exists():
        path.unlink()


def _cleanup_old_refs():
    """Remove ref files older than DELETE_REF_DAYS to prevent unbounded growth."""
    if not REFS_DIR.exists():
        return
    now = datetime.now()
    for f in REFS_DIR.iterdir():
        if f.suffix != ".ref":
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if (now - mtime).days >= DELETE_REF_DAYS:
                f.unlink()
        except Exception:
            continue


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
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    COMPRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(COMPRESS_LOG, 'w') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _load_compression_config() -> dict:
    """Load compression settings from config.yaml, with defaults."""
    cfg = {}
    try:
        import yaml
        cfg_path = Path(__file__).parent / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path) as f:
                raw = yaml.safe_load(f) or {}
            cfg = raw.get("compression", {})
    except Exception:
        pass
    return {
        "enabled": cfg.get("enabled", True),
        "budget_chars": cfg.get("budget_chars", DEFAULT_BUDGET),
        "mild_threshold": cfg.get("mild_threshold", DEFAULT_MILD),
        "auto_threshold": cfg.get("auto_threshold", DEFAULT_AUTO),
        "warn_threshold": cfg.get("warn_threshold", DEFAULT_WARN),
        "warn_language": cfg.get("warn_language", "en"),
    }


# ── Injection Payload ──


class InjectionPayload:
    """Represents everything about to be injected into context."""

    def __init__(self, budget: int = DEFAULT_BUDGET,
                 mild_at: float = DEFAULT_MILD,
                 auto_at: float = DEFAULT_AUTO):
        self.budget = budget
        self.mild_at = mild_at
        self.auto_at = auto_at
        self.mild_limit = int(budget * mild_at)
        self.auto_limit = int(budget * auto_at)
        self.hard_limit = budget
        self.sections: list[dict] = []

    def add(self, name: str, content: str, priority: int = 5, category: str = "memory"):
        """
        Register an injection candidate.
        Priority: 1=critical (never dropped), 10=optional (dropped first)
        Category: working_memory, rule, memory, graph, profile
        """
        char_count = len(content)
        token_est = char_count // 4
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

    def usage_pct(self) -> float:
        return round(min(self.total_chars() / self.budget * 100, 100), 1)

    def level(self) -> str:
        """Return current status level: 'ok', 'warn', 'mild', 'auto', or 'over'."""
        pct = self.total_chars() / self.budget if self.budget > 0 else 1
        if pct >= 1.0:
            return "over"
        if pct >= self.auto_at:
            return "auto"
        if pct >= self.mild_at:
            return "mild"
        if pct >= DEFAULT_WARN:
            return "warn"
        return "ok"

    def compress(self) -> list[dict]:
        """
        Two-tier graduated compression.

        Mild (≥ mild_threshold) — truncate long memories, defer priority >= 9
        Auto (≥ auto_threshold) — demote non-critical, aggressive truncate

        Returns list of compression actions taken.
        """
        actions = []
        total = self.total_chars()

        if total <= self.mild_limit:
            return actions

        # ── Mild compression ──
        self.sections.sort(key=lambda s: s["priority"])

        deferrable = [s for s in self.sections if s["priority"] >= 9]
        kept = [s for s in self.sections if s["priority"] < 9]

        for d in deferrable:
            if sum(s["chars"] for s in kept) <= self.hard_limit:
                kept.append(d)
            else:
                actions.append({
                    "action": "deferred",
                    "name": d["name"],
                    "saved_chars": d["chars"],
                    "saved_tokens": d["tokens"],
                    "tier": "mild",
                })

        self.sections = kept
        total = sum(s["chars"] for s in self.sections)

        for s in self.sections:
            if s["category"] != "memory" or s["priority"] < 5:
                continue
            if total <= self.mild_limit:
                break
            original_text = s["content"]
            original = s["chars"]
            max_len = min(int(original * 0.6), 200)
            if len(original_text) > max_len:
                # Save ref before truncating
                ref_path = _save_ref(s["name"], original_text)
                s["content"] = original_text[:max_len] + f"… [↩ ref:{s['name']}]"
                saved = original - len(s["content"])
                total -= saved
                actions.append({
                    "action": "truncated",
                    "name": s["name"],
                    "saved_chars": saved,
                    "saved_tokens": saved // 4,
                    "tier": "mild",
                    "ref": ref_path,
                })

        if total <= self.auto_limit:
            return actions

        # ── Aggressive compression ──
        deferrable2 = [s for s in self.sections if s["priority"] >= 7]
        kept2 = [s for s in self.sections if s["priority"] < 7]

        for d in deferrable2:
            if sum(s["chars"] for s in kept2) <= self.hard_limit:
                kept2.append(d)
            else:
                actions.append({
                    "action": "demoted",
                    "name": d["name"],
                    "saved_chars": d["chars"],
                    "saved_tokens": d["tokens"],
                    "tier": "auto",
                })

        self.sections = kept2
        total = sum(s["chars"] for s in self.sections)

        for s in self.sections:
            if s["category"] != "memory":
                continue
            if total <= self.hard_limit:
                break
            original_text = s["content"]
            original = s["chars"]
            max_len = min(int(original * 0.3), 100)
            if len(original_text) > max_len:
                # Save ref before truncating (if not already saved by mild tier)
                ref_path = _save_ref(s["name"], original_text)
                s["content"] = original_text[:max_len] + f"… [↩ ref:{s['name']}]"
                saved = original - len(s["content"])
                total -= saved
                actions.append({
                    "action": "truncated_aggressive",
                    "name": s["name"],
                    "saved_chars": saved,
                    "saved_tokens": saved // 4,
                    "tier": "auto",
                    "ref": ref_path,
                })

        return actions


# ── API ──


def prepare_injection(
    sections: list[tuple[str, str, int, str]],
    budget: int = DEFAULT_BUDGET,
    mild_at: float = DEFAULT_MILD,
    auto_at: float = DEFAULT_AUTO,
) -> tuple[str, dict]:
    """Build compressed injection string from sections.

    Each section: (name, content, priority, category)
    Returns: (compressed_string, compression_report)
    """
    _cleanup_old_refs()  # Trim stale refs before adding new ones
    payload = InjectionPayload(budget=budget, mild_at=mild_at, auto_at=auto_at)

    for name, content, priority, category in sections:
        payload.add(name, content, priority, category)

    actions = payload.compress()

    output_parts = []
    for s in payload.sections:
        output_parts.append(s["content"])

    result = "\n\n".join(p for p in output_parts if p.strip())

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


def show_config():
    """Print current compression config."""
    cfg = _load_compression_config()
    print()
    print("  Compression Config")
    print("=" * 35)
    print(f"  {'enabled':25s}  {cfg['enabled']}")
    print(f"  {'budget_chars':25s}  {cfg['budget_chars']}")
    print(f"  {'mild_threshold':25s}  {cfg['mild_threshold']}  (70% = start mild)")
    print(f"  {'auto_threshold':25s}  {cfg['auto_threshold']}  (85% = aggressive)")
    print(f"  {'warn_threshold':25s}  {cfg['warn_threshold']}  (70% = warn user)")
    print(f"  {'warn_language':25s}  {cfg['warn_language']}  (en = English, zh = Chinese)")
    print()


def set_config(key: str, value: str):
    """Set a compression parameter in config.yaml."""
    if key not in ALLOWED_KEYS:
        print(f"Unknown key: {key}")
        print(f"Allowed: {', '.join(sorted(ALLOWED_KEYS))}")
        return
    try:
        import yaml
    except ImportError:
        print("PyYAML not available. Edit config.yaml manually.")
        return

    cfg_path = Path(__file__).parent / "config.yaml"
    if not cfg_path.exists():
        print("config.yaml not found")
        return

    with open(cfg_path) as f:
        cfg = yaml.safe_load(f) or {}

    try:
        if key == "enabled":
            val = value.lower() in ("true", "yes", "1", "on")
        elif key == "budget_chars":
            val = int(value)
            if val < MIN_BUDGET:
                raise ValueError(f"Minimum budget is {MIN_BUDGET}")
        elif key == "warn_language":
            val = str(value).strip()
            if val not in ("en", "zh"):
                raise ValueError("Must be 'en' or 'zh'")
        else:
            val = float(value)
            if not (0.1 <= val <= 1.0):
                raise ValueError("Must be between 0.1 and 1.0")
    except (ValueError, TypeError) as e:
        print(f"Invalid value for {key}: '{value}'. {e}")
        return

    if "compression" not in cfg:
        cfg["compression"] = {}
    cfg["compression"][key] = val

    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

    print(f"✅ Set compression.{key} = {val}")
    show_config()


def stats():
    """Show compression statistics and current status."""
    log = _load_compress_log()
    cfg = _load_compression_config()
    events = log.get("compression_events", 0)
    saved_chars = log.get("total_saved_chars", 0)
    saved_tokens = log.get("total_saved_tokens", 0)
    last = log.get("last_event")

    payload = InjectionPayload(budget=cfg["budget_chars"],
                                mild_at=cfg["mild_threshold"],
                                auto_at=cfg["auto_threshold"])
    status = payload.level()
    pct = payload.usage_pct()

    status_icons = {"ok": "✅", "warn": "⚠️", "mild": "🌤️", "auto": "⚡", "over": "🔴"}
    icon = status_icons.get(status, "❓")
    mild_pct = int(cfg["mild_threshold"] * 100)
    auto_pct = int(cfg["auto_threshold"] * 100)

    print(f"\n📦 MOYU Context Compression")
    print("=" * 50)
    print(f"  {icon}  Used: {pct}%  |  Mild: {mild_pct}%  |  Auto: {auto_pct}%")
    print(f"  Budget: {cfg['budget_chars']} chars (~{cfg['budget_chars']//4} tokens)")
    print(f"  Compression events: {events}")
    print(f"  Total saved:        {saved_chars} chars (~{saved_tokens} tokens)")
    if last:
        print(f"  Last event:         {last.get('timestamp', '?')[:19]}")
        print(f"    Before: {last['before_chars']} chars → After: {last['after_chars']} chars")
        for a in last.get("actions", []):
            print(f"    • [{a.get('tier','?')}] {a['action']}: {a['name']} (saved {a['saved_chars']} chars)")
    print()
    return status


def last_report_message() -> str:
    """Return a short, direct message about the last compression event."""
    log = _load_compress_log()
    last = log.get("last_event")
    if not last:
        return ""

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


def status_line() -> str:
    """MOYU 注入预算 + Hermes 真实上下文窗口，一行一条。"""
    cfg = _load_compression_config()
    payload = InjectionPayload(budget=cfg["budget_chars"],
                                mild_at=cfg["mild_threshold"],
                                auto_at=cfg["auto_threshold"])
    lines = []
    budget_pct = payload.usage_pct()
    if budget_pct > 0:
        left = 100 - int(budget_pct)
        mild_pct = int(cfg["mild_threshold"] * 100)
        auto_pct = int(cfg["auto_threshold"] * 100)
        lines.append(f"MOYU预算: {budget_pct:.0f}% ({left}% left) — mild {mild_pct}% / auto {auto_pct}%")
    lines.append(provider_context_line())
    warn_pct = int(cfg.get("warn_threshold", DEFAULT_WARN) * 100)
    lines.append(f"预警线: {warn_pct}%")
    return "\n".join(lines) if lines else ""


def check_status() -> dict:
    """Quick health check — returns current compression status."""
    cfg = _load_compression_config()
    payload = InjectionPayload(budget=cfg["budget_chars"],
                                mild_at=cfg["mild_threshold"],
                                auto_at=cfg["auto_threshold"])
    return {
        "level": payload.level(),
        "usage_pct": payload.usage_pct(),
        "mild_threshold": cfg["mild_threshold"],
        "auto_threshold": cfg["auto_threshold"],
        "warn_threshold": cfg["warn_threshold"],
        "budget": cfg["budget_chars"],
    }


# ── Provider 上下文监测（自动扫描 + 多 Agent 适配） ──

PROVIDER_CACHE = {"name": None, "data": None}  # 缓存扫描结果，避免反复读


def _scan_providers():
    """自动扫描本地常见 Agent，返回 (provider_name, context_data) 或 (None, None)。"""
    # ── 环境变量覆盖 ──
    force_provider = os.environ.get("MOYU_FORCE_PROVIDER")
    force_path = os.environ.get("MOYU_PROVIDER_PATH")
    if force_provider and force_path:
        path = os.path.expandvars(os.path.expanduser(force_path))
        if os.path.exists(path):
            try:
                with sqlite3.connect(path) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.execute(
                        "SELECT input_tokens, api_call_count FROM sessions "
                        "ORDER BY started_at DESC LIMIT 1"
                    )
                    row = cur.fetchone()
                if row:
                    total = row["input_tokens"] or 0
                    calls = row["api_call_count"] or 0
                    pct = min(100, round((total / 128000) * 100))
                    return force_provider, dict(pct=pct, total_tokens=total, context_length=128000,
                                                 api_calls=calls, likely_compressed=calls > 50 or total > 128000)
            except Exception:
                pass

    import platform
    import glob as _glob
    import json as _j
    _is_win = platform.system() == "Windows"

    def _candidates(mac, win, linux=None):
        """按平台返回候选路径列表。"""
        if _is_win:
            return [os.path.expandvars(p) for p in (win if isinstance(win, list) else [win])]
        elif platform.system() == "Darwin":
            return [os.path.expanduser(p) for p in (mac if isinstance(mac, list) else [mac])]
        else:
            paths = linux if linux else mac
            return [os.path.expanduser(p) for p in (paths if isinstance(paths, list) else [paths])]

    # ── Hermes ──
    def _parse_hermes():
        for db in _candidates(
            mac="~/.hermes/state.db",
            win=[
                "%USERPROFILE%\\.hermes\\state.db",
                "%LOCALAPPDATA%\\hermes\\state.db",
            ],
        ):
            if not os.path.exists(db):
                continue
            try:
                with sqlite3.connect(db) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.execute(
                        "SELECT input_tokens, api_call_count FROM sessions "
                        "ORDER BY started_at DESC LIMIT 1"
                    )
                    row = cur.fetchone()
                if not row:
                    continue
                total = row["input_tokens"] or 0
                calls = row["api_call_count"] or 0
                pct = min(100, round((total / 128000) * 100))
                return dict(pct=pct, total_tokens=total, context_length=128000,
                            api_calls=calls, likely_compressed=calls > 50 or total > 128000)
            except Exception:
                continue
        return None

    # ── Claude Code ──
    def _parse_claude():
        for base in _candidates(
            mac="~/.claude/projects",
            win="%USERPROFILE%\\.claude\\projects",
        ):
            if not os.path.isdir(base):
                continue
            files = sorted(_glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True),
                           key=os.path.getmtime, reverse=True)
            if not files:
                continue
            try:
                with open(files[0], "r") as f:
                    lines = f.readlines()
                tail = [l for l in lines[-20:] if l.strip()]
                if not tail:
                    continue
                total_in = 0
                calls = 0
                for line in tail:
                    try:
                        obj = _j.loads(line)
                        inp = obj.get("input_tokens", obj.get("inputTokens", 0))
                        if inp:
                            total_in += inp
                            calls += 1
                    except Exception:
                        continue
                if calls == 0:
                    continue
                pct = min(100, round((total_in / 200000) * 100))
                return dict(pct=pct, total_tokens=total_in, context_length=200000,
                            api_calls=calls, likely_compressed=calls > 30 or total_in > 200000)
            except Exception:
                continue
        return None

    # ── OpenClaw ──
    def _parse_openclaw():
        for base in _candidates(
            mac="~/.openclaw/agents",
            win="%USERPROFILE%\\.openclaw\\agents",
        ):
            if not os.path.isdir(base):
                continue
            files = sorted(_glob.glob(os.path.join(base, "**", "sessions", "*.jsonl"), recursive=True),
                           key=os.path.getmtime, reverse=True)
            if not files:
                continue
            try:
                with open(files[0], "r") as f:
                    lines = f.readlines()
                tail = [l for l in lines[-20:] if l.strip()]
                if not tail:
                    continue
                total_in = 0
                calls = 0
                for line in tail:
                    try:
                        obj = _j.loads(line)
                        inp = obj.get("inputTokens", obj.get("totalTokens", 0))
                        if inp:
                            total_in += inp
                            calls += 1
                    except Exception:
                        continue
                if calls == 0:
                    continue
                pct = min(100, round((total_in / 128000) * 100))
                return dict(pct=pct, total_tokens=total_in, context_length=128000,
                            api_calls=calls, likely_compressed=calls > 30 or total_in > 128000)
            except Exception:
                continue
        return None

    # ── Cursor ──
    def _parse_cursor():
        candidates = _candidates(
            mac=[
                "~/Library/Application Support/Cursor/User/workspaceStorage",
                "~/.config/Cursor/User/workspaceStorage",
            ],
            win=[
                "%APPDATA%\\Cursor\\User\\workspaceStorage",
            ],
            linux=["~/.config/Cursor/User/workspaceStorage"],
        )
        for cand in candidates:
            dbs = sorted(_glob.glob(os.path.join(cand, "**", "state.vscdb"), recursive=True),
                         key=os.path.getmtime, reverse=True)
            if not dbs:
                continue
            try:
                with sqlite3.connect(dbs[0]) as conn:
                    cursor = conn.execute(
                        "SELECT count(*) FROM cursor_messages WHERE created_at > datetime('now', '-1 day')"
                    )
                    count = cursor.fetchone()[0] or 0
                if count > 0:
                    pct = min(100, round((count * 1500 / 128000) * 100))
                    return dict(pct=pct, total_tokens=count * 1500,
                                context_length=128000, api_calls=count,
                                likely_compressed=count > 40 or (count * 1500) > 128000)
            except Exception:
                continue
        return None

    # ── Continue ──
    def _parse_continue():
        for base in _candidates(
            mac="~/.continue/sessions",
            win="%USERPROFILE%\\.continue\\sessions",
        ):
            if not os.path.isdir(base):
                continue
            files = sorted(_glob.glob(os.path.join(base, "*.json")),
                           key=os.path.getmtime, reverse=True)
            if not files:
                continue
            try:
                with open(files[0], "r") as f:
                    data = _j.load(f)
                messages = data.get("messages", data.get("history", []))
                calls = len(messages)
                if calls < 2:
                    continue
                total_in = calls * 1000
                pct = min(100, round((total_in / 128000) * 100))
                return dict(pct=pct, total_tokens=total_in, context_length=128000,
                            api_calls=calls, likely_compressed=calls > 40 or total_in > 128000)
            except Exception:
                continue
        return None

    # ── 检测顺序 ──
    detectors = [
        ("Hermes", _parse_hermes),
        ("Claude Code", _parse_claude),
        ("OpenClaw", _parse_openclaw),
        ("Cursor", _parse_cursor),
        ("Continue", _parse_continue),
    ]

    for name, parser in detectors:
        data = parser()
        if data:
            return name, data
    return None, None


def get_context():
    """获取当前检测到的 Agent 上下文占用率。
    返回 (provider_name, context_data dict) 或 (None, None)。
    结果会缓存，避免每次调用都扫描磁盘。
    """
    if PROVIDER_CACHE["data"]:
        return PROVIDER_CACHE["name"], PROVIDER_CACHE["data"]

    name, data = _scan_providers()
    if name and data:
        PROVIDER_CACHE["name"] = name
        PROVIDER_CACHE["data"] = data
    return name, data


def reset_provider_cache():
    """重置 provider 缓存，下次调用时重新扫描。"""
    PROVIDER_CACHE["name"] = None
    PROVIDER_CACHE["data"] = None


def provider_context_line() -> str:
    """检测到的 Agent 上下文状态一行概览。"""
    name, data = get_context()
    if not name or not data:
        return "Agent窗口: 未检测到支持的 Agent（当前支持: Hermes/Claude Code/OpenClaw/Cursor/Continue，暂不支持 Windsurf/Copilot/Aider 等）\n⚠️ 注意：你的 Agent 可能有自己的压缩阈值（如 Hermes 默认 50%），请在 MOYU 设置合适的警戒线低于它：moyu compress set warn_threshold 0.4"
    flag = " ⚠️ 已深度压缩" if data["likely_compressed"] else ""
    return (
        f"{name}窗口: {data['pct']}%"
        f" (累计{data['total_tokens']:,}/{data['context_length']:,}, {data['api_calls']}次调用)"
        f"{flag}"
    )


def warning_message() -> str:
    """如果上下文接近压缩阈值，返回警告文字。"""
    name, data = get_context()
    if not name or not data:
        return ""
    cfg = _load_compression_config()
    warn_at = cfg.get("warn_threshold", DEFAULT_WARN)
    warn_pct = int(warn_at * 100)
    lang = cfg.get("warn_language", "en")
    if data["likely_compressed"]:
        if lang == "zh":
            return f"{name}上下文用到 {data['pct']}% 了，对话已深，可以考虑 /new"
        return f"{name} context at {data['pct']}%, conversation deeply compressed — /new recommended"
    if data["pct"] >= warn_pct:
        if lang == "zh":
            return f"{name}上下文用到 {data['pct']}% 了，快到 {warn_pct}% 预警线（注意你的 Agent 有自己的压缩阈值，低于它才有效：moyu compress set warn_threshold 0.4）"
        return f"{name} context at {data['pct']}%, approaching {warn_pct}% warning — your Agent may have its own compression threshold, set MOYU warn below it: moyu compress set warn_threshold 0.4"
    return ""


def diagnose():
    """逐项扫描 Provider 并输出详细结果，用于排查检测不到的问题。"""
    import platform
    import glob as _glob
    import json as _j
    _is_win = platform.system() == "Windows"
    system = platform.system()
    print(f"系统: {system}")
    print(f"环境变量 MOYU_FORCE_PROVIDER: {os.environ.get('MOYU_FORCE_PROVIDER', '(未设置)')}")
    print(f"环境变量 MOYU_PROVIDER_PATH: {os.environ.get('MOYU_PROVIDER_PATH', '(未设置)')}")
    print()

    def _candidates(mac, win, linux=None):
        if _is_win:
            return [os.path.expandvars(p) for p in (win if isinstance(win, list) else [win])]
        elif system == "Darwin":
            return [os.path.expanduser(p) for p in (mac if isinstance(mac, list) else [mac])]
        else:
            paths = linux if linux else mac
            return [os.path.expanduser(p) for p in (paths if isinstance(paths, list) else [paths])]

    checks = [
        ("Hermes", lambda: _candidates("~/.hermes/state.db",
                                        ["%USERPROFILE%\\.hermes\\state.db", "%LOCALAPPDATA%\\hermes\\state.db"])),
        ("Claude Code", lambda: _candidates("~/.claude/projects",
                                              "%USERPROFILE%\\.claude\\projects")),
        ("OpenClaw", lambda: _candidates("~/.openclaw/agents",
                                          "%USERPROFILE%\\.openclaw\\agents")),
        ("Continue", lambda: _candidates("~/.continue/sessions",
                                          "%USERPROFILE%\\.continue\\sessions")),
    ]

    for name, path_fn in checks:
        paths = path_fn()
        print(f"[{name}]")
        for p in paths:
            exists = "✅" if os.path.exists(p) else "❌"
            kind = "目录" if os.path.isdir(p) else "文件"
            print(f"  {exists} {kind}: {p}")
        print()

    # Cursor has macOS-only paths
    print("[Cursor]")
    if _is_win:
        print("  ❌ 路径: %APPDATA%\\Cursor\\User\\workspaceStorage")
    elif system == "Darwin":
        for p in ["~/Library/Application Support/Cursor/User/workspaceStorage",
                   "~/.config/Cursor/User/workspaceStorage"]:
            ep = os.path.expanduser(p)
            exists = "✅" if os.path.exists(ep) else "❌"
            print(f"  {exists} 目录: {ep}")
    else:
        print("  ❌ 路径: ~/.config/Cursor/User/workspaceStorage")

    print()
    name, data = get_context()
    if name and data:
        print(f"✅ 检测结果: {name} — {data['pct']}% ({data['api_calls']}次调用)")
    else:
        print("❌ 检测结果: 未找到任何支持的 Agent")
        print("  提示: 设置 MOYU_FORCE_PROVIDER 和 MOYU_PROVIDER_PATH 绕过自动检测")


def build_injection(
    working_memory: str = "",
    behavioral_rules: str = "",
    memory_search: str = "",
    knowledge_graph: str = "",
    user_profile: str = "",
    quiet: bool = False,  # True = 不附加预警文字，供内部调用
) -> tuple[str, dict]:
    """Build a compressed injection payload from all available context sources.

    Automatically appends Hermes context warning to behavioral_rules.
    Set quiet=True to suppress (for internal calls like moyu_wake).
    """
    cfg = _load_compression_config()

    if not cfg["enabled"]:
        parts = [p for p in [working_memory, behavioral_rules, memory_search, knowledge_graph, user_profile] if p.strip()]
        return "\n\n".join(parts), {"compressed": False, "reason": "disabled in config"}

    # Auto-append context warning to behavioral_rules
    if not quiet:
        warn = warning_message()
        if warn:
            behavioral_rules = (behavioral_rules + "\n\n" + warn).strip()

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

    return prepare_injection(sections,
                             budget=cfg["budget_chars"],
                             mild_at=cfg["mild_threshold"],
                             auto_at=cfg["auto_threshold"])


def demo() -> dict:
    """Return demo content for moyu_demo.py discovery engine."""
    return {
        "capability": 12,
        "title": "Context-Aware Compression (V2.1 — Two-Tier)",
        "output": """\
📦 V2.1 FEATURE — Two-Tier Context Compression
────────────────────────────────────────────
  Mild (70%+): truncate long memories, defer optional items
  Auto (85%+): aggressive demote non-critical, hard truncate
  Budget: 2000 chars (~500 tokens)

  Usage: 89% → after compression: 68%
  Saved: 520 chars (~130 tokens)
""",
    }


# ── Alias: remote compatibility ──
build_context_prompt = build_injection


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if not args or args[0] == "stats":
        stats()
    elif args[0] == "config":
        show_config()
    elif args[0] == "set" and len(args) >= 2:
        set_config(args[1], args[2] if len(args) > 2 else "0")
    elif args[0] == "diagnose":
        diagnose()
    else:
        print(__doc__)
