#!/usr/bin/env python3
"""
moyu_demo.py — MOYU capability showcase (self-adapting architecture)

Each module provides a demo() method → this engine auto-discovers & displays them.
Adding a new capability? Just add its module path to MODULES below.

Usage:
    python3 moyu_demo.py              # Show all
    python3 moyu_demo.py --compact    # Compact mode
"""

import sys
import os

# Add toolkit dir to path
TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLKIT_DIR not in sys.path:
    sys.path.insert(0, TOOLKIT_DIR)

# Module paths for each capability — add new ones here
MODULES = [
    "agent_memory",
    "active_context",
    "knowledge_graph",
    "learner",
    "defense_toolkit.integrity_checker",
    "security",
    "auto_extractor",
    "defense_toolkit.signature",
    "defense_toolkit.defense_log",
    "defense_toolkit.loop_detect",
]


def _load_demos() -> list:
    results = []
    for mod_path in MODULES:
        try:
            # Convert path to importable name
            import_name = mod_path.replace("/", ".").replace("\\", ".")
            mod = __import__(import_name, fromlist=["demo"])
            if hasattr(mod, "demo"):
                d = mod.demo()
                if d is not None:
                    results.append(d)
        except Exception as e:
            print(f"  ⚠️  {mod_path}: {e}", file=sys.stderr)

    results.sort(key=lambda r: r.get("capability", 999))
    return results


def run():
    compact = "--compact" in sys.argv
    demos = _load_demos()

    if not demos:
        print("❌ No demo() methods found.")
        print("   Make sure moyu_toolkit/ modules are properly installed.")
        sys.exit(1)

    total = len(demos)
    print()
    print("╔══════════════════════════════════════════════════╗")
    print(f"║       MOYU Demo — {total} capabilities in 20 seconds      ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    for i, d in enumerate(demos):
        cap = d.get("capability", i + 1)
        title = d.get("title", f"Capability #{cap}")
        output = d.get("output", "")

        if not compact:
            print("─" * 54)

        print(output)
        print()

    print("─" * 54)
    print("✅ Demo complete")
    print("─" * 54)
    print()
    print("  Want to see this with your own data?")
    print("  >>  Clear the memory_data/ directory and start using MOYU.")
    print()


if __name__ == "__main__":
    run()
