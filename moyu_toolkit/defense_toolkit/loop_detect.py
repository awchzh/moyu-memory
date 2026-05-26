#!/usr/bin/env python3
"""
loop_detect.py — MOYU 工具循环检测（V1.1）

README 描述：SHA256 fingerprint + exhaustive cycle scan + hard abort

三层检测：
  1. SHA256 fingerprint — 对 (操作名+完整参数) 取 SHA256，精确识别完全相同的调用
  2. Exhaustive cycle scan — 检测 A→B→A→B / A→B→C→A→B→C 等周期性循环
  3. Hard abort — 判定循环后主动阻断（返回 BLOCKED 状态，调用方必须响应）

用法：
    from defense_toolkit.loop_detect import record_operation, check_loop, get_status, is_blocked
    record_operation("search", "Python list comprehension", {"key": "val"})
    if is_blocked():
        print("🔴 操作已被阻断 — 检测到工具循环")
"""

import time
import hashlib
from collections import deque
from datetime import datetime

# ── 配置 ──
_MIN_OPS = 6         # 至少 6 次操作才开始检测
_CYCLE_MIN = 3       # 检测 3+ 次操作为周期的循环
_FP_WINDOW = 180     # 180 秒窗口
_FP_REPEAT = 3       # 同一指纹出现 3+ 次 → 循环

# ── 状态 ──
_operations = deque(maxlen=20)  # [(op, arg, fingerprint, timestamp), ...]
_blocked = False
_blocked_reason = ""


def _fingerprint(op: str, arg: str) -> str:
    """SHA256 fingerprint of operation + full arguments."""
    raw = f"{op}::{arg}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def record_operation(op: str, arg: str = "", metadata: dict = None):
    """
    记录一次工具调用。

    Args:
        op: 工具/操作名称
        arg: 参数（完整传入，无需截断，内部自动指纹）
        metadata: 可选，附加信息（返回值、耗时等）
    """
    global _blocked, _blocked_reason
    fp = _fingerprint(op, arg)
    _operations.append((op, arg, fp, time.time()))
    # New operation clears block state (caller should check is_blocked BEFORE calling)
    _blocked = False
    _blocked_reason = ""


def _scan_exhaustive_cycle(recent: list) -> bool:
    """
    穷尽周期扫描：检测操作序列中是否存在周期性模式。

    原理：尝试 2..window/2 的周期长度，
    检查序列是否按该周期重复。
    """
    n = len(recent)
    if n < _CYCLE_MIN * 2:
        return False

    ops_seq = [r[0] for r in recent]

    for period in range(2, n // 2 + 1):
        pattern = ops_seq[:period]
        matches = 0
        for i in range(period, n):
            expected = pattern[i % period]
            if ops_seq[i] == expected:
                matches += 1
        # 周期匹配率
        match_ratio = matches / (n - period)
        if match_ratio >= 0.8 and (n // period) >= 2:
            return True
    return False


def check_loop() -> bool:
    """
    三层循环检测。如果发现循环，设置阻断状态。

    Returns:
        True 表示检测到循环，调用方应停止当前操作。
    """
    global _blocked, _blocked_reason

    if len(_operations) < _MIN_OPS:
        return False

    now = time.time()
    recent = [(op, arg, fp, ts) for op, arg, fp, ts in _operations if now - ts < _FP_WINDOW]

    if len(recent) < _MIN_OPS:
        return False

    fpps = [r[2] for r in recent]
    ops = [r[0] for r in recent]
    args = [r[1] for r in recent]

    is_loop = False
    reason = ""

    # Layer 1: SHA256 fingerprint — 完全相同的调用重复
    fp_counts = {}
    for fp in fpps:
        fp_counts[fp] = fp_counts.get(fp, 0) + 1
    max_fp = max(fp_counts.values())
    if max_fp >= _FP_REPEAT:
        is_loop = True
        reason = f"SHA256 fingerprint repeat: {max_fp}x identical calls"

    # Layer 2: Exhaustive cycle scan — 周期模式
    if not is_loop:
        if _scan_exhaustive_cycle(recent):
            is_loop = True
            reason = f"Exhaustive cycle detected: {len(set(ops))} ops in periodic pattern"

    # Layer 3: 同操作 + 同参数重复（兜底）
    if not is_loop:
        top_op = max(set(ops), key=ops.count)
        top_op_count = ops.count(top_op)
        top_arg = max(set(args), key=args.count) if args else ""
        top_arg_count = args.count(top_arg) if top_arg else 0

        same_op_ratio = top_op_count / len(ops)
        same_arg_ratio = top_arg_count / max(len(args), 1) if top_arg else 0

        if same_op_ratio >= 0.7 and same_arg_ratio >= 0.5:
            is_loop = True
            reason = f"Same operation {top_op} ({top_op_count}/{len(ops)}), same arg ({top_arg_count})"

    # ── Hard abort: set block state ──
    if is_loop:
        _blocked = True
        _blocked_reason = reason

        # 记防御日志
        try:
            from defense_toolkit.defense_log import report as _dl_report
            _dl_report("loop_detect", "yellow", {
                "event": f"工具循环阻断 — {reason[:60]}",
                "source": "运行时监控",
                "detail": f"最近 {len(recent)} 次操作，{reason}",
                "auto_resolved": False,
            })
        except Exception:
            pass

    return is_loop


def is_blocked() -> bool:
    """检查当前是否处于阻断状态。调用方应每次操作前检查此函数。"""
    return _blocked


def block_reason() -> str:
    """获取阻断原因。"""
    return _blocked_reason


def get_status() -> dict:
    """获取循环检测状态。"""
    now = time.time()
    recent = [(op, arg, fp, ts) for op, arg, fp, ts in _operations if now - ts < _FP_WINDOW]
    ops = [r[0] for r in recent]
    fpps = [r[2] for r in recent]

    fp_counts = {}
    for fp in fpps:
        fp_counts[fp] = fp_counts.get(fp, 0) + 1
    max_fp = max(fp_counts.values()) if fp_counts else 0

    return {
        "tracked": len(_operations),
        "recent_window": len(recent),
        "unique_ops": len(set(ops)),
        "max_fingerprint_repeat": max_fp,
        "is_blocked": _blocked,
        "block_reason": _blocked_reason,
        "has_cycle": _scan_exhaustive_cycle(recent) if len(recent) >= _MIN_OPS else False,
    }


def reset():
    """完全重置检测状态。"""
    global _operations, _blocked, _blocked_reason
    _operations.clear()
    _blocked = False
    _blocked_reason = ""


def demo() -> dict:
    """Demo for moyu_demo discovery engine."""
    return {
        "capability": 5,
        "title": "Tool Loop Detection",
        "output": "🔄 工具循环检测 — SHA256 指纹 + 穷尽周期扫描 + 硬中断",
    }
