#!/usr/bin/env python3
"""feedback.py — MOYU Phase 2: Search feedback collection.

Records user signals (ref reads, votes, corrections) to JSONL files
for future adaptive retrieval tuning (Phase 3).

Storage: memory_data/search_feedback_YYYY-MM.jsonl (monthly rotation).
"""

import json
import os
from datetime import datetime
def _storage_path() -> str:
    """Get the feedback log directory (same as main storage)."""
    base = os.environ.get("MOYU_STORAGE", "")
    if not base:
        from moyu_toolkit._moyu_paths import get_default_storage
        base = get_default_storage()
    return base


def _feedback_path() -> str:
    """Get the current feedback log path with monthly rotation."""
    stamp = datetime.now().strftime("%Y-%m")
    return os.path.join(_storage_path(), f"search_feedback_{stamp}.jsonl")


def record(kind: str, query: str, memory_id: str, detail: str = "",
           metadata: dict | None = None) -> None:
    """Record a search feedback event.

    Args:
        kind: Signal type — 'ref', 'vote_good', 'vote_bad', 'correction'
        query: The search query (or empty string if not from a search)
        memory_id: The memory ID that was interacted with
        detail: Optional extra info (vote comment, etc.)
        metadata: Optional extra fields
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "kind": kind,
        "query": query or "",
        "memory_id": memory_id,
        "detail": detail or "",
    }
    if metadata is not None:
        entry["metadata"] = metadata

    try:
        path = _feedback_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except (OSError, json.JSONEncodeError) as e:
        print(f"[feedback] warning: failed to write {path} — {e}", file=__import__('sys').stderr)


def record_vote(query: str, memory_id: str, vote: str) -> None:
    """Record a user vote (good/bad) on a search result."""
    if vote not in ("good", "bad"):
        raise ValueError(f"vote must be 'good' or 'bad', got '{vote}'")
    kind = f"vote_{vote}"
    record(kind, query, memory_id, detail=f"user voted {vote}")


def record_ref(memory_id: str) -> None:
    """Record that a user read a memory via ref command."""
    record("ref", "", memory_id, detail="user read ref")


def record_correction(text: str, detected_signals: list) -> None:
    """Record a correction event as feedback signal."""
    record("correction", "", "", detail=text[:200],
           metadata={"signals": detected_signals})


def stats() -> dict:
    """Show feedback collection stats."""
    path = _feedback_path()
    if not os.path.exists(path):
        return {"total": 0, "kinds": {}, "file": "none"}

    counts = {}
    total = 0
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    kind = entry.get("kind", "unknown")
                    counts[kind] = counts.get(kind, 0) + 1
                    total += 1
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    return {
        "total": total,
        "kinds": counts,
        "file": os.path.basename(path),
        "path": path,
    }
