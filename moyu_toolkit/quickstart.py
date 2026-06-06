#!/usr/bin/env python3
"""quickstart.py — MOYU Quickstart Launcher.

When run, asks the user to pick a language, then delegates to the
appropriate tour version.

Usage:
    python3 -c "from moyu_toolkit.quickstart import run; run()"
"""

import sys


def run():
    print()
    print("  🌐 Select language / 选择语言")
    print()
    print("    1. 中文 (简体)")
    print("    2. English")
    print()
    try:
        choice = input("  Enter 1 or 2 / 输入 1 或 2: ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = ""

    if choice == "2":
        _run_en()
    else:
        _run_cn()


def _run_cn():
    from moyu_toolkit.quickstart_v2 import run as cn_run
    cn_run()


def _run_en():
    from moyu_toolkit.quickstart_v2_en import run as en_run
    en_run()


if __name__ == "__main__":
    run()
