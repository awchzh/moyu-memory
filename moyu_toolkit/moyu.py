#!/usr/bin/env python3
"""
moyu — MOYU unified CLI entry point

Usage:
    moyu search <query>     Search memories
    moyu search <query> --ns <namespace>  Search within namespace
    moyu learn <text>       Learn from correction (auto-detects security rules)
    moyu learn <text> --ns <name>  Learn and store under a namespace
    moyu rules              List custom security rules
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

from moyu_toolkit._moyu_paths import get_package_dir
TOOLKIT_DIR = str(get_package_dir())
sys.path.insert(0, TOOLKIT_DIR)


def _import(name, silent=False):
    import importlib.util
    path = os.path.join(TOOLKIT_DIR, *name.split(".")) + ".py"
    if silent and not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
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
    storage_base = _os.environ.get("MOYU_STORAGE", get_default_storage() if 'get_default_storage' in dir() else _os.path.join(TOOLKIT_DIR, "memory_data"))
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
    import shutil
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
        # Disk usage
        total_size = 0
        for dirpath, _, filenames in os.walk(storage):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_size += os.path.getsize(fp)
                except Exception:
                    pass
        usage = shutil.disk_usage(storage) if os.path.exists(storage) else None
        if usage:
            pct = usage.used / usage.total * 100
            size_mb = total_size / 1024 / 1024
            free_gb = usage.free / 1024 / 1024 / 1024
            print(f"  Disk:     💾 {size_mb:.1f} MB used | {free_gb:.1f} GB free ({pct:.0f}% full)")
    else:
        print("  Storage:  ⚠️ Not initialized")
    print(f"  Security: {'✅ ready' if os.path.exists(os.path.join(TOOLKIT_DIR, 'security.py')) else '⚠️ Not available'}")
    
    # Audit log stats
    audit_path = os.path.join(storage, "audit_log.json")
    if os.path.exists(audit_path):
        try:
            import json as _j
            with open(audit_path) as _f:
                entries = _j.load(_f)
            demotes = sum(1 for e in entries if e.get("event") == "demote")
            distills = sum(1 for e in entries if e.get("event") == "distill")
            merges = sum(1 for e in entries if e.get("event") == "merge")
            protects = sum(1 for e in entries if e.get("event") in ("protect", "unprotect"))
            print(f"  Audit:    📋 {len(entries)} events ({demotes} demote, {distills} distill, {merges} merge, {protects} protect)")
        except Exception:
            pass
    
    # SQLite FTS5 index health
    sqlite_path = os.path.join(storage, "memory_search.db")
    if os.path.exists(sqlite_path):
        try:
            import sqlite3
            conn = sqlite3.connect(sqlite_path)
            cur = conn.execute("SELECT count(*) FROM search_index")
            idx_count = cur.fetchone()[0]
            conn.close()
            print(f"  FTS5:     🔍 {idx_count} entries indexed")
        except Exception:
            print(f"  FTS5:     ⚠️  Index exists but unreadable")
    else:
        print(f"  FTS5:     ⚠️  Not created yet (run moyu search to initialize)")
    
    # Protected memories count
    try:
        from moyu_toolkit.forgetting_curve import protected_ids
        prot_ids = protected_ids()
        if prot_ids:
            print(f"  Protected:🔒 {len(prot_ids)} memories")
    except Exception:
        pass
    
    print()
    # Defense chain visualization
    print(f"  {'─' * 48}")
    print(f"  🛡️  Defense Chain")
    print(f"  {'─' * 48}")
    import json as _json2
    import os as _os2
    _sec_cfg = {}
    _scp = _os2.path.join(storage, "security_config.json")
    if _os2.path.exists(_scp):
        try:
            with open(_scp) as _f:
                _sec_cfg = _json2.load(_f)
        except Exception:
            pass
    _pw_set = bool(_sec_cfg.get("safe_word_hash", ""))
    print(f"  ⚡ Pre-op:   {'✅ Password Set' if _pw_set else '⚠️ No Password'}  (moyu setup)")
    _has_man = _os2.path.exists(_os2.path.join(storage, "manifest.json"))
    print(f"  🔍 On-wake:  {'✅ Manifest Ready' if _has_man else '⚠️ Not Initialized'}  (moyu init)")
    _bak = _os2.path.join(storage, "backups")
    _has_bak = _os2.path.isdir(_bak) and any(f.startswith("daily_") for f in _os2.listdir(_bak)) if _os2.path.isdir(_bak) else False
    print(f"  🔄 Post:     {'✅ Recovery Ready' if _has_bak else '⚠️ No Backups Yet'}")
    print(f"  {'─' * 48}")
    print()
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
    "learn":      lambda args: _handle_learn_with_ns(args),
    "detect":     lambda args: _call_func("learner", "detect_corrections", [" ".join(args)]),
    "context":     lambda args: print(_import("learner").format_behavior_rules()),
    "signals":    lambda args: _call_func("learner", "signals", args),
    "setup":      lambda args: _handle_setup(args),
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
    "protect":    lambda args: _protect_handler(args),
    "tune":       lambda args: _handle_tune(args),
    "rules":      lambda args: _handle_rules(args),
    "benchmark":  lambda args: _import("security_benchmark").main(*args),
    "mutate":     lambda args: _import("injection_mutator").main(*args),
    "doctor":     lambda args: _import("moyu_doctor").main(*args),
    "snapshot":   lambda args: _import("moyu_snapshot").main(*args),
    "demo-attack": lambda args: _import("moyu_demo_attack").main(*args),
    "config":     lambda args: _config_handler(args),
    "inject":     lambda args: _handle_inject(args),
    "quickstart": lambda args: _call_func("quickstart", "run", []),
    "extract":    lambda args: _handle_extract(args),
    "session":    lambda args: _handle_session(args),
    "frequency":  lambda args: _handle_frequency(args),
}

HELP_DESCRIPTIONS = {
    "search": "Search memories (TEMPR multi-strategy)",
    "stats": "Show all statistics (memory, learner, security)",
    "status": "Show system status with defense chain visualization",
    "learn": "Learn from a user correction",
    "detect": "Detect correction signals in text",
    "context": "Get behavioral rules (for agent context)",
    "signals": "View active trigger words (learner)",
    "setup": "Set a security password",
    "verify": "Verify a dangerous operation",
    "unlock": "Unlock security system (after 3 failed attempts)",
    "check": "Check memory file integrity (SHA256)",
    "init": "Initialize integrity verification manifest",
    "audit": "Full security audit (all 3 defense layers)",
    "rules": "List and manage custom security rules",
    "benchmark": "Run security capability benchmark (--quick, --full for RTPB2026)",
    "mutate": "Run injection pattern mutation scan to find blind spots",
    "doctor": "Run memory health check (redudancy, refs, integrity, security)",
    "snapshot": "Export/restore read-only memory snapshots",
    "demo-attack": "Interactive injection attack demonstration",
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
    "protect":    "Manage protected memories: {list|add|remove}",
    "tune":      "Auto-tune retrieval weights from feedback data (moyu tune / --dry-run / --reset)",
    "config":    "Show/set retrieval weights (moyu config show / set retrieval.weights.<dim> <val>)",
    "inject":    "Inject relevant memories into agent context (moyu inject <query>)",
    "quickstart": "5-minute interactive demo — auto-stores memories, tests defense chain, zero config",
    "extract":    "Auto-extract memories from conversation text (moyu extract <text> / stats)",
    "session":    "Session state — state, prompt, decisions, pending (moyu session <state|prompt|decision|pending>)",
    "frequency":  "Frequency guard — stats, unlock (moyu frequency stats / unlock <name>)",
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


def _handle_learn_with_ns(args):
    """Handle 'moyu learn' with optional --ns namespace flag."""
    ns = None
    remaining = list(args)
    # Look for --ns <namespace>
    for i, arg in enumerate(args):
        if arg == "--ns" and i + 1 < len(args):
            ns = args[i + 1]
            remaining = [a for j, a in enumerate(args) if j not in (i, i + 1)]
            break
    text = " ".join(remaining)
    if ns:
        # Store as memory with namespace AND try custom rules
        try:
            cr = _import("custom_rules")
            result = cr.analyze_and_learn(text)
            if result.get("learned"):
                print(f"🛡️  [{ns}] {result['message']}")
            else:
                print(f"📝 [{ns}] Stored as memory in namespace '{ns}'")
        except Exception:
            print(f"📝 [{ns}] Stored as memory in namespace '{ns}'")
        # Also store as a memory with namespace
        try:
            mem = _import("agent_memory")
            mem.add_memory(text, source="user", metadata={"namespace": ns})
        except Exception:
            pass
    else:
        _handle_learn(text)


def _handle_learn(text):
    """Handle 'moyu learn' — try custom rules first, then fall back to learner."""
    if not text:
        print("Usage: moyu learn <text>")
        return
    
    # Try to extract a security rule first
    try:
        cr = _import("custom_rules")
        result = cr.analyze_and_learn(text)
        if result.get("learned"):
            print(f"🛡️  {result['message']}")
            return
        if result.get("message"):
            print(f"ℹ️  {result['message']}")
    except Exception as e:
        pass  # Fall through to learner
    
    # Fall back to regular learner
    _call_func("learner", "learn", [text])
    
    # Phase 2: record correction as feedback signal
    try:
        fb = _import("feedback")
        fb.record_correction(text, [])
    except Exception:
        pass


def _handle_rules(args):
    """Handle 'moyu rules' — list/delete custom security rules."""
    cr = _import("custom_rules")
    
    if args and args[0] == "delete":
        cr._ensure_rules_file()
        rules_path = os.path.join(__import__("moyu_toolkit._moyu_paths", fromlist=["get_default_storage"]).get_default_storage(), "custom_rules.json")
        if os.path.exists(rules_path):
            os.remove(rules_path)
        print("🗑️  All custom rules deleted")
        return
    
    stats = cr.stats()
    if stats["count"] == 0:
        print("📭 No custom rules yet. Teach me with: moyu learn \"\\\"some pattern\\\" should be blocked\"")
        return
    
    print(f"\n📋 Custom Security Rules ({stats['count']})")
    print("=" * 50)
    for r in stats["rules"]:
        print(f"  • {r['note'][:70]}")
    print()
    print("Teach me a new rule: moyu learn \"\\\"pattern\\\" should be blocked\"")
    print("Delete all rules:     moyu rules delete")


def _handle_search(args):
    if not args:
        print("Usage: moyu search <query> [--vote <id> good|bad]")
        return
    
    # Check for --vote parameter
    vote_id = None
    vote_val = None
    cleaned_args = list(args)
    for i in range(len(args) - 2):
        if args[i] == "--vote" and i + 2 < len(args):
            vote_id = args[i + 1]
            vote_val = args[i + 2]
            cleaned_args = [a for j, a in enumerate(args) if j not in (i, i + 1, i + 2)]
            break
    
    query = " ".join(cleaned_args)
    mem = _import("agent_memory")
    
    # If --vote was given without a new query, try recording without searching
    if not query and vote_id and vote_val:
        try:
            fb = _import("feedback")
            fb.record_vote("", vote_id, vote_val)
            print(f"✅ Vote recorded: {vote_id} = {vote_val}")
        except Exception as e:
            print(f"⚠️  Could not record vote: {e}")
        return
    
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
        mid = r.get('memory_id', '')[:20]
        print(f"  ID: {mid}  Score: {r.get('score', 0)}")
    
    # Track access for forgetting curve density analysis
    try:
        fc = _import("forgetting_curve")
        fc.track_access([r['memory_id'] for r in results])
    except Exception:
        pass
    
    # Show vote hint
    if len(results) > 0:
        first = results[0]
        print(f"\n  💡 Tip: moyu search --vote {first['memory_id']} good")
        print(f"              to tell MOYU this result was useful")

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
        if result.get("pip_upgrade"):
            print(f"⬆️  v{info['latest']} 已发布。运行以下命令升级：")
            print(f"   pip install --upgrade moyu")
        else:
            print(result["message"])
    else:
        up.stats()


def _protect_handler(args):
    """Handle protect command: list/add/remove protected memories."""
    fc = _import("forgetting_curve")
    if not args or args[0] in ("list", "--list"):
        ids = fc.protected_ids()
        if ids:
            print(f"🔒 受保护记忆 ({len(ids)} 条):")
            for mid in ids:
                print(f"  • {mid}")
        else:
            print("🔒 当前没有受保护记忆")
        return
    if args[0] in ("add", "--add") and len(args) >= 2:
        fc.protect(args[1])
        return
    if args[0] in ("remove", "rm", "--remove") and len(args) >= 2:
        fc.unprotect(args[1])
        return
    print("Usage: moyu protect <list|add <id>|remove <id>>")


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
                print(f"    • {r}")
            print()
        else:
            print("No refs.")
    else:
        content = cm.read_ref(args[0])
        if content:
            print(content)
            # Phase 2: record ref read as positive feedback signal
            try:
                fb = _import("feedback")
                fb.record_ref(args[0])
            except Exception:
                pass
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


def _handle_setup(args):
    """Handle setup subcommands."""
    if not args:
        _import("security").setup()
        return
    if args[0] == "agents":
        _auto_register_agents()
    else:
        _import("security").setup()


def _auto_register_agents():
    """Auto-detect and configure agents to use moyu inject."""
    import os as _ao_os
    import shutil as _ao_shutil
    detected = []
    configured = []
    
    home = _ao_os.path.expanduser("~")
    
    # 1. Hermes — write to config or prefill
    hermes_cfg = _ao_os.path.join(home, ".hermes", "config.yaml")
    hermes_prefill = _ao_os.path.join(home, ".hermes", "prefill.json")
    if _ao_os.path.isdir(_ao_os.path.join(home, ".hermes")):
        detected.append("Hermes")
        # Check if prefill.json exists and already has MOYU injection
        has_inject = False
        if _ao_os.path.exists(hermes_prefill):
            try:
                import json as _ao_json
                with open(hermes_prefill) as _f:
                    pf = _ao_json.load(_f)
                for entry in pf:
                    if "moyu inject" in str(entry.get("content", "")):
                        has_inject = True
                        break
            except Exception:
                pass
        if not has_inject:
            # Actually write the MOYU inject into Hermes prefill.json
            try:
                import json as _ao_json
                existing = []
                if _ao_os.path.exists(hermes_prefill):
                    with open(hermes_prefill) as _f:
                        existing = _ao_json.load(_f)
                # Add a system entry that tells Hermes to run moyu inject at startup
                inject_entry = {
                    "role": "system",
                    "content": "📡 MOYU记忆已连接。每次对话前调用 `moyu inject \"当前对话主题\"` 获取相关记忆。"
                }
                # Don't add duplicates
                already_has = False
                for e in existing:
                    if "MOYU记忆已连接" in str(e.get("content", "")):
                        already_has = True
                        break
                if not already_has:
                    existing.append(inject_entry)
                    with open(hermes_prefill, "w") as _f:
                        _ao_json.dump(existing, _f, ensure_ascii=False, indent=2)
                    configured.append("Hermes (prefill.json ✅ auto-configured)")
                else:
                    configured.append("Hermes (prefill.json ✅ already configured)")
            except Exception:
                configured.append("Hermes (prefill.json ⚠️ write failed)")

    # 2. Claude Code
    cc_dir = _ao_os.path.join(home, ".claude")
    if _ao_os.path.isdir(cc_dir):
        detected.append("Claude Code")
        configured.append("Claude Code (run manually: moyu inject in claude.md)")
    
    # 3. Cursor
    cursor_dir = _ao_os.path.join(home, ".cursor")
    if _ao_os.path.isdir(cursor_dir):
        detected.append("Cursor")
    
    # Report
    print("\n📡 Agent Auto-Detection Results")
    print("=" * 36)
    if detected:
        for agent in detected:
            print(f"  ✅ {agent}")
    else:
        print("  (no supported agents detected)")
    
    if configured:
        print("\n  Auto-configured:")
        for c in configured:
            print(f"    • {c}")
    
    print("\n  💡 Use `moyu inject <query>` to inject relevant memories")
    print("     into any agent's context or prompt.")
    print()


def _handle_tune(args):
    """Handle tune command — adaptive weight tuning."""
    if args and args[0] in ("--reset", "reset"):
        try:
            tn = _import("tune")
            tn.reset()
            print("✅ Weights reset to defaults")
            return
        except Exception as e:
            print(f"⚠️  Reset failed: {e}")
            return
    dry_run = "--dry-run" in args
    try:
        tn = _import("tune")
        result = tn.tune(dry_run=dry_run)
        if result["status"] == "insufficient_data":
            need = result.get("needed", 0)
            print(f"⚠️  Need {need} more signals ({result.get('total_signals',0)} collected)")
        elif result["status"] == "no_signals":
            print("ℹ️  No feedback data yet. Use moyu search --vote to collect.")
        elif result["status"] == "tuned":
            r = result.get("reasoning", {})
            print(f"\n📊 Adaptive Tuning: {r.get('positive_signals',0)}+/"
                  f"{r.get('negative_signals',0)}-")
            print(f"  Direction: {r.get('direction','balanced')}")
            for dim in ['semantic','keyword','recency','entity']:
                b4 = result.get("current",{}).get(dim,0)
                aft = result.get("suggested",{}).get(dim,0)
                if abs(b4 - aft) >= 0.01:
                    arrow = "↑" if aft > b4 else "↓"
                    print(f"  {dim}: {b4:.2f} {arrow} {aft:.2f}")
            print(f"\n  {'Dry run —' if dry_run else '✅'} weights {'would be' if dry_run else ''} updated.")
        else:
            print(f"Unknown: {result}")
    except Exception as e:
        print(f"⚠️  Tuning failed: {e}")


def _handle_inject(args):
    """Inject relevant memories into agent context.
    
    Usage: moyu inject <query>
           moyu inject <query> --limit 3
           moyu inject <query> --format context
    """
    query = " ".join([a for a in args if not a.startswith("--")]).strip()
    limit = 5
    fmt = "prompt"
    
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif args[i] == "--format" and i + 1 < len(args):
            fmt = args[i + 1]
            i += 2
        else:
            i += 1
    
    if not query:
        print("Usage: moyu inject <query> [--limit N] [--format prompt|context]")
        return
    
    try:
        am = _import("agent_memory")
        results = am.search(query, top_k=limit)
    except Exception as e:
        print(f"⚠️  Memory search failed: {e}")
        return
    
    if not results:
        if fmt == "prompt":
            print("[MOYU: No relevant memories found.]")
        else:
            print("(no relevant memories)")
        return
    
    if fmt == "context":
        for r in results:
            print(f"  • {r.get('summary', '')[:120]}")
        return
    
    # Default: prompt format — clean, ready for injection
    print("[MOYU Memory Injection]")
    print()
    for r in results:
        score = r.get("score", 0)
        bar = "▸" if score > 0 else " "
        summary = r.get("summary", "")
        if summary:
            print(f"  {bar} {summary[:200]}")
    print()
    print(f"[{len(results)} memories injected]")
    
    # Auto-append context warning to injected output
    try:
        cm = _import("context_manager")
        name, data = cm.get_context()
        if name and data:
            pct = data.get("pct", 0)
            cfg = getattr(cm, '_load_compression_config', lambda: {})()
            lang = cfg.get("warn_language", "zh") if isinstance(cfg, dict) else "zh"
            warn_at = int(cfg.get("warn_threshold", 0.7) * 100) if isinstance(cfg, dict) else 70
            if isinstance(pct, (int, float)) and pct >= warn_at:
                if lang == "zh":
                    print(f"\n[NOTE] {name}上下文用到 {pct}% 了，对话已深，可以考虑 /new")
                else:
                    print(f"\n[NOTE] {name} context at {pct}%, /new recommended")
    except Exception:
        pass


def _handle_extract(args):
    """Handle extract command — auto-extract memories from text.
    
    Usage: moyu extract <text>
           moyu extract stats
    """
    try:
        ae = _import("auto_extractor")
    except ImportError:
        print("⚠️  auto_extractor not available (added in v2.7.x)")
        return
    except Exception as e:
        print(f"⚠️  auto_extractor failed to load: {e}")
        return

    if not args:
        print("Usage: moyu extract <text> | moyu extract stats")
        return

    if args[0] in ("stats", "--stats"):
        s = ae.stats()
        print(f"📊 Auto Extractor Stats")
        print(f"   Total extracted: {s['total_extracted']}")
        print(f"   By method: {s['by_method']}")
        print(f"   By type: {s['by_type']}")
        if s["paused_types"]:
            print(f"   ⏸️  Paused types: {s['paused_types']}")
        return

    text = " ".join(args)
    count = ae.extract_and_store(text)
    print(f"✅ Extracted {count} memories")
    if count == 0:
        print("   (no new facts found — text may be too short or contain only noise)")


def _handle_session(args):
    """Handle session command — show state, generate prompt, manage decisions/pending.

    Usage:
        moyu session state           Show session state summary
        moyu session prompt          Generate system prompt snippet for manual config
        moyu session decision <text> Record a decision
        moyu session pending <text>  Add a pending item
        moyu session clear           Clear all decisions and pending
    """
    sb = _import("session_bridge")

    if not args:
        print("Usage: moyu session <state|prompt|decision|pending|clear>")
        print()
        print("  moyu session state    — Show current session state")
        print("  moyu session prompt   — Get prompt snippet for Agent system prompt")
        print("  moyu session decision <text>  — Record a decision")
        print("  moyu session pending <text>   — Add a pending item")
        print("  moyu session clear    — Clear all decisions and pending")
        print()
        print("  For Hermes users: session state auto-syncs to prefill — zero config.")
        print("  For other agents: run `moyu session prompt` and paste into system prompt.")
        return

    cmd = args[0]

    if cmd in ("state", "status"):
        summary = sb.format_state_summary()
        if summary:
            print(summary)
        else:
            print("（暂无状态）")

    elif cmd == "prompt":
        prompt = sb.generate_session_prompt()
        print(prompt)
        print()
        print("---")
        print("Copy the text above into your Agent's system prompt configuration.")
        print("Or run `moyu session prompt > ~/.moyu/session_prompt.md` to save to file.")

    elif cmd in ("decision", "decide"):
        text = " ".join(args[1:])
        if not text:
            print("Usage: moyu session decision <text>")
            return
        sb.add_decision(text)
        print(f"✅ Decision recorded")

    elif cmd in ("pending", "todo", "add"):
        text = " ".join(args[1:])
        if not text:
            print("Usage: moyu session pending <text>")
            return
        sb.add_pending(text)
        print(f"✅ Pending added")

    elif cmd == "clear":
        from session_bridge import _load, _sync_all
        data = sb._load()
        data["decisions"] = []
        data["pending"] = []
        sb._sync_all(data)
        print("✅ Session state cleared")

    else:
        print(f"Unknown session subcommand: {cmd}")
        print("Usage: moyu session <state|prompt|decision|pending|clear>")


def _handle_frequency(args):
    """Handle frequency command — guard stats and unlock.

    Usage:
        moyu frequency stats           Show frequency guard stats
        moyu frequency unlock <name>   Unlock a rule (write/read)
    """
    try:
        fg = _import("frequency_guard")
    except ImportError:
        print("⚠️  frequency_guard not available")
        return
    except Exception as e:
        print(f"⚠️  frequency_guard failed to load: {e}")
        return

    if not args or args[0] in ("stats", "--stats"):
        s = fg.guard_stats()
        print("📊 Frequency Guard Stats")
        for name, info in s.items():
            status = "🔒 LOCKED" if info["locked"] else "✅ OK"
            print(f"  [{name}] {info['recent_count']}/{info['threshold']} in {info['window']}s — {status}")
            if info["locked"]:
                remaining = fg.get_guard().lock_remaining(name)
                print(f"           Lock expires in {remaining:.0f}s")
        return

    if args[0] == "unlock" and len(args) >= 2:
        fg.get_guard().unlock(args[1])
        print(f"✅ Unlocked ({args[1]})")
        return

    print("Usage: moyu frequency stats | moyu frequency unlock <name>")


def _config_handler(args):
    """Handle config command — show and set retrieval weights."""
    import os as _cfg_os
    from moyu_toolkit._moyu_paths import get_config_path

    if not args or args[0] in ("help", "--help", "-h"):
        print("moyu config commands:")
        print("  moyu config show                    Show current retrieval weights")
        print("  moyu config set retrieval.weights.<dim> <val>  Set a retrieval weight:")
        print("    semantic  — Semantic similarity weight (default 0.5)")
        print("    keyword   — BM25 keyword weight (default 0.3)")
        print("    recency   — Recency/decay weight (default 0.2)")
        print("    entity    — Entity boost weight (default 0.0)")
        print()
        print("  Example: moyu config set retrieval.weights.entity 0.3")
        return
    if args[0] in ("show", "list", "--show", "--list"):
        try:
            am = _import("agent_memory")
            w = am._get_retrieval_weights()
            print("\n📋 Current Retrieval Weights")
            print("=" * 32)
            for dim in ["semantic", "keyword", "recency", "entity"]:
                print(f"  {dim:12s} = {w.get(dim, 0.0):.2f}")
            print()
        except Exception as e:
            print(f"❌ Error reading weights: {e}")
        return
    if args[0] == "set" and len(args) >= 3:
        key = args[1]
        val = args[2]
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == "retrieval" and parts[1] == "weights":
            dim = parts[2]
            allowed = ["semantic", "keyword", "recency", "entity"]
            if dim not in allowed:
                print(f"❌ Unknown dimension '{dim}'. Allowed: {', '.join(allowed)}")
                return
            try:
                fval = float(val)
                if fval < 0:
                    print("❌ Weight must be >= 0")
                    return
                config_path = get_config_path()
                am = _import("agent_memory")
                cfg = am._load_config()
                if "memory" not in cfg:
                    cfg["memory"] = {}
                if "weights" not in cfg["memory"]:
                    cfg["memory"]["weights"] = {}
                cfg["memory"]["weights"][dim] = fval
                import yaml as _yaml
                with open(config_path, "w") as _f:
                    _yaml.dump(cfg, _f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                print(f"✅ retrieval.weights.{dim} = {fval}")
                print("   Changes take effect on next search.")
            except ValueError:
                print(f"❌ Invalid value '{val}'. Must be a number.")
        else:
            print(f"❌ Unknown config key '{key}'. Use 'retrieval.weights.<dim>'")
        return
    print(f"Unknown subcommand: {args[0]}")
    _config_help()


def _config_help():
    """Show config help."""
    print("moyu config commands:")
    print("  moyu config show                    Show current retrieval weights")
    print("  moyu config set retrieval.weights.<dim> <val>  Set a retrieval weight:")
    print("    semantic  — Semantic similarity weight (default 0.5)")
    print("    keyword   — BM25 keyword weight (default 0.3)")
    print("    recency   — Recency/decay weight (default 0.2)")
    print("    entity    — Entity boost weight (default 0.0)")
    print()
    print("  Example: moyu config set retrieval.weights.entity 0.3")


def _load_auto_extract_config() -> bool:
    """Load auto_extract enabled flag from config.yaml. Returns True by default."""
    try:
        import yaml as _yaml
        cfg_path = os.path.join(TOOLKIT_DIR, "config.yaml")
        if os.path.exists(cfg_path):
            with open(cfg_path) as _f:
                cfg = _yaml.safe_load(_f) or {}
            return cfg.get("memory", {}).get("auto_extract", True)
    except Exception:
        pass
    return True


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
    
    # ── First-run auto-setup: detect agents + set tune cron ──
    init_marker = os.path.join(TOOLKIT_DIR, ".initialized")
    if cmd not in ("help", "--help", "-h", "setup", "init") and not os.path.exists(init_marker):
        try:
            _auto_register_agents()
            # Mark initialized so this only runs once
            try:
                with open(init_marker, "w") as _mf:
                    _mf.write(f"MOYU initialized at {__import__('datetime').datetime.now().isoformat()}")
            except Exception:
                pass
        except Exception:
            pass

    # ── First-run session state tip (show once after update) ──
    session_tip_marker = os.path.join(TOOLKIT_DIR, ".session_tip_shown")
    if cmd not in ("help", "--help", "-h", "setup", "init", "session") and not os.path.exists(session_tip_marker):
        try:
            sb = _import("session_bridge")
            # Check if session state has content - if not, show tip
            summary = sb.format_state_summary()
            if not summary:
                print()
                print("  🌉 Tip: Session state lets you continue conversations across sessions.")
                print("     Hermes users: zero config — state auto-syncs to prefill.")
                print("     Other agents: run `moyu session prompt` for setup instructions.")
                print()
            # Mark shown (even if no content, don't show again)
            try:
                with open(session_tip_marker, "w") as _tf:
                    _tf.write(f"Session tip shown at {__import__('datetime').datetime.now().isoformat()}")
            except Exception:
                pass
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
                # Phase 2: record auto-detected correction as feedback
                try:
                    fb = _import("feedback")
                    fb.record_correction(user_text, hits)
                except Exception:
                    pass
        except Exception:
            pass

    # ── Auto-extract memories from command text (when enabled) ──
    # Silently runs extractor on every moyu command's text arguments.
    # Skip when the command itself is "extract" (would double-extract).
    # User only sees output if something was actually stored.
    # Disable via config.yaml → memory.auto_extract: false
    if rest and cmd != "extract":
        cmd_text = " ".join(rest)
        try:
            # Import without triggering hard error if module not available
            ae = _import("auto_extractor", silent=True)
            if ae is None:
                pass
            else:
                # Check config for auto_extract flag
                _cfg_ae = _load_auto_extract_config()
                if _cfg_ae:
                    count = ae.extract_and_store(cmd_text)
                    if count > 0:
                        # Only show brief feedback when something was stored
                        print(f"🧠 从输入中提取了 {count} 条记忆")
        except Exception:
            pass

    # ── Security initialization prompt (silent) ──
    if cmd not in ("setup", "init", "audit", "help", "--help", "-h"):
        try:
            sec = _import("security")
            sec_info = sec.status()
            ic_module = _import("defense_toolkit.integrity_checker")
            import os as _os3
            sto = _os3.environ.get("MOYU_STORAGE", _os3.path.join(TOOLKIT_DIR, "memory_data"))
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


def main_cli():
    """Entry point for pip-installed `moyu` command (console_scripts)."""
    main()


if __name__ == "__main__":
    main()
