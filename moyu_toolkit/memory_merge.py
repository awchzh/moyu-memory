#!/usr/bin/env python3
"""
memory_merge.py — MOYU Topic-Aware Memory Merge (V2.0)

Detects related memories by keyword overlap and merges them into
composite entries. Original details are preserved in metadata.

Run on wake (after forgetting curve, before compression):
    python3 memory_merge.py          # Auto-merge
    python3 memory_merge.py stats    # Show merge status
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

STORAGE = Path(os.environ.get("MOYU_STORAGE", str(Path(__file__).parent / "memory_data")))

# ── Config ──
SIMILARITY_THRESHOLD = 0.25   # Keyword overlap ratio to consider "related"
MAX_MERGE_GROUP = 5           # Max memories to merge into one
MIN_KEYWORDS = 3              # Min keywords to consider for matching


def _load_memories() -> list:
    p = STORAGE / "conversation_memory.json"
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_memories(memories: list):
    STORAGE.mkdir(parents=True, exist_ok=True)
    with open(STORAGE / "conversation_memory.json", 'w') as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)


def _tokenize(text: str) -> set:
    """Extract meaningful keywords from text."""
    text = text.lower()
    # Chinese words (2-4 chars)
    cn = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
    # English words (3+ chars, skip common)
    en = re.findall(r'[a-z]{3,}', text)
    stopwords = {'the', 'and', 'for', 'not', 'are', 'was', 'but', 'have',
                 'this', 'that', 'with', 'from', 'been', 'than', 'they',
                 'what', 'when', 'where', 'which', 'their', 'will', 'would',
                 'could', 'should', 'about', 'into', 'over', 'after',
                 'still', 'more', 'your', 'also', 'than', 'very', 'just',
                 'been', 'said', 'done', 'made', 'each', 'than', 'than'}
    return set(w for w in cn + en if w not in stopwords)


def _similarity(a: str, b: str) -> float:
    """Jaccard similarity of keyword sets."""
    ta = _tokenize(a)
    tb = _tokenize(b)
    if len(ta) < MIN_KEYWORDS or len(tb) < MIN_KEYWORDS:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def run(dry_run: bool = False) -> dict:
    """
    Run memory merge. Groups similar memories together.
    Returns a report of what was merged (or would be merged in dry run).
    """
    memories = _load_memories()
    # Only consider non-demoted, non-merged memories
    candidates = [m for m in memories
                  if not m.get("demoted", False)
                  and not m.get("merged_into", None)
                  and not m.get("is_merged", False)]

    # Compute pairwise similarity
    n = len(candidates)
    groups = []
    used = set()

    for i in range(n):
        if i in used:
            continue
        group = [i]
        used.add(i)
        for j in range(i + 1, n):
            if j in used:
                continue
            sim = _similarity(
                candidates[i].get("summary", ""),
                candidates[j].get("summary", "")
            )
            if sim >= SIMILARITY_THRESHOLD:
                group.append(j)
                used.add(j)
        if len(group) >= 2:
            groups.append(group)

    if dry_run:
        result = []
        for group in groups:
            items = [candidates[i] for i in group[:MAX_MERGE_GROUP]]
            result.append({
                "count": len(items),
                "ids": [m["id"] for m in items],
                "topics": list(_tokenize(" ".join(m.get("summary", "") for m in items)))[:5],
            })
        return {"status": "dry_run", "merge_candidates": result}

    # Execute merges
    merged_count = 0
    for group in groups:
        items = [candidates[i] for i in group[:MAX_MERGE_GROUP]]
        if len(items) < 2:
            continue

        # Build merged summary
        summaries = [m.get("summary", "") for m in items]
        # Use the most recent timestamp as base
        sorted_items = sorted(items, key=lambda m: m.get("timestamp", ""), reverse=True)
        latest = sorted_items[0]

        # Generate composite title
        keywords = list(_tokenize(" ".join(summaries)))[:3]
        title_part = "、".join(keywords) if keywords else "相关记录"
        merged_summary = f"[合并] {title_part} — {len(items)}条相关记录"

        # Build expandable details
        details = []
        for m in sorted_items:
            ts = m.get("timestamp", "")[:10]
            src = m.get("source", "?")
            summ = m.get("summary", "")[:150]
            details.append(f"• [{ts}] ({src}) {summ}")

        # Create merged entry
        merged_id = f"MERGE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        merged_entry = {
            "id": merged_id,
            "timestamp": latest.get("timestamp", datetime.now().isoformat()),
            "source": "merge",
            "summary": merged_summary,
            "content_hash": merged_id,
            "is_merged": True,
            "merged_ids": [m["id"] for m in items],
            "expandable": "\n".join(details),
            "merged_at": datetime.now().isoformat(),
        }

        # Mark originals
        for m in items:
            m["merged_into"] = merged_id

        memories.append(merged_entry)
        merged_count += 1

    if merged_count > 0:
        _save_memories(memories)

    return {
        "status": "ok",
        "merged_groups": merged_count,
    }


def stats():
    """Show merge status."""
    memories = _load_memories()
    merged = [m for m in memories if m.get("is_merged")]
    originals = [m for m in memories if m.get("merged_into")]
    demoted = [m for m in memories if m.get("demoted")]

    print(f"\n🗂️ MOYU Memory Merge")
    print("=" * 50)
    print(f"  Total memories:  {len(memories)}")
    print(f"  Merged entries:  {len(merged)}")
    print(f"  Original (merged-in): {len(originals)}")
    print(f"  Demoted:              {len(demoted)}")
    if merged:
        print()
        for m in merged[:5]:
            detail = m.get("summary", "?")[:60]
            count = len(m.get("merged_ids", []))
            print(f"  📦 {detail} ({count}条)")
    print()


def demo() -> dict:
    return {
        "capability": 14,
        "title": "Memory Merge (V2.0)",
        "output": """\
🗂️ V2.0 FEATURE — Memory Merge
────────────────────────────────────
  Detects similar memories → merges into one composite entry

  Before (3 separate memories):
    • [05-08] Project kickoff meeting — discussed Plan A/B
    • [05-08] Plan discussion — A vs B tradeoffs
    • [05-09] Decision: team chose MVP route (Plan B)

  After (1 merged entry + expandable details):
    📦 [合并] 计划、方案、项目 — 3条相关记录
       Expandable: view original details on request
""",
    }


if __name__ == "__main__":
    import sys
    if "--dry" in sys.argv:
        result = run(dry_run=True)
        candidates = result.get("merge_candidates", [])
        if candidates:
            print(f"\n🔍 Dry run: {len(candidates)} merge groups found")
            for c in candidates:
                print(f"  • {c['count']} items — topics: {', '.join(c['topics'][:3])}")
                for mid in c['ids'][:3]:
                    print(f"    - {mid}")
        else:
            print("No merge candidates found.")
    elif "stats" in sys.argv:
        stats()
    else:
        result = run()
        if result.get("merged_groups", 0) > 0:
            print(f"✅ Merged {result['merged_groups']} groups of related memories")
        else:
            print("No related memories to merge.")
