#!/usr/bin/env python3
"""
moyu — MOYU unified CLI entry point

Usage:
    moyu search <query>     Search memories
    moyu learn <text>       Learn from correction
    moyu stats              Show all statistics
    moyu status             Show system status
    moyu setup              Set up security password
    moyu verify <type> [desc]  Verify dangerous operation
    moyu unlock             Unlock security system
    moyu check              Check file integrity
    moyu context           Get behavior rules
    moyu signals            View active trigger words
    moyu demo               Show all capabilities
    moyu compress           Show compression status
    moyu compress --now     Force manual compression
    moyu compress config    Show compression parameters
    moyu compress set <k> <v>  Set parameter (mild_threshold, auto_threshold, etc.)
    moyu forget             Show memory lifecycle (forgetting curve)
    moyu forget stats       Same as above
    moyu forget config      Show current forgetting curve parameters
    moyu forget set <k> <v> Set a parameter (demote_days, archive_days, etc.)
    moyu ref <name>         Read original content of a compressed memory
    moyu ref list           List available refs (compressed memory originals)
    moyu update             Check for updates
    moyu update now         Download & apply update
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


def cmd_stats():
    mem = _import("agent_memory")
    ctx = _import("active_context")
    lrn = _import("learner")
    print()
    print("=" * 50)
    print("  MOYU — Global Statistics")
    print("=" * 50)
    mem.stats()
    ctx.status()
    lrn.stats()
    # User profile stats
    try:
        profile = lrn.profile_stats()
        if profile["count"]:
            print(f"📋 User Profile ({profile['count']} fields): {', '.join(profile['fields'])}")
        else:
            print(f"📋 User Profile: no data yet (auto-extracted from conversation)")
    except Exception:
        pass
    try:
        sec = _import("security")
        sec.status()
    except Exception:
        pass
    print()


def cmd_audit():
    """Security audit — one-report summary of all defense layers."""
    print()
    print("=" * 52)
    print("  🛡️  MOYU Security Audit")
    print("=" * 52)

    # Layer 1: Memory Self-Defense (pre-operation)
    sec_mod = _import("security")
    has_pw = sec_mod.check_password_set()
    # Count failures (from security_failures.json)
    import json as _json, os as _os
    fail_path = _os.path.join(TOOLKIT_DIR, "memory_data", "security_failures.json")
    failures = 0
    if _os.path.exists(fail_path):
        try:
            with open(fail_path) as _f:
                failures = len(_json.load(_f))
        except Exception:
            pass
    print(f"\n  ⚡ Layer 1 — Pre-operation (security.py)")
    if has_pw:
        print(f"     ✅  Password set")
    else:
        print(f"     ⚠️   Password not set — run `moyu setup`")
    if failures:
        print(f"     ⚠️   {failures} recent failed attempts")

    # Layer 2: Integrity Check (on-wake detection)
    ic = _import("defense_toolkit.integrity_checker")
    import os as _os
    storage_base = _os.environ.get("MOYU_STORAGE",
                                    _os.path.join(TOOLKIT_DIR, "memory_data"))
    manifest_path = _os.path.join(storage_base, "manifest.json")
    backup_dir = _os.path.join(storage_base, "backups")
    has_manifest = _os.path.exists(manifest_path)
    print(f"\n  🔍 Layer 2 — On-wake detection (integrity_checker.py)")
    if has_manifest:
        print(f"     ✅  Manifest initialized")
        # Show data file change tracking
        hash_log_path = _os.path.join(storage_base, "hash_change_log.json")
        if _os.path.exists(hash_log_path):
            try:
                with open(hash_log_path) as _f:
                    changes = _json.load(_f)
                from datetime import datetime as _dt
                recent = [c for c in changes if c.get("timestamp","").startswith(_dt.now().strftime("%Y-%m-%d"))]
                if recent:
                    print(f"     📝  {len(recent)} data file change(s) today")
                    for c in recent[-3:]:
                        print(f"        {c['timestamp'][11:19]}  {c['file'][:30]}")
                else:
                    print(f"     ✅  No data file changes today")
            except Exception:
                pass
        # Count daily backups
        if _os.path.isdir(backup_dir):
            backups = [f for f in _os.listdir(backup_dir) if f.startswith("daily_")]
            print(f"     ✅  {len(backups)} daily backup(s) available")
        else:
            print(f"     ⚠️   No backups yet (will be created on next wake)")
    else:
        print(f"     ⚠️   Manifest not initialized — run `moyu init`")

    # Layer 3: Auto Recovery (post-tamper)
    print(f"\n  🔄 Layer 3 — Post-tamper recovery")
    if has_manifest and _os.path.isdir(backup_dir):
        backups = [f for f in _os.listdir(backup_dir) if f.startswith("daily_")]
        if backups:
            dates = set()
            for f in backups:
                parts = f.split("_", 2)
                if len(parts) >= 2:
                    dates.add(parts[1])
            print(f"     ✅  Auto-recovery ready — {len(dates)} days of backup available")
        else:
            print(f"     ⚠️   No backup data yet")
    else:
        print(f"     —  Not ready (run `moyu init` first)")

    print()
    print(f"  {'=' * 52}")
    all_good = has_pw and has_manifest
    print(f"  {'✅ All defense layers operational' if all_good else '⚠️  Some layers need attention'}")
    print()


def cmd_status():
    import yaml
    print()
    print("=" * 50)
    print("  MOYU — System Status")
    print("=" * 50)
    cfg_path = os.path.join(TOOLKIT_DIR, "config.yaml")
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}
        print(f"  API Key:  {'✅ Configured' if cfg.get('api', {}).get('api_key', '') else '⚠️ Not set (local mode)'}")
    else:
        print("  API Key:  ❌ config.yaml not found")
    storage = os.environ.get("MOYU_STORAGE", os.path.join(TOOLKIT_DIR, "memory_data"))
    if os.path.isdir(storage):
        files = [f for f in os.listdir(storage) if f.endswith(".json")]
        print(f"  Storage:  ✅ {len(files)} data files")
    else:
        print("  Storage:  ⚠️ Not initialized")
    print(f"  Security: {'✅ ready' if os.path.exists(os.path.join(TOOLKIT_DIR, 'security.py')) else '⚠️ Not available'}")
    print()
    # Defense chain visualization
    print(f"  {'─' * 48}")
    print(f"  🛡️  Defense Chain")
    print(f"  {'─' * 48}")
    # Layer 1 — Pre-op (read config directly, avoid sec.status() which prints)
    import json as _json2
    import os as _os2
    _sec_cfg = {}
    _scp = _os2.path.join(TOOLKIT_DIR, "memory_data", "security_config.json")
    if _os2.path.exists(_scp):
        try:
            with open(_scp) as _f:
                _sec_cfg = _json2.load(_f)
        except Exception:
            pass
    _pw_set = bool(_sec_cfg.get("safe_word_hash", ""))
    print(f"  ⚡ Pre-op:   {'✅ Password Set' if _pw_set else '⚠️ No Password'}  (moyu setup)")
    # Layer 2 — On-wake
    _sto = _os2.environ.get("MOYU_STORAGE", _os2.path.join(TOOLKIT_DIR, "memory_data"))
    _has_man = _os2.path.exists(_os2.path.join(_sto, "manifest.json"))
    print(f"  🔍 On-wake:  {'✅ Manifest Ready' if _has_man else '⚠️ Not Initialized'}  (moyu init)")
    # Layer 3 — Post-tamper
    _bak = _os2.path.join(_sto, "backups")
    _has_bak = _os2.path.isdir(_bak) and any(f.startswith("daily_") for f in _os2.listdir(_bak)) if _os2.path.isdir(_bak) else False
    print(f"  🔄 Post:     {'✅ Recovery Ready' if _has_bak else '⚠️ No Backups Yet'}")
    print(f"  {'─' * 48}")
    print()


def cmd_demo():
    """Safely import and run moyu_demo."""
    import importlib.util
    demo_path = os.path.join(TOOLKIT_DIR, "moyu_demo.py")
    spec = importlib.util.spec_from_file_location("moyu_demo", demo_path)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "run"):
            mod.run()


CMD_TABLE = {
    "search":     lambda args: _handle_search(args),
    "stats":      lambda args: cmd_stats(),
    "status":     lambda args: cmd_status(),
    "learn":      lambda args: _call_func("learner", "learn", [" ".join(args)]),
    "detect":     lambda args: _call_func("learner", "detect_corrections", [" ".join(args)]),
    "context":     lambda args: print(_import("learner").format_behavior_rules()),
    "signals":    lambda args: _call_func("learner", "signals", args),
    "setup":      lambda args: _import("security").setup(),
    "verify":     lambda args: _verify_op(args),
    "unlock":     lambda args: _import("security").unlock(),
    "check":      lambda args: _call_func("defense_toolkit.integrity_checker", "verify", args),
    "init":       lambda args: _call_func("defense_toolkit.integrity_checker", "init_manifest", args),
    "compress":   lambda args: _compress(args),
    "context":    lambda args: print(_import("context_manager").status_line()),
    "forget":     lambda args: _forget(args),
    "lifecycle":  lambda args: _forget(args),  # alias
    "bridge":     lambda args: _import("session_bridge").status(),
    "ref":        lambda args: _ref_handler(args),
    "update":     lambda args: _update(args),
    "demo":       lambda args: cmd_demo(),
    "reflect":    lambda args: _call_func("self_reflection", "run", []),
    "audit":      lambda args: cmd_audit(),
    "kb":         lambda args: _kb_handler(args),
    "kg":         lambda args: _kg_handler(args),
}

HELP_DESCRIPTIONS = {
    "search": "Search memories (TEMPR multi-strategy)",
    "stats": "Show all statistics (memory, learner, security)",
    "status": "Show system status with defense chain visualization",
    "learn": "Learn from a user correction",
    "detect": "Detect correction signals in text",
    "context": "Get behavioral rules for system prompt",
    "signals": "View active trigger words (learner)",
    "setup": "Set a security password",
    "verify": "Verify a dangerous operation",
    "unlock": "Unlock security system (after 3 failed attempts)",
    "check": "Check memory file integrity (SHA256)",
    "init": "Initialize integrity verification manifest",
    "audit": "Full security audit (all 3 defense layers)",
    "reflect": "Run self-reflection (analyze contradictions & connections)",
    "compress": "Show compression status and context usage",
    "forget": "Show forgetting curve status and parameters",
    "ref": "Read original content of a compressed memory",
    "update": "Check for MOYU updates on GitHub",
    "demo": "Show all capabilities with examples",
    "kb": "Knowledge base: {index|search|list|read}",
    "kg": "Knowledge graph: {search <entity>}",
    "bridge": "Show session bridge status",
 "lifecycle":  "Alias for forget (memory lifecycle)",
    "context":    "Show context usage percentage in one line",
    "help": "Show this help message",
}


def _call_func(module, func, args):
    m = _import(module)
    fn = getattr(m, func, None)
    if fn:
        result = fn(*args)
        if result is not None:
            print(result)


def _verify_op(args):
    sec = _import("security")
    if len(args) < 1:
        print("Usage: moyu verify <op_type> [context]")
        return
    op = args[0]
    ctx = " ".join(args[1:])
    result = sec.verify_operation(op, ctx)
    print("✅ Allowed" if result else "❌ Denied")


def _handle_search(args):
    if not args:
        print("Usage: moyu search <query>")
        return
    query = " ".join(args)
    mem = _import("agent_memory")
    try:
        results = mem.search(query)
    except Exception:
        results = []
    if not results:
        print("No results found.")
        return
    print(f"\nSearch results for: {query}")
    print("=" * 40)
    for r in results:
        print(f"  [{r['timestamp'][:10]}] {r['summary'][:80]}")
        print(f"  Score: {r.get('score', 0)}")
    
    # Track access for forgetting curve density analysis
    try:
        fc = _import("forgetting_curve")
        fc.track_access([r['memory_id'] for r in results])
    except Exception:
        pass

def _require_auth(op_type: str, context: str = "") -> bool:
    """Prompt for security password before dangerous operations.
    Returns True if allowed (or no password set), False if denied."""
    sec = _import("security")
    result = sec.verify_operation(op_type, context)
    return result


def _compress(args):
    """Handle compress command — status, config, and settings."""
    cm = _import("context_manager")
    if not args or args[0] in ("stats", "--stats"):
        cm.stats()
    elif args[0] == "--now":
        if not _require_auth("compress", "Force manual memory compression"):
            return
        ctx = _import("active_context")
        lrn = _import("learner")
        wm = ctx.format_context()
        rules = lrn.format_behavior_rules()
        result, report = cm.build_context_prompt(working_memory=wm, behavioral_rules=rules)
        msg = cm.last_report_message()
        print(f"🚚 Manual compression triggered")
        print(f"  {msg}" if msg else f"  No compression needed ({report['usage_pct']}% of budget)")
        print()
    elif args[0] in ("config", "show", "--config"):
        cm.show_config()
    elif args[0] == "set" and len(args) >= 3:
        cm.set_config(args[1], args[2])
    elif args[0] == "diagnose":
        cm.diagnose()
    elif args[0] in ("help", "--help"):
        _compress_help()
    else:
        print(f"Unknown subcommand: {args[0]}")
        _compress_help()


def _compress_help():
    print("moyu compress commands:")
    print("  moyu compress                  Show compression status")
    print("  moyu compress stats            Same as above")
    print("  moyu compress --now            Force manual compression")
    print("  moyu compress config           Show current compression parameters")
    print("  moyu compress set <key> <val>  Set a parameter:")
    print("    mild_threshold    — Mild compression trigger (0.7 = 70%)")
    print("    auto_threshold    — Aggressive compression trigger (0.85 = 85%)")
    print("    budget_chars      — Target context budget")
    print("    warn_threshold    — Hermes context warning threshold (0.7 = 70%)")
    print("    warn_language     — Warning language (en = English, zh = Chinese)")
    print("    enabled           — true/false")
    print("  moyu compress diagnose         Show detailed scan results for all agents")


def _forget(args):
    """Handle forget command — status, config, and settings."""
    fc = _import("forgetting_curve")
    if not args or args[0] in ("stats", "--stats"):
        fc.stats()
    elif args[0] == "--summary":
        print(fc.summary())
    elif args[0] in ("config", "show", "--config"):
        _forget_config()
    elif args[0] == "set" and len(args) >= 3:
        if not _require_auth("forget_set", f"Set forgetting_curve.{args[1]}={args[2]}"):
            return
        _forget_set(args[1], args[2])
    elif args[0] in ("help", "--help"):
        _forget_help()
    elif args[0] in ("history", "digest"):
        _forget_history(args[1:])
    else:
        print(f"Unknown subcommand: {args[0]}")
        _forget_help()


def _forget_help():
    print("moyu forget commands:")
    print("  moyu forget                  Show memory lifecycle stats")
    print("  moyu forget stats            Same as above")
    print("  moyu forget --summary        One-line summary")
    print("  moyu forget config           Show current config")
    print("  moyu forget set <key> <val>  Set a parameter:")
    print("    demote_days       — Safety window before demotion (default: 14)")
    print("    archive_days      — Days after demotion before archivable (default: 60)")
    print("    density_window    — Max access timestamps tracked (default: 20)")
    print("    min_keyword_length — Min chars for auto-extracted scene keywords (default: 3)")
    print("    auto_scene_extraction — Enable/disable automatic scene keyword extraction (true/false)")
    print("  moyu forget scene labels")
    print("    Set custom scene labels in config.yaml → forgetting_curve → scene_labels")
    print("    Format:")
    print("      scene_labels:")
    print('        SceneName1: [keyword1, keyword2]')
    print('        SceneName2: [keyword3, keyword4, keyword5]')
    print("    A memory whose summary contains 'keyword1' → assigned to 'SceneName1'")
    print("  moyu forget history [--today]  Show recent demotion/retention history")


def _forget_history(args):
    """Show what the forgetting curve has been doing — which memories
    were demoted, which were kept, and why."""
    import json as _json
    import os as _os
    from datetime import datetime as _dt
    mem_path = _os.path.join(TOOLKIT_DIR, "memory_data", "conversation_memory.json")
    if not _os.path.exists(mem_path):
        print("No memory data found.")
        return
    with open(mem_path) as _f:
        memories = _json.load(_f)

    # Filter by today if --today flag
    today_filter = "--today" in args
    today_str = _dt.now().strftime("%Y-%m-%d")

    demoted = [m for m in memories if m.get("demoted")]
    demoted.sort(key=lambda m: m.get("demoted_at", m.get("timestamp", "")), reverse=True)

    active = [m for m in memories if not m.get("demoted")]

    # Show non-demoted that are past the 14-day window
    now = _dt.now()
    past_window = []
    for m in active:
        ts = m.get("last_accessed") or m.get("timestamp", "")
        try:
            age = (now - _dt.fromisoformat(ts.replace("Z", "+00:00"))).days
        except Exception:
            age = 0
        if age >= 14:
            reason = "kept_by_scene" if m.get("protected_by_scene") else "kept_by_density"
            past_window.append((age, reason, m))

    print()
    print(f"  🧠 Forgetting Curve Digest{' (今日)' if today_filter else ''}")
    print(f"  {'=' * 50}")
    print(f"  总记忆: {len(memories)}  |  已降级: {len(demoted)}  |  活跃: {len(active)}")
    print()

    # Recently demoted (non-archived)
    recent = [m for m in demoted if not m.get("archived")]
    if recent:
        print(f"  ⏳ 已降级 ({len(recent)}):")
        for m in recent[:5]:
            scene = m.get("scene", "?")
            reason = m.get("demoted_reason", "")[:60]
            summary = m.get("summary", "")[:35]
            print(f"    · {summary:35s}  scene={scene:12s}  {reason}")
        print()

    # Retentions past the 14-day window
    if past_window:
        print(f"  🔒 超过14天仍在保留 ({len(past_window)}):")
        past_window.sort(key=lambda x: -x[0])
        for age, reason, m in past_window[:5]:
            scene = m.get("scene", "?")
            summary = m.get("summary", "")[:35]
            tag = "场景保护" if reason == "kept_by_scene" else "密度稳定"
            print(f"    · {summary:35s}  scene={scene:12s}  {tag}  ({age}d)")
        print()

    # Archivable
    archivable = [m for m in memories
                  if m.get("demoted") and m.get("demoted_reason", "").find("60") >= 0]
    if archivable:
        print(f"  📦 可归档 ({len(archivable)}):")
        for m in archivable[:3]:
            summary = m.get("summary", "")[:40]
            print(f"    · {summary}")
        print()


def _forget_config():
    """Show current forgetting_curve config from config.yaml."""
    import yaml
    cfg_path = os.path.join(TOOLKIT_DIR, "config.yaml")
    if not os.path.exists(cfg_path):
        print("Config not found")
        return
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f) or {}
    fc = cfg.get("forgetting_curve", {})
    print()
    print("  Forgetting Curve Config")
    print("=" * 35)
    for key in ("demote_days", "archive_days", "density_window"):
        val = fc.get(key, "?")
        print(f"  {key:20s}  {val}")
    print(f"  {'enabled':20s}  {fc.get('enabled', True)}")
    print(f"  {'min_keyword_length':20s}  {fc.get('min_keyword_length', 3)}")
    print(f"  {'auto_scene_extraction':20s}  {fc.get('auto_scene_extraction', True)}")
    # Show scene labels
    labels = fc.get("scene_labels", {})
    if labels:
        print(f"  {'scene_labels':20s}")
        for scene_name, keywords in labels.items():
            print(f"    {scene_name:16s}  {', '.join(keywords)}")
    print()


def _forget_set(key: str, value: str):
    """Set a forgetting_curve parameter in config.yaml."""
    import yaml
    cfg_path = os.path.join(TOOLKIT_DIR, "config.yaml")
    if not os.path.exists(cfg_path):
        print("Config not found")
        return
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f) or {}

    allowed = {"demote_days", "archive_days", "density_window", "enabled", "min_keyword_length", "auto_scene_extraction"}
    if key not in allowed:
        print(f"Unknown key: {key}")
        print(f"Allowed: {', '.join(sorted(allowed))}")
        return

    # Coerce type: bool for enabled/auto_scene_extraction, int for the rest
    try:
        if key in ("enabled", "auto_scene_extraction"):
            val = value.lower() in ("true", "yes", "1", "on")
        else:
            val = int(value)
            if val < 1:
                raise ValueError
    except (ValueError, TypeError):
        print(f"Invalid value for {key}: '{value}'. Expected a positive integer.")
        return

    if "forgetting_curve" not in cfg:
        cfg["forgetting_curve"] = {}
    cfg["forgetting_curve"][key] = val

    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

    print(f"✅ Set forgetting_curve.{key} = {val}")

    # Show updated config
    _forget_config()


def _update(args):
    """Handle update command — check, confirm, and apply updates."""
    up = _import("updater")
    if "--dry" in args or "check" in args:
        info = up.check()
        if "error" in info:
            print(f"Error: {info['error']}")
        else:
            print(f"Current: v{info['current']} → Latest: v{info['latest']}")
            print(f"Update available: {info['is_newer']}")
            if info.get("body"):
                print(f"\nChanges:\n{info['body'][:200]}")
    elif "now" in args or "apply" in args:
        if not _require_auth("update_now", "Update MOYU to latest version"):
            return
        # Preview changes and confirm
        info = up.check()
        if "error" in info:
            print(f"Error: {info['error']}")
            return
        if not info.get("is_newer"):
            print(f"Already up to date (v{info['current']})")
            return
        print(f"Update: v{info['current']} → v{info['latest']}")
        if info.get("body"):
            print(f"Changes:\n{info['body'][:200]}")
        print()
        confirm = input("Apply this update? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Update cancelled.")
            return
        result = up.update()
        print(result["message"])
    else:
        up.stats()


def _kb_handler(args):
    """Handle knowledge base commands: search, list, index, read."""
    kb = _import("knowledge_base")
    if not args or args[0] in ("help", "--help"):
        print("moyu kb commands:")
        print("  moyu kb index              Rebuild keyword index")
        print("  moyu kb search  <query>    Search knowledge files")
        print("  moyu kb list               List all knowledge files")
        print("  moyu kb read   <file>      Read a knowledge file")
        return
    subcmd = args[0]
    subargs = args[1:]
    if subcmd == "index":
        idx = kb.index()
        print(f"Indexed {idx['total']} knowledge files")
    elif subcmd == "search":
        query = " ".join(subargs)
        if not query:
            print("Usage: moyu kb search <query>")
            return
        results = kb.search(query)
        if results:
            print(f"\n📚 Knowledge Base results for: {query}")
            print("=" * 40)
            for r in results:
                print(f"  📄 {r['filename']} (score: {r['score']})")
                print(f"     path: {r['path']}")
                if r.get("triggers"):
                    print(f"     triggers: {', '.join(r['triggers'][:5])}")
                print()
        else:
            print(f"No results for '{query}'. Try `moyu kb index` first, or add files to knowledge/")
    elif subcmd == "list":
        kb.stats()
    elif subcmd == "read":
        fname = " ".join(subargs)
        content = kb.read(fname)
        if content:
            print(content)
        else:
            print(f"File not found. Try `moyu kb list` to see available files.")
    else:
        print(f"Unknown kb subcommand: {subcmd}")
        print("Usage: moyu kb {index|search|list|read}")


def _kg_handler(args):
    """Handle knowledge graph commands: search"""
    kg = _import("knowledge_graph")
    if not args or args[0] in ("help", "--help"):
        print("moyu kg commands:")
        print("  moyu kg search <entity>    Search knowledge graph for an entity")
        return
    subcmd = args[0]
    subargs = args[1:]
    if subcmd == "search":
        query = " ".join(subargs)
        if not query:
            print("Usage: moyu kg search <entity>")
            return
        results = kg.search(query)
        if results:
            print(f"\n🔗 Knowledge Graph results for: {query}")
            print("=" * 40)
            for r in results:
                print(f"  {r['entity']} — {r.get('relation', '?')} — {r.get('target', '?')}")
                if r.get("source"):
                    print(f"     source: {r['source']}")
                print()
        else:
            print(f"No knowledge graph entries found for '{query}'")
    else:
        print(f"Unknown kg subcommand: {subcmd}")
        print("Usage: moyu kg {search}")


def _ref_handler(args):
    """Handle ref command — list and read compressed refs."""
    cm = _import("context_manager")
    if not args or args[0] in ("list", "ls"):
        refs = cm._list_refs()
        if refs:
            print(f"\n  Available refs ({len(refs)}):")
            for r in refs:
                print(f"    \u2022 {r}")
            print()
        else:
            print("No refs.")
    else:
        content = cm.read_ref(args[0])
        if content:
            print(content)
        else:
            print(f"Ref not found: {args[0]}")


def show_help():
    """Show all available commands dynamically from CMD_TABLE."""
    print("\n  MOYU — CLI Entry Point")
    print("  " + "=" * 40)
    print("  Usage: moyu <command> [args]")
    print()
    cmds = sorted(CMD_TABLE.keys())
    for cmd in cmds:
        desc = HELP_DESCRIPTIONS.get(cmd, "??? (no description)")
        print(f"    {cmd:12s}  {desc}")
    print()
    print("  Run `moyu <command> help` for subcommand details.")
    print()


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "--help", "-h"):
        show_help()
        sys.exit(0)

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    # ── Silent integrity check + daily backup ──
    # Runs verify() on every moyu command. Checks hashes, triggers daily backup.
    # User only sees output if tampering is detected or manifest is missing.
    if cmd not in ("setup", "init", "audit", "check", "help", "--help", "-h"):
        try:
            ic = _import("defense_toolkit.integrity_checker")
            ic.verify()
        except Exception:
            pass

    # ── Auto-detect corrections on every command ──
    # Skip when the command itself is "learn" (would double-learn)
    if rest and cmd != "learn":
        user_text = " ".join(rest)
        try:
            lrn = _import("learner")
            hits = lrn.detect_corrections(user_text)
            if hits:
                lrn.learn(user_text)
        except Exception:
            pass

    # ── Security initialization prompt (silent) ──
    if cmd not in ("setup", "init", "audit", "help", "--help", "-h"):
        try:
            sec = _import("security")
            sec_info = sec.status()
            ic_module = _import("defense_toolkit.integrity_checker")
            import os as _os3
            sto = _os3.environ.get("MOYU_STORAGE",
                                    _os3.path.join(TOOLKIT_DIR, "memory_data"))
            man = _os3.path.join(sto, "manifest.json")
            if not sec_info.get("password_set", False) or not _os3.path.exists(man):
                print()
                print("  ⚡ Tip: Protect your memory layer!")
                if not sec_info.get("password_set", False):
                    print("     Run `moyu setup` to set a memory self-defense password")
                if not _os3.path.exists(man):
                    print("     Run `moyu init` to initialize integrity verification")
                print()
        except Exception:
            pass

    handler = CMD_TABLE.get(cmd)
    if handler:
        handler(rest)
    else:
        print(f"Unknown command: {cmd}")
        print()
        show_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
