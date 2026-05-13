#!/usr/bin/env python3
"""learner.py — MOYU Adaptive Learner Module (v1.1)

Automatically learn from user corrections — avoid repeating the same mistakes.
Adapts to each user's speech patterns — you say "注意！" and I learn "注意！"
After 3 similar corrections, promotes to a permanent behavioral rule.

Usage:
    python3 learner.py detect <text>  # Detect correction signal
    python3 learner.py learn <text>   # Learn from correction
    python3 learner.py stats          # Show statistics
    python3 learner.py inject         # Get injection format
    python3 learner.py signals        # View all active trigger words
"""

import json
import os
import re
from datetime import datetime

STORAGE_PATH = os.environ.get("MOYU_STORAGE", os.path.join(os.path.dirname(__file__), "memory_data"))

# Seed trigger words — built-in, covering most common correction patterns
DEFAULT_SIGNALS = [
    "不是", "不对", "错了", "应该是", "不要",
    "记住", "我告诉过你", "我说过", "别", "别再",
    "你又", "还说",
    # English seed words
    "no", "wrong", "don't", "stop", "hey",
    "remember", "i told you", "not", "never",
    "hold on", "wait", "actually", "correction",
]

IGNORE_PATTERNS = [r"他\w*不", r"我不(知道|确定)", r"不太好",
                      r"i don't (know|think)", r"not (sure|really|bad)", r"not bad"]


def _load_config() -> dict:
    import yaml
    cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


# ==================== Adaptive Trigger Words ====================

def _learned_signals_path() -> str:
    os.makedirs(STORAGE_PATH, exist_ok=True)
    return os.path.join(STORAGE_PATH, "learned_signals.json")


def _load_learned_signals() -> list:
    p = _learned_signals_path()
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_learned_signals(signals: list):
    with open(_learned_signals_path(), 'w') as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)


def _all_signals() -> list:
    """Return all active trigger words: seed words + learned new words"""
    cfg = _load_config()
    config_signals = cfg.get("learner", {}).get("correction_signals", None)
    base = config_signals if config_signals and len(config_signals) > 0 else DEFAULT_SIGNALS
    learned = _load_learned_signals()
    return base + learned


def _register_new_signal(text: str):
    """
    Extract a new trigger word from the current text and register it to the adaptive library.
    
    Strategy: find the short word before the first exclamation mark/comma as a correction trigger.
    E.g., "Hey! That file does not exist" → extract "Hey"
    "Hey! That's wrong" → extract "Hey"
    """
    known = set(DEFAULT_SIGNALS + _load_learned_signals())
    
    # Find the word before the first punctuation
    m = re.match(r'^\s*([^\s，。！？、!?.]{1,10})[，。！？、!?.]', text[:30])
    if m:
        cand = m.group(1)
        if cand not in known and cand not in ['这个', '那个', '什么', '怎么', '这样',
                                                '就是', '不是', '没有', '如果', '因为',
                                                '所以', '然后', '但是', '还是', '或者',
                                                '可以', '一个', '我觉', '你说', '要么',
                                                'the', 'a', 'an', 'it', 'is', 'i', 'you',
                                                'he', 'she', 'we', 'they', 'this', 'that',
                                                'are', 'was', 'were', 'be', 'been', 'have',
                                                'has', 'had', 'do', 'does', 'did', 'will',
                                                'would', 'could', 'should', 'may', 'might',
                                                'can', 'shall', 'to', 'of', 'in', 'for',
                                                'on', 'with', 'at', 'by', 'from', 'as',
                                                'and', 'or', 'but', 'if', 'so', 'about',
                                                'up', 'out', 'all', 'just', 'not', 'no']:
            learned = _load_learned_signals()
            if cand not in learned:
                learned.append(cand)
                _save_learned_signals(learned)
                print(f"  🧠 Learned new trigger word: \"{cand}\"")
                return True
    return False


# ==================== API Calls ====================

def _call_llm(prompt: str) -> str:
    import yaml, requests as rq
    cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if not os.path.exists(cfg_path):
        return ""
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f) or {}
    api_cfg = cfg.get("api", {})
    key = api_cfg.get("api_key", "") or os.environ.get("MOYU_API_KEY", "")
    if not key:
        return ""
    url = api_cfg.get("base_url", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    model = api_cfg.get("chat_model", "gpt-4o-mini")
    try:
        resp = rq.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       json={"model": model, "messages": [
                           {"role": "system", "content": "You are an experience extractor."},
                           {"role": "user", "content": prompt}
                       ], "temperature": 0.1}, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception:
        pass
    return ""


# ==================== Core Logic ====================

def detect_corrections(text: str) -> list:
    """
    Detect correction signals in dialog text.
    Checks both seed words and adaptively learned new words.
    """
    if not text:
        return []
    signals = _all_signals()
    last_msg = text.split("\n")[-1][:300]
    hits = []
    for sig in signals:
        if sig in last_msg.lower():
            ignored = any(re.search(p, last_msg, re.IGNORECASE) for p in IGNORE_PATTERNS)
            if not ignored:
                hits.append(f"[{sig}] {last_msg[:100]}")
    return hits


def learn(text: str) -> bool:
    """
    Two-step learning from correction text:
    1. Extract lesson (saved to lessons.json)
    2. If no known trigger words matched but correction content exists → adaptively learn new trigger word
    
    Returns True if something new was learned (lesson or new word).
    """
    lessons = _load_lessons()
    corrections = _load_corrections()
    lesson_text = _extract_lesson(text)
    if not lesson_text:
        return False
    
    now = datetime.now().isoformat()
    
    # Check if any known trigger words were hit
    known_signals = _all_signals()
    any_known_hit = any(sig in text for sig in known_signals)
    
    # If none of the known trigger words matched but lesson was extracted — user used a new expression
    if not any_known_hit:
        _register_new_signal(text)
    
    # Same-lesson detection & promotion (v1.0 original logic)
    existing = next((l for l in lessons["lessons"]
                     if _similar(l.get("lesson", ""), lesson_text)), None)
    
    if existing:
        existing["count"] += 1
        existing["last_triggered"] = now
        if existing["count"] >= 3 and not existing.get("promoted"):
            existing["promoted"] = True
            print(f"  ⬆️ Promoted to rule: {existing['lesson'][:60]}")
    else:
        for c in corrections:
            if text[:50] in c:
                return True  # Same text repeated, but new word may have been registered
        lessons["lessons"].append({
            "id": f"LSN-{len(lessons['lessons'])+1:03d}",
            "lesson": lesson_text, "count": 1, "created": now,
            "last_triggered": now, "promoted": False
        })
        print(f"  📝 New lesson: {lesson_text[:60]}")
    
    _save_lessons(lessons)
    entry = f"## {now[:16]}\n\n{text}\n"
    corrections.append(entry)
    _save_corrections(corrections)
    return True


def _extract_lesson(text: str) -> str:
    reply = _call_llm(f"The user corrected the AI. Extract one lesson: {text[:500]}")
    if reply and reply != "无":
        return reply[:100]
    patterns = [
        r"不要(.+?)[。，]?", r"别(.+?)[。，]?", r"应该(.+?)[。，]?",
        r"记住(.+?)[。，]?", r"正确的做法是(.+?)[。，]?",
        r"[！!](.+?)(?:[。，.!?]|$)",  # General: content after exclamation mark
        # English patterns
        r"don't (.+?)[.,!?]", r"never (.+?)[.,!?]",
        r"stop (.+?)[.,!?]", r"(?:remember|correct|right) (.+?)[.,!?]",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m and m.group(1):
            return f"User correction: {m.group(1)[:60].strip()}"
    return ""


def _similar(a: str, b: str) -> bool:
    wa = set(re.findall(r'[\u4e00-\u9fff]', a))
    wb = set(re.findall(r'[\u4e00-\u9fff]', b))
    if not wa or not wb:
        return False
    return len(wa & wb) / max(len(wa), len(wb)) > 0.3


# ==================== Persistence ====================

def _path(kind: str) -> str:
    os.makedirs(STORAGE_PATH, exist_ok=True)
    return os.path.join(STORAGE_PATH, kind)


def _load_lessons() -> dict:
    p = _path("lessons.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return {"lessons": []}


def _save_lessons(d):
    with open(_path("lessons.json"), 'w') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _load_corrections() -> list:
    p = _path("corrections.md")
    if os.path.exists(p):
        with open(p) as f:
            return [e.strip() for e in f.read().split("---") if e.strip()]
    return []


def _save_corrections(entries):
    lines = ["# Correction Log", "---"] + [e + "\n---" for e in entries[-50:]]
    with open(_path("corrections.md"), 'w') as f:
        f.write("\n".join(lines))


def get_rules_for_injection() -> str:
    lessons = _load_lessons()
    promoted = [l for l in lessons["lessons"] if l.get("promoted")]
    if promoted:
        lines = ["### ✅ Behavioral Rules (from user corrections)"]
        for l in promoted:
            lines.append(f"- {l['lesson']}")
        return "\n".join(lines)
    pending = [l for l in lessons["lessons"] if l.get("count", 0) >= 2 and not l.get("promoted")]
    if pending:
        lines = ["### ⚠️ Pending Rules"]
        for l in pending:
            lines.append(f"- {l['lesson']} ({l['count']} times)")
        return "\n".join(lines)
    return ""


def stats():
    lessons = _load_lessons()
    all_l = lessons["lessons"]
    promoted = [l for l in all_l if l.get("promoted")]
    learned = _load_learned_signals()
    active = _all_signals()
    
    print(f"\n📚 MOYU Learner")
    print("=" * 50)
    print(f"Total lessons: {len(all_l)} | Rules: {len(promoted)}")
    print(f"Trigger words: {len(active)} (seed {len(DEFAULT_SIGNALS)} + adaptive {len(learned)})")
    
    if learned:
        print(f"\n🧠 Adaptively learned trigger words:")
        for s in learned:
            print(f"  • {s}")
    
    for l in promoted:
        print(f"  ✅ [{l['count']} times] {l['lesson'][:60]}")
    for l in all_l:
        if not l.get("promoted"):
            print(f"  ⏳ [{l['count']} times] {l['lesson'][:60]}")
    print()

def signals():
    """Print active trigger words."""
    active = _all_signals()
    learned = _load_learned_signals()
    print(f"\n🔊 Active trigger words ({len(active)})")
    print("=" * 40)
    for s in DEFAULT_SIGNALS:
        print(f"  🧬 {s}")
    if learned:
        print(f"\n🧠 Adaptive:")
        for s in learned:
            print(f"  • {s}")
    print()

def demo() -> dict:
    """Return demo content for moyu_demo.py discovery engine."""
    return {
        "capability": 5,
        "title": "Learn from Corrections",
        "output": """🎯 5/6  DEMO
────────────────────────────────────
  You said: \"别再用A方案了，我们选了B\"
  → Agent learns: \"User wants no more mention of Plan A\"

  Second time: \"又提A方案，不是说了选B吗\"
  → count +1 → promotion check

  Third time same mistake: promoted to permanent rule
  → Auto-loaded on every wake → same mistake never repeated""",
    }

# ==================== Command Line ====================\n
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: detect | learn | stats | inject | signals")
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "detect":
        for h in detect_corrections(" ".join(sys.argv[2:])):
            print(f"  {h}")
    elif cmd == "learn":
        learn(" ".join(sys.argv[2:]))
        stats()
    elif cmd == "stats":
        stats()
    elif cmd == "inject":
        print(get_rules_for_injection())
    elif cmd == "signals":
        active = _all_signals()
        learned = _load_learned_signals()
        print(f"\n🔊 Active trigger words ({len(active)})")
        for s in DEFAULT_SIGNALS:
            mark = "🧬" if s in active else ""
            print(f"  {mark} {s}")
        if learned:
            print(f"\n🧠 Adaptive:")
            for s in learned:
                print(f"  • {s}")
