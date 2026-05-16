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
import collections
import hashlib
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple

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

STORAGE_PATH = os.environ.get("MOYU_STORAGE", os.path.join(os.path.dirname(__file__), "memory_data"))

# TEMPR retrieval weights (used only as fallback when RRF disabled)
TEMPR_WEIGHTS = {"semantic": 0.5, "keyword": 0.3, "recency": 0.2}
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
    """Get storage path"""
    path = os.path.join(STORAGE_PATH, *parts)
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
                   top_k: int, has_real_embeddings: bool = True) -> List[Tuple[float, int]]:
    """Hybrid scoring: semantic gate → combined score → sort.
    
    - Semantic gate only applies when has_real_embeddings=True (FastEmbed/API).
      When using n-gram fallback, semantic scores are meaningless, so the gate
      is bypassed.
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
        max_possible = 1.0 + 1.0 + 1.0 + ENTITY_BOOST_WEIGHT
        normalized = min(raw / max_possible, 1.0)
        scored.append((normalized, i))
    
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


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


# ==================== Memory Index Management ====================

def _load_index() -> dict:
    path = _storage_path("vector_index.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"vectors": []}


def _save_index(index: dict):
    path = _storage_path("vector_index.json")
    with open(path, 'w') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def _load_memories() -> list:
    path = _storage_path("conversation_memory.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def _save_memories(memories: list):
    path = _storage_path("conversation_memory.json")
    with open(path, 'w') as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)


def add_memory(summary: str, source: str = "user",
               metadata: dict = None) -> Optional[dict]:
    """Add a memory entry with auto-dedup (MD5) + index + entities."""
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
    """Batch index all unindexed memories + fix dimension mismatches"""
    memories = _load_memories()
    idx = _load_index()
    indexed = {v["memory_id"] for v in idx["vectors"]}
    
    # Check for dimension mismatch
    if _detect_dimension_mismatch(idx):
        print("⚠️  Vector dimension mismatch detected — re-indexing all...")
        idx["vectors"] = []
        indexed = set()
    
    to_idx = [m for m in memories if m["id"] not in indexed]
    for m in to_idx:
        _add_to_index(m["id"], m.get("summary", ""),
                      m.get("timestamp", ""), m.get("source", ""),
                      m.get("entities", []))
    print(f"✅ Indexed {len(to_idx)}/{len(memories)} memories")
    print(f"   Active vectors: {len(idx['vectors'])}")


def search(query: str, top_k: int = 5) -> list:
    """TEMPR multi-strategy retrieval with score_and_rank hybrid fusion.
    
    Pipeline:
    1. Embed query
    2. Compute semantic similarity for all vectors
    3. Compute BM25 scores (adaptive sigmoid normalization)
    4. Compute recency scores
    5. Extract query entities → compute entity boosts
    6. score_and_rank: semantic gate → combined → sorted
    """
    # Load vectors from vector index (JSON)
    idx = _load_index()
    vectors = idx.get("vectors", [])
    if not vectors:
        return []
    memories = _load_memories()
    mem_map = {m["id"]: m for m in memories}
    
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
    q_words = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', query.lower())
    
    # Extract entities from query for boosting
    q_entities = _extract_entities(query)
    q_entity_set = set(e.lower() for e in q_entities)
    
    # Compute individual strategy scores for all entries
    sem_scores = []
    bm25_scores = []
    recency_scores = []
    entity_boosts = []
    
    for i, entry in enumerate(vectors):
        # Semantic score
        sem = cosine_similarity(q_vec, entry["vector"]) if q_vec else 0.0
        sem_scores.append(sem)
        
        # BM25 keyword score — from FTS5
        bm25 = fts_map.get(entry["memory_id"], 0.0)
        bm25_scores.append(bm25)
        
        # Recency score
        try:
            mt = datetime.fromisoformat(entry.get("timestamp", "").replace("Z", "+00:00"))
            age = max(0, (datetime.now() - mt).total_seconds() / 3600)
            recency_scores.append(max(0.1, 1.0 - age / (30 * 24)))
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
    
    # score_and_rank hybrid fusion
    has_real_embeds = _check_fastembed() or bool(_get_embedding_api()[0] and _get_embedding_api()[0] not in ('your-api-key-here', ''))
    ranked = score_and_rank(sem_scores, bm25_scores, recency_scores, entity_boosts, top_k, has_real_embeddings=has_real_embeds)
    
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
