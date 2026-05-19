# Contributing to MOYU

MOYU is a zero-trust memory toolkit for AI Agents. We welcome contributions that align with our core principles:

- **Lightweight** — zero infrastructure, zero external services
- **Self-defending** — security as a built-in feature, not an afterthought
- **Practical** — solve real problems without over-engineering

## How to Contribute

### 1. Reporting Issues

Open a GitHub issue with:
- A clear description of the problem
- Steps to reproduce (if applicable)
- The version you're using (`moyu update` shows the current version)

### 2. Adding a New Injection Pattern

Injection patterns live in `moyu_toolkit/defense_toolkit/forensic_patterns_base64.json`.

Each pattern is a `[pattern_string, label]` pair, Base64-encoded:
- **Plain substring patterns**: `["ignore all previous", "rule_injection"]`
- **Regex patterns**: Prefix with `re:`, e.g. `["re:(forget|ignore)\\s+(all|previous)\\s+(instructions|rules)", "rule_injection"]`

To add a pattern:
1. Add your `[pattern, label]` pair to the list
2. Base64-encode it: `python3 -c "import base64; print(base64.b64encode(b'your pattern').decode())"`
3. Replace the plaintext version in the JSON with the Base64 string
4. Submit a PR

### 3. Adding a New Provider Detector

Provider detectors auto-detect which Agent is running (Hermes, Claude Code, etc.). They live in `context_manager.py` > `_scan_providers()`.

To add a new detector:

```python
# ── YourNewAgent ──
def _parse_your_agent():
    for base in _candidates(
        mac="~/path/to/data",
        win="%USERPROFILE%\\path\\to\\data",
    ):
        if not os.path.exists(base):
            continue
        try:
            # Parse session data, return:
            return dict(pct=..., total_tokens=..., context_length=...,
                        api_calls=..., likely_compressed=...)
        except Exception:
            continue
    return None
```

Then add it to the `detectors` list in the same function:

```python
detectors = [
    ("Hermes", _parse_hermes),
    ("Claude Code", _parse_claude),
    ("YourNewAgent", _parse_your_agent),
    # ...
]
```

### 4. Code Style

- Python 3.8+ compatible
- `snake_case` for functions and variables
- Private functions prefixed with `_`
- Docstrings for all public functions
- No external dependencies beyond those in `requirements.txt`

### 5. Testing

Run the existing test suite before submitting:

```bash
cd moyu_toolkit
python3 tests/test_all.py
```

If adding a new feature, include tests.

## PR Checklist

- [ ] Code compiles without errors
- [ ] Existing tests pass
- [ ] New tests added (if applicable)
- [ ] Documentation updated (if applicable)
- [ ] CHANGELOG.md entry added
