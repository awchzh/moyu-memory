"""custom_rules.py — Self-updating custom security rules for MOYU.

Stores user-taught rules in custom_rules.json, checked before built-in patterns.
Designed so you can tell me "this pattern should be blocked" and it takes effect
immediately — no code changes, no version release needed.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from moyu_toolkit._moyu_paths import get_default_storage

_RULES_PATH = os.path.join(get_default_storage(), "custom_rules.json")


def _ensure_rules_file():
    """Lazy init: create empty rules file if not exists."""
    os.makedirs(os.path.dirname(_RULES_PATH), exist_ok=True)
    if not os.path.exists(_RULES_PATH):
        with open(_RULES_PATH, "w") as f:
            json.dump({"rules": [], "created_at": datetime.now().isoformat()}, f)


def _load_rules() -> list:
    """Load all custom rules. Returns list of {pattern, note, added_at}."""
    _ensure_rules_file()
    try:
        with open(_RULES_PATH) as f:
            data = json.load(f)
        return data.get("rules", [])
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save_rules(rules: list):
    """Save rules list to file."""
    _ensure_rules_file()
    with open(_RULES_PATH, "w") as f:
        json.dump({"rules": rules, "updated_at": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)


def add_rule(pattern: str, note: str = ""):
    """Add a new custom security rule from user correction."""
    rules = _load_rules()
    
    # Check if similar pattern already exists
    for rule in rules:
        if rule["pattern"] == pattern:
            rule["note"] = note
            rule["updated_at"] = datetime.now().isoformat()
            _save_rules(rules)
            return False  # Updated existing
    
    rules.append({
        "pattern": pattern,
        "note": note,
        "added_at": datetime.now().isoformat(),
    })
    _save_rules(rules)
    return True  # New rule added


def check_custom(content: str) -> list:
    """Check content against custom rules.
    
    Returns list of matched pattern descriptions (empty = safe).
    Run BEFORE the built-in content gate — custom rules get first priority.
    """
    # Check whitelist first — if content matches whitelist, skip all rules
    if check_whitelist(content):
        return []
    
    matches = []
    for rule in _load_rules():
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        try:
            if re.search(pattern, content, re.IGNORECASE):
                matches.append(rule.get("note", pattern))
        except re.error:
            pass  # Skip invalid patterns silently
    return matches


def analyze_and_learn(text: str) -> dict:
    """Analyze user correction text and determine if it's a security rule.
    
    Returns dict with:
      - learned: bool — whether a rule was added
      - rule: str — the pattern extracted (if any)
      - note: str — human-readable note
      - message: str — what happened
    """
    text_lower = text.lower()
    
    # Detect if this is about security/injection/blocking
    security_keywords = [
        "规则", "拦截", "阻断", "安全", "注入", "放过", "不应该",
        "rule", "block", "inject", "security", "bypass", "bypasses",
        "绕过", "没拦到", "没检测", "漏了",
    ]
    is_security = any(kw in text_lower for kw in security_keywords)
    
    if not is_security:
        return {
            "learned": False,
            "message": "Not a security rule — stored as regular memory instead.",
        }
    
    # Try to extract a pattern from the correction
    # Pattern: "X应该被拦截" / "X is blocked" / terms in quotes
    quoted = re.findall(r'[""「]([^""」]+)[""」]', text)
    if quoted:
        import re as re_module
        # Escape the quoted term and use it as a pattern
        raw_pattern = quoted[0]
        pattern = re_module.escape(raw_pattern)
        note = f"Custom rule: block '{raw_pattern}'"
        is_new = add_rule(pattern, f"Custom rule: '{raw_pattern}' — learned from: {text[:100]}")
        
        return {
            "learned": True,
            "rule": pattern,
            "note": note,
            "message": f"{'Added' if is_new else 'Updated'} custom security rule: [{raw_pattern}]",
        }
    
    # No quoted term found — try to extract key terms
    terms = re.findall(r'\b(forget|ignore|skip|override|dan|jailbreak)\b', text_lower)
    if terms:
        term = terms[0]
        pattern = re.escape(term)
        is_new = add_rule(pattern, f"Custom rule: block '{term}' related patterns")
        return {
            "learned": True,
            "rule": pattern,
            "note": f"Block '{term}'",
            "message": f"{'Added' if is_new else 'Updated'} custom pattern: [{term}]",
        }
    
    return {
        "learned": False,
        "message": "Could not extract a clear pattern. Try quoting the term: \"forget instructions\"",
    }


def list_rules() -> list:
    """List all custom rules for display."""
    return _load_rules()


def stats() -> dict:
    """Return summary stats about custom rules."""
    rules = _load_rules()
    return {
        "count": len(rules),
        "rules": [{"pattern": r.get("pattern", "?"), "note": r.get("note", "")[:60]} for r in rules],
    }


# ── False-positive learning / Whitelist ──────────────────────────────────

def _load_whitelist() -> list:
    """Load whitelist entries from custom_rules.json."""
    _ensure_rules_file()
    try:
        with open(_RULES_PATH) as f:
            data = json.load(f)
        return data.get("whitelist", [])
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def check_whitelist(content: str) -> bool:
    """Check if content matches any whitelist pattern. True = whitelisted (skip block)."""
    for item in _load_whitelist():
        pattern = item.get("pattern", "")
        if not pattern:
            continue
        try:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        except re.error:
            pass
    return False


def add_whitelist(pattern: str, note: str = ""):
    """Add a whitelist pattern. Matching content passes content_scan.

    Returns True if newly added, False if updated (deduped).
    """
    _ensure_rules_file()
    with open(_RULES_PATH) as f:
        data = json.load(f)
    whitelist = data.get("whitelist", [])
    # Dedup — update existing entry if same pattern
    for w in whitelist:
        if w["pattern"] == pattern:
            w["note"] = note
            w["updated_at"] = datetime.now().isoformat()
            with open(_RULES_PATH, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return False
    whitelist.append({
        "pattern": pattern,
        "note": note,
        "added_at": datetime.now().isoformat(),
    })
    data["whitelist"] = whitelist
    with open(_RULES_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True


def list_whitelist() -> list:
    """List all whitelist entries."""
    return _load_whitelist()


# ── Rule removal ────────────────────────────────────────────────────────

def remove_rule(pattern_text: str) -> tuple:
    """Remove all rules whose pattern contains pattern_text.

    Returns (found, count) — whether any were found, and how many removed.
    """
    rules = _load_rules()
    if not rules:
        return (False, 0)
    new_rules = [r for r in rules if pattern_text not in r.get("pattern", "")]
    removed = len(rules) - len(new_rules)
    if removed > 0:
        _save_rules(new_rules)
    return (removed > 0, removed)
