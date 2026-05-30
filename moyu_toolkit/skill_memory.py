"""skill_memory.py — 每个"技能"（底层函数）的跨调用经验积累。

每个核心函数有一个 .memory.md 文件，记录调用经验。
每次调用时自动注入到返回值，调用方无感。
每次检测到纠正信号时自动追加教训。
"""

import os
from datetime import datetime
from typing import Optional

_STORAGE_DIR: Optional[str] = None


def _get_dir() -> str:
    global _STORAGE_DIR
    if _STORAGE_DIR is None:
        from moyu_toolkit._moyu_paths import get_default_storage
        base = get_default_storage()
        _STORAGE_DIR = os.path.join(os.path.dirname(base), "skill_memory")
    os.makedirs(_STORAGE_DIR, exist_ok=True)
    return _STORAGE_DIR


def _path(skill_name: str) -> str:
    """Get the .memory.md path for a skill."""
    return os.path.join(_get_dir(), f"{skill_name}.memory.md")


def load(skill_name: str, max_chars: int = 600) -> str:
    """Load accumulated experience for a skill.

    Returns the most recent content (tail-first within max_chars).
    Empty string if no experience yet.
    """
    path = _path(skill_name)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return ""
    # Keep most recent portion
    if len(content) > max_chars:
        content = "…" + content[-max_chars:]
    return content


def append(skill_name: str, note: str):
    """Append a new experience note to a skill's .memory.md.

    Called automatically when the learner detects a correction
    that maps to a specific skill.
    """
    path = _path(skill_name)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## {ts}\n{note.strip()}"
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


def record_from_correction(skill_name: str, correction_text: str):
    """Detect and record a structured lesson from correction text."""
    # Extract the actionable part
    lines = [l.strip() for l in correction_text.strip().split("\n") if l.strip()]
    if not lines:
        return
    # Try to pick the most informative line
    note = " | ".join(lines[:3])[:400]
    append(skill_name, note)


def list_skills() -> list:
    """List all skills that have accumulated experience."""
    d = _get_dir()
    if not os.path.exists(d):
        return []
    files = sorted(os.listdir(d))
    result = []
    for f in files:
        if f.endswith(".memory.md"):
            name = f.replace(".memory.md", "")
            with open(os.path.join(d, f), "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            entry_count = sum(1 for ln in lines if ln.startswith("## "))
            result.append({"name": name, "entries": entry_count})
    return result
