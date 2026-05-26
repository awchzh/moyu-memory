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

from moyu_toolkit._moyu_paths import get_default_storage, get_config_path
STORAGE = Path(get_default_storage())

# ── Config ──
SIMILARITY_THRESHOLD = 0.25   # Keyword overlap ratio to consider "related"
MAX_MERGE_GROUP = 5           # Max memories to merge into one
MIN_KEYWORDS = 3              # Min keywords to consider for matching

# ── LLM Merge Summarization (Optional) ──

_LLM_MERGE_FAILURES = 0
_LLM_MERGE_NO_KEY_WARNED = False


def _call_llm_merge(system_prompt: str, user_prompt: str) -> str:
    """Call LLM for merge summarization. Returns empty string on failure.
    Uses unified _llm_client for config resolution and HTTP call."""
    global _LLM_MERGE_FAILURES
    if _LLM_MERGE_FAILURES >= 3:
        return ""

    from moyu_toolkit._llm_client import resolve_llm_config, call_llm_api
    api_key, base_url, model = resolve_llm_config()
    if not api_key or api_key == "your-api-key-here":
        global _LLM_MERGE_NO_KEY_WARNED
        if not _LLM_MERGE_NO_KEY_WARNED:
            _LLM_MERGE_NO_KEY_WARNED = True
            print("⚠️  MOYU 记忆合并：未检测到有效 API Key，已降级为关键词拼接摘要。")
        _LLM_MERGE_FAILURES += 1
        return ""

    result = call_llm_api(
        api_key, base_url, model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=300,
        timeout=15,
    )
    if result:
        _LLM_MERGE_FAILURES = 0
    else:
        _LLM_MERGE_FAILURES += 1
    return result


def _llm_merge_summaries(items: list) -> str:
    """Generate a coherent summary from related memories using LLM.

    Items are sorted by recency. The LLM synthesizes them into one
    narrative that retains all key facts. Falls back to text concatenation.
    """
    summaries = []
    for m in sorted(items, key=lambda x: x.get("timestamp", ""), reverse=True):
        ts = m.get("timestamp", "")[:10]
        src = m.get("source", "user")
        summ = m.get("summary", "")[:200]
        summaries.append(f"[{ts}] ({src}) {summ}")

    system_prompt = (
        "You are a memory merging assistant. Given several related memory entries "
        "with timestamps and sources, synthesize them into ONE coherent summary "
        "that captures all key facts, decisions, and relationships.\n\n"
        "Rules:\n"
        "- Preserve ALL facts, names, numbers, decisions, and preferences\n"
        "- Remove repetition and redundant details across entries\n"
        "- Create a logical narrative flow (chronological by timestamp)\n"
        "- Output in the SAME language as the input entries\n"
        "- Max 300 characters\n"
        "- Output ONLY the summary text, no explanations, no labels"
    )
    user_prompt = f"Synthesize these related memories into one summary:\n\n{chr(10).join(summaries)}"

    response = _call_llm_merge(system_prompt, user_prompt)
    if response and len(response.strip()) > 10:
        return f"[合并] {response.strip()[:300]}"
    return ""


def _should_llm_merge() -> bool:
    """Check if LLM merge summarization is enabled in config."""
    cfg_path = get_config_path()
    if not os.path.exists(cfg_path):
        return False
    try:
        import yaml
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("memory", {}).get("llm_merge", {}).get("enabled", False)
    except Exception:
        return False


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
    # Chinese words (2-5 chars, captures longer compound terms)
    cn = re.findall(r'[\u4e00-\u9fff]{2,5}', text)
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

        # Generate composite title — LLM merge or keyword fallback
        if _should_llm_merge():
            llm_summary = _llm_merge_summaries(items)
            if llm_summary:
                merged_summary = llm_summary
            else:
                # LLM fallback → keyword concatenation
                keywords = list(_tokenize(" ".join(summaries)))[:3]
                title_part = "、".join(keywords) if keywords else "相关记录"
                merged_summary = f"[合并] {title_part} — {len(items)}条相关记录"
        else:
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

        # Create merged entry with security check
        try:
            from moyu_toolkit.defense_toolkit.integrity_checker import content_scan
            hits = content_scan(merged_summary)
            if hits:
                print(f"⚠️ memory_merge: skipped — merged content blocked by security gate: {', '.join(hits)}")
                continue
        except Exception:
            pass

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
        from datetime import datetime as _dt
        _ts = _dt.now().isoformat()
        # Load existing audit log
        _audit_path = STORAGE / "audit_log.json"
        _audit_entries = []
        if _audit_path.exists():
            try:
                with open(_audit_path) as f:
                    _audit_entries = json.load(f)
            except Exception:
                _audit_entries = []
        for group in groups:
            items = [candidates[i] for i in group[:MAX_MERGE_GROUP]]
            if len(items) >= 2:
                _audit_entries.append({
                    "ts": _ts, "event": "merge",
                    "merged_ids": [m["id"] for m in items],
                    "count": len(items),
                    "topics": list(_tokenize(" ".join(m.get("summary", "") for m in items)))[:3],
                })
        _audit_entries = _audit_entries[-500:]
        _tmp = str(_audit_path) + ".tmp"
        try:
            with open(_tmp, 'w') as f:
                json.dump(_audit_entries, f, ensure_ascii=False, indent=2)
            import os as _os
            _os.replace(_tmp, _audit_path)
        except Exception:
            if _os.path.exists(_tmp):
                _os.remove(_tmp)
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
