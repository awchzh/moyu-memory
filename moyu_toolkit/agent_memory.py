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
import fcntl
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
            from defense_toolkit.isolation import get_storage_path, get_user
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
            from defense_toolkit.encrypt import encrypt_bytes, decrypt_bytes, is_encrypted
            _ENCRYPTION = {"encrypt": encrypt_bytes, "decrypt": decrypt_bytes, "is_encrypted": is_encrypted}
        except Exception:
            _ENCRYPTION = False
    return _ENCRYPTION or None

def _get_encryption_password() -> str:
    """Read encryption password from env var MOYU_ENCRYPTION_PASSWORD only.
    Plaintext passwords in config.yaml are no longer supported for security reasons."""
    return os.environ.get("MOYU_ENCRYPTION_PASSWORD", "")

# ==================== SQLite FTS5 ====================
from agent_memory_sqlite import _fts_search

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

STORE = os.path.dirname(os.path.abspath(__file__))
STORAGE_PATH = os.environ.get("MOYU_STORAGE", os.path.join(STORE, "memory_data"))

# Write frequency guard (burst protection)
WRITE_FREQ_FILE = os.path.join(STORAGE_PATH, "write_freq.json")
WRITE_LOCK_FILE = os.path.join(STORAGE_PATH, "write_lock.json")
WRITE_FLOCK_FILE = os.path.join(STORAGE_PATH, "write_flock.lock")
WRITE_BURST_THRESHOLD = 30   # max writes in the window before trigger
WRITE_BURST_WINDOW = 60      # seconds
WRITE_LOCK_MINUTES = 5       # auto-lock duration after burst

# TEMPR retrieval weights (used only as fallback when RRF disabled)
TEMPR_WEIGHTS = {"semantic": 0.5, "keyword": 0.3, "recency": 0.2}

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
    """Load config.yaml (if exists)"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(config_path):
        try:
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
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
                   connectivity_bonuses: dict = None) -> List[Tuple[float, int]]:
    """Hybrid scoring: semantic gate → combined score → sort.
    
    - Semantic gate only applies when has_real_embeddings=True (FastEmbed/API).
      When using n-gram fallback, semantic scores are meaningless, so the gate
      is bypassed.
    - source_weights: per-entry weight from SOURCE_WEIGHTS map (1.0 for user/agent_confirmed).
    - connectivity_bonuses: cross-memory entity linking boost.
    """
    scored = []
    for i in range(len(semantic_scores)):
        sem = semantic_scores[i]
        # Only gate when using real embeddings (n-gram has no semantic signal)
        if has_real_embeddings and sem < SEMANTIC_GATE:
            continue
        bm25 = bm25_norm_scores[i]
        rec = recency_scores[i]
        ent = entity_boosts[i] if i < len(entity_boosts) else 0.0
        
        raw = sem + bm25 + rec + ent
        
        # Source weight: agent_confirmed = user = 1.0, system/agent = 0.85
        if source_weights and i < len(source_weights):
            raw *= source_weights[i]
        
        # Cross-memory entity connectivity bonus (per-result, after weighting)
        # This is separate from entity_boosts (which rewards query-entity overlap)
        max_possible = 1.0 + 1.0 + 1.0 + ENTITY_BOOST_WEIGHT
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
    
    # Level 3: Pure local fallback
    return _get_ngram_embedding(text)


# ==================== Write Frequency Guard (Burst Protection) ====================

class _Flock:
    """Simple file lock via fcntl.flock. Prevents concurrent writes to shared state files."""
    def __init__(self, path: str):
        self.path = path
        self.fp = None
    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.fp = open(self.path, 'w')
        fcntl.flock(self.fp, fcntl.LOCK_EX)
        return self
    def __exit__(self, *args):
        if self.fp:
            fcntl.flock(self.fp, fcntl.LOCK_UN)
            self.fp.close()
            self.fp = None


def _check_write_lock() -> bool:
    """Check if memory writes are currently locked after a burst event."""
    if not os.path.exists(WRITE_LOCK_FILE):
        return False
    try:
        with open(WRITE_LOCK_FILE) as f:
            lock = json.load(f)
        elapsed = time.time() - lock.get("locked_at", 0)
        if elapsed < WRITE_LOCK_MINUTES * 60:
            return True  # still locked
        else:
            os.remove(WRITE_LOCK_FILE)  # expired
            return False
    except Exception:
        return False


def _record_write():
    """Record a memory write timestamp. If burst threshold exceeded, trigger rollback + lock."""
    with _Flock(WRITE_FLOCK_FILE):
        now = time.time()
        records = []
        if os.path.exists(WRITE_FREQ_FILE):
            try:
                with open(WRITE_FREQ_FILE) as f:
                    records = json.load(f)
            except Exception:
                records = []
    
        # Prune entries outside the window
        cutoff = now - WRITE_BURST_WINDOW
        records = [t for t in records if t > cutoff]
        records.append(now)
    
        # Check burst
        if len(records) > WRITE_BURST_THRESHOLD:
            # Burst detected — save the burst timestamps before clearing
            burst_records = list(records)
            _handle_write_burst(burst_records)
            # Clear freq records after handling
            with open(WRITE_FREQ_FILE, 'w') as f:
                json.dump([], f)
            return
    
        # Save updated records
        with open(WRITE_FREQ_FILE, 'w') as f:
            json.dump(records, f)


def _handle_write_burst(burst_records: list = None):
    """Fine-grained rollback: remove entries written during the burst window.
    Does NOT touch entries written before the burst started.
    Locks writes and sends alert."""
    from defense_toolkit.integrity_checker import log, BASE

    # Lock writes
    lock_data = {
        "locked_at": time.time(),
        "lock_minutes": WRITE_LOCK_MINUTES,
        "reason": f"Write burst: >{WRITE_BURST_THRESHOLD} writes in {WRITE_BURST_WINDOW}s",
        "timestamp": datetime.now().isoformat(),
    }
    os.makedirs(os.path.dirname(WRITE_LOCK_FILE), exist_ok=True)
    with open(WRITE_LOCK_FILE, 'w') as f:
        json.dump(lock_data, f, ensure_ascii=False, indent=2)

    # Determine burst window: earliest timestamp in burst_records is the cutoff
    cutoff_ts = None
    if burst_records:
        min_unix = min(burst_records)
        cutoff_ts = datetime.fromtimestamp(min_unix).isoformat()
    else:
        # Fallback: use current time minus burst window
        cutoff_ts = datetime.fromtimestamp(time.time() - WRITE_BURST_WINDOW).isoformat()

    # Fine-grained rollback: remove entries written during burst window
    removed_count = 0

    # conversation_memory.json: remove entries with timestamp >= cutoff_ts
    mem_path = _storage_path("conversation_memory.json")
    if os.path.exists(mem_path):
        try:
            with open(mem_path) as f:
                memories = json.load(f)
            before = len(memories)
            memories = [m for m in memories if m.get("timestamp", "") < cutoff_ts]
            removed = before - len(memories)
            if removed:
                with open(mem_path, 'w') as f:
                    json.dump(memories, f, ensure_ascii=False, indent=2)
                removed_count += removed
        except Exception:
            pass

    # vector_index.json: remove entries with timestamp >= cutoff_ts
    vec_path = _storage_path("vector_index.json")
    if os.path.exists(vec_path):
        try:
            with open(vec_path) as f:
                idx = json.load(f)
            before = len(idx.get("vectors", []))
            idx["vectors"] = [v for v in idx.get("vectors", []) if v.get("timestamp", "") < cutoff_ts]
            removed = before - len(idx["vectors"])
            if removed:
                with open(vec_path, 'w') as f:
                    json.dump(idx, f, ensure_ascii=False, indent=2)
                removed_count += removed
        except Exception:
            pass

    if removed_count:
        log(f"Write burst: removed {removed_count} entry/entries after burst, locked {WRITE_LOCK_MINUTES}min", "CRITICAL")

    # Send alert
    try:
        from defense_toolkit.integrity_checker import _send_alert
        _send_alert(
            f"🔴 MOYU Write Burst Alert: locked for {WRITE_LOCK_MINUTES}min",
            f"Detected >{WRITE_BURST_THRESHOLD} writes in {WRITE_BURST_WINDOW}s\n"
            f"Actions: removed {removed_count} burst entries, writes locked for {WRITE_LOCK_MINUTES}min"
        )
    except Exception:
        pass


# ==================== Memory Index Management ====================

def _load_index() -> dict:
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
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _load_memories() -> list:
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
            return json.loads(raw.decode())
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
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def add_memory(summary: str, source: str = "user",
               metadata: dict = None) -> Optional[dict]:
    """Add a memory entry with auto-dedup (MD5) + content security gate + index + entities."""
    # Content Security Gate: reject injection patterns before writing
    try:
        from defense_toolkit.integrity_checker import content_scan
        hits = content_scan(summary)
        if hits:
            print(f"🔴 Content Security Gate: memory blocked — detected: {', '.join(hits)}")
            return None
    except ImportError:
        pass
    except Exception:
        pass

    # ── PII Redaction: detect and mask sensitive info before storage ──
    try:
        from defense_toolkit.pii_redactor import redact as _redact_pii
        redacted, pii_types = _redact_pii(summary)
        if pii_types:
            print(f"🔏 PII redacted: {', '.join(pii_types)}")
            summary = redacted  # Replace summary with redacted version
    except ImportError:
        pass
    except Exception:
        pass

    content_hash = hashlib.md5(summary.encode()).hexdigest()[:16]
    memories = _load_memories()
    
    # In-library dedup
    for m in memories:
        if m.get("content_hash") == content_hash:
            return None
    
    # Extract entities
    entities = _extract_entities(summary)
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    entry = {
        "id": f"mem_{ts}",
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "summary": summary[:500],
        "content_hash": content_hash,
        "entities": entities,
        "metadata": metadata or {}
    }
    memories.append(entry)
    _save_memories(memories)
    _add_to_index(entry["id"], entry["summary"], entry["timestamp"], source, entities)
    
    # Cross-scene tunnel maintenance: detect entity overlaps across scenes
    # Runs best-effort — silently skips if scenes are not assigned yet
    try:
        from knowledge_graph import add_cross_scene_tunnels
        add_cross_scene_tunnels()
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


def _add_to_index(mid: str, summary: str, ts: str, source: str, entities: list = None):
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
    Returns {memory_id: bonus_score} (cap 0.3)."""
    bonuses = {}
    for mid in candidate_ids:
        # Gather all entities mentioned in this memory (via entity index)
        mem_entities = set()
        for entity, mem_ids in entity_index.items():
            if mid in mem_ids:
                mem_entities.add(entity)
        if not mem_entities:
            continue
        # Count how many OTHER top candidates share at least one entity with this memory
        shared_count = 0
        for other_id in all_ranked_ids:
            if other_id == mid:
                continue
            for entity in mem_entities:
                if other_id in entity_index.get(entity, []):
                    shared_count += 1
                    break
        # Per-entry cap 0.3, total sum capped globally if passed via context
        bonuses[mid] = min(shared_count * 0.05, 0.3)
    # Global cap: no single memory should get more than 0.3 total connectivity bonus
    # (prevents stacking across multiple entity overlaps from dominating results)
    for mid in bonuses:
        bonuses[mid] = min(bonuses[mid], 0.3)
    return bonuses


def search(query: str, top_k: int = 5) -> list:
    """TEMPR multi-strategy retrieval with score_and_rank hybrid fusion.
    
    Pipeline:
    1. Embed query
    2. Compute semantic similarity for all vectors
    3. Compute BM25 scores (adaptive sigmoid normalization)
    4. Detect temporal signal → compute recency scores
    5. Extract query entities → compute entity boosts
    6. Build entity index → compute connectivity bonuses
    7. score_and_rank: semantic gate → source-weighted → combined → sorted
    """
    # Load vectors from vector index (JSON)
    idx = _load_index()
    vectors = idx.get("vectors", [])
    if not vectors:
        return []
    memories = _load_memories()
    mem_map = {m["id"]: m for m in memories}
    
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
    
    # Dimension mismatch guard: if query vec dim differs from indexed vecs, fall back to n-gram
    if q_vec and vectors and len(q_vec) != len(vectors[0].get("vector", [])):
        q_vec = _get_ngram_embedding(query)
    
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
    all_ids = {v["memory_id"] for v in vectors}
    connectivity_bonuses = _compute_entity_connectivity_boost(all_ids, entity_index, all_ids)
    
    ranked = score_and_rank(sem_scores, bm25_scores, recency_scores, entity_boosts, top_k,
                            has_real_embeddings=has_real_embeds,
                            source_weights=source_weights,
                            connectivity_bonuses=connectivity_bonuses)
    
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
    return results


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
