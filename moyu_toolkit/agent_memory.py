#!/usr/bin/env python3
"""
agent_memory.py — MOYU Vector Memory Engine

Core Features:
- TEMPR multi-strategy retrieval (semantic + BM25 keyword + time decay)
- FastEmbed local embeddings (auto-fallback to n-gram)
- Hybrid score_and_rank with entity boost + semantic gate
- Adaptive BM25 parameters (dynamic sigmoid by query length)
- MD5 deduplication (in-library + in-batch)
- Optional spaCy entity extraction (auto-fallback to regex)

Usage:
    python3 agent_memory.py index      # Batch index all memories
    python3 agent_memory.py search q   # Search relevant memories
    python3 agent_memory.py stats      # Show index status
"""

import json
import os
import math
import re
import time
import collections
import hashlib
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# ==================== Optional Security Modules ====================

# User isolation (optional — config.yaml > security.isolation.enabled)
_ISOLATION = None
def _get_isolation():
    global _ISOLATION
    if _ISOLATION is None:
        try:
            from moyu_toolkit.defense_toolkit.isolation import get_storage_path, get_user
            _ISOLATION = {"get_storage_path": get_storage_path, "get_user": get_user}
        except Exception:
            _ISOLATION = False
    return _ISOLATION or None

# Encryption (optional — config.yaml > security.encryption.enabled + password)
_ENCRYPTION = None
def _get_encryption():
    global _ENCRYPTION
    if _ENCRYPTION is None:
        try:
            from moyu_toolkit.defense_toolkit.encrypt import encrypt_bytes, decrypt_bytes, is_encrypted
            _ENCRYPTION = {"encrypt": encrypt_bytes, "decrypt": decrypt_bytes, "is_encrypted": is_encrypted}
        except Exception:
            _ENCRYPTION = False
    return _ENCRYPTION or None

def _get_encryption_password() -> str:
    """Read encryption password from env var MOYU_ENCRYPTION_PASSWORD only.
    Plaintext passwords in config.yaml are no longer supported for security reasons."""
    return os.environ.get("MOYU_ENCRYPTION_PASSWORD", "")

# ==================== SQLite FTS5 ====================
from moyu_toolkit.agent_memory_sqlite import _fts_search

# ==================== Optional Dependencies ====================

# Try FastEmbed (local ONNX, no GPU needed)
_FASTEMBED_AVAILABLE = False
_fastembed_model = None
_fastembed_failed = False
def _check_fastembed():
    global _FASTEMBED_AVAILABLE, _fastembed_failed
    if not _FASTEMBED_AVAILABLE and not _fastembed_failed:
        try:
            from fastembed import TextEmbedding
            _FASTEMBED_AVAILABLE = True
        except ImportError:
            _fastembed_failed = True
        except Exception:
            _fastembed_failed = True
    return _FASTEMBED_AVAILABLE

# Try spaCy for entity extraction (auto-downloads en_core_web_sm)
_SPACY_AVAILABLE = False
_nlp = None
def _check_spacy():
    global _SPACY_AVAILABLE
    if not _SPACY_AVAILABLE:
        try:
            import spacy
            _SPACY_AVAILABLE = True
        except ImportError:
            pass
    return _SPACY_AVAILABLE

# ==================== Configuration ====================

from moyu_toolkit._moyu_paths import get_config_path
from moyu_toolkit._storage import storage
STORAGE_PATH = os.path.dirname(storage.path("."))

# Frequency guard — imported from frequency_guard.py

# Default retrieval weights — overridden by config.yaml memory.weights
DEFAULT_WEIGHTS = {"semantic": 0.5, "keyword": 0.3, "recency": 0.2, "entity": 0.05}


def _get_retrieval_weights() -> dict:
    """Read retrieval weights from config.yaml, falling back to DEFAULT_WEIGHTS."""
    config = _load_config()
    cfg_w = config.get("memory", {}).get("weights", {})
    weights = {}
    for dim in ["semantic", "keyword", "recency", "entity"]:
        val = cfg_w.get(dim)
        if isinstance(val, (int, float)) and val >= 0:
            weights[dim] = float(val)
        else:
            weights[dim] = DEFAULT_WEIGHTS[dim]
    return weights

# Source weight map — agent_confirmed facts are equal to user; system/default discounted
SOURCE_WEIGHTS = {
    "user": 1.0,
    "agent_confirmed": 1.0,
    "system": 0.85,
    "agent": 0.85,
}

# Temporal signal keywords — detect time intent in queries
TEMPORAL_SIGNALS = {
    "past": ["上次", "之前", "上周", "昨天", "以前", "过去", "上回", "前段时间", "前一阵",
             "last", "previous", "before", "yesterday", "earlier", "prior", "ago"],
    "future": ["计划", "接下来", "下次", "以后", "打算", "想要", "将要", "即将",
               "plan", "next", "future", "upcoming", "will", "going to"],
    "recent": ["最近", "近期", "刚刚", "这几天", "近来", "近日",
               "recent", "lately", "just", "recently"],
}
RRF_K = 60
SEMANTIC_GATE = 0.08  # Drop results below this semantic similarity
ENTITY_BOOST_WEIGHT = 0.5  # Max entity boost added to score

# n-gram fallback configuration
NGRAM_N = 3
NGRAM_DIM = 256
MAX_TEXT_LENGTH = 512

# FastEmbed configuration
FASTEMBED_DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"  # 384-dim, Chinese + English, fast


def _storage_path(*parts: str) -> str:
    """Get storage path, optionally with user isolation.
    Safe from path traversal — all paths are resolved relative to STORAGE_PATH."""
    base = STORAGE_PATH
    iso = _get_isolation()
    if iso:
        base = iso["get_storage_path"](base)
    path = os.path.join(base, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _load_config() -> dict:
    """Load config.yaml (if exists). On parse failure, returns conservative defaults."""
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            # Config corrupted — return conservative (safer) defaults
            return {
                "security": {"isolation": {"enabled": True}},
                "alert": {"channel": "none"},
            }
    return {}


def _get_embedding_api() -> Tuple[str, str, str]:
    """Get embedding API configuration"""
    config = _load_config()
    api_cfg = config.get("api", {})
    base_url = api_cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
    api_key = api_cfg.get("api_key", "") or os.environ.get("MOYU_API_KEY", "")
    model = api_cfg.get("embedding_model", "text-embedding-3-small")
    chat_url = base_url + "/embeddings"
    return api_key, chat_url, model


def _get_fastembed_model():
    """Lazy-load FastEmbed model (thread-safe singleton)"""
    global _fastembed_model, _fastembed_failed
    if _fastembed_model is None and _check_fastembed():
        try:
            from fastembed import TextEmbedding
            config = _load_config()
            model_name = config.get("embedding", {}).get("fastembed_model", FASTEMBED_DEFAULT_MODEL)
            # Use HuggingFace mirror for Chinese users
            import os as _hf_os
            if not _hf_os.environ.get("HF_ENDPOINT"):
                _hf_os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
            _fastembed_model = TextEmbedding(model_name=model_name, cache_dir=_hf_os.path.expanduser("~/.cache/huggingface"))
        except Exception:
            _fastembed_failed = True
            return None
    return _fastembed_model


def _get_spacy_nlp():
    """Lazy-load spaCy model (auto-download if missing)"""
    global _nlp
    if _nlp is None and _check_spacy():
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            try:
                from spacy.cli import download
                download("en_core_web_sm")
                _nlp = spacy.load("en_core_web_sm")
            except Exception:
                pass
    return _nlp


# ==================== Vector Operations ====================

def cosine_similarity(vec1: list, vec2: list) -> float:
    a, b = np.array(vec1), np.array(vec2)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


# ==================== Entity Extraction ====================

def _extract_entities(text: str) -> list:
    """Extract entities from text. Uses spaCy if available, regex fallback."""
    nlp = _get_spacy_nlp()
    if nlp:
        doc = nlp(text)
        entities = set()
        for ent in doc.ents:
            if ent.label_ in ("PERSON", "ORG", "GPE", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW"):
                entities.add(ent.text.lower().strip())
        # Also extract noun phrases as potential entities
        for chunk in doc.noun_chunks:
            text_lower = chunk.text.lower().strip()
            if len(text_lower) > 2 and not text_lower.startswith(("the ", "a ", "an ")):
                entities.add(text_lower)
        return list(entities)

    # Regex fallback: multi-word capitalized sequences, quoted terms
    entities = set()
    # Multi-word capitalized: "John Smith", "San Francisco"
    for m in re.finditer(r'[A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)*', text):
        entities.add(m.group(0).lower())
    # Quoted terms: "machine learning"
    for m in re.finditer(r'"([^"]{2,})"', text):
        entities.add(m.group(1).lower())
    # Chinese proper nouns (capitalized or quoted not available in CJK)
    for m in re.finditer(r'「([^」]{2,})」', text):
        entities.add(m.group(1))
    return list(entities)


def _extract_entities_batch(texts: list) -> list:
    """Batch entity extraction (for bulk operations)."""
    nlp = _get_spacy_nlp()
    if nlp and len(texts) > 1:
        try:
            results = []
            for doc in nlp.pipe(texts, batch_size=32):
                entities = set()
                for ent in doc.ents:
                    if ent.label_ in ("PERSON", "ORG", "GPE", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW"):
                        entities.add(ent.text.lower().strip())
                for chunk in doc.noun_chunks:
                    t = chunk.text.lower().strip()
                    if len(t) > 2 and not t.startswith(("the ", "a ", "an ")):
                        entities.add(t)
                results.append(list(entities))
            return results
        except Exception:
            pass
    return [_extract_entities(t) for t in texts]


# ==================== TEMPR Multi-Strategy Retrieval ====================

def _get_bm25_params(query_words: list) -> tuple:
    """Adaptive BM25 sigmoid parameters based on query length.
    Short queries: more selective. Long queries: more lenient."""
    n = len(query_words)
    if n <= 3:
        return 5.0, 0.7    # midpoint, steepness
    elif n <= 6:
        return 7.0, 0.6
    elif n <= 9:
        return 9.0, 0.5
    elif n <= 15:
        return 10.0, 0.5
    return 12.0, 0.5


def _bm25_score(query_words: list, doc_words: list,
                avg_len: float, doc_len: float,
                doc_freq: dict, total_docs: int,
                k1=1.5, b=0.75) -> float:
    score = 0.0
    for qw in query_words:
        if qw not in doc_freq or doc_freq[qw] == 0:
            continue
        idf = math.log((total_docs - doc_freq[qw] + 0.5) / (doc_freq[qw] + 0.5) + 1.0)
        tf = doc_words.count(qw)
        score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_len)))
    return score


def _normalize_bm25(raw_bm25: float, query_words: list) -> float:
    """Sigmoid normalize BM25 score with adaptive parameters."""
    midpoint, steepness = _get_bm25_params(query_words)
    return 1.0 / (1.0 + math.exp(-steepness * (raw_bm25 - midpoint)))


def _build_bm25_index(summaries: list) -> tuple:
    tokenized, word_df, total_len = [], collections.defaultdict(int), 0
    for s in summaries:
        words = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', s.lower())
        tokenized.append(words)
        total_len += len(words)
        for w in set(words):
            word_df[w] += 1
    avg_len = total_len / max(len(summaries), 1)
    return tokenized, dict(word_df), avg_len


# ==================== score_and_rank — Hybrid Scoring ====================

def score_and_rank(semantic_scores: list, bm25_norm_scores: list,
                   recency_scores: list, entity_boosts: list,
                   top_k: int, has_real_embeddings: bool = True,
                   source_weights: list = None,
                   connectivity_bonuses: dict = None,
                   retrieval_weights: dict = None) -> List[Tuple[float, int]]:
    """Hybrid scoring: semantic gate → weighted fusion → sort.
    
    - Semantic gate only applies when has_real_embeddings=True (FastEmbed/API).
      When using n-gram fallback, semantic scores are meaningless, so the gate
      is bypassed.
    - source_weights: per-entry weight from SOURCE_WEIGHTS map (1.0 for user/agent_confirmed).
    - connectivity_bonuses: cross-memory entity linking boost.
    - retrieval_weights: configurable weights from config.yaml memory.weights.
      If None, defaults from DEFAULT_WEIGHTS are used.
    """
    if retrieval_weights is None:
        retrieval_weights = DEFAULT_WEIGHTS.copy()
    
    w_sem = retrieval_weights.get("semantic", 0.5)
    w_bm25 = retrieval_weights.get("keyword", 0.3)
    w_rec = retrieval_weights.get("recency", 0.2)
    w_ent = retrieval_weights.get("entity", 0.0)
    weight_sum = w_sem + w_bm25 + w_rec + w_ent
    if weight_sum <= 0:
        weight_sum = 1.0  # prevent division by zero
    scored = []
    for i in range(len(semantic_scores)):
        sem = semantic_scores[i]
        # Only gate when using real embeddings (n-gram has no semantic signal)
        if has_real_embeddings and sem < SEMANTIC_GATE:
            continue
        bm25 = bm25_norm_scores[i]
        rec = recency_scores[i]
        ent = entity_boosts[i] if i < len(entity_boosts) else 0.0
        
        raw = sem * w_sem + bm25 * w_bm25 + rec * w_rec + ent * w_ent
        
        # Source weight: agent_confirmed = user = 1.0, system/agent = 0.85
        if source_weights and i < len(source_weights):
            raw *= source_weights[i]
        
        # Cross-memory entity connectivity bonus (per-result, after weighting)
        # This is separate from entity_boosts (which rewards query-entity overlap)
        max_possible = weight_sum + ENTITY_BOOST_WEIGHT
        normalized = min(raw / max_possible, 1.0)
        scored.append((normalized, i))
    
    scored.sort(key=lambda x: -x[0])
    ranked = scored[:top_k]
    
    # Apply connectivity bonuses to ranked results (post-sort, additive)
    if connectivity_bonuses:
        boosted = []
        for norm, i in ranked:
            bonus = connectivity_bonuses.get(i, 0.0)
            boosted.append((min(norm + bonus, 1.0), i))
        boosted.sort(key=lambda x: -x[0])
        return boosted[:top_k]
    
    return ranked


# ==================== Embedding ====================

def _get_fastembed_embedding(text: str) -> Optional[list]:
    """Get embedding via FastEmbed (local ONNX, no API key needed)."""
    model = _get_fastembed_model()
    if model is None:
        return None
    try:
        text_clean = text.replace("\n", " ")[:MAX_TEXT_LENGTH]
        embeddings = list(model.embed(text_clean))
        if embeddings:
            return embeddings[0].tolist()
    except Exception:
        pass
    return None


def _get_ngram_embedding(text: str) -> list:
    text = text[:MAX_TEXT_LENGTH]
    ngrams = set()
    for i in range(len(text) - NGRAM_N + 1):
        ngrams.add(abs(hash(text[i:i+NGRAM_N])) % NGRAM_DIM)
    vec = [0.0] * NGRAM_DIM
    for idx in ngrams:
        vec[idx] = 1.0
    return vec


def get_embedding(text: str, is_query: bool = False) -> Optional[list]:
    """Get text embedding with multi-level fallback:
    1. FastEmbed (local ONNX, no API key)
    2. API-based embedding (if configured)
    3. n-gram hash embedding (always works)
    """
    text = text[:MAX_TEXT_LENGTH]
    
    # Level 1: FastEmbed (best local quality)
    if _check_fastembed():
        vec = _get_fastembed_embedding(text)
        if vec is not None:
            return vec
    
    # Level 2: API-based (if configured with a real key)
    api_key, url, model = _get_embedding_api()
    if api_key and api_key not in ("your-api-key-here", ""):
        try:
            import requests
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"input": text, "model": model},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                vec = data.get("data", [{}])[0].get("embedding")
                if vec:
                    return vec
        except Exception:
            pass
        print("⚠️ Embedding API failed — falling back to n-gram (no semantic guarantee)", file=__import__("sys").stderr)
    
    # Level 3: Pure local fallback
    return _get_ngram_embedding(text)


# ==================== Frequency Guard (Burst Protection, unified) ====================

from moyu_toolkit.frequency_guard import record_write as _record_write
from moyu_toolkit.frequency_guard import is_write_locked as _check_write_lock
from moyu_toolkit.frequency_guard import record_read as _record_read


def _handle_write_burst(_burst_records=None):
    """Legacy no-op — kept for backward compat. FrequencyGuard handles it now."""
    pass


# ==================== Lazy Initialization ====================

def _ensure_storage():
    """Lazy init: create storage directory and data files on first use.
    
    No errors if files already exist — safe to call before any read/write.
    """
    os.makedirs(STORAGE_PATH, exist_ok=True)
    # Ensure key data files exist (empty initial state)
    for filename, default_data in [
        ("conversation_memory.json", []),
        ("vector_index.json", {"vectors": []}),
        ("write_freq.json", []),
    ]:
        path = _storage_path(filename)
        if not os.path.exists(path):
            try:
                with open(path, 'w') as f:
                    json.dump(default_data, f)
            except Exception:
                pass  # Best-effort — next read/write will trigger creation


# ==================== Memory Index Management ====================

def _load_index() -> dict:
    _ensure_storage()
    path = _storage_path("vector_index.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"vectors": []}


def _save_index(index: dict):
    # Write burst guard — check lock first
    if _check_write_lock():
        print("🔴 写入已锁定，请等待锁自动解除 (5分钟)")
        return
    _record_write()  # record BEFORE write to avoid missing counts on write failure
    path = _storage_path("vector_index.json")
    tmp = path + ".tmp"
    try:
        with open(tmp, 'w') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        # Sign after write
        try:
            from defense_toolkit.signature import sign
            with open(path, 'r') as f:
                content = f.read()
            sign(path, content)
        except Exception:
            pass
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _load_memories() -> list:
    _ensure_storage()
    path = _storage_path("conversation_memory.json")
    if os.path.exists(path):
        # Encryption-aware: if encryption is configured, try decryption first
        enc = _get_encryption()
        password = _get_encryption_password()
        if enc and password:
            try:
                from defense_toolkit.encrypt import decrypt_file
                raw = decrypt_file(path, password)
                return json.loads(raw)
            except Exception:
                pass  # Fall through to normal read
        # Normal read (not encrypted, or enc configured but no password)
        try:
            with open(path, 'rb') as f:
                raw = f.read()
            # If file is encrypted but we have no password configured, warn
            if raw.startswith(b'ENCv1:'):
                print(f"🔐 {os.path.basename(path)} is encrypted — configure encryption password to read")
                return []
            data = json.loads(raw.decode())
            if not isinstance(data, list):
                return []  # Valid JSON but not a list — treat as corrupted
            return data
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []  # Corrupted or empty file
    return []


def _save_memories(memories: list):
    # Write burst guard — check lock first
    if _check_write_lock():
        print("🔴 写入已锁定，请等待锁自动解除 (5分钟)")
        return
    _record_write()  # record BEFORE write
    path = _storage_path("conversation_memory.json")
    tmp = path + ".tmp"

    # Encryption-aware: encrypt before writing if configured
    enc = _get_encryption()
    password = _get_encryption_password()
    if enc and password:
        try:
            from defense_toolkit.encrypt import encrypt_bytes
            data = json.dumps(memories, ensure_ascii=False, indent=2)
            encrypted = encrypt_bytes(data.encode('utf-8'), password)
            with open(tmp, 'wb') as f:
                f.write(encrypted)
            os.replace(tmp, path)
            # Sign after write
            try:
                from defense_toolkit.signature import sign
                sign(path, data)
            except Exception:
                pass
            return
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            pass  # Fall through to plaintext write

    # Default (no encryption)
    try:
        with open(tmp, 'w') as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        # Sign after write
        try:
            from defense_toolkit.signature import sign
            with open(path, 'r') as f:
                content = f.read()
            sign(path, content)
        except Exception:
            pass
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def add_memory(summary: str, source: str = "user",
               metadata: dict = None,
               overview: str = None,
               full: str = None) -> Optional[dict]:
    """Add a memory entry with auto-dedup (MD5) + content security gate + index + entities.

    Args:
        summary: One-line summary (shown in search results).
        source: Source label.
        metadata: Optional metadata dict.
        overview: 2-3 sentence overview (shown when expanded).
        full: Complete content (loaded on demand).
    """
    # Content Security Gate: reject injection patterns before writing
    try:
        from moyu_toolkit.defense_toolkit.integrity_checker import content_scan
        hits = content_scan(summary)
        if hits:
            print(f"🔴 Content Security Gate: memory blocked — detected: {', '.join(hits)}")
            return None
    except ImportError:
        pass
    except Exception:
        print("⚠️ Content Security Gate check failed — memory written without security scan")
        pass

    # ── PII Redaction: detect and mask sensitive info before storage ──
    try:
        from moyu_toolkit.defense_toolkit.pii_redactor import redact as _redact_pii
        redacted, pii_types = _redact_pii(summary)
        if pii_types:
            print(f"🔏 PII redacted: {', '.join(pii_types)}")
            summary = redacted  # Replace summary with redacted version
            # Report to defense log
            try:
                from moyu_toolkit.defense_toolkit.defense_log import report as _dl_report
                _dl_report("pii", "green", {
                    "event": f"PII 脱敏 — {', '.join(pii_types)}",
                    "source": "写入前扫描",
                    "detail": f"检测到敏感信息，已脱敏后写入: {summary[:60]}",
                    "auto_resolved": True,
                })
            except Exception:
                pass
    except ImportError:
        pass
    except Exception:
        print("⚠️ PII redaction failed — storage may contain unmasked sensitive info")
        pass

    # ── LLM Security Guard (optional second layer) ──
    try:
        from moyu_toolkit.defense_toolkit.integrity_checker import llm_scan
        result = llm_scan(summary)
        if result.get("verdict") == "suspect":
            print(f"🔴 LLM Security Guard: memory blocked — {result.get('reason', '')}")
            # Report to defense log
            try:
                from moyu_toolkit.defense_toolkit.defense_log import report as _dl_report
                _dl_report("llm_guard", "yellow", {
                    "event": "LLM 安检层 — 语义绕过检测",
                    "source": result.get("reason", "未知")[:60],
                    "detail": f"正则层未拦截，LLM 判定为可疑: {summary[:60]}",
                    "auto_resolved": True,
                })
            except Exception:
                pass
            return None
    except ImportError:
        pass
    except Exception:
        pass

    # ── LLM Summary Enhancement (Optional): refine raw text before storage ──
    if _should_llm_summary():
        enhanced = _llm_summarize(summary)
        if enhanced and enhanced != summary:
            print(f"📝 LLM summary: {len(summary)} → {len(enhanced)} chars")
            summary = enhanced

    content_hash = hashlib.md5(summary.encode()).hexdigest()[:16]
    memories = _load_memories()
    
    # In-library dedup
    for m in memories:
        if m.get("content_hash") == content_hash:
            return None
    
    # Extract entities
    entities = _extract_entities(summary)
    namespace = (metadata or {}).get("namespace", "")
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    entry = {
        "id": f"mem_{ts}",
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "namespace": namespace,
        "summary": summary[:500],
        "overview": overview[:1000] if overview else None,
        "full": full if full else None,
        "content_hash": content_hash,
        "heat": 0.5,
        "heat_tier": "warm",
        "last_accessed": datetime.now().isoformat(),
        "entities": entities,
        "metadata": metadata or {}
    }
    memories.append(entry)
    _save_memories(memories)
    _add_to_index(entry["id"], entry["summary"], entry["timestamp"], source, entities, namespace)
    
    # Cross-scene tunnel maintenance: detect entity overlaps across scenes
    # Runs best-effort — silently skips if scenes are not assigned yet
    try:
        from moyu_toolkit.knowledge_graph import add_cross_scene_tunnels
        add_cross_scene_tunnels()
    except Exception:
        pass

    # ── Skill-level memory injection ──
    try:
        from moyu_toolkit import skill_memory
        exp = skill_memory.load("add_memory")
        if exp and entry is not None:
            entry["_experience"] = exp
    except Exception:
        pass

    return entry


def _detect_dimension_mismatch(idx: dict) -> bool:
    """Check if stored vectors have inconsistent dimensions (e.g., after switching embedding model)."""
    dims = set()
    for v in idx.get("vectors", []):
        vec = v.get("vector", [])
        dims.add(len(vec))
        if len(dims) > 1:
            return True
    return False


def _add_to_index(mid: str, summary: str, ts: str, source: str, entities: list = None, namespace: str = ""):
    idx = _load_index()
    for v in idx["vectors"]:
        if v["memory_id"] == mid:
            return
    vec = get_embedding(summary)
    if vec is None:
        return
    
    # Detect dimension mismatch on first add
    if idx["vectors"] and _detect_dimension_mismatch(idx):
        # Mismatch detected — silently schedule re-index on next batch_index
        pass
    
    idx["vectors"].append({
        "memory_id": mid, "timestamp": ts,
        "source": source, "summary": summary[:80],
        "entities": entities or [],
        "namespace": namespace,
        "vector": vec
    })
    _save_index(idx)


def batch_index():
    """Batch index all unindexed memories + fix dimension mismatches.
    Writes are consolidated into a single _save_index call to avoid triggering
    the write burst guard (30 writes/60s = batch index of 31+ entries)."""
    memories = _load_memories()
    idx = _load_index()
    indexed = {v["memory_id"] for v in idx["vectors"]}
    
    # Check for dimension mismatch
    if _detect_dimension_mismatch(idx):
        print("⚠️  Vector dimension mismatch detected — re-indexing all...")
        idx["vectors"] = []
        indexed = set()
    
    to_idx = [m for m in memories if m["id"] not in indexed]
    added = 0
    for m in to_idx:
        vec = get_embedding(m.get("summary", ""))
        if vec is None:
            continue
        idx["vectors"].append({
            "memory_id": m["id"],
            "timestamp": m.get("timestamp", ""),
            "source": m.get("source", ""),
            "summary": m.get("summary", "")[:80],
            "entities": m.get("entities", []),
            "vector": vec,
        })
        added += 1
    
    if added:
        _save_index(idx)
    print(f"✅ Indexed {added}/{len(memories)} memories")
    print(f"   Active vectors: {len(idx['vectors'])}")


def _detect_temporal_signal(query: str) -> Optional[str]:
    """Detect temporal intent in a query: 'past', 'future', 'recent', or None."""
    q_lower = query.lower()
    for signal, keywords in TEMPORAL_SIGNALS.items():
        for kw in keywords:
            if kw.lower() in q_lower:
                return signal
    return None


def _build_entity_index(memories: list) -> dict:
    """Build entity → [memory_id, ...] index for cross-memory linking."""
    idx = {}
    for m in memories:
        for e in m.get("entities", []):
            key = e.lower()
            if key not in idx:
                idx[key] = []
            if m["id"] not in idx[key]:
                idx[key].append(m["id"])
    return idx


def _compute_entity_connectivity_boost(candidate_ids: set, entity_index: dict,
                                        all_ranked_ids: list) -> dict:
    """Compute connectivity bonus: memories sharing entities with other top candidates get boosted.
    Uses pre-built reverse index (memory_id → entities) for O(1) entity lookup.
    Falls back to no bonus when candidate pool exceeds size threshold (avoids O(n²) overhead).
    Returns {memory_id: bonus_score} (cap 0.3)."""
    # Size guard: skip connectivity boost for large pools to prevent O(n²) cost
    if len(candidate_ids) > 500 or len(all_ranked_ids) > 500:
        return {}

    # Build reverse index: memory_id → set(entity_names) — O(E) one-time cost
    # replaces the old O(E) scan per memory
    memory_to_entities = {}
    for entity, mem_ids in entity_index.items():
        for mid in mem_ids:
            if mid not in memory_to_entities:
                memory_to_entities[mid] = set()
            memory_to_entities[mid].add(entity)

    bonuses = {}
    candidate_set = set(candidate_ids) if isinstance(candidate_ids, list) else candidate_ids
    for mid in candidate_ids:
        mem_entities = memory_to_entities.get(mid, set())
        if not mem_entities:
            continue
        # 用 entity_index 直接找共现记忆，替代扫描全量 ranked IDs
        connected_memories = set()
        for entity in mem_entities:
            connected = entity_index.get(entity, [])
            for other_id in connected:
                if other_id != mid and other_id in candidate_set:
                    connected_memories.add(other_id)
            if len(connected_memories) >= 6:  # 6 * 0.05 = 0.3，提前退出
                break
        shared_count = len(connected_memories)
        bonuses[mid] = min(shared_count * 0.05, 0.3)
    return bonuses


# ==================== LLM Rerank (Optional) ====================

_LLM_RERANK_FAILURES = 0
_LLM_RERANK_NO_KEY_WARNED = False


def _call_llm_rerank(system_prompt: str, user_prompt: str) -> str:
    """Call configured LLM for reranking. Returns empty string on failure.
    Uses unified _llm_client for config resolution and HTTP call."""
    global _LLM_RERANK_FAILURES
    if _LLM_RERANK_FAILURES >= 3:
        return ""

    from moyu_toolkit._llm_client import resolve_llm_config, call_llm_api
    api_key, base_url, model = resolve_llm_config()
    if not api_key or api_key == "your-api-key-here":
        global _LLM_RERANK_NO_KEY_WARNED
        if not _LLM_RERANK_NO_KEY_WARNED:
            _LLM_RERANK_NO_KEY_WARNED = True
            print("⚠️  MOYU 语义重排：未检测到有效 API Key，已跳过 LLM 重排。")
        _LLM_RERANK_FAILURES += 1
        return ""

    result = call_llm_api(
        api_key, base_url, model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=500,
        timeout=15,
    )
    if result:
        _LLM_RERANK_FAILURES = 0
    else:
        _LLM_RERANK_FAILURES += 1
    return result


def _llm_rerank(query: str, candidates: list) -> list:
    """Re-rank candidate search results by LLM-judged semantic relevance.

    The LLM evaluates each candidate's relevance to the query beyond what
    keyword/embedding scoring captures — understanding context, intent, and
    implicit relationships.

    Args:
        query: The original user search query.
        candidates: List of result dicts with 'summary' and 'timestamp'.
    
    Returns:
        Reordered list (same items, new order). Falls back to original on failure.
    """
    if len(candidates) <= 1:
        return candidates

    # Build candidate listing for the prompt
    lines = []
    for i, r in enumerate(candidates):
        summary = r.get("summary", "")[:120].replace('"', "'")
        ts = r.get("timestamp", "")[:10]
        lines.append(f'  {{"idx": {i}, "summary": "{summary}", "date": "{ts}"}}')

    candidate_block = ",\n".join(lines)
    system_prompt = (
        "You are a search relevance re-ranker. Given a user query and candidate "
        "memory entries, re-rank them by how relevant they are to the query.\n\n"
        "Consider:\n"
        "- Direct relevance: does the memory directly address the user's intent?\n"
        "- Information value: how much useful/specific information does it contain?\n"
        "- Temporal fit: does the timing match the query's temporal signal?\n\n"
        "Output valid JSON ONLY with this structure:\n"
        '{"ranked_indices": [3, 0, 1, 2]} '
        "- an array of the candidate indices in order of relevance (most relevant first)."
    )

    user_prompt = (
        f'Query: "{query}"\n\n'
        f"Candidates (\n{candidate_block}\n)"
    )

    response_text = _call_llm_rerank(system_prompt, user_prompt)
    if not response_text:
        return candidates

    # Parse JSON response
    try:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        result = json.loads(cleaned)
        indices = result.get("ranked_indices", [])
        if not indices:
            return candidates
        # Filter valid indices and deduplicate
        seen = set()
        ordered = []
        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in seen:
                seen.add(idx)
                ordered.append(candidates[idx])
        # Append any missing candidates at the end
        for i, c in enumerate(candidates):
            if i not in seen:
                ordered.append(c)
        return ordered if ordered else candidates
    except Exception:
        return candidates


# ==================== LLM Summary Enhancement (Optional) ====================

_LLM_SUMMARY_FAILURES = 0
_LLM_SUMMARY_NO_KEY_WARNED = False


def _call_llm_summary(system_prompt: str, user_prompt: str) -> str:
    """Call LLM for summarization. Returns empty string on failure.
    Uses unified _llm_client for config resolution and HTTP call."""
    global _LLM_SUMMARY_FAILURES
    if _LLM_SUMMARY_FAILURES >= 3:
        return ""

    from moyu_toolkit._llm_client import resolve_llm_config, call_llm_api
    api_key, base_url, model = resolve_llm_config()
    if not api_key or api_key == "your-api-key-here":
        global _LLM_SUMMARY_NO_KEY_WARNED
        if not _LLM_SUMMARY_NO_KEY_WARNED:
            _LLM_SUMMARY_NO_KEY_WARNED = True
            print("⚠️  MOYU 摘要增强：未检测到有效 API Key，已降级为纯截断摘要。")
        _LLM_SUMMARY_FAILURES += 1
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
        _LLM_SUMMARY_FAILURES = 0
    else:
        _LLM_SUMMARY_FAILURES += 1
    return result


def _llm_summarize(text: str) -> str:
    """Generate a clean, structured summary from raw user input using LLM.

    Focuses on preserving facts, decisions, and preferences while removing
    conversational filler. Falls back to original text on failure.
    """
    if not text or len(text) < 30:
        return text  # Too short to benefit from LLM

    system_prompt = (
        "You are a memory summarizer for a personal AI assistant. "
        "Given raw user input, produce a clean, concise summary for long-term storage.\n\n"
        "Rules:\n"
        "- Keep ALL key facts, preferences, decisions, names, and numbers\n"
        "- Remove filler words, repetition, and conversational artifacts\n"
        "- Preserve the original tone, language, and intent\n"
        "- Output in the SAME language as the input (Chinese → Chinese, English → English)\n"
        "- Max 200 characters\n"
        "- Output ONLY the summary text, no explanations, no labels"
    )
    user_prompt = f"Summarize this for memory storage:\n{text[:1000]}"

    response = _call_llm_summary(system_prompt, user_prompt)
    if response and len(response.strip()) > 5:
        return response.strip()[:300]  # Safety cap
    return text


def _should_llm_summary() -> bool:
    """Check if LLM summary enhancement is enabled in config."""
    cfg_path = get_config_path()
    if not os.path.exists(cfg_path):
        return False
    try:
        import yaml
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}
        mem = cfg.get("memory", {})
        return mem.get("llm_summary", {}).get("enabled", False)
    except Exception:
        return False


def _should_llm_rerank() -> bool:
    """Check if LLM rerank is enabled in config."""
    cfg_path = get_config_path()
    if not os.path.exists(cfg_path):
        return False
    try:
        import yaml
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}
        srch = cfg.get("search", {})
        return srch.get("llm_rerank", {}).get("enabled", False)
    except Exception:
        return False


def get_memory(memory_id: str) -> Optional[dict]:
    """Retrieve a single memory by ID, including overview/full if available."""
    memories = _load_memories()
    for m in memories:
        if m.get("id") == memory_id:
            # Bump heat more for explicit detail view
            try:
                _bump_heat(memory_id, 0.1)
            except Exception:
                pass
            return m
    return None


def _bump_heat(memory_id: str, amount: float = 0.05):
    """Increment heat for a memory (called on access). Auto-persists."""
    memories = _load_memories()
    for m in memories:
        if m.get("id") == memory_id:
            old = m.get("heat", 0.5)
            m["heat"] = min(old + amount, 1.0)
            m["last_accessed"] = datetime.now().isoformat()
            _save_memories(memories)
            return True
    return False


def _recalc_heat_tiers() -> dict:
    """
    Recalculate heat tiers: decay, sort, reassign HOT/WARM/COLD.
    
    Decay all heats by 5% per day since last access.
    Top 20% → HOT, middle 40% → WARM, bottom 40% → COLD.
    
    Returns summary dict.
    """
    memories = _load_memories()
    if not memories:
        return {"total": 0, "hot": 0, "warm": 0, "cold": 0}
    
    now = datetime.now()
    for m in memories:
        heat = m.get("heat", 0.5)
        last = m.get("last_accessed", m.get("timestamp", ""))
        try:
            days_since = (now - datetime.fromisoformat(last)).total_seconds() / 86400
        except Exception:
            days_since = 0
        # Decay 5% per day
        decay = heat - 0.05 * days_since
        m["heat"] = max(min(decay, 1.0), 0.1)  # clamp [0.1, 1.0]
    
    # Sort by heat descending
    memories.sort(key=lambda m: m.get("heat", 0), reverse=True)
    total = len(memories)
    hot_count = max(1, total // 5)
    warm_count = max(1, total * 2 // 5)
    
    for i, m in enumerate(memories):
        if i < hot_count:
            m["heat_tier"] = "hot"
        elif i < hot_count + warm_count:
            m["heat_tier"] = "warm"
        else:
            m["heat_tier"] = "cold"
    
    _save_memories(memories)
    
    hot = sum(1 for m in memories if m.get("heat_tier") == "hot")
    warm = sum(1 for m in memories if m.get("heat_tier") == "warm")
    cold = sum(1 for m in memories if m.get("heat_tier") == "cold")
    return {"total": total, "hot": hot, "warm": warm, "cold": cold}

_last_decay_monotonic = None

def search(query: str, top_k: int = 5, namespace: str = None) -> list:
    """TEMPR multi-strategy retrieval with score_and_rank hybrid fusion.
    
    Args:
        query: Search text.
        top_k: Max results to return.
        namespace: If set, filter to this namespace only.
            None = return all namespaces (default).
            Empty string = only unnamespaced memories.
    
    Pipeline:
    1. Embed query
    2. Compute semantic similarity for all vectors
    3. Compute BM25 scores (adaptive sigmoid normalization)
    4. Detect temporal signal → compute recency scores
    5. Extract query entities → compute entity boosts
    6. Build entity index → compute connectivity bonuses
    7. score_and_rank: semantic gate → source-weighted → combined → sorted
    8. (Optional) LLM rerank: semantic reordering of top-2k candidates
    """
    # Record read event for frequency monitoring
    try:
        _record_read()
    except Exception:
        pass
    # Load vectors from vector index (JSON)
    idx = _load_index()
    vectors = idx.get("vectors", [])
    if not vectors:
        return []
    memories = _load_memories()
    mem_map = {m["id"]: m for m in memories}
    
    # ── Auto-decay: lightweight heat decay on search (throttled to once per 30 min) ──
    global _last_decay_monotonic
    now_ts = time.monotonic()
    if _last_decay_monotonic is None or (now_ts - _last_decay_monotonic) > 1800:
        for m in memories:
            heat = m.get("heat", 0.5)
            last = m.get("last_accessed", m.get("timestamp", ""))
            try:
                days_since = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 86400
            except Exception:
                days_since = 0
            m["heat"] = max(min(heat - 0.05 * days_since, 1.0), 0.1)
        _last_decay_monotonic = now_ts
    
    # Detect temporal signal in query (Mem0-inspired temporal reasoning)
    temporal_signal = _detect_temporal_signal(query)
    
    # FTS5 BM25 search
    fts_results = _fts_search(query, top_k * 4)
    fts_map = {}  # memory_id -> normalized BM25 score
    if fts_results:
        # Normalize FTS ranks to [0, 1]
        max_rank = max(r["fts_rank"] for r in fts_results) if fts_results else 1
        for r in fts_results:
            # FTS5 rank is negative; lower = better. Normalize inversely.
            norm = 1.0 / (1.0 + abs(r["fts_rank"]) / max(abs(max_rank), 1))
            fts_map[r["memory_id"]] = norm
    
    q_vec = get_embedding(query, is_query=True)
    
    # Dimension mismatch guard: if query vec dim differs from indexed vecs, drop semantic scoring
    # n-gram fallback (256-dim) still won't match stored vectors from a different model (e.g. 384/512)
    _dim_mismatch = False
    if q_vec and vectors and len(q_vec) != len(vectors[0].get("vector", [])):
        _dim_mismatch = True
        q_vec = None
        print("⚠️  Vector dimension mismatch between query and index — "
              "semantic scoring disabled. Run 'moyu index' to rebuild vector index.", file=__import__("sys").stderr)
    
    q_words = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', query.lower())
    
    # Extract entities from query for boosting
    q_entities = _extract_entities(query)
    q_entity_set = set(e.lower() for e in q_entities)
    
    # Build entity index for cross-memory connectivity
    entity_index = _build_entity_index(memories)
    
    # Compute individual strategy scores for all entries
    sem_scores = []
    bm25_scores = []
    recency_scores = []
    entity_boosts = []
    source_weights = []
    
    # Namespace filter: pre-filter vectors to matching namespace
    if namespace is not None:
        filtered_vectors = []
        for v in vectors:
            v_ns = v.get("namespace", "")
            if v_ns == namespace:
                filtered_vectors.append(v)
        vectors = filtered_vectors
        if not vectors:
            return []

    # ── BM25 + heat pre-filter: 降低 cosine 全量计算 ──
    # 只保留 FTS5 命中的 + HOT 档的热门记忆，其它记忆跳过 cosine 计算
    # 记忆量 < 500 时跳过预过滤 — 全量余弦计算的开销可以忽略，语义召回更重要
    # 预过滤前保存全量 IDs，供 connectivity boost 使用完整图谱
    all_vector_ids = {v["memory_id"] for v in vectors}
    if len(vectors) >= 500:
        fts_candidates = set(fts_map.keys())
        hot_candidates = set()
        for m in memories:
            if m.get("heat_tier") == "hot":
                hot_candidates.add(m["id"])
        candidate_ids = fts_candidates | hot_candidates
        if candidate_ids:
            filtered = [v for v in vectors if v["memory_id"] in candidate_ids]
            if filtered:
                vectors = filtered
            # 如果 filter 后空了就全保留（保底不吞结果）
        # else: 没有 FTS5 也没 HOT（空库），继续走原有逻辑

    for i, entry in enumerate(vectors):
        # Semantic score
        sem = cosine_similarity(q_vec, entry["vector"]) if q_vec else 0.0
        sem_scores.append(sem)
        
        # BM25 keyword score — from FTS5
        bm25 = fts_map.get(entry["memory_id"], 0.0)
        bm25_scores.append(bm25)
        
        # Recency score — with temporal reasoning
        try:
            mt = datetime.fromisoformat(entry.get("timestamp", "").replace("Z", "+00:00"))
            age_hours = max(0, (datetime.now() - mt).total_seconds() / 3600)
            age_days = age_hours / 24
            
            if temporal_signal == "recent":
                # Heavy boost for very recent (< 3 days), steep decay after
                recency_scores.append(max(0.1, 1.0 - age_hours / (7 * 24)))
            elif temporal_signal == "past":
                # Invert: boost older memories, cap recent ones
                recency_scores.append(min(1.0, max(0.1, age_days / 30)))
            elif temporal_signal == "future":
                # Neutral: all equally relevant for planning
                recency_scores.append(0.7)
            else:
                # Default: linear decay over 30 days
                recency_scores.append(max(0.1, 1.0 - age_days / 30))
        except Exception:
            recency_scores.append(0.5)
        
        # Entity boost: query entities mentioned in this memory → boost
        mem_entities = set(e.lower() for e in entry.get("entities", []))
        overlap = q_entity_set & mem_entities
        if overlap:
            # Boost decays with number of linked entities (prevent noise domination)
            boost = ENTITY_BOOST_WEIGHT / (1.0 + 0.001 * (len(overlap) - 1) ** 2)
            entity_boosts.append(boost)
        else:
            entity_boosts.append(0.0)
        
        # Source weight: agent_confirmed = user = 1.0, system/agent discounted
        src = entry.get("source", "user")
        source_weights.append(SOURCE_WEIGHTS.get(src, 0.7))
    
    # score_and_rank hybrid fusion
    has_real_embeds = _check_fastembed() or bool(_get_embedding_api()[0] and _get_embedding_api()[0] not in ('your-api-key-here', ''))
    
    # Build connectivity bonuses from entity index (cross-memory linking)
    connectivity_bonuses = _compute_entity_connectivity_boost(all_vector_ids, entity_index, all_vector_ids)
    
    # Determine candidate pool size: larger when LLM rerank is enabled
    use_rerank = _should_llm_rerank()
    candidate_k = top_k * 2 if use_rerank else top_k

    ranked = score_and_rank(sem_scores, bm25_scores, recency_scores, entity_boosts, candidate_k,
                            has_real_embeddings=has_real_embeds,
                            source_weights=source_weights,
                            connectivity_bonuses=connectivity_bonuses,
                            retrieval_weights=_get_retrieval_weights())
    
    results = []
    for score, i in ranked:
        entry = vectors[i]
        mem = mem_map.get(entry["memory_id"], {})
        results.append({
            "memory_id": entry["memory_id"],
            "timestamp": entry["timestamp"],
            "source": entry["source"],
            "summary": mem.get("summary", entry.get("summary", "")),
            "entities": entry.get("entities", []),
            "score": round(score, 4)
        })

    # Step 8: Optional LLM rerank — semantic reordering of candidate pool
    if use_rerank and len(results) > 1:
        reranked = _llm_rerank(query, results)
        if reranked:
            results = reranked

    # Bump heat for returned results (search access drives heat) — reuse loaded memories
    try:
        updated = 0
        for r in results:
            mid = r.get("memory_id")
            if not mid:
                continue
            for m in memories:
                if m.get("id") == mid:
                    old = m.get("heat", 0.5)
                    m["heat"] = min(old + 0.02, 1.0)
                    m["last_accessed"] = datetime.now().isoformat()
                    updated += 1
                    break
        if updated:
            _save_memories(memories)
    except Exception:
        pass

    # ── Semantic dedup: remove results too similar to higher-ranked ones ──
    if len(results) > 1:
        # Build vector lookup from the vectors we already have
        vec_lookup = {}
        for v in vectors:
            vid = v.get("memory_id")
            vvec = v.get("vector")
            if vid and vvec:
                vec_lookup[vid] = vvec
        
        keep = []
        for r in results:
            mid = r.get("memory_id")
            rvec = vec_lookup.get(mid)
            if not rvec:
                keep.append(r)
                continue
            is_dup = False
            for k in keep:
                kvec = vec_lookup.get(k.get("memory_id"))
                if not kvec:
                    continue
                try:
                    sim = cosine_similarity(rvec, kvec)
                    if sim > 0.9:
                        # Keep the one with higher heat
                        r_heat = 0.5
                        k_heat = 0.5
                        for m in memories:
                            if m.get("id") == mid:
                                r_heat = m.get("heat", 0.5)
                            if m.get("id") == k.get("memory_id"):
                                k_heat = m.get("heat", 0.5)
                        if r_heat <= k_heat:
                            is_dup = True
                        else:
                            # Replace k with r (r is hotter)
                            keep.remove(k)
                            keep.append(r)
                            is_dup = True
                        break
                except Exception:
                    pass
            if not is_dup:
                keep.append(r)
        results = keep

    # ── Skill-level memory injection: attach accumulated experience ──
    try:
        from moyu_toolkit import skill_memory
        exp = skill_memory.load("search_memory")
        if exp:
            for r in results[:top_k]:
                r["_experience"] = exp
    except Exception:
        pass

    return results[:top_k]



def stats():
    idx = _load_index()
    vecs = idx["vectors"]
    print(f"\n📊 MOYU Vector Memory")
    print("=" * 50)
    print(f"Indexed: {len(vecs)} entries")
    if vecs:
        dim = len(vecs[0].get("vector", []))
        embed_type = "FastEmbed" if _check_fastembed() else "n-gram"
        print(f"Embedding: {embed_type} ({dim}-dim)")
        srcs = collections.Counter(v.get("source", "unknown") for v in vecs)
        print(f"\nSource distribution:")
        for s, c in srcs.most_common():
            print(f"  {s}: {c} entries")
        # Entity stats
        all_entities = set()
        for v in vecs:
            for e in v.get("entities", []):
                all_entities.add(e)
        if all_entities:
            print(f"\nEntities: {len(all_entities)} unique")
    print(f"FastEmbed: {'✅ available' if _check_fastembed() else '❌ not installed (pip install fastembed)'}")
    print(f"spaCy:    {'✅ available' if _check_spacy() else '❌ not installed (pip install spacy && python3 -m spacy download en_core_web_sm)'}")


def demo() -> dict:
    return {
        "capability": 1,
        "title": "TEMPR Multi-Strategy Retrieval",
        "output": """🔍 1/6  DEMO
────────────────────────────────────
  You said: "上次开会说了什么方案"

  ⭐ Hit [Discussion] Confirmed A/B roadmap for smart photo frame
  ⭐ Hit [Meeting] Discussed pricing and feature priorities
  ⭐ Hit [Decision] Team decided to go with MVP first

  Even if your search words don't match the original text exactly,
  TEMPR (semantic + BM25 keyword + time-weighted) still finds it.""",
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: index | search <query> | stats")
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "index":
        batch_index()
    elif cmd == "search":
        q = " ".join(sys.argv[2:])
        for r in search(q):
            print(f"[{r['score']:.4f}] {r['timestamp'][:10]} [{r['source']}]")
            if r.get("entities"):
                print(f"  entities: {', '.join(r['entities'][:5])}")
            print(f"  {r['summary'][:100]}\n")
    elif cmd == "stats":
        stats()
