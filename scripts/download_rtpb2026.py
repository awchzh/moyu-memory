#!/usr/bin/env python3
"""RTPB2026 数据集下载器

从公开源拉取 RTPB2026 对抗测试语料库，缓存到本地。
数据不打包进 MOYU，按需下载。

用法：
    python3 download_rtpb2026.py              # 下载并缓存
    python3 download_rtpb2026.py --path-only  # 只打印缓存路径
"""

import sys
import os
import json
import hashlib
import urllib.request
import tarfile
import tempfile
import shutil

# ── 数据集源 ──
# RTPB2026 来自 Safety-Prompts 项目及补充对抗样本
# 主源：https://github.com/thu-coai/Safety-Prompts
# 对抗子集：组合中英文注入 + 编码绕过 + 越狱变体

SOURCES = {
    "safety_prompts_cn": {
        "url": "https://raw.githubusercontent.com/thu-coai/Safety-Prompts/main/data/prompt_injection_zh.json",
        "size_estimate": "~2000 samples",
    },
    "safety_prompts_en": {
        "url": "https://raw.githubusercontent.com/thu-coai/Safety-Prompts/main/data/prompt_injection_en.json",
        "size_estimate": "~2000 samples",
    },
}

CACHE_DIR = os.path.expanduser("~/.cache/moyu/rtpb2026")
MANIFEST_FILE = os.path.join(CACHE_DIR, "manifest.json")


def _ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cached_path(name: str) -> str:
    return os.path.join(CACHE_DIR, f"{name}.json")


def download_source(name: str, url: str, force: bool = False) -> dict:
    """Download a single source file and cache it."""
    cache_path = _cached_path(name)
    if os.path.exists(cache_path) and not force:
        with open(cache_path) as f:
            return json.load(f)

    print(f"  ⬇️  Downloading {name}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MOYU/2.5.2"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            data = json.loads(raw)
            with open(cache_path, "w") as f:
                json.dump(data, f, ensure_ascii=False)
            print(f"     ✅ {len(data)} samples cached")
            return data
    except Exception as e:
        print(f"     ⚠️  Failed: {e}")
        return []


def _extract_injection_samples(data: list, source_label: str) -> list:
    """Extract injection samples from Safety-Prompts format.
    
    Safety-Prompts format: list of {id, prompt, type, ...}
    We extract the 'prompt' field and label with the 'type' or source.
    """
    samples = []
    for item in data:
        if isinstance(item, dict):
            prompt = item.get("prompt", "") or item.get("text", "") or ""
            label = item.get("type", "") or item.get("label", "") or source_label
            if prompt and len(prompt) > 3:
                samples.append({"text": prompt, "label": label, "source": source_label})
        elif isinstance(item, str):
            if len(item) > 3:
                samples.append({"text": item, "label": source_label, "source": source_label})
    return samples


def download_all(force: bool = False) -> dict:
    """Download all sources and aggregate into a single dataset."""
    _ensure_cache()
    
    all_samples = []
    source_stats = {}
    
    for name, info in SOURCES.items():
        data = download_source(name, info["url"], force)
        samples = _extract_injection_samples(data, name)
        all_samples.extend(samples)
        source_stats[name] = {"expected": info["size_estimate"], "got": len(samples)}
    
    # Add built-in adversarial samples if available
    builtin_path = os.path.join(os.path.dirname(__file__), "..", "moyu_toolkit", "defense_toolkit", "forensic_patterns.json")
    if os.path.exists(builtin_path):
        with open(builtin_path) as f:
            patterns = json.load(f)
        # Generate samples from pattern labels for positive control
        source_stats["builtin_patterns"] = {"got": len(patterns)}
    
    # Write manifest
    manifest = {
        "downloaded_at": __import__("time").time(),
        "total_samples": len(all_samples),
        "sources": source_stats,
        "files": {name: info["url"] for name, info in SOURCES.items()},
    }
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    # Write aggregated dataset
    dataset_path = os.path.join(CACHE_DIR, "rtpb2026_aggregated.json")
    with open(dataset_path, "w") as f:
        json.dump(all_samples, f, ensure_ascii=False)
    
    print(f"\n  📦 Total: {len(all_samples)} samples from {len(SOURCES)} sources")
    print(f"  📍 Cached at: {dataset_path}")
    
    return manifest


def get_dataset_path() -> str:
    """Get path to cached dataset, downloading if needed."""
    dataset_path = os.path.join(CACHE_DIR, "rtpb2026_aggregated.json")
    if not os.path.exists(dataset_path):
        print("📡 Dataset not cached. Downloading...")
        download_all()
    return dataset_path


def get_manifest() -> dict:
    """Read cached manifest."""
    if os.path.exists(MANIFEST_FILE):
        with open(MANIFEST_FILE) as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    if "--path-only" in sys.argv:
        path = get_dataset_path()
        print(path)
    elif "--status" in sys.argv:
        m = get_manifest()
        if m:
            print(f"📊 RTPB2026 Cache Status")
            print(f"   Samples: {m.get('total_samples', '?')}")
            print(f"   Downloaded: {__import__('time').strftime('%Y-%m-%d %H:%M', __import__('time').localtime(m.get('downloaded_at', 0)))}")
            print(f"   Location: {CACHE_DIR}")
        else:
            print("📭 Not cached yet. Run: python3 download_rtpb2026.py")
    else:
        download_all()
