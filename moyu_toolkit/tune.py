#!/usr/bin/env python3
"""tune.py — MOYU Phase 3: Adaptive retrieval weight tuning.

Reads feedback data (search_feedback_*.jsonl) and automatically adjusts
config.yaml retrieval weights to improve search relevance over time.

Usage:
    moyu tune              — Auto-tune weights from collected feedback
    moyu tune --dry-run    — Show recommended changes without applying
    moyu tune --reset      — Reset weights to defaults
"""

import json
import os
import glob
import math
from collections import defaultdict
from datetime import datetime
from typing import Optional


WEIGHT_DIMS = ["semantic", "keyword", "recency", "entity"]
DEFAULT_WEIGHTS = {"semantic": 0.5, "keyword": 0.3, "recency": 0.2, "entity": 0.0}
TUNE_STEP = 0.02       # Amount to adjust per batch of signals
MIN_SIGNALS = 5        # Minimum feedback signals before tuning
LEARNING_RATE = 0.3    # How aggressively to adjust toward optimal


def _storage_path() -> str:
    base = os.environ.get("MOYU_STORAGE", "")
    if not base:
        from moyu_toolkit._moyu_paths import get_default_storage
        base = get_default_storage()
    return base


def _load_feedback() -> list[dict]:
    """Load all feedback entries from all monthly files."""
    data_dir = _storage_path()
    entries = []
    for fpath in sorted(glob.glob(os.path.join(data_dir, "search_feedback_*.jsonl"))):
        try:
            with open(fpath) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except (FileNotFoundError, PermissionError):
            pass
    return entries


def _current_weights() -> dict:
    """Read current weights from config.yaml."""
    from moyu_toolkit.agent_memory import _get_retrieval_weights
    return _get_retrieval_weights()


def _write_weights(weights: dict) -> None:
    """Write weights to config.yaml."""
    from moyu_toolkit._moyu_paths import get_config_path
    from moyu_toolkit.agent_memory import _load_config
    import yaml

    config_path = get_config_path()
    cfg = _load_config()
    if "memory" not in cfg:
        cfg["memory"] = {}
    if "weights" not in cfg["memory"]:
        cfg["memory"]["weights"] = {}
    for dim in WEIGHT_DIMS:
        cfg["memory"]["weights"][dim] = weights[dim]
    with open(config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _analyze_signals(entries: list) -> dict:
    """Analyze feedback signals: group positive/negative per dimension impact."""
    # For every positive signal (vote_good, ref), we know the user found that memory useful
    # For negative (vote_bad), we know the user found it NOT useful
    # We look at what dimensions the vector index suggests for correlation

    pos_signals = [e for e in entries if e.get("kind") in ("vote_good", "ref")]
    neg_signals = [e for e in entries if e.get("kind") == "vote_bad"]

    return {"positive": len(pos_signals), "negative": len(neg_signals), "total": len(entries)}


def _compute_tune(entries: list, dry_run: bool = False) -> dict:
    """Compute optimal weight adjustments from feedback."""
    current = _current_weights()
    signal_summary = _analyze_signals(entries)

    if signal_summary["total"] < MIN_SIGNALS:
        return {
            "status": "insufficient_data",
            "needed": MIN_SIGNALS - signal_summary["total"],
            "current": current,
            "total_signals": signal_summary["total"],
        }

    # Count signals per dimension preference
    # vote_good + ref = positive signal for the memory that was used
    # vote_bad = negative signal
    pos_count = signal_summary["positive"]
    neg_count = signal_summary["negative"]

    if pos_count == 0 and neg_count == 0:
        return {"status": "no_signals", "current": current}

    # Simple heuristic: if more positive than negative, semantic weight should dominate
    # (users find semantically relevant results useful)
    # If more negative, keyword might be too dominant
    ratio = pos_count / max(pos_count + neg_count, 1)

    suggested = current.copy()

    if ratio > 0.6:
        # Users find results useful → boost semantic, slightly reduce keyword
        suggested["semantic"] = min(1.0, suggested["semantic"] + TUNE_STEP)
        suggested["keyword"] = max(0.0, suggested["keyword"] - TUNE_STEP * 0.5)
    elif ratio < 0.4:
        # Users find results NOT useful → reduce semantic, boost keyword + recency
        suggested["semantic"] = max(0.0, suggested["semantic"] - TUNE_STEP)
        suggested["keyword"] = min(1.0, suggested["keyword"] + TUNE_STEP * 0.5)
        suggested["recency"] = min(1.0, suggested["recency"] + TUNE_STEP * 0.3)

    # Normalize so sum ≈ 1.0
    total = sum(suggested.values())
    if total > 0:
        for dim in WEIGHT_DIMS:
            suggested[dim] = round(suggested[dim] / total, 2)

    # Ensure recency floor
    if suggested["recency"] < 0.05:
        suggested["recency"] = 0.05

    return {
        "status": "tuned",
        "current": current,
        "suggested": suggested,
        "changed": {dim: round(suggested[dim] - current[dim], 2) for dim in WEIGHT_DIMS
                    if abs(suggested[dim] - current[dim]) >= 0.01},
        "reasoning": {
            "positive_signals": pos_count,
            "negative_signals": neg_count,
            "ratio": round(ratio, 2),
            "direction": "boost_semantic" if ratio > 0.6 else "reduce_semantic" if ratio < 0.4 else "balanced",
        },
    }


def tune(dry_run: bool = False) -> dict:
    """Run adaptive weight tuning."""
    entries = _load_feedback()
    result = _compute_tune(entries, dry_run)

    if result["status"] == "tuned" and not dry_run:
        _write_weights(result["suggested"])
        result["applied"] = True
    else:
        result["applied"] = False

    return result


def reset() -> dict:
    """Reset weights to defaults."""
    _write_weights(DEFAULT_WEIGHTS)
    return {"status": "reset", "weights": DEFAULT_WEIGHTS}


def show_stats() -> dict:
    """Show tuning statistics."""
    entries = _load_feedback()
    analysis = _analyze_signals(entries)
    current = _current_weights()
    return {
        "signals": analysis,
        "current_weights": current,
    }
