#!/usr/bin/env python3
"""
auto_extractor.py — MOYU Automatic Memory Extraction (V1.0)

Two-tier extraction pipeline:
  Fast path (rules)   — regex patterns for high-confidence facts (0 token cost)
  Slow path (LLM)     — structured extraction for remaining text (~500 tokens)

Usage (programmatic):
    from moyu_toolkit.auto_extractor import extract_and_store
    count = extract_and_store("今天用户说：我是开发者...")

Usage (CLI):
    python3 auto_extractor.py extract <text>
    python3 auto_extractor.py stats
"""

import json
import os
import re
import hashlib
import math
import gzip
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

# ───────────────────────────────────────────────
# Configuration
# ───────────────────────────────────────────────

MAX_PER_SESSION = 5              # Max memories per extract_and_store call
DEDUP_SIMILARITY = 0.88          # Cosine similarity threshold for semantic dedup
CONFIDENCE_RULE = 1.0            # Fast path confidence (store immediately)
CONFIDENCE_LLM = 0.8             # Slow path confidence (needs confirmation)
TYPE_DENSITY_CAP = 10            # Max memories of same type in 24h before pause
STORAGE_NAME = "auto_extractor"  # For storing stats in memory_data


def _storage_path() -> str:
    """Get path for auto_extractor's own metadata storage."""
    from moyu_toolkit._moyu_paths import get_default_storage
    return os.path.join(get_default_storage(), "auto_extractor_stats.json")


def _load_stats() -> dict:
    """Load extraction stats (type density tracking)."""
    p = _storage_path()
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return {"extracted": [], "paused_types": [], "total_extracted": 0}


def _save_stats(stats: dict):
    """Save extraction stats."""
    p = _storage_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


# ───────────────────────────────────────────────
# Late imports (avoid circular dependency)
# ───────────────────────────────────────────────

def _get_add_memory():
    """Import and return add_memory from agent_memory."""
    import importlib.util
    try:
        from moyu_toolkit import agent_memory as am
        return am.add_memory
    except ImportError:
        try:
            import sys
            # This works when called from the tool via sys.path
            from agent_memory import add_memory
            return add_memory
        except ImportError:
            return None


def _get_embedding_fn():
    """Import and return get_embedding from agent_memory."""
    try:
        from moyu_toolkit import agent_memory as am
        return am.get_embedding
    except ImportError:
        try:
            from agent_memory import get_embedding
            return get_embedding
        except ImportError:
            return None


# ───────────────────────────────────────────────
# Fast Path: Rule-Based Extraction
# ───────────────────────────────────────────────

# Each rule: (regex_pattern, fact_type, confidence_weight)
# Ordered by specificity — more specific rules first to avoid greedy captures
_RULES = [
    # ── Corrections (highest priority) ──
    (r'(?:不是|不对|纠正|更正|说错了?|搞错了?|我改[了]?|重新说)\s*[,，:：]?\s*(.+?)(?:[。！!？?]|$)', 'correction', 1.0),

    # ── Decisions ──
    (r'(?:决定|选择|选了?|采纳|采用|敲定|确定|定了?|拍板|就?这么定)\s*[,，:：]?\s*(.+?)(?:[。！!？?]|$)', 'decision', 1.0),
    (r'(?:走|跟|按)\s*(.+?)\s*(?:方案|路线|方向|策略)', 'decision', 0.9),

    # ── Preferences ──
    (r'(?:喜欢|偏好|偏爱|更[偏向于喜欢爱]|钟意|钟情|更倾向)\s*[,，:：]?\s*(.+?)(?:[。！!？?]|$)', 'preference', 0.9),
    (r'(?:习惯|常用|爱用|一直?用|坚持用|最?擅[长]?)\s*[,，:：]?\s*(.+?)(?:[。！!？?]|$)', 'preference', 0.8),
    (r'(?:推荐|建议|力荐)\s*[,，:：]?\s*(.+?)(?:[。！!？?]|$)', 'preference', 0.7),
    (r'(?:讨厌|不喜欢|反感|受不了|最烦|忍不了)\s*[,，:：]?\s*(.+?)(?:[。！!？?]|$)', 'preference_negative', 0.9),

    # ── Personal facts ──
    (r'(?:我是\s*(?:一[个名位])?\s*(.+?))(?:[。，；]|$)', 'personal', 0.9),
    (r'(?:我在\s*(.+?)\s*(?:工作|上班|任职|学习|读书))(?:[。，；]|$)', 'personal', 0.9),
    (r'(?:我[在就]?来自\s*(.+?))(?:[。，；]|$)', 'personal', 0.9),
    (r'(?:我住在?\s*(.+?))(?:[。，；]|$)', 'personal', 0.8),
    (r'(?:我毕业于?\s*(.+?))(?:[。，；]|$)', 'personal', 0.8),
    (r'(?:我的[职业专业身份]\s*(?:是|为)?\s*(.+?))(?:[。，；]|$)', 'personal', 0.9),
    (r'(?:我(?:今年|已经)\s*\d+\s*岁)', 'personal', 0.6),
    (r'(?:我(?:是|有)\s*\d+\s*年\s*(?:经验|工作|开发)经历)', 'personal', 0.8),

    # ── Technical facts ──
    (r'(?:用|使用|采用|基于|依赖|集成|切换|迁移[到至]?)\s*(?:了|的|过)?\s*'
     r'(Python|JavaScript|TypeScript|Rust|Go|Java|C[+#]?|Kotlin|Swift|Scala|'
     r'Flask|Django|FastAPI|Spring|React|Vue[23]?|Angular|Svelte|Next[.]?js|Nuxt|'
     r'PostgreSQL|MySQL|SQLite|Redis|MongoDB|Elasticsearch|'
     r'Docker|Kubernetes|K8s|AWS|GCP|Azure|Linux|macOS|Windows|'
     r'PyTorch|TensorFlow|JAX|LangChain|LlamaIndex|'
     r'nginx|Apache|RabbitMQ|Kafka|gRPC|GraphQL)', 'technical', 0.9),
    (r'(?:框架|工具|语言|库|平台|服务|系统|中间件)\s*(?:是|为|用)的?\s*(.+?)(?:[。，；]|$)', 'technical', 0.7),
    (r'(?:部署在|上线到|运行在|托管在|发布到)\s*(.+?)(?:[。，；]|$)', 'technical', 0.7),

    # ── Habits & temporal ──
    (r'(?:每周|每天|每月|周[末一至日]|工作日|周末|平时|一般)\s*(?:都|会|就|是)?\s*(.+?)(?:[。！!？?]|$)', 'habit', 0.7),
    (r'(?:截止|截至|月底|年底|下[周月年]|这[周月年]|下个?[周月年])', 'temporal', 0.5),

    # ── Relations ──
    (r'(?:负责|管理|对接|配合|协助|合作|带领|带领)\s*(.+?)(?:[。，；]|$)', 'relation', 0.7),
    (r'(.+?)(?:说|提到|认为|觉得|建议|吐槽|抱怨)(?:\s*[:：]|\s+)(.+?)(?:[。！!？?]|$)', 'relation', 0.5),

    # ── Project info ──
    (r'(?:项目|产品|功能|模块)\s*(?:叫|称为|命名为?|是)\s*(.+?)(?:[。，；]|$)', 'project', 0.8),
    (r'(?:已完成|已实现|已上线|开发[了完]|交付[了]?|发布[了]?)\s*(.+?)(?:[。，；]|$)', 'project', 0.7),

    # ── Cognitive judgments / analysis ──
    (r'(?:本质上是|本质上是在|归根结底|说白了|说白了就是|其核心是|核心问题在于)\s*(.+?)(?:[。！!？?]|$)', 'judgment', 0.8),
    (r'(?:我(?:开始)?意识到|我发现了?|我注意到|我终于明白了?|我才明白|我理解[了到]?)\s*(.+?)(?:[。！!？?]|$)', 'judgment', 0.8),
    (r'(?:这(?:件|种|类|个)事[情]?\s*(?:说明|意味着|揭示[了]?|暴露[了]?|体现[了]?))\s*(.+?)(?:[。！!？?]|$)', 'judgment', 0.7),
]

# Patterns that are clearly NOT worth storing
_NEGATIVE_PATTERNS = [
    r'你好|您好|hi|hello|早上好|晚上好|下午好|晚安|拜拜|再见|see you',
    r'谢谢|感谢|辛苦了|麻烦了|多谢',
    r'哈哈|呵呵|嘿嘿|嗯嗯|嘻嘻|hhh|233|666',
    r'好的|行吧|可以吗|是吗|对呀|对的|没错|是的',
    r'看看|试试|想想|可能|大概|也许|或许|应该|好像|估计',
    r'今天[天气]|好累|好困|好烦|心情|饿[了]?|吃[了过]?|睡了',
]

# General knowledge (not personal) — single-word filter
_GENERAL_KNOWLEDGE = {
    "Python", "JavaScript", "TypeScript", "Rust", "Go", "Java", "C++",
    "程序", "代码", "电脑", "服务器", "数据库", "网站", "APP", "手机",
    "天气", "时间", "日期", "星期", "月份", "年", "月", "日",
    "吃饭", "睡觉", "喝水", "运动", "跑步", "看书",
    "Linux", "Windows", "macOS", "Docker", "Git",
    "AI", "LLM", "GPT", "大模型", "人工智能",
}


def _is_general_knowledge(text: str) -> bool:
    """Check if text is general/common knowledge rather than personal fact."""
    text_lower = text.lower().strip()
    # Single token that's general
    if text_lower in {k.lower() for k in _GENERAL_KNOWLEDGE}:
        return True
    # Generic fact patterns
    for kw in ["是一种", "是指", "指的是", "通常", "一般", "默认", "标准", "泛指"]:
        if kw in text_lower:
            return True
    return False


def _fast_extract(text: str) -> List[Dict]:
    """Fast path: extract high-confidence facts using regex patterns.

    Returns list of dicts:
        {summary: str, type: str, confidence: float, source: str}
    """
    results = []
    matched_spans = []

    # Pre-clean: strip code blocks and markdown noise
    clean = re.sub(r'```[\s\S]*?```', '', text)
    clean = re.sub(r'`[^`]+`', '', clean)
    clean = re.sub(r'\*\*.*?\*\*', '', clean)
    clean = re.sub(r'\n{3,}', '\n\n', clean)

    for pattern, fact_type, weight in _RULES:
        for match in re.finditer(pattern, clean):
            # Extract the meaningful capture group
            if match.lastindex and match.lastindex >= 1:
                content = match.group(1).strip()
            else:
                content = match.group(0).strip()

            if not content or len(content) < 4:
                continue

            # Skip if it looks like noise
            if any(re.search(neg, content, re.IGNORECASE) for neg in _NEGATIVE_PATTERNS):
                continue

            # Skip general knowledge
            if _is_general_knowledge(content):
                continue

            # Check span overlap (avoid duplicate catches from different rules)
            span = (match.start(), match.end())
            if _overlaps(span, matched_spans):
                continue

            matched_spans.append(span)
            results.append({
                "summary": content[:200],
                "type": fact_type,
                "confidence": weight,
                "source": "rule",
            })

            if len(results) >= MAX_PER_SESSION:
                break
        if len(results) >= MAX_PER_SESSION:
            break

    return results


def _overlaps(span: Tuple[int, int], spans: List[Tuple[int, int]]) -> bool:
    """Check if span overlaps with any existing spans."""
    for s in spans:
        if not (span[1] <= s[0] or span[0] >= s[1]):
            return True
    return False


# ───────────────────────────────────────────────
# Slow Path: LLM-Based Extraction
# ───────────────────────────────────────────────

def _llm_extract(text: str, already_found: List[Dict]) -> List[Dict]:
    """Slow path: use LLM to extract facts not caught by fast path.

    Returns list of dicts:
        {summary: str, type: str, confidence: float, source: str}
    """
    try:
        from _llm_client import resolve_llm_config, call_llm_api
    except ImportError:
        return []

    api_key, base_url, model = resolve_llm_config()
    if not api_key or api_key == "your-api-key-here":
        return []

    # Tell LLM what we already found so it doesn't duplicate
    already_text = ""
    if already_found:
        summaries = "\n".join(
            f"- [{f['type']}] {f['summary']}" for f in already_found
        )
        already_text = f"Already extracted (DO NOT repeat):\n{summaries}\n"

    remaining = len(already_found)
    max_new = max(1, MAX_PER_SESSION - remaining)

    prompt = f"""You are a memory extraction assistant for an AI called MoBai.

Your job: extract atomic facts worth remembering from this conversation.

WHAT to extract:
- Personal info (role, location, background)
- Preferences and opinions
- Decisions and choices
- Corrections (when someone corrects a previous statement)
- Technical details (tools, languages, frameworks used)
- Habits and routines
- Project information
- Relationships between people
- **Cognitive judgments and analysis** — when MoBai analyzes another AI, a person, or a phenomenon and forms a judgment or conclusion, extract the judgment + the reasoning behind it. These are essential for MoBai's personality development.

WHAT to SKIP:
- Greetings, goodbyes, filler
- General knowledge or common sense
- Emotional venting or one-off complaints
- Jokes or sarcasm (unless it reveals a real opinion)
- Anything already listed in "Already extracted"

Format each fact as a concise, complete sentence.
Use third-person perspective (e.g. "User prefers Python over JavaScript").

{already_text}
CONVERSATION:
{text[:3000]}

Return a JSON array. Each object has:
  "summary": str  — the fact (max 100 chars)
  "type": str     — one of: preference, decision, correction, personal, technical, habit, relation, project
  "confidence": float — 0.0 to 1.0 (how sure you are this is worth remembering)

Max {max_new} items. Return ONLY the JSON array, no other text."""

    result = call_llm_api(
        api_key, base_url, model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1000,
        timeout=20,
    )

    if not result:
        return []

    # Parse JSON from response (handle possible markdown fence wrapping)
    try:
        json_str = result.strip()
        if json_str.startswith("```"):
            json_str = re.sub(r'^```(?:json)?\s*', '', json_str)
            json_str = re.sub(r'\s*```$', '', json_str)
        items = json.loads(json_str)
        if not isinstance(items, list):
            return []
    except (json.JSONDecodeError, Exception):
        return []

    # Validate and normalize
    validated = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary", ""))[:200].strip()
        if len(summary) < 4:
            continue
        fact_type = str(item.get("type", "fact"))
        confidence = max(0.0, min(1.0, float(item.get("confidence", 0.8))))
        validated.append({
            "summary": summary,
            "type": fact_type if fact_type in ("preference", "decision", "correction",
                                                "personal", "technical", "habit",
                                                "relation", "project") else "fact",
            "confidence": confidence,
            "source": "llm",
        })
        if len(validated) >= max_new:
            break

    return validated


# ───────────────────────────────────────────────
# Dedup (semantic + MD5)
# ───────────────────────────────────────────────

def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(ai * bi for ai, bi in zip(a, b))
    na = math.sqrt(sum(ai * ai for ai in a))
    nb = math.sqrt(sum(bi * bi for bi in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _semantic_dedup(summary: str) -> bool:
    """Check if summary is semantically similar to existing memories.
    Returns True if should be skipped (duplicate)."""
    embed_fn = _get_embedding_fn()
    if not embed_fn:
        return False  # Can't check, let it through

    try:
        from moyu_toolkit import agent_memory as am
        _load_index = am._load_index
        _load_memories = am._load_memories
    except ImportError:
        try:
            from agent_memory import _load_index, _load_memories
        except ImportError:
            return False

    # Get embedding for new text
    vec = embed_fn(summary)
    if not vec:
        return False

    # Check against all existing memory embeddings
    idx = _load_index()
    for entry in idx.get("vectors", []):
        existing_vec = entry.get("vector", [])
        if not existing_vec:
            continue
        sim = _cosine_similarity(vec, existing_vec)
        if sim >= DEDUP_SIMILARITY:
            return True  # Too similar, skip

    # Also check MD5 (exact match)
    md5 = hashlib.md5(summary.encode()).hexdigest()[:16]
    memories = _load_memories()
    for m in memories:
        if m.get("content_hash") == md5:
            return True

    return False


# ───────────────────────────────────────────────
# Density check (prevent type flooding)
# ───────────────────────────────────────────────

def _check_density(fact_type: str, stats: dict) -> bool:
    """Check if this fact type has been extracted too often recently.
    Returns True if OK to proceed, False if paused."""
    if fact_type in stats.get("paused_types", []):
        return False  # Type is paused

    # Count extractions of this type in last 24h
    now = datetime.now()
    count = 0
    for entry in stats.get("extracted", []):
        if entry.get("type") == fact_type:
            try:
                ts = datetime.fromisoformat(entry["timestamp"])
                if (now - ts).total_seconds() < 86400:
                    count += 1
            except Exception:
                pass

    if count >= TYPE_DENSITY_CAP:
        # Auto-pause this type
        if fact_type not in stats.get("paused_types", []):
            stats.setdefault("paused_types", []).append(fact_type)
            _save_stats(stats)
        return False

    return True


# ───────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────

def extract_and_store(conversation_text: str, source: str = "auto_extracted") -> int:
    """Extract facts from conversation text and store as memories.

    Args:
        conversation_text: The raw conversation text to extract from.
        source: Source label for stored memories (default: "auto_extracted").

    Returns:
        Number of memories successfully stored.
    """
    add_memory = _get_add_memory()
    if not add_memory:
        print("⚠️  auto_extractor: add_memory() not available, skipping")
        return 0

    if not conversation_text or len(conversation_text.strip()) < 20:
        return 0  # Too short to extract anything useful

    stats = _load_stats()
    stored_count = 0

    # Phase 1: Fast path (rules)
    fast_results = _fast_extract(conversation_text)

    for fact in fast_results:
        if not _check_density(fact["type"], stats):
            continue
        if _semantic_dedup(fact["summary"]):
            continue

        entry = add_memory(
            summary=fact["summary"],
            source=source,
            metadata={
                "extractor": "auto_extractor",
                "extract_method": "rule",
                "fact_type": fact["type"],
                "confidence": fact["confidence"],
            },
        )
        if entry:
            stored_count += 1
            stats.setdefault("extracted", []).append({
                "type": fact["type"],
                "timestamp": datetime.now().isoformat(),
                "method": "rule",
            })

    # Phase 2: Slow path (LLM) — only if fast didn't fill the quota
    remaining = MAX_PER_SESSION - len(fast_results)
    if remaining > 0:
        llm_results = _llm_extract(conversation_text, fast_results)

        for fact in llm_results:
            if stored_count >= MAX_PER_SESSION:
                break
            if not _check_density(fact["type"], stats):
                continue
            if _semantic_dedup(fact["summary"]):
                continue

            entry = add_memory(
                summary=fact["summary"],
                source=source,
                metadata={
                    "extractor": "auto_extractor",
                    "extract_method": "llm",
                    "fact_type": fact["type"],
                    "confidence": fact["confidence"],
                },
            )
            if entry:
                stored_count += 1
                stats.setdefault("extracted", []).append({
                    "type": fact["type"],
                    "timestamp": datetime.now().isoformat(),
                    "method": "llm",
                })

    # Update stats — always save, even if nothing stored (paused_types may have changed)
    if stored_count > 0:
        stats["total_extracted"] = stats.get("total_extracted", 0) + stored_count
    # Keep only last 200 entries to prevent unbounded growth
    if len(stats.get("extracted", [])) > 200:
        stats["extracted"] = stats["extracted"][-200:]
    _save_stats(stats)

    return stored_count


def stats() -> dict:
    """Show auto_extractor statistics."""
    s = _load_stats()
    total = s.get("total_extracted", 0)
    by_method = {}
    by_type = {}
    for entry in s.get("extracted", []):
        by_method[entry.get("method", "?")] = by_method.get(entry.get("method", "?"), 0) + 1
        by_type[entry.get("type", "?")] = by_type.get(entry.get("type", "?"), 0) + 1
    return {
        "total_extracted": total,
        "by_method": by_method,
        "by_type": by_type,
        "paused_types": s.get("paused_types", []),
    }


def demo() -> dict:
    """Return demo content for moyu_demo.py discovery engine."""
    return {
        "capability": 13,
        "title": "Auto Memory Extraction (V1.0 — Dual-Channel)",
        "output": """\
🔍 MOYU V1.0 — Automatic Memory Extraction
────────────────────────────────────────
  Two-tier extraction pipeline:
    Fast path (rules, 0 token): corrections, decisions, preferences,
                                personal info, technical facts, habits,
                                relations, project info, cognitive judgments
    Slow path (LLM, ~500 tokens): semantic extraction for edge cases

  Built-in safety:
    • Semantic dedup (embedding similarity >0.88 skipped)
    • Type density cap (24h max 10 per type)
    • Max 5 memories per session
    • General knowledge filter

  Usage: moyu extract <text>   # Extract and store
         moyu extract stats    # Show extraction history""",
    }


# ───────────────────────────────────────────────
# CLI Entry Point
# ───────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "extract" and len(sys.argv) >= 3:
        text = sys.argv[2]
        count = extract_and_store(text)
        print(f"✅ Stored {count} memories")
    elif len(sys.argv) >= 2 and sys.argv[1] == "stats":
        s = stats()
        print(f"📊 Auto Extractor Stats:")
        print(f"   Total extracted: {s['total_extracted']}")
        print(f"   By method: {s['by_method']}")
        print(f"   By type: {s['by_type']}")
        if s["paused_types"]:
            print(f"   ⏸️  Paused types: {s['paused_types']}")
    else:
        print("Usage:")
        print("  python3 auto_extractor.py extract <text>   # Extract and store")
        print("  python3 auto_extractor.py stats             # Show statistics")
