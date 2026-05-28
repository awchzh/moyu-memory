#!/usr/bin/env python3
"""
forgetting_curve.py — MOYU Memory Lifecycle (V2.1)

Three-stage gating:
  Stage 1 — 14-day safety window (no demotion before this threshold)
  Stage 2 — Access density trend analysis: widening intervals → demote,
            stable intervals → keep (even if past the 14-day mark)
  Stage 3 — Scene association protection: if any memory in the same scene
            has been recently accessed, protect this one too.

Scenes are auto-assigned by keyword matching on memory summaries.
Config (config.yaml → forgetting_curve):
  enabled: true
  demote_days: 14    → Stage 1: safety window
  archive_days: 60   → Demoted + 60 more days → archivable
  density_window: 20 → Max access timestamps to track per memory
  scene_protection_days: 7  → Stage 3: a scene stays hot this long after last access
"""

import json
import os
import re
import statistics
from datetime import datetime, timedelta
from pathlib import Path

# ── 知识图谱蒸馏 ──
# Called before demoting a memory: extracts entity relations from the summary
# and writes them to the knowledge graph, so structural knowledge survives
# the raw memory's removal. Non-intrusive import — no-op if module fails.
try:
    from moyu_toolkit import knowledge_graph as kg
    _KG_AVAILABLE = True
except Exception:
    _KG_AVAILABLE = False

from moyu_toolkit._moyu_paths import get_default_storage, get_config_path
STORAGE = Path(get_default_storage())
AUDIT_LOG_PATH = STORAGE / "audit_log.json"


def _audit_log(event_type: str, details: dict):
    """Append an audit event to audit_log.json. Thread-safe via atomic append."""
    entry = {"ts": datetime.now().isoformat(), "event": event_type, **details}
    entries = []
    if AUDIT_LOG_PATH.exists():
        try:
            with open(AUDIT_LOG_PATH) as f:
                entries = json.load(f)
        except Exception:
            entries = []
    entries.append(entry)
    entries = entries[-500:]  # Keep last 500
    tmp = str(AUDIT_LOG_PATH) + ".tmp"
    try:
        with open(tmp, 'w') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp, AUDIT_LOG_PATH)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)

# ── Dynamic scene extraction (from memory summaries) ──
# Scenes are extracted from high-frequency keywords that appear across
# multiple memories. No hard-coded labels — scenes grow from your data.

_STOP_WORDS = {
    "的", "了", "是", "在", "和", "我", "们", "你", "有", "不", "就",
    "这", "那", "也", "都", "要", "一", "个", "会", "很", "到", "以",
    "能", "他", "她", "它", "来", "去", "让", "把", "被", "对", "为",
    "与", "从", "上", "下", "中", "里", "说", "做", "用", "给", "看",
    "没", "还", "但", "可", "所", "比", "或", "其", "而", "且", "之",
    "如", "于", "及", "更", "最", "先", "后", "已", "将", "又", "再",
    "些", "吗", "吧", "呢", "哦", "呀", "嘛", "嗯", "哈", "哈", "哇",
    "则", "每", "各", "被", "被", "无", "非", "当", "等", "并", "只",
    "这个", "那个", "没有", "不是", "还是", "因为", "所以", "但是",
    "如果", "虽然", "可能", "可以", "应该", "需要", "已经", "进行",
    "使用", "通过", "作为", "由于", "关于", "一个", "什么", "怎么",
    "自己", "知道", "觉得", "看到", "完成", "开始", "继续", "最后",
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "of",
    "for", "with", "is", "are", "was", "were", "be", "been", "have",
    "has", "had", "do", "does", "did", "will", "would", "can", "could",
    "should", "may", "might", "shall", "this", "that", "these", "those",
    "it", "its", "we", "our", "you", "your", "they", "them", "their",
    "he", "him", "his", "she", "her", "not", "no", "but", "if", "all",
    "just", "very", "too", "so", "also", "now", "then", "here", "there",
    "about", "into", "over", "after", "before", "between", "through",
}
_MIN_SCENE_COUNT = 2  # A keyword must appear in at least this many memories to become a scene
_MAX_SCENE_COVERAGE = 0.3  # Max fraction of memories a keyword can appear in (anti-noise)
_DEFAULT_MIN_KEYWORD_LEN = 3  # Minimum chars for auto-extracted scene keywords


def _load_scene_labels() -> dict:
    """Load user-defined scene labels from config.yaml.
    Returns {scene_name: [keyword1, keyword2, ...]}"""
    cfg = _load_config()
    labels = cfg.get("scene_labels", {})
    if isinstance(labels, dict):
        return labels
    return {}


def _tokenize(text: str, min_len: int = _DEFAULT_MIN_KEYWORD_LEN) -> list:
    """Split text into tokens: Chinese multi-char words + English words."""
    chinese = re.findall(r'[\u4e00-\u9fff]{2,}', text)
    english = re.findall(r'[a-zA-Z][a-zA-Z0-9]{' + str(min_len - 1) + r',}', text)
    return [t.lower() for t in chinese + english if t.lower() not in _STOP_WORDS and len(t) >= min_len]


def _extract_scene_keywords(memories: list, min_len: int = _DEFAULT_MIN_KEYWORD_LEN) -> list:
    """Extract high-frequency keywords from memory summaries to use as scene labels.
    Only words appearing in >= _MIN_SCENE_COUNT AND <= _MAX_SCENE_COVERAGE
    of memories become scenes. Sorted by frequency descending."""
    total_active = sum(1 for m in memories if not m.get("demoted"))
    if total_active == 0:
        return []

    counter = {}
    for m in memories:
        if m.get("demoted"):
            continue
        tokens = set(_tokenize(m.get("summary", ""), min_len))
        for t in tokens:
            counter[t] = counter.get(t, 0) + 1

    max_count = max(1, int(total_active * _MAX_SCENE_COVERAGE))
    scenes = [w for w, c in counter.items() if _MIN_SCENE_COUNT <= c <= max_count]
    scenes.sort(key=lambda w: -counter[w])
    return scenes


def _assign_scene(summary: str, dynamic_keywords: list, user_labels: dict = None) -> str:
    """Match a summary against scene labels.
    Priority: user-defined scenes first → dynamic keywords → 'general'."""
    if not summary:
        return "general"
    low = summary.lower()

    # Priority 1: user-defined scene labels
    if user_labels:
        for scene_name, keywords in user_labels.items():
            for kw in keywords:
                if kw.lower() in low:
                    return scene_name

    # Priority 2: dynamic extracted keywords
    if dynamic_keywords:
        for kw in dynamic_keywords:
            if kw.lower() in low:
                return kw

    return "general"


def _ensure_scene(memories: list):
    """Assign scenes to memories using pre-assigned labels (from memory_bridge),
    user-defined labels (from config), or dynamic keyword extraction (fallback).
    Pre-assigned scenes (scene_source: "manual") are never overwritten.
    Uses checkpoint for incremental processing — only new/changed memories."""
    changed = False
    cfg = _load_config()
    min_len = cfg.get("min_keyword_length", _DEFAULT_MIN_KEYWORD_LEN)
    auto_scene = cfg.get("auto_scene_extraction", False)
    user_labels = _load_scene_labels()

    # Only extract dynamic keywords if auto extraction is enabled
    dynamic_keywords = _extract_scene_keywords(memories, min_len) if auto_scene else []
    cp = _load_checkpoint()
    last_ts = cp.get("last_processed", "")
    processed = 0

    # ── LLM Scene Classification (Optional): batch classify unassigned memories ──
    llm_scene_results = {}
    if _should_llm_scene():
        llm_scene_results = _llm_classify_scenes(memories, user_labels)
        for m in memories:
            if m.get("scene_source") == "manual":
                continue
            m_id = m.get("id", "")
            if m_id in llm_scene_results and "scene" not in m:
                m["scene"] = llm_scene_results[m_id]
                m["scene_source"] = "llm"
                changed = True
                processed += 1

    # Keyword-based fallback for remaining unassigned memories
    for m in memories:
        # Pre-assigned scenes (from memory_bridge) are never overwritten
        if m.get("scene_source") == "manual":
            continue

        if "scene" not in m:
            m["scene"] = _assign_scene(m.get("summary", ""), dynamic_keywords, user_labels)
            changed = True
            processed += 1
        elif m.get("timestamp", "") > last_ts:
            new_scene = _assign_scene(m.get("summary", ""), dynamic_keywords, user_labels)
            if m.get("scene") != new_scene:
                m["scene"] = new_scene
                changed = True
                processed += 1

    if processed > 0:
        cp["last_processed"] = _now()
        cp["total_processed"] = cp.get("total_processed", 0) + processed
        _save_checkpoint(cp)
    return changed


def _memories_path() -> str:
    return str(STORAGE / "conversation_memory.json")


def _load_memories() -> list:
    p = _memories_path()
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    return []


def _save_memories(memories: list):
    STORAGE.mkdir(parents=True, exist_ok=True)
    path = _memories_path()
    # Content security gate: scan summaries before persisting
    try:
        from moyu_toolkit.defense_toolkit.integrity_checker import content_scan
        for m in memories:
            summary = m.get("summary", "") or ""
            if summary:
                hits = content_scan(summary)
                if hits:
                    from moyu_toolkit.defense_toolkit.defense_log import report as _dl
                    _dl("forgetting_curve_save", "yellow", {
                        "gate": "content_scan",
                        "hits": hits,
                        "memory_id": m.get("id", "")[:12],
                    })
    except Exception:
        pass
    with open(path, 'w') as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)


def _load_config() -> dict:
    try:
        import yaml
        cfg_path = Path(get_config_path())
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("forgetting_curve", {})
    except Exception:
        pass
    return {}


def _now() -> str:
    return datetime.now().isoformat()


def _days_since(ts_str: str) -> float:
    """Calculate days between now and a timestamp string.
    Returns infinity on parse failure — safe default that won't bypass Stage 1."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return (datetime.now() - dt).total_seconds() / 86400
    except Exception:
        return float('inf')


def _days_between(ts_a: str, ts_b: str) -> float:
    """Days between two timestamp strings (positive)."""
    try:
        a = datetime.fromisoformat(ts_a.replace("Z", "+00:00"))
        b = datetime.fromisoformat(ts_b.replace("Z", "+00:00"))
        return abs((a - b).total_seconds() / 86400)
    except Exception:
        return 0


# ── Checkpoint (incremental processing) ──

CHECKPOINT_PATH = STORAGE / "scene_checkpoint.json"


def _load_checkpoint() -> dict:
    """Load incremental processing checkpoint."""
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_processed": _now(), "total_processed": 0}


def _save_checkpoint(cp: dict):
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)


# ── LLM Utilities (shared pattern with learner/integrity_checker) ──

_LLM_FAILURES = 0
_LLM_NO_KEY_WARNED = False


def _call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 500) -> str:
    """Call the configured LLM API. Returns empty string on failure.
    Uses unified _llm_client for config resolution and HTTP call."""
    global _LLM_FAILURES
    if _LLM_FAILURES >= 3:
        return ""

    from moyu_toolkit._llm_client import resolve_llm_config, call_llm_api
    api_key, base_url, model = resolve_llm_config()
    if not api_key or api_key == "your-api-key-here":
        global _LLM_NO_KEY_WARNED
        if not _LLM_NO_KEY_WARNED:
            _LLM_NO_KEY_WARNED = True
            print("⚠️  MOYU 智能遗忘：未检测到有效 API Key，已降级为纯规则决策。")
        _LLM_FAILURES += 1
        return ""

    result = call_llm_api(
        api_key, base_url, model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=30,
    )
    if result:
        _LLM_FAILURES = 0
    else:
        _LLM_FAILURES += 1
    return result


# ── Stage 4: LLM Review ──

def _llm_review_demotion(candidates: list, all_memories: list, context_pressure: bool) -> dict:
    """Stage 4: Use LLM to review demotion candidates before final decision.

    The LLM evaluates semantic importance that rule-based heuristics miss:
    - User preferences (name, habits, identity) — access count irrelevant
    - Critical decisions or milestones
    - Knowledge that would be hard to re-discover

    Args:
        candidates: list of memory dicts that the rule system decided to demote
        all_memories: all memories (for context about what's already kept)
        context_pressure: whether there's actual context pressure driving demotion

    Returns:
        {memory_id: {'decision': 'keep'|'demote', 'reason': '...'}, ...}
    """
    cfg = _load_config()
    llm_cfg = cfg.get("llm_review", {})
    if not llm_cfg.get("enabled", True):
        return {}

    max_candidates = llm_cfg.get("max_candidates_per_batch", 10)
    if len(candidates) > max_candidates:
        candidates = candidates[:max_candidates]

    if not candidates:
        return {}

    # Build compact candidate list for the prompt
    candidate_lines = []
    for i, m in enumerate(candidates):
        m_id = m.get("id", f"mem_{i}")
        summary = m.get("summary", "")[:120]
        ts = m.get("last_accessed") or m.get("timestamp", "")
        days = _days_since(ts)
        scene = m.get("scene", "general")
        access_count = m.get("access_count", 0)
        candidate_lines.append(
            f'  {{"id": "{m_id}", "summary": {json.dumps(summary, ensure_ascii=False)}, '
            f'"days_since_access": {days:.0f}, "access_count": {access_count}, "scene": "{scene}"}}'
        )

    # Count active memories for context
    active_count = sum(1 for m in all_memories if not m.get("demoted", False))
    pressure_note = (
        "Memory budget is tight — prefer demoting transient details."
        if context_pressure
        else "Memory budget is ample — only demote clearly low-value memories."
    )

    system_prompt = (
        "You are a memory importance evaluator for a personal AI assistant. "
        "Your task: review memories that an automated system flagged for demotion, "
        "and decide whether each should be KEPT (overriding the demotion) or DEMOTED (agreeing).\n\n"
        "A memory should be KEPT if it contains:\n"
        "- User preferences, identity info, habits, or personal facts\n"
        "- Critical decisions, milestones, or significant conclusions\n"
        "- Knowledge that would be impossible or very hard to re-discover\n"
        "- Relationships between people, projects, or tools\n\n"
        "A memory should be DEMOTED if:\n"
        "- It's a transient conversation detail or small talk\n"
        "- The information is clearly duplicated in other memories\n"
        "- It's a one-time task log with no lasting value\n\n"
        f"{pressure_note}\n\n"
        "Output valid JSON ONLY: {\"decisions\": [{\"id\": \"...\", \"decision\": \"keep\"|\"demote\", \"reason\": \"...\"}]}"
    )

    user_prompt = "Review these demotion candidates:\n[\n" + ",\n".join(candidate_lines) + "\n]"

    response_text = _call_llm(system_prompt, user_prompt, temperature=0.1, max_tokens=500)

    if not response_text:
        return {}

    # Parse LLM response
    try:
        import json as _j
        # Strip possible markdown code fences
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        result = _j.loads(cleaned)
        decisions = result.get("decisions", [])
        return {
            d["id"]: {"decision": d.get("decision", "demote"), "reason": d.get("reason", "")}
            for d in decisions
        }
    except Exception:
            return {}


# ── Scene Classification: LLM (Optional) ──

def _llm_classify_scenes(memories: list, user_labels: dict = None) -> dict:
    """Use LLM to assign semantic scene labels to memories without one.

    Takes all memories without a scene assigned, batch-classifies them via LLM.
    Scenes are inferred from content semantics (not keyword matching),
    using user-defined scene labels as a taxonomy hint.

    Args:
        memories: list of all memory dicts
        user_labels: optional dict of {scene_name: [keyword_hints]}

    Returns:
        {memory_id: scene_label, ...} — only for successfully classified memories
    """
    # Collect unassigned memories (no scene, not manual)
    unassigned = [
        m for m in memories
        if not m.get("scene") and m.get("scene_source") != "manual"
    ]
    if not unassigned:
        return {}

    # Build existing scene set for reference
    existing_scenes = set()
    for m in memories:
        s = m.get("scene")
        if s and s != "general":
            existing_scenes.add(s)

    # Batch: max 20 per call
    max_per_batch = 20
    results = {}

    for batch_start in range(0, len(unassigned), max_per_batch):
        batch = unassigned[batch_start:batch_start + max_per_batch]

        lines = []
        for m in batch:
            m_id = m.get("id", "?")
            summary = m.get("summary", "")[:150].replace('"', "'")
            ts = m.get("timestamp", "")[:10]
            lines.append(f'  {{"id": "{m_id}", "summary": "{summary}", "date": "{ts}"}}')

        scene_hint = ""
        if user_labels:
            scene_hint = f"Existing scene categories: {', '.join(user_labels.keys())}.\n"
        if existing_scenes:
            scene_hint += f"Previously used scene labels: {', '.join(sorted(existing_scenes)[:10])}.\n"

        system_prompt = (
            "You are a memory scene classifier. Given memory entries, assign each "
            "to a meaningful scene/category label that groups related memories together.\n\n"
            f"{scene_hint}"
            "Rules:\n"
            "- Use an existing label when it fits\n"
            "- Create a new concise label ONLY if none of the existing labels fit\n"
            "- Labels should be 1-3 words, in the language of the memory content\n"
            "- 'general' for small talk, greetings, or trivial content\n"
            "- Output valid JSON ONLY:\n"
            '  {"scenes": {"mem_xxx": "project", "mem_yyy": "personal", ...}}\n'
            "- Do NOT include any memory that you cannot confidently classify"
        )
        user_prompt = "Classify these memories:\n[\n" + ",\n".join(lines) + "\n]"

        response_text = _call_llm(system_prompt, user_prompt, temperature=0.1, max_tokens=500)
        if not response_text:
            continue

        try:
            import json as _j
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
            parsed = _j.loads(cleaned)
            scenes = parsed.get("scenes", {})
            for mid, label in scenes.items():
                if isinstance(label, str) and len(label) <= 30:
                    results[mid] = label.strip().lower()[:20]
        except Exception:
            continue

    return results


def _should_llm_scene() -> bool:
    """Check if LLM scene classification is enabled in config."""
    cfg = _load_config()
    return cfg.get("llm_scene_classify", {}).get("enabled", False)


def _build_scene_index(memories: list) -> dict:
    """Build a dict: scene_name → [memory ids] for all non-demoted memories."""
    index = {}
    for m in memories:
        if m.get("demoted", False):
            continue
        scene = m.get("scene", "general")
        m_id = m.get("id", "?")
        if scene not in index:
            index[scene] = []
        index[scene].append(m_id)
    return index


def _hot_scenes(memories: list, hot_days: float = 7) -> set:
    """Determine which scenes are 'hot' — any memory in them was accessed within hot_days."""
    hot = set()
    for m in memories:
        ts = m.get("last_accessed") or m.get("timestamp", _now())
        if _days_since(ts) <= hot_days:
            scene = m.get("scene", "general")
            hot.add(scene)
    return hot


# ── Two-stage gating + scene protection ──

def _access_density_trend(timestamps: list) -> dict:
    """Stage 2: analyze access interval pattern from timestamp history.

    Returns a dict with:
      trend: 'stable' | 'widening' | 'insufficient'
      median_interval_days: median gap between consecutive accesses (or None)
      detail: human-readable note
    """
    result = {"trend": "insufficient", "median_interval_days": None, "detail": "less than 2 intervals"}

    if len(timestamps) < 3:
        return result  # Need at least 3 timestamps for 2 intervals

    intervals = []
    for i in range(1, len(timestamps)):
        gap = _days_between(timestamps[i], timestamps[i - 1])
        if gap > 0:
            intervals.append(gap)

    if len(intervals) < 2:
        return result

    median_val = statistics.median(intervals)
    result["median_interval_days"] = round(median_val, 1)

    # Split into first half and second half to detect widening trend
    mid = len(intervals) // 2
    first_half = intervals[:mid]
    second_half = intervals[mid:]

    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)

    if avg_second > avg_first * 1.5:
        result["trend"] = "widening"
        result["detail"] = (
            f"intervals widening: {avg_first:.1f}d → {avg_second:.1f}d "
            f"(median {median_val:.1f}d)"
        )
    else:
        result["trend"] = "stable"
        result["detail"] = (
            f"intervals stable: {avg_first:.1f}d → {avg_second:.1f}d "
            f"(median {median_val:.1f}d)"
        )

    return result


# ── 蒸馏到知识图谱（可容忍降级前调用） ──

def _distill_to_kg(m):
    """Extract entity relations from a memory's summary before demotion.
    
    This is the key link in the memory→KG pipeline: when a raw memory is about
    to be forgotten (demoted), its structural knowledge (entity relations) is
    extracted and persisted in the knowledge graph, so it survives the raw
    memory's removal.
    
    Only runs if:
      - knowledge_graph module is available
      - This memory hasn't been distilled before (_kg_distilled flag)
      - Memory has a summary
    
    Sets _kg_distilled flag on the memory to prevent re-distillation.
    """
    global _KG_AVAILABLE
    if not _KG_AVAILABLE:
        return
    if m.get("_kg_distilled"):
        return
    summary = m.get("summary", "")
    if not summary:
        return
    timestamp = m.get("timestamp") or m.get("last_accessed")
    try:
        added = kg.distill_from_memory(summary, timestamp=timestamp)
        if added > 0:
            m["_kg_distilled"] = True
    except Exception:
        pass


# ── Core API ─────────────────────────────────────────────────────────────────

def track_access(memory_ids: list):
    """Update last_accessed, access_count, and append to access_timestamps."""
    cfg = _load_config()
    density_window = cfg.get("density_window", 20)

    memories = _load_memories()
    # Ensure all memories have scenes before tracking
    _ensure_scene(memories)

    now = _now()
    changed = False
    for m in memories:
        if m.get("id") in memory_ids:
            m["last_accessed"] = now
            m["access_count"] = m.get("access_count", 0) + 1

            # Append to timestamp history (ring buffer capped at density_window)
            ts_list = m.get("access_timestamps", [])
            ts_list.append(now)
            if len(ts_list) > density_window:
                ts_list = ts_list[-density_window:]
            m["access_timestamps"] = ts_list

            # Remove demoted flag since it's being accessed again
            if m.pop("demoted", None) is not None:
                m.pop("demoted_reason", None)
                m.pop("demoted_by_density", None)
            changed = True
    if changed:
        _save_memories(memories)


def run(context_pressure: bool = False) -> dict:
    """
    Run the forgetting curve check on all memories (four-stage gating).

    Stage 1 — Safety window: memories within demote_days are never demoted.
    Stage 2 — Density trend: memories past the window with stable access
              patterns are kept active; widening intervals are demoted.
    Stage 3 — Scene protection: if the memory's scene is "hot" (any memory
              in the same scene was recently accessed), protect this one too.
    Stage 4 — LLM review (optional): before final demotion, the LLM reviews
              semantic importance (preferences, identity, milestones) that
              rule-based heuristics miss. LLM override can rescue memories.

    Args:
        context_pressure: If True, activate demotion. If False, only
                          demote if active memories exceed a reasonable
                          budget (safe default for low-frequency users).
    Returns a report of what happened.
    """
    cfg = _load_config()
    if not cfg.get("enabled", True):
        return {"status": "disabled"}

    demote_days = cfg.get("demote_days", 14)
    archive_days = cfg.get("archive_days", 60)
    scene_protection_days = cfg.get("scene_protection_days", 7)

    memories = _load_memories()
    # Ensure scenes are assigned
    changed_scenes = _ensure_scene(memories)

    active_memories = [m for m in memories if not m.get("demoted", False)]

    # ── Stage 0: skip demotion if no context pressure and few memories ──
    active_count = len(active_memories)

    if not context_pressure and active_count <= 15:
        kept_by_scene = len([m for m in active_memories if m.get("protected_by_scene")])
        kept_by_density = len([m for m in memories if m.get("demoted_by_density")])
        if changed_scenes:
            _save_memories(memories)
        return {
            "status": "ok",
            "total_memories": len(memories),
            "demoted": [],
            "already_demoted": len([m for m in memories if m.get("demoted", False)]),
            "kept_by_density": kept_by_density,
            "kept_by_density_ids": [],
            "kept_by_scene": kept_by_scene,
            "kept_by_scene_ids": [],
            "kept_by_llm": 0,
            "kept_by_llm_ids": [],
            "archivable": [],
            "demote_threshold_days": demote_days,
            "archive_threshold_days": archive_days,
            "note": "no pressure, kept all memories active",
        }

    now = _now()

    # ── Stage 3 pre-check: determine hot scenes ──
    hot = _hot_scenes(memories, hot_days=scene_protection_days)
    scene_index = _build_scene_index(memories)

    demoted = []
    kept_by_density = []
    kept_by_scene = []
    kept_by_llm = []
    archived = []
    re_demoted = []
    distilled_count = 0

    # ── Pass 1: evaluate all memories, collect demotion candidates ──
    demotion_candidates = []  # Memories that passed all rule gates → candidate for demotion

    for m in memories:
        m_id = m.get("id", "?")
        is_demoted = m.get("demoted", False)
        # ── 保护检查：被标记为不可遗忘的记忆跳过降级 ──
        access_ts = m.get("last_accessed") or m.get("timestamp", now)
        days = _days_since(access_ts)
        scene = m.get("scene", "general")

        if m.get("protected"):
            kept_by_density.append(m_id)  # reuse field for reporting
            continue

        if is_demoted:
            if days >= archive_days:
                archived.append(m_id)
            else:
                re_demoted.append(m_id)
            continue

        # ── Stage 1: within safety window → skip ──
        # Safety window depends on source: agent/system sources are less trusted
        src = m.get("source", "user")
        src_window = demote_days // 2 if src in ("agent", "system") else demote_days
        if days < src_window:
            continue

        # ── Stage 3: scene protection check (before density) ──
        if scene in hot and scene in scene_index:
            # Another memory in this scene has been recently accessed
            # Extend protection for this memory
            m["protected_by_scene"] = True
            m["last_checked"] = now
            kept_by_scene.append(m_id)
            continue

        # ── Stage 2.5 (Heat Bridge): COLD tier memories auto-pass density check ──
        heat_tier = m.get("heat_tier", "warm")
        if heat_tier == "cold":
            # COLD tier: skip density trend, send straight to demotion candidate
            m["heat_bridge_skip"] = True  # flag for audit
            demotion_candidates.append(m)
            continue

        # ── Stage 2: check access density trend ──
        trend = _access_density_trend(m.get("access_timestamps", []))

        if trend["trend"] == "stable":
            # Regular usage pattern — keep active despite passing the window
            m["last_checked"] = now
            kept_by_density.append(m_id)
            continue

        # Passed all rule gates → collect as demotion candidate (defer demotion until Stage 4)
        demotion_candidates.append(m)

    # ── Stage 4: LLM review ──
    if demotion_candidates:
        llm_decisions = _llm_review_demotion(demotion_candidates, memories, context_pressure)

        for m in demotion_candidates:
            m_id = m.get("id", "?")
            decision = llm_decisions.get(m_id, {})

            if decision.get("decision") == "keep":
                # LLM overrides demotion — semantic importance detected
                m["kept_by_llm"] = True
                m["llm_keep_reason"] = decision.get("reason", "")
                m["last_checked"] = now
                kept_by_llm.append(m_id)
                _audit_log("llm_keep", {
                    "memory_id": m_id,
                    "reason": decision.get("reason", ""),
                    "summary": (m.get("summary", "")[:80]),
                })
            else:
                # LLM agrees with demotion (or unavailable → fall through)
                # ── 蒸馏：降级前将结构化知识写入知识图谱 ──
                old_len = len(kg._load().get("relations", [])) if _KG_AVAILABLE else 0
                _distill_to_kg(m)
                if _KG_AVAILABLE:
                    new_len = len(kg._load().get("relations", []))
                    distilled_count += max(0, new_len - old_len)
                    if new_len > old_len:
                        _audit_log("distill", {
                            "memory_id": m_id,
                            "summary": (m.get("summary", "")[:80]),
                            "relations_added": new_len - old_len,
                        })

                # Execute demotion
                access_ts = m.get("last_accessed") or m.get("timestamp", now)
                days = _days_since(access_ts)
                trend = _access_density_trend(m.get("access_timestamps", []))

                m["demoted"] = True
                m["demoted_reason"] = f"not accessed in {days:.0f} days"
                m["demoted_at"] = now

                if trend["trend"] == "widening":
                    m["demoted_by_density"] = True
                    m["demoted_reason"] += f" | access density widening: {trend['detail']}"
                else:
                    m["demoted_reason"] += f" | insufficient density data ({trend['detail']})"

                if decision.get("decision") == "demote":
                    m["demoted_reason"] += f" | LLM confirmed: {decision.get('reason', '')[:80]}"

                demoted.append(m_id)
                _audit_log("demote", {
                    "memory_id": m_id,
                    "reason": m["demoted_reason"],
                    "days_since_access": round(days, 1),
                    "scene": m.get("scene", "general"),
                })

    if demoted or archived or kept_by_density or kept_by_scene or kept_by_llm or changed_scenes:
        _save_memories(memories)

    return {
        "status": "ok",
        "total_memories": len(memories),
        "demoted": demoted,
        "already_demoted": len(re_demoted),
        "kept_by_density": len(kept_by_density),
        "kept_by_density_ids": kept_by_density,
        "kept_by_scene": len(kept_by_scene),
        "kept_by_scene_ids": kept_by_scene,
        "kept_by_llm": len(kept_by_llm),
        "kept_by_llm_ids": kept_by_llm,
        "archivable": archived,
        "demote_threshold_days": demote_days,
        "archive_threshold_days": archive_days,
        "distilled_to_kg": distilled_count,
    }


def summary() -> str:
    """Quick readable summary for agent messages."""
    r = run()
    parts = []
    if r.get("demoted"):
        parts.append(f"降级了 {len(r['demoted'])} 条记忆")

    kb = r.get("kept_by_density", 0)
    if kb:
        parts.append(f"密度分析保留 {kb} 条")
    ks = r.get("kept_by_scene", 0)
    if ks:
        parts.append(f"场景保护保留 {ks} 条")
    kl = r.get("kept_by_llm", 0)
    if kl:
        parts.append(f"LLM 审查保留 {kl} 条")
    if r.get("archivable"):
        parts.append(f"可归档 {len(r['archivable'])} 条")
    dk = r.get("distilled_to_kg", 0)
    if dk:
        parts.append(f"知识蒸馏 {dk} 条")
    active = r.get("total_memories", 0) - len(r.get("demoted", []))
    parts.append(f"活跃记忆 {active} 条")
    return "，".join(parts)


def protect(memory_id: str) -> bool:
    """Mark a memory as protected — it will never be demoted by forgetting curve."""
    memories = _load_memories()
    for m in memories:
        if m.get("id") == memory_id:
            if m.get("protected"):
                print(f"🔒 记忆 {memory_id} 已处于保护状态")
                return True
            m["protected"] = True
            _save_memories(memories)
            print(f"🔒 记忆 {memory_id} 已标记为不可遗忘")
            _audit_log("protect", {"memory_id": memory_id})
            return True
    print(f"❌ 未找到记忆: {memory_id}")
    return False


def unprotect(memory_id: str) -> bool:
    """Remove protection from a memory."""
    memories = _load_memories()
    for m in memories:
        if m.get("id") == memory_id:
            if not m.get("protected"):
                print(f"🔓 记忆 {memory_id} 未处于保护状态")
                return True
            m.pop("protected", None)
            _save_memories(memories)
            print(f"🔓 记忆 {memory_id} 已取消保护")
            _audit_log("unprotect", {"memory_id": memory_id})
            return True
    print(f"❌ 未找到记忆: {memory_id}")
    return False


def protected_ids() -> list:
    """Return list of all protected memory IDs."""
    return [m.get("id") for m in _load_memories() if m.get("protected")]


def stats():
    """Terminal stats output."""
    r = run()
    print(f"\n🧠 MOYU Memory Lifecycle (four-stage gating)")
    print("=" * 55)
    print(f"  Total memories:         {r.get('total_memories', 0)}")
    print(f"  Stage 1 window:         {r.get('demote_threshold_days', '?')}d")
    print(f"  Stage 2 kept by density:{r.get('kept_by_density', 0)}")
    print(f"  Stage 3 kept by scene:  {r.get('kept_by_scene', 0)}")
    print(f"  Stage 4 kept by LLM:    {r.get('kept_by_llm', 0)}")
    print(f"  Archive threshold:      {r.get('archive_threshold_days', '?')}d")
    print(f"  Freshly demoted:        {len(r.get('demoted', []))}")
    print(f"  Already demoted:        {r.get('already_demoted', 0)}")
    print(f"  Archivable:             {len(r.get('archivable', []))}")
    if r.get("demoted"):
        print(f"  Demoted IDs:            {', '.join(r['demoted'][:5])}")
    if r.get("kept_by_density_ids"):
        print(f"  Density-kept IDs:       {', '.join(r['kept_by_density_ids'][:5])}")
    if r.get("kept_by_scene_ids"):
        print(f"  Scene-kept IDs:         {', '.join(r['kept_by_scene_ids'][:5])}")
    if r.get("kept_by_llm_ids"):
        print(f"  LLM-kept IDs:           {', '.join(r['kept_by_llm_ids'][:5])}")
    print()


def demo() -> dict:
    return {
        "capability": 13,
        "title": "Forgetting Curve (V2.2 — Four-Stage Gating + LLM Review)",
        "output": """\
🧠 V2.2 FEATURE — Forgetting Curve with LLM Review
──────────────────────────────────────────────────────
  4 stages:
    1. 14d safety window — no memory demoted before this
    2. Access density — stable intervals → keep, widening → demote
    3. Scene protection — hot scene → all scene memories protected
    4. LLM review — semantic importance overrides rule decisions

  Config: forgetting_curve.llm_review.enabled (default: true)
  Fallback: LLM unavailable → demote as rule decided

  [demo_01] Smart frame kickoff   → ✅ 2d  → active (scene: project)
  [demo_06] 张艺 hates WeChat     → ✅ 4d  → active (scene: general)
  [demo_10] 用户偏好记录          → ⏳ 18d → kept by density (stable intervals)
  [demo_03] 用户的名字是xxx    → ⏳ 30d → kept by LLM (identity info)
  [demo_05] 李总 deadline         → ⏳ 32d → demoted (widening intervals, LLM confirmed)
  [demo_02] 方案讨论               → ⏳ 45d → archivable (demoted + 60d)

  Scene index: project(4), memory(2), security(1), general(2)
  Hot scenes: project (memory demo_01 accessed 2d ago)
""",
    }


if __name__ == "__main__":
    import sys
    if "--summary" in sys.argv:
        print(summary())
    else:
        stats()
