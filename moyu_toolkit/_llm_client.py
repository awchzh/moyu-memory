#!/usr/bin/env python3
"""MOYU unified LLM client — single source of truth for all LLM calls.

v2.6.1 — Consolidated key resolution, API call, and model auto-correction
that were previously copy-pasted across 6 modules.

Key resolution priority (top wins):
  1. config.yaml → api.api_key
  2. MOYU_LLM_BASE_URL env var (overrides config.yaml base_url)
  3. MOYU_API_KEY env var
  4. ~/.hermes/.env → DEEPSEEK_API_KEY
  5. DEEPSEEK_API_KEY env var (lowest)"""

import os
from typing import Tuple, List, Dict


def resolve_llm_config() -> Tuple[str, str, str]:
    """Resolve LLM API configuration: (api_key, base_url, model).

    Auto-correction:
      - If base_url points to DeepSeek but model starts with 'gpt-',
        model is auto-corrected to 'deepseek-chat'.
    """
    api_key, base_url, model = "", "https://api.openai.com/v1", "gpt-4o-mini"

    # Step 1: Load config.yaml
    try:
        import yaml as _yaml
        from _moyu_paths import get_config_path

        cfg_path = get_config_path()
        if os.path.exists(cfg_path):
            with open(cfg_path) as _f:
                cfg = _yaml.safe_load(_f) or {}
            api_cfg = cfg.get("api", {})
            api_key = api_cfg.get("api_key", "") or ""
            base_url = (api_cfg.get("base_url", "https://api.openai.com/v1") or "").rstrip("/")
            model = api_cfg.get("chat_model", "gpt-4o-mini") or "gpt-4o-mini"
    except Exception:
        pass

    # Step 2: MOYU_LLM_BASE_URL env var (overrides config.yaml base_url)
    env_base_url = os.environ.get("MOYU_LLM_BASE_URL", "") or ""
    if env_base_url:
        base_url = env_base_url.rstrip("/")

    # Step 4: MOYU_API_KEY env var
    env_key = os.environ.get("MOYU_API_KEY", "") or ""
    if env_key:
        api_key = env_key

    # Step 5: ~/.hermes/.env → DEEPSEEK_API_KEY
    if not api_key or api_key == "your-api-key-here":
        try:
            env_path = os.path.expanduser("~/.hermes/.env")
            if os.path.exists(env_path):
                with open(env_path) as _f:
                    for _line in _f:
                        if _line.startswith("DEEPSEEK_API_KEY="):
                            val = _line.strip().split("=", 1)[1].strip()
                            if val:
                                api_key = val
                            break
        except Exception:
            pass

    # Step 6: DEEPSEEK_API_KEY env var (lowest priority)
    if not api_key or api_key == "your-api-key-here":
        env_key2 = os.environ.get("DEEPSEEK_API_KEY", "") or ""
        if env_key2:
            api_key = env_key2

    # Auto-correct: DeepSeek URL + gpt- model name → deepseek-chat
    if "deepseek.com" in base_url and model.startswith("gpt-"):
        model = "deepseek-chat"

    return api_key, base_url, model


def call_llm_api(
    api_key: str,
    base_url: str,
    model: str,
    messages: List[Dict],
    temperature: float = 0.1,
    max_tokens: int = 500,
    timeout: int = 15,
) -> str:
    """Make a single LLM API call. Returns response text, or empty string on failure."""
    if not api_key or api_key == "your-api-key-here":
        return ""

    try:
        import requests as _rq

        resp = _rq.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        return ""
    except Exception:
        pass
    return ""
