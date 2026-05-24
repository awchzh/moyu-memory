#!/usr/bin/env python3
"""
pii_redactor.py — MOYU PII Detection & Redaction

Detects and redacts personal identifiable information (PII) from memory content
before it enters the knowledge graph or persistent storage.

中文 + English coverage via regex patterns. Zero external dependencies.

Usage:
    redacted_text, types_detected = redact(text)
    has_pii, types_detected = scan(text)
"""

import re
from typing import Tuple, List

# ── 中文 PII ───────────────────────────────────────────────

_CN_PATTERNS = [
    # 手机号: 138-1234-5678 / 13812345678
    (r"(?<!\d)(1[3-9]\d)\s?[-–—]?\s?(\d{4})\s?[-–—]?\s?(\d{4})(?!\d)",
     lambda m: f"{m.group(1)}****{m.group(3)}",
     "phone_cn"),

    # 身份证: 110101199001011234 → 1101**********1234
    (r"(?<!\d)(\d{4})\d{10}(\d{4})(?!\d)",
     lambda m: f"{m.group(1)}**********{m.group(2)}",
     "id_card_cn"),

    # 身份证带 x/X: 11010119900101123X
    (r"(?<!\d)(\d{4})\d{9}(\d{4}[\dXx])(?!\d)",
     lambda m: f"{m.group(1)}*********{m.group(2).upper()}",
     "id_card_cn"),

    # 银行卡: 6217001234567890123 → 6217***********0123
    (r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)",
     lambda m: f"{m.group(1)}***********{m.group(2)}",
     "bank_card_cn"),

    # 固定电话: 010-8888-6666 / 02188886666
    (r"(?<!\d)(0\d{2,3})[-–—\s]?(\d{4})\d{4}(?!\d)",
     lambda m: f"{m.group(1)}-{m.group(2)}****",
     "landline_cn"),
]

# ── 英文/通用 PII ──────────────────────────────────────────

_EN_PATTERNS = [
    # Email: alice@example.com → a***@example.com
    (r"([\w.+-]+)@([\w-]+\.[\w.]+)",
     lambda m: f"{m.group(1)[0]}***@{m.group(2)}" if len(m.group(1)) > 1 else f"*@{m.group(2)}",
     "email"),

    # International phone with + prefix: +1-212-555-1212 / +44 20 7946 0958 / +852 9123 4567
    (r"(?<!\d)(\+\d{1,3})[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{3,10}(?!\d)",
     lambda m: f"{m.group(1)}-***-{m.group(0)[-4:]}",
     "phone_intl"),

    # US local format with parentheses: (212) 555-1212
    (r"\(\d{3}\)\s?\d{3}[-.\s]?\d{4}",
     lambda m: "(***) ***-" + m.group(0)[-4:],
     "phone_intl"),

    # 信用卡: 4111-1111-1111-1111 / 4111111111111111
    (r"(?<!\d)(\d{4})[–—\s]?(\d{4})[–—\s]?(\d{4})[–—\s]?(\d{4})(?!\d)",
     lambda m: f"****-****-****-{m.group(4)}",
     "credit_card"),

    # IP 地址: 192.168.1.1 → 192.168.*.*
    (r"(?<!\d)(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?!\d)",
     lambda m: f"{m.group(1)}.{m.group(2)}.***.***" if int(m.group(1)) <= 255 else m.group(0),
     "ip_address"),

    # US SSN: 123-45-6789 → ***-**-6789
    (r"(?<!\d)(\d{3})[-–—](\d{2})[-–—](\d{4})(?!\d)",
     lambda m: f"***-**-{m.group(3)}",
     "ssn"),

    # API Key: sk-xxx / ark-xxx / AKIDxxx / ghp_xxx / gho_xxx / ghu_xxx → 保留前后4位
    (r"(?<![a-zA-Z0-9])((?:sk-|ark-|AKID|AKTP|ghp_|gho_|ghu_)[a-zA-Z0-9_-]{16,})(?![a-zA-Z0-9_-])",
     lambda m: m.group(1)[:4] + "***" + m.group(1)[-4:],
     "api_key"),
]


def _apply_patterns(text: str, patterns: list) -> Tuple[str, List[str]]:
    """Apply a list of (regex, replacement_fn, label) to text.
    Returns (redacted_text, detected_types).
    """
    detected = []
    for pattern, repl_fn, label in patterns:
        def _make_replacer(fn, lbl):
            """Capture fn and lbl in closure so each pattern has its own."""
            def replacer(m):
                if lbl not in detected:
                    detected.append(lbl)
                return fn(m)
            return replacer

        try:
            text = re.sub(pattern, _make_replacer(repl_fn, label), text)
        except Exception:
            pass
    return text, detected


# ═══════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════

def scan(text: str) -> Tuple[bool, List[str]]:
    """Scan text for PII without modifying it.
    
    Returns:
        (has_pii, types_detected) — e.g. (True, ["phone_cn", "email"])
    """
    _, detected_cn = _apply_patterns(text, _CN_PATTERNS)
    _, detected_en = _apply_patterns(text, _EN_PATTERNS)
    all_types = detected_cn + [t for t in detected_en if t not in detected_cn]
    return len(all_types) > 0, all_types


def redact(text: str) -> Tuple[str, List[str]]:
    """Redact PII in text by replacing matched patterns with masked versions.
    
    Returns:
        (redacted_text, types_redacted) — e.g. ("my phone is 138****5678", ["phone_cn"])
    
    Note: returns the original text if no PII found (no copy overhead for common case).
    """
    text_cn, detected_cn = _apply_patterns(text, _CN_PATTERNS)
    text_en, detected_en = _apply_patterns(text_cn, _EN_PATTERNS)
    all_types = detected_cn + [t for t in detected_en if t not in detected_cn]
    
    if not all_types:
        return text, []
    
    return text_en, all_types


def demo() -> dict:
    """Return demo output for moyu_demo.py."""
    tests = [
        "我的手机号是13812345678",
        "我的身份证是110101199001011234",
        "银行卡号6217001234567890123",
        "email me at alice@example.com",
        "信用卡4111111111111111",
        "IP是192.168.1.1",
        "这是我男朋友13412345678",
        "美国电话+1-212-555-1212",
        "英国电话+44 20 7946 0958",
        "日本电话+81 90-1234-5678",
        "香港电话+852 9123 4567",
        "带括号的美式(212) 555-1212",
        "豆包API KEY：ark-424a098e-5717-4529-a560-85e432fef418-dec3f",
        "OpenAI Key: sk-proj-abcdefghijklmnopqrstuvwx",
        "GitHub token: ghp_abcdefghijklmnopqrstuvwxyz123456",
        # Clean — should not trigger
        "我今天工作很忙",
        "项目版本号是2.3.0",
    ]
    lines = []
    for t in tests:
        r, types = redact(t)
        changed = "⚠️" if types else "✅"
        lines.append(f"  {changed} {t}")
        if types:
            types_str = ", ".join(types)
            lines.append(f"       → {r}  [{types_str}]")
    return {
        "capability": 17,
        "title": "PII Redactor",
        "output": "🔏 17/17  PII Detection & Redaction\n" +
                  "────────────────────────────────────\n" +
                  "\n".join(lines) + "\n\n" +
                  "  Zero external dependencies. Runs before memory is written.\n" +
                  "  PII never enters the knowledge graph.",
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        result, types = redact(text)
        if types:
            print(f"🔏 PII detected: {', '.join(types)}")
            print(f"  Original: {text}")
            print(f"  Redacted: {result}")
        else:
            print(f"✅ No PII detected in: {text}")
    else:
        # Demo mode
        d = demo()
        print(d["output"])
