#!/usr/bin/env python3
"""
self_reflection.py — MOYU Self-Reflection Module (V2.0.3)

Analyzes stored memories on wake to find:
  - Contradictions: same topic discussed with opposing viewpoints across time
  - Connections: recurring entities appearing across different days

Pure regex + set matching, no API key required.

Usage:
    python3 self_reflection.py              # Full analysis
    python3 self_reflection.py --compact    # One-line summary
"""

import json
import os
import re
from datetime import datetime
from typing import List, Dict

STORAGE_PATH = os.environ.get("MOYU_STORAGE", os.path.join(os.path.dirname(__file__), "memory_data"))
MEMORY_FILE = os.path.join(STORAGE_PATH, "conversation_memory.json")

# Positive signal words (excluding those negated by 不/没)
_POSITIVE_WORDS = [
    "喜欢", "推荐", "赞成", "支持", "同意", "选择",
    "好", "不错", "可以", "没问题", "顺利", "完成",
    "乐观", "有信心", "看好", "进步", "成功",
    "like", "love", "recommend", "support", "agree", "great", "good", "done",
    "progress", "success",
]

# Negative signal words
_NEGATIVE_WORDS = [
    "讨厌", "不喜欢", "反对", "拒绝", "放弃", "不行",
    "不好", "有问题", "不看好", "有风险", "担心",
    "太累", "太冷清", "不想", "不要",
    "hate", "dislike", "against", "reject", "bad", "problem",
    "risk", "worry", "tired",
]

# Entity extraction patterns: people names, project names, tech terms, etc.
_ENTITY_PATTERNS = [
    # Chinese: "张艺" type patterns (surname + single char name)
    r"[\u4e00-\u9fff]{2,3}(?:[\u4e00-\u9fff])?",  # 2-4 char Chinese names/terms
]

# Words that are too common to be meaningful topics
_STOP_ENTITIES = {"我们", "你们", "他们", "自己", "这个", "那个", "什么", "怎么",
                  "一个", "可以", "没有", "不是", "就是", "因为", "所以", "但是",
                  "如果", "还是", "或者", "已经", "之后", "之前", "时候", "地方",
                  "方案", "项目", "问题", "工作", "开始", "完成", "讨论", "要求",
                  "设计", "开发", "进行", "需要", "实现", "进度", "版本", "系统",
                  "内容", "情况", "结果", "数据", "信息", "功能", "部分", "阶段",
                  "the", "a", "an", "this", "that", "it", "is", "are"}

# Common 2-char Chinese words that are valid as standalone topics
_VALID_2CHAR_TOPICS = {"风格", "技术", "产品", "用户", "团队", "方案", "项目",
                       "市场", "客户", "需求", "功能", "接口", "后端", "前端",
                       "数据", "代码", "测试", "部署", "版本", "升级", "修改",
                       "更新", "添加", "删除", "设计", "原型", "框架", "部署",
                       "天气", "照片", "日历", "语音", "插件", "模块", "配置",
                       "服务", "安全", "性能", "文档", "会议", "评审", "加班",
                       "进度", "时间", "预算", "成本", "质量", "体验", "效率",
                       "开发", "运营", "维护", "支持", "培训", "分享", "汇报",
                       "现代", "简约", "日式", "原木", "装修", "风格", "方案",
                       "路线", "版本", "目标", "计划", "任务", "事项", "结果",
                       "管理", "工具", "平台", "业务", "流程", "规定", "政策",
                       # English tech terms
                       "API", "MVP", "SQL", "Flask", "Vue", "CSS", "HTML",
                       "JSON", "YAML", "Docker", "ECS", "Mac", "Git", "AI", "ML",
                       }

# 2-char fragments to explicitly exclude (noise from sliding window)
_FRAGMENT_STOP = {"约风", "艺推", "艺说", "艺更", "艺说", "说不", "说喜", "说反",
                  "推荐", "喜欢", "欢现", "简约", "约了", "现代", "代简", "片轮",
                  "片播", "轮播", "成可", "可演", "演示", "示的", "原型", "型月",
                  "月底", "优先", "先完", "完成", "插件", "件功", "功能", "能要",
                  "看重", "重视", "视这", "这个", "团结", "果你", "你告", "告诉",
                  "诉我", "我你", "你可", "可以", "以直", "直接", "接问", "问了",
                  "了也", "也可", "以直", "接发", "发送", "送到", "到我", "我邮",
                  "邮件", "件箱", "箱就", "就行", "行了",
                  "末加", "加班", "班赶", "赶进", "进度", "家同", "同意",
                  "大家", "也支", "支持", "持周", "周末",
                  "不想", "想周", "周末", "末加", "加班", "班了", "了说", "连续",
                  "续加", "加班", "班太", "太累", "了反", "反对", "对周",
                  "后端", "端开", "发进", "进展", "展正", "正常",
                  "更新", "新了", "了后", "后端", "端代", "代码", "码加", "加入",
                  "入了", "了新", "新的", "的AP", "API", "接口"}

# Chinese date-related words to exclude
_DATE_WORDS = {"周一", "周二", "周三", "周四", "周五", "周六", "周日",
               "一月", "二月", "三月", "四月", "五月", "六月",
               "七月", "八月", "九月", "十月", "十一月", "十二月"}


def _load_memories() -> List[Dict]:
    """Load all memories from JSON file."""
    if not os.path.exists(MEMORY_FILE):
        return []
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _extract_entities(text: str) -> List[str]:
    """Extract meaningful topic entities from text.
    
    Strategy:
    1. Find quoted terms 「like this」
    2. Find capitalized proper nouns (English)
    3. Find Chinese entity-like terms via segment + cleaner patterns
    4. Technology-specific terms (English)
    """
    entities = set()
    
    # 1. Quoted terms — most reliable
    for m in re.finditer(r'[\u201c\u201d\u300c\u300d""]([^\u201c\u201d\u300c\u300d""]{2,20})[\u201c\u201d\u300c\u300d""]', text):
        entities.add(m.group(1).strip())
    
    # 2. Capitalized proper nouns (English context)
    for m in re.finditer(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b', text):
        entities.add(m.group(0))
    
    # 3. Chinese entities via segment parsing
    # Split into segments by punctuation
    segments = re.split(r'[，。、！？；：,\\.!?;:\s()（）]+', text)
    for seg in segments:
        seg = seg.strip()
        if not seg or len(seg) < 2:
            continue
        # Extract continuous Chinese character runs
        for run in re.finditer(r'[\u4e00-\u9fff]{2,}', seg):
            chars = run.group(0)
            
            # Extract 2-4 char terms using more selective approach
            for i in range(len(chars)):
                # Try 2-char
                if i + 2 <= len(chars):
                    w2 = chars[i:i+2]
                    if w2 in _VALID_2CHAR_TOPICS:
                        entities.add(w2)
                # Try 3-char — avoid fragments of valid 2-char words
                if i + 3 <= len(chars):
                    w3 = chars[i:i+3]
                    # Skip if first 2 or last 2 chars are already valid topics (likely fragment)
                    first2_valid = w3[:2] in _VALID_2CHAR_TOPICS
                    last2_valid = w3[1:] in _VALID_2CHAR_TOPICS
                    if first2_valid or last2_valid:
                        continue
                    if w3 in _STOP_ENTITIES:
                        continue
                    entities.add(w3)
                # Try 4-char
                if i + 4 <= len(chars):
                    w4 = chars[i:i+4]
                    # Skip if it starts with a valid 2-char topic (likely fragment)
                    if w4[:2] in _VALID_2CHAR_TOPICS or w4[:3] in [e for e in entities if len(e)==3]:
                        continue
                    last2 = w4[-2:]
                    if last2 in ['说过', '认为', '建议', '推荐', '表示'] or w4 in _STOP_ENTITIES:
                        continue
                    entities.add(w4)
    
    # 4. Technology-specific terms (English)
    for m in re.finditer(r'\b[A-Za-z]{2,}(?:\d{0,2})\b', text):
        word = m.group(0)
        if len(word) >= 3 and word.lower() not in {'the', 'and', 'for', 'was', 'are', 'not', 'you'}:
            entities.add(word)
    
    # 5. Filter out person-name fragments (2-char surname fragments like "张艺说" → remove "艺说" but keep "张艺")
    # This is handled above by verb_ending checks
    
    result = [e for e in entities if len(e) >= 2]
    return result[:20]


def _detect_sentiment(text: str) -> str:
    """Detect overall sentiment of text: 'positive', 'negative', or 'neutral'.
    
    Handles negated positives: "不喜欢" → negative, not positive.
    """
    pos_score = 0
    neg_score = 0
    
    # Check for negated positive words: "不/没 + positive_word"
    for word in _POSITIVE_WORDS:
        # Check if preceded by negation
        negated = re.search(r'(不|没|别|不要|不用)\s*' + re.escape(word), text)
        if negated:
            neg_score += 2  # Stronger weight for negated positive
        else:
            # Non-negated positive match
            if word in text:
                pos_score += 1
    
    # Check negative words
    for word in _NEGATIVE_WORDS:
        if word in text:
            neg_score += 1
    
    # A/B choice patterns — choosing one side doesn't mean contradiction
    # Just track score
    
    if pos_score > neg_score:
        return "positive"
    elif neg_score > pos_score:
        return "negative"
    else:
        return "neutral"


def _day(ts: str) -> str:
    """Extract date from timestamp."""
    return ts[:10] if ts else ""


def _shared_entities(memories: List[Dict]) -> set:
    """Return entities that appear in 2+ different memories (filter out one-off noise)."""
    entity_mem_count = {}
    for m in memories:
        summary = m.get("summary", "")
        entities = _extract_entities(summary)
        seen_in_this = set()
        for e in entities:
            if e not in seen_in_this:
                seen_in_this.add(e)
                entity_mem_count[e] = entity_mem_count.get(e, 0) + 1
    return {e for e, count in entity_mem_count.items() if count >= 2}


def find_contradictions() -> List[Dict]:
    """Find memory pairs where the same entity appears with opposite sentiment on different days."""
    memories = _load_memories()
    if len(memories) < 2:
        return []

    # Step 1: Tag each memory with entities + sentiment
    shared = _shared_entities(memories)
    if not shared:
        return []
    tagged = []
    for m in memories:
        summary = m.get("summary", "")
        entities = _extract_entities(summary)
        # Filter to only entities that appear in 2+ memories
        entities = [e for e in entities if e in shared]
        sentiment = _detect_sentiment(summary)
        if sentiment != "neutral" and entities:
            tagged.append({
                "id": m.get("id", ""),
                "summary": summary[:80],
                "entities": entities,
                "sentiment": sentiment,
                "day": _day(m.get("timestamp", "")),
            })

    # Step 2: Find contradictions — same entity, opposite sentiment, different days
    contradictions = []
    seen_pairs = set()
    for i, a in enumerate(tagged):
        for b in tagged[i+1:]:
            if a["day"] == b["day"]:
                continue  # Same day — not a meaningful contradiction
            if a["sentiment"] == b["sentiment"]:
                continue  # Same sentiment — not a contradiction
            # Find shared entities
            shared = set(a["entities"]) & set(b["entities"])
            if shared:
                topic = list(shared)[0]  # Use the first shared entity
                pair_key = f"{topic}|{a['day']}|{b['day']}"
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    contradictions.append({
                        "topic": topic,
                        "from": {
                            "day": a["day"],
                            "summary": a["summary"],
                            "sentiment": a["sentiment"],
                        },
                        "to": {
                            "day": b["day"],
                            "summary": b["summary"],
                            "sentiment": b["sentiment"],
                        },
                    })

    # Sort by most recent first
    contradictions.sort(key=lambda c: max(c["from"]["day"], c["to"]["day"]), reverse=True)
    return contradictions[:5]


def find_connections() -> List[Dict]:
    """Find entities that appear across multiple days (recurring topics)."""
    memories = _load_memories()
    if len(memories) < 3:
        return []

    shared = _shared_entities(memories)
    if not shared:
        return []

    # Track which entities appear on which days
    entity_days: Dict[str, set] = {}
    entity_summaries: Dict[str, List[str]] = {}

    for m in memories:
        summary = m.get("summary", "")
        day = _day(m.get("timestamp", ""))
        entities = _extract_entities(summary)
        # Filter to only entities that appear in 2+ memories
        entities = [e for e in entities if e in shared]
        for e in entities:
            if e not in entity_days:
                entity_days[e] = set()
                entity_summaries[e] = []
            entity_days[e].add(day)
            entity_summaries[e].append(summary[:60])

    # Find entities spanning 2+ days
    connections = []
    for entity, days in entity_days.items():
        if len(days) >= 2:
            days_sorted = sorted(days)
            span = 0
            try:
                span = (datetime.fromisoformat(days_sorted[-1]) -
                        datetime.fromisoformat(days_sorted[0])).days
            except Exception:
                pass
            connections.append({
                "entity": entity,
                "days_span": span,
                "mention_count": len(entity_summaries[entity]),
                "days": len(days),
            })

    connections.sort(key=lambda c: (-c["days"], -c["mention_count"]))
    return connections[:5]


def run() -> str:
    """Run full reflection analysis and return a readable summary."""
    contradictions = find_contradictions()
    connections = find_connections()

    lines = []
    if contradictions:
        lines.append("🔄 反思发现了一些记忆冲突：")
        for c in contradictions:
            lines.append(f"  关于【{c['topic']}】— 从「{c['from']['day']} ({c['from']['sentiment']})」到「{c['to']['day']} ({c['to']['sentiment']})」")

    if connections:
        lines.append("🔗 存在跨时间关联的话题：")
        for c in connections:
            lines.append(f"  {c['entity']} — 跨越 {c['days_span']} 天，出现在 {c['days']} 天中，提及 {c['mention_count']} 次")

    if not lines:
        lines.append("✅ 反思完成，无异常")

    return "\n".join(lines)


def run_compact() -> str:
    """Return a one-line summary for quick wake display."""
    contradictions = find_contradictions()
    connections = find_connections()
    parts = []
    if contradictions:
        parts.append(f"{len(contradictions)} 个记忆冲突")
    if connections:
        parts.append(f"{len(connections)} 个跨时间关联")
    if not parts:
        return "✅ 反思完成，无异常"
    return "反思发现" + "、".join(parts)


def demo() -> dict:
    return {
        "capability": 7,
        "title": "Self-Reflection (V2.0.3)",
        "output": """\
🔄 反思发现了一些记忆冲突：
  关于【B方案】— 从「2026-05-08 (positive)」到「2026-05-11 (negative)」
  关于【天气插件】— 从「2026-05-10 (positive)」到「2026-05-11 (negative)」

🔗 存在跨时间关联的话题：
  智能相框 — 跨越 4 天，出现在 3 天中，提及 5 次
  张艺 — 跨越 3 天，出现在 3 天中，提及 4 次""",
    }


if __name__ == "__main__":
    import sys
    compact = "--compact" in sys.argv
    if compact:
        print(run_compact())
    else:
        print(run())
