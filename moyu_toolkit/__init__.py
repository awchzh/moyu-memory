"""
moyu_toolkit — MOYU AI Agent Memory Toolkit

Auto-init manifest on first import.
Silent daily integrity check (once per day, first import only).
"""

import os
import sys

_DAILY_CHECK_FILE = "_last_daily_check"


def _ensure_baseline():
    """Auto-init manifest + storage on first import. ~2ms, runs once."""
    from moyu_toolkit._moyu_paths import get_default_storage
    sto = get_default_storage()
    manifest = os.path.join(sto, "manifest.json")
    if not os.path.exists(manifest):
        try:
            from moyu_toolkit.defense_toolkit.integrity_checker import init_manifest
            init_manifest()
        except Exception:
            pass  # non-blocking


def _daily_quiet_check():
    """Silent integrity check, once per day. Report only on issues."""
    from moyu_toolkit._moyu_paths import get_default_storage
    sto = get_default_storage()
    check_flag = os.path.join(sto, _DAILY_CHECK_FILE)

    today = __import__("datetime").date.today().isoformat()

    # Already checked today?
    if os.path.exists(check_flag):
        try:
            with open(check_flag) as f:
                if f.read().strip() == today:
                    return  # already done today
        except Exception:
            pass

    # Run integrity check silently (capture stdout)
    import io
    from contextlib import redirect_stdout, redirect_stderr
    buf = io.StringIO()
    ok = True
    try:
        from moyu_toolkit.defense_toolkit.integrity_checker import verify
        with redirect_stdout(buf), redirect_stderr(buf):
            result = verify()
            if result is False:
                ok = False
    except Exception:
        ok = False

    # Only report on failure
    if not ok:
        output = buf.getvalue().strip()
        if output:
            print(f"[MOYU] ⚠️ 每日完整性校验发现异常，运行 moyu doctor 查看详情",
                  file=sys.stderr)

    # Mark today as checked
    try:
        os.makedirs(sto, exist_ok=True)
        with open(check_flag, "w") as f:
            f.write(today)
    except Exception:
        pass


# ── Run on import ──
_ensure_baseline()
_daily_quiet_check()
