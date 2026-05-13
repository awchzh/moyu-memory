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
    moyu inject             Get rules for injection
    moyu signals            View active trigger words
    moyu demo               Show all capabilities
    moyu compress           Show compression status
    moyu compress --now     Force manual compression
    moyu forget             Show memory lifecycle (forgetting curve)
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
    try:
        sec = _import("security")
        sec.status()
    except Exception:
        pass
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


def cmd_demo():
    demo_path = os.path.join(TOOLKIT_DIR, "moyu_demo.py")
    exec(open(demo_path).read(), {"__name__": "__main__", "__file__": demo_path})


CMD_TABLE = {
    "search":     lambda args: _handle_search(args),
    "stats":      lambda args: cmd_stats(),
    "status":     lambda args: cmd_status(),
    "learn":      lambda args: _call_func("learner", "learn", [" ".join(args)]),
    "detect":     lambda args: _call_func("learner", "detect", [" ".join(args)]),
    "inject":     lambda args: print(_import("learner").get_rules_for_injection()),
    "signals":    lambda args: _call_func("learner", "signals", args),
    "setup":      lambda args: _import("security").setup(),
    "verify":     lambda args: _verify_op(args),
    "unlock":     lambda args: _import("security").unlock(),
    "check":      lambda args: _call_func("defense_toolkit.integrity_checker", "verify", args),
    "init":       lambda args: _call_func("defense_toolkit.integrity_checker", "init_manifest", args),
    "compress":   lambda args: _compress(args),
    "forget":     lambda args: _forget(args),
    "lifecycle":  lambda args: _forget(args),  # alias
    "bridge":     lambda args: _import("session_bridge").status(),
    "update":     lambda args: _update(args),
    "demo":       lambda args: cmd_demo(),
}


def _call_func(module, func, args):
    m = _import(module)
    fn = getattr(m, func, None)
    if fn:
        fn(*args)


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
        print()


def _compress(args):
    cm = _import("context_manager")
    if "--now" in args:
        ctx = _import("active_context")
        lrn = _import("learner")
        wm = ctx.format_for_injection()
        rules = lrn.get_rules_for_injection()
        result, report = cm.build_injection(working_memory=wm, behavioral_rules=rules)
        msg = cm.last_report_message()
        print(f"🚚 Manual compression triggered")
        print(f"  {msg}" if msg else f"  No compression needed ({report['usage_pct']}% of budget)")
        print()
    else:
        cm.stats()


def _forget(args):
    """Handle forget command — check forgetting curve status."""
    fc = _import("forgetting_curve")
    if "--summary" in args:
        print(fc.summary())
    else:
        fc.stats()


def _update(args):
    """Handle update command — check and apply updates."""
    up = _import("updater")
    if "--dry" in args or "check" in args:
        info = up.check()
        if "error" in info:
            print(f"Error: {info['error']}")
        else:
            print(f"Current: v{info['current']} → Latest: v{info['latest']}")
            print(f"Update available: {info['is_newer']}")
    elif "now" in args or "apply" in args:
        result = up.update()
        print(result["message"])
    else:
        up.stats()


def show_help():
    print(__doc__.strip())


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "--help", "-h"):
        show_help()
        sys.exit(0)

    cmd = sys.argv[1]
    rest = sys.argv[2:]

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
