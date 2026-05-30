#!/usr/bin/env python3
"""knowledge_graph.py — MOYU Lightweight Knowledge Graph

Auto-extracts entities and relations from conversation to assist memory retrieval.
JSON file storage, zero database dependency.

Temporal features (v2.4):
  - valid_from / valid_until on entities and relations
  - Snapshot query: view the graph as it existed at any point in time
  - Invalidation: mark relations as outdated without deleting them

Usage:
    python3 knowledge_graph.py extract <text>             # Extract relations
    python3 knowledge_graph.py search <query>              # Search entities (current only)
    python3 knowledge_graph.py search <query> --snapshot YYYY-MM-DD  # Snapshot query
    python3 knowledge_graph.py invalidate --source X --target Y --relation Z  # Invalidate a relation
    python3 knowledge_graph.py invalidate --entity "Alice"  # Invalidate all relations of an entity
    python3 knowledge_graph.py stats                       # Show statistics
"""

import json
import os
import re
from datetime import datetime
from typing import List, Dict, Optional

from moyu_toolkit._moyu_paths import get_config_path
from moyu_toolkit._storage import storage

RELATION_TYPES = {
    "works_at": "works at", "uses": "uses", "lives_in": "lives in",
    "manages": "manages", "created": "created", "owns": "owns",
    "knows": "knows", "prefers": "prefers", "is_a": "is a",
    "belongs_to": "belongs to", "located_at": "located at", "develops": "develops",
    "depends_on": "depends on", "related_to": "related to",
    "cross_scene": "cross-scene tunnel",
}


# ═══════════════════════════════════════════════════════════
# 底层 IO
# ═══════════════════════════════════════════════════════════

def _load_kg() -> dict:
    """Load knowledge graph from storage."""
    return storage.read_or_default("knowledge_graph.json", {"entities": {}, "relations": []})


def _normalize(name: str) -> str:
    return re.sub(r'[^\w\u4e00-\u9fff]', '', name.strip().lower())


def _backfill_temporal(kg: dict) -> bool:
    """Ensure all entities and relations have temporal fields.
    Backfills from existing fields for backward compatibility with pre-v2.4 data.
    Returns True if any backfill was applied.
    """
    changed = False
    for entity in kg["entities"].values():
        if "valid_from" not in entity:
            entity["valid_from"] = entity.get("first_seen", "unknown")
            changed = True
        if "valid_until" not in entity:
            entity["valid_until"] = None
            changed = True
    for r in kg["relations"]:
        if "valid_from" not in r:
            r["valid_from"] = r.get("created", "unknown")
            changed = True
        if "valid_until" not in r:
            r["valid_until"] = None
            changed = True
        if "invalid_reason" not in r:
            r["invalid_reason"] = None
            changed = True
    return changed


# ═══════════════════════════════════════════════════════════
# 实体/关系抽取
# ═══════════════════════════════════════════════════════════

_LLM_EXTRACT_FAILURES = 0
_LLM_EXTRACT_NO_KEY_WARNED = False

def _call_llm(prompt: str) -> str:
    """Call the configured LLM API for entity extraction.
    Circuit breaker: returns '' after 3 consecutive failures.
    Falls back to env vars and ~/.hermes/.env for API key."""
    global _LLM_EXTRACT_FAILURES
    if _LLM_EXTRACT_FAILURES >= 3:
        return ""

    from moyu_toolkit._llm_client import resolve_llm_config, call_llm_api
    api_key, base_url, model = resolve_llm_config()
    if not api_key or api_key == "your-api-key-here":
        global _LLM_EXTRACT_NO_KEY_WARNED
        if not _LLM_EXTRACT_NO_KEY_WARNED:
            _LLM_EXTRACT_NO_KEY_WARNED = True
            print("Warning: MOYU knowledge graph: no valid API Key, falling back to regex extraction.")
        _LLM_EXTRACT_FAILURES += 1
        return ""

    result = call_llm_api(
        api_key, base_url, model,
        messages=[
            {"role": "system", "content": "You are a precise relation extractor."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=500,
        timeout=15,
    )
    if result:
        _LLM_EXTRACT_FAILURES = 0
    else:
        _LLM_EXTRACT_FAILURES += 1
    return result


def _extract_fallback(text: str) -> List[Dict]:
    """Regex-based entity extraction fallback (no API key required).
    Covers common patterns: X is Y, X works at Y, X uses Y, etc.
    Also extracts named entities (PERSON, ORG, etc.) from common patterns.
    """
    triples = []
    patterns = [
        # Chinese patterns
        (r"(\S{2,8})\s*是\s*(\S{2,12})(?:[，。、！？]|$)", "is_a"),
        (r"(\S{2,8})\s*在\s*(\S{2,20})\s*(?:工作|上班|任职)", "works_at"),
        (r"(\S{2,8})\s*(?:使用|用|用的是)\s*(\S{2,20})(?:[，。、！？]|$)", "uses"),
        (r"(\S{2,8})\s*(?:喜欢|热爱|偏爱)\s*(\S{2,20})(?:[，。、！？]|$)", "prefers"),
        (r"(\S{2,8})\s*(?:属于|隶属于|归属于)\s*(\S{2,20})(?:[，。、！？]|$)", "belongs_to"),
        (r"(\S{2,8})\s*(?:开发|创建|发明)\s*(?:了)?\s*(\S{2,20})(?:[，。、！？]|$)", "created"),
        (r"(\S{2,8})\s*(?:住在|居住于|位于)\s*(\S{2,20})(?:[，。、！？]|$)", "located_at"),
        (r"(\S{2,8})\s*(?:管理|负责|掌管)\s*(\S{2,20})(?:[，。、！？]|$)", "manages"),
        (r"(\S{2,8})\s*(?:拥有|持有)\s*(\S{2,20})(?:[，。、！？]|$)", "owns"),
        (r"(\S{2,8})\s*(?:认识|知道)\s*(\S{2,8})(?:[，。、！？]|$)", "knows"),
        # English patterns
        (r"(\S{2,20})\s+is\s+(?:a|an)\s+(\S{2,20})", "is_a"),
        (r"(\S{2,20})\s+works?\s+(?:at|for)\s+(\S{2,30})", "works_at"),
        (r"(\S{2,20})\s+uses\s+(\S{2,30})", "uses"),
        (r"(\S{2,20})\s+(?:likes|loves|prefers)\s+(\S{2,30})", "prefers"),
        (r"(\S{2,20})\s+created\s+(\S{2,30})", "created"),
        (r"(\S{2,20})\s+(?:lives? in|is based in)\s+(\S{2,30})", "located_at"),
        (r"(\S{2,20})\s+(?:owns?|manages?)\s+(\S{2,30})", "owns"),
        (r"(\S{2,20})\s+(?:knows?)\s+(\S{2,20})", "knows"),
    ]
    for pattern, rel in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            src, tgt = m.group(1).strip(), m.group(2).strip()
            skip_words = {"他", "她", "它", "我", "你", "这个", "那个", "什么", "怎么",
                          "the", "a", "an", "this", "that", "it", "he", "she"}
            if src.lower() not in skip_words and tgt.lower() not in skip_words:
                triples.append({"source": src, "relation": rel, "target": tgt})
    return triples


_rel_type_names = {v: k for k, v in RELATION_TYPES.items()}


def extract_entities(text: str) -> List[Dict]:
    """Extract entity-relation triples from text.

    Priority:
    1. LLM extraction (if enabled + API available) — JSON structured output
    2. Regex fallback (always available, synchronous)

    Config: config.yaml -> knowledge_graph.llm_extract.enabled (default: false)
    """
    # Check if LLM extraction is enabled
    cfg_path = get_config_path()
    llm_enabled = False
    if os.path.exists(cfg_path):
        try:
            import yaml as _y
            with open(cfg_path) as _f:
                _cfg = _y.safe_load(_f) or {}
            llm_enabled = _cfg.get("knowledge_graph", {}).get("llm_extract", {}).get("enabled", False)
        except Exception:
            pass

    if llm_enabled:
        triples = _llm_extract(text)
        if triples:
            return triples

    return _extract_fallback(text)


def _llm_extract(text: str) -> List[Dict]:
    """LLM-based entity-relation extraction with JSON structured output.

    Returns parsed triples, or empty list on failure/API error.
    """
    valid_rels = ", ".join(f'"{k}" ({v})' for k, v in sorted(RELATION_TYPES.items()))

    system_prompt = (
        "You are a precise entity-relation extractor. Given text, extract "
        "entity-relation triples that represent factual knowledge.\n\n"
        f"Valid relation types: {valid_rels}\n\n"
        "Rules:\n"
        "- Extract ONLY clear, factual relationships\n"
        "- Entity names should be specific (person names, tool names, company names)\n"
        "- Skip pronouns (he, she, it, \u4ed6, \u5979, \u5b83)\n"
        "- Skip vague or conversational statements\n"
        "- If no relations found, output: {\"triples\": []}\n\n"
        'Output valid JSON ONLY: {"triples": [{"source": "...", "relation": "...", "target": "..."}]}'
    )
    user_prompt = f"Extract relations from:\n{text[:1500]}"

    response = _call_llm(f"{system_prompt}\n\n{user_prompt}")
    if not response:
        return []

    try:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        result = json.loads(cleaned)
        triples = result.get("triples", [])
        validated = []
        rev_map = {v: k for k, v in RELATION_TYPES.items()}

        for t in triples:
            src = t.get("source", "").strip()
            rel = t.get("relation", "").strip()
            tgt = t.get("target", "").strip()
            if not src or not rel or not tgt:
                continue
            # Map display name -> key, or use as-is if already a key
            rel_key = rev_map.get(rel, rel)
            if rel_key not in RELATION_TYPES and rel not in RELATION_TYPES:
                continue
            skip_words = {"\u4ed6", "\u5979", "\u5b83", "\u6211", "\u4f60", "\u8fd9\u4e2a", "\u90a3\u4e2a",
                          "\u4ec0\u4e48", "\u600e\u4e48",
                          "the", "a", "an", "this", "that", "it", "he", "she"}
            if src.lower() not in skip_words and tgt.lower() not in skip_words:
                validated.append({"source": src, "relation": rel_key, "target": tgt})
        return validated
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════
# 时间辅助函数
# ═══════════════════════════════════════════════════════════

def _is_valid_at(item: dict, snapshot_at: str) -> bool:
    """Check if a relation or entity is valid at a given snapshot time.
    
    Logic: valid_from <= snapshot AND (valid_until IS NULL OR valid_until > snapshot)
    """
    vf = item.get("valid_from", "")
    vu = item.get("valid_until")
    if not vf or vf == "unknown":
        return True  # Can't determine, assume valid
    if vf > snapshot_at:
        return False  # Not yet valid at snapshot time
    if vu is not None and vu <= snapshot_at:
        return False  # Already expired before snapshot time
    return True


def _now() -> str:
    return datetime.now().isoformat()


# ═══════════════════════════════════════════════════════════
# 写入操作
# ═══════════════════════════════════════════════════════════

def add_triples(text: str, valid_from: str = None) -> int:
    """Extract entity-relation triples from text and add to knowledge graph.
    
    Args:
        text: Source text to extract from
        valid_from: Timestamp to use as valid_from (default: now).
                    Used by forgetting_curve distillation to set the memory's timestamp.
    
    Returns: Number of new relations added (not duplicates or reactivations)
    """
    # Content Security Gate
    try:
        from moyu_toolkit.defense_toolkit.integrity_checker import content_scan
        hits = content_scan(text)
        if hits:
            print(f"🔴 knowledge_graph: write blocked — detected: {', '.join(hits)}",
                  file=__import__('sys').stderr)
            return 0
    except Exception:
        pass

    triples = extract_entities(text)
    if not triples:
        return 0
    kg = _load_kg()
    _backfill_temporal(kg)
    now = valid_from or _now()
    added = 0
    for t in triples:
        sn, tn = _normalize(t["source"]), _normalize(t["target"])
        # Upsert entities
        for name, orig in [(sn, t["source"]), (tn, t["target"])]:
            if name not in kg["entities"]:
                kg["entities"][name] = {
                    "name": orig, "type": "entity",
                    "first_seen": now, "last_seen": now, "mention_count": 1,
                    "valid_from": now, "valid_until": None,
                }
            else:
                kg["entities"][name]["last_seen"] = now
                kg["entities"][name]["mention_count"] += 1
                # Reactivate entity if it was previously invalidated
                if kg["entities"][name].get("valid_until") is not None:
                    kg["entities"][name]["valid_until"] = None
        # ── Conflict detection: same (source, relation) with different target → invalidate old ──
        for r in kg["relations"]:
            if (r["source"] == sn and r["relation"] == t["relation"]
                    and r["target"] != tn and r.get("valid_until") is None):
                r["valid_until"] = now
                r["invalid_reason"] = f"superseded: new target '{t['target']}' ({now[:10]})"

        # Only add if no *active* record of this relation exists
        # Invalidated relations CAN be re-added (reactivation)
        exists_active = any(
            r["source"] == sn and r["target"] == tn and r["relation"] == t["relation"]
            and r.get("valid_until") is None
            for r in kg["relations"]
        )
        if not exists_active:
            kg["relations"].append({
                "source": sn, "target": tn, "relation": t["relation"],
                "weight": 1, "created": now,
                "valid_from": now, "valid_until": None, "invalid_reason": None,
            })
            added += 1
    if added:
        storage.write("knowledge_graph.json", kg)
    return added


def invalidate(source: str, target: str, relation: str,
               valid_until: str = None, reason: str = "") -> bool:
    """Mark a specific relation as invalidated.
    
    Sets valid_until on matching (source, target, relation) triples that
    are currently active (valid_until IS NULL).
    
    Args:
        source: Source entity name (raw, will be normalized)
        target: Target entity name (raw, will be normalized)
        relation: Relation type
        valid_until: When it became invalid (default: now)
        reason: Human-readable reason for invalidation
    
    Returns: True if any relation was invalidated
    """
    kg = _load_kg()
    _backfill_temporal(kg)
    sn, tn = _normalize(source), _normalize(target)
    until = valid_until or _now()
    found = False
    for r in kg["relations"]:
        if (r["source"] == sn and r["target"] == tn
                and r["relation"] == relation and r.get("valid_until") is None):
            r["valid_until"] = until
            r["invalid_reason"] = reason or ""
            found = True
    if found:
        storage.write("knowledge_graph.json", kg)
    return found


def invalidate_entity(entity_name: str, valid_until: str = None, reason: str = "") -> int:
    """Invalidate an entity and all its currently active relations.
    
    Sets valid_until on the entity itself, and on all relations
    where the entity is source or target.
    
    Args:
        entity_name: Entity name (raw, will be normalized)
        valid_until: When it became invalid (default: now)
        reason: Human-readable reason
    
    Returns: Number of items invalidated (entity + relations)
    """
    kg = _load_kg()
    _backfill_temporal(kg)
    en = _normalize(entity_name)
    until = valid_until or _now()
    count = 0
    
    # Invalidate relations where this entity is source or target
    for r in kg["relations"]:
        if (r["source"] == en or r["target"] == en) and r.get("valid_until") is None:
            r["valid_until"] = until
            r["invalid_reason"] = reason or f"Entity '{entity_name}' invalidated"
            count += 1
    
    # Invalidate the entity itself
    if en in kg["entities"] and kg["entities"][en].get("valid_until") is None:
        kg["entities"][en]["valid_until"] = until
        count += 1
    
    if count:
        storage.write("knowledge_graph.json", kg)
    return count


# ═══════════════════════════════════════════════════════════
# 查询操作
# ═══════════════════════════════════════════════════════════

def search(query: str, snapshot_at: str = None) -> list:
    """Search entities matching the query.
    
    Args:
        query: Search text (matched against entity names)
        snapshot_at: ISO date string for point-in-time query.
                     None = current time (only active relations).
                     "'all'" = include all (historical + current, no filter).
                     A date string = only relations valid at that time.
    
    Returns: [{entity: name, relations: [str, ...]}, ...]
    """
    kg = _load_kg()
    _backfill_temporal(kg)
    if not kg["entities"]:
        return []
    q_words = set(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', _normalize(query)))
    hits = []
    for eid, entity in kg["entities"].items():
        ew = set(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', _normalize(entity["name"])))
        if not (q_words & ew):
            continue
        related = []
        for r in kg["relations"]:
            if r["source"] != eid and r["target"] != eid:
                continue
            # Apply snapshot filter
            if snapshot_at == "all":
                pass  # Include all, no filter
            elif snapshot_at:
                if not _is_valid_at(r, snapshot_at):
                    continue
            else:
                # Default: only current active relations
                if r.get("valid_until") is not None:
                    continue
            # Format the relation
            if r["source"] == eid:
                tgt = kg["entities"].get(r["target"], {}).get("name", r["target"])
                label = RELATION_TYPES.get(r["relation"], r["relation"])
                text = f"{entity['name']} → {label} → {tgt}"
            else:
                src = kg["entities"].get(r["source"], {}).get("name", r["source"])
                label = RELATION_TYPES.get(r["relation"], r["relation"])
                text = f"{src} → {label} → {entity['name']}"
            # Add temporal annotation for non-current relations
            if r.get("valid_until") is not None:
                vu = r["valid_until"][:10] if r["valid_until"] else "?"
                text += f" [expired {vu}]"
            related.append(text)
        if related:
            hits.append({"entity": entity["name"], "relations": related[:8]})
    return hits


def get_entity_history(entity_name: str) -> dict:
    """Get the full timeline of an entity: all its relations (active and expired).
    
    Returns: {
        "entity": {name, valid_from, valid_until, ...},
        "timeline": [{"relation": ..., "valid_from": ..., "valid_until": ..., "status": "active"|"expired"}, ...]
    }
    """
    kg = _load_kg()
    _backfill_temporal(kg)
    en = _normalize(entity_name)
    entity = kg["entities"].get(en)
    if not entity:
        return {"entity": None, "timeline": []}
    
    timeline = []
    for r in kg["relations"]:
        if r["source"] != en and r["target"] != en:
            continue
        vu = r.get("valid_until")
        entry = {
            "relation": r["relation"],
            "valid_from": r.get("valid_from", "?"),
            "valid_until": vu or "current",
            "status": "expired" if vu else "active",
        }
        if r["source"] == en:
            tgt = kg["entities"].get(r["target"], {}).get("name", r["target"])
            entry["display"] = f"→ {RELATION_TYPES.get(r['relation'], r['relation'])} → {tgt}"
        else:
            src = kg["entities"].get(r["source"], {}).get("name", r["source"])
            entry["display"] = f"{src} → {RELATION_TYPES.get(r['relation'], r['relation'])} →"
        timeline.append(entry)
    
    timeline.sort(key=lambda x: x["valid_from"])
    return {"entity": entity, "timeline": timeline}


def add_cross_scene_tunnels() -> int:
    """Scan all scene-tagged memories for cross-scene entity overlaps.
    
    When the same entity appears in memories with different scene tags,
    create 'cross_scene' edges in the knowledge graph (MemPalace-inspired tunnels).
    
    Returns number of new tunnels created.
    """
    mem_path = os.path.join(STORAGE_PATH, "conversation_memory.json")
    if not os.path.exists(mem_path):
        return 0
    try:
        with open(mem_path) as f:
            memories = json.load(f)
    except Exception:
        return 0
    
    entity_scenes = {}
    for m in memories:
        scene = m.get("scene", "general")
        for e in m.get("entities", []):
            key = e.lower()
            if key not in entity_scenes:
                entity_scenes[key] = set()
            entity_scenes[key].add(scene)
    
    kg = _load_kg()
    _backfill_temporal(kg)
    existing_edges = {(r["source"], r["target"]) for r in kg["relations"] if r.get("relation") == "cross_scene"}
    added = 0
    now = _now()
    
    for entity, scenes in entity_scenes.items():
        if len(scenes) < 2:
            continue
        scenes_list = sorted(scenes)
        for i in range(len(scenes_list)):
            for j in range(i + 1, len(scenes_list)):
                edge = (_normalize(scenes_list[i]), _normalize(scenes_list[j]))
                if edge not in existing_edges:
                    kg["relations"].append({
                        "source": scenes_list[i], "target": scenes_list[j],
                        "relation": "cross_scene", "weight": 1,
                        "entity": entity, "created": now,
                        "valid_from": now, "valid_until": None, "invalid_reason": None,
                    })
                    existing_edges.add(edge)
                    added += 1
    if added:
        storage.write("knowledge_graph.json", kg)
    return added


# ═══════════════════════════════════════════════════════════
# 蒸馏（给遗忘曲线调用）
# ═══════════════════════════════════════════════════════════

def distill_from_memory(summary: str, timestamp: str = None) -> int:
    """Extract entity-relation triples from a memory summary and add to knowledge graph.
    
    Called by forgetting_curve before demoting a memory, so the structural
    knowledge survives the raw memory's removal.
    
    Uses regex fallback only (no LLM call — too expensive at scale). The patterns
    cover common Chinese and English entity-relation structures.
    
    Args:
        summary: Memory summary text
        timestamp: Memory's timestamp, used as valid_from (default: now)
    
    Returns: Number of new relations added to KG
    """
    if not summary:
        return 0
    triples = _extract_fallback(summary)
    if not triples:
        return 0
    
    kg = _load_kg()
    _backfill_temporal(kg)
    now = timestamp or _now()
    added = 0
    
    for t in triples:
        sn, tn = _normalize(t["source"]), _normalize(t["target"])
        # Ensure entities exist
        for name, orig in [(sn, t["source"]), (tn, t["target"])]:
            if name not in kg["entities"]:
                kg["entities"][name] = {
                    "name": orig, "type": "entity",
                    "first_seen": now, "last_seen": now, "mention_count": 1,
                    "valid_from": now, "valid_until": None,
                }
        # ── Conflict detection ──
        for r in kg["relations"]:
            if (r["source"] == sn and r["relation"] == t["relation"]
                    and r["target"] != tn and r.get("valid_until") is None):
                r["valid_until"] = now
                r["invalid_reason"] = f"superseded: new target '{t['target']}' ({now[:10]})"

        # Only add if this exact triple doesn't exist anywhere in KG
        exists = any(
            r["source"] == sn and r["target"] == tn and r["relation"] == t["relation"]
            for r in kg["relations"]
        )
        if not exists:
            kg["relations"].append({
                "source": sn, "target": tn, "relation": t["relation"],
                "weight": 1, "created": now,
                "valid_from": now, "valid_until": None, "invalid_reason": None,
            })
            added += 1
    
    if added:
        storage.write("knowledge_graph.json", kg)
    return added


# ═══════════════════════════════════════════════════════════
# 统计与展示
# ═══════════════════════════════════════════════════════════

def stats():
    kg = _load_kg()
    _backfill_temporal(kg)
    active_relations = [r for r in kg["relations"] if r.get("valid_until") is None]
    expired_relations = [r for r in kg["relations"] if r.get("valid_until") is not None]
    active_entities = [e for e in kg["entities"].values() if e.get("valid_until") is None]
    expired_entities = [e for e in kg["entities"].values() if e.get("valid_until") is not None]
    
    print(f"\n📊 MOYU Knowledge Graph")
    print("=" * 50)
    print(f"Entities:   {len(active_entities)} active + {len(expired_entities)} expired = {len(kg['entities'])} total")
    print(f"Relations:  {len(active_relations)} active + {len(expired_relations)} expired = {len(kg['relations'])} total")
    print()
    top = sorted(kg["entities"].items(), key=lambda x: -x[1].get("mention_count", 0))[:5]
    for eid, data in top:
        status = "⏳" if data.get("valid_until") else "✓"
        vu = f" → expired {data['valid_until'][:10]}" if data.get("valid_until") else ""
        name = data.get("name", eid)
        print(f"  {status} {name} ({data.get('mention_count', 0)} appearances){vu}")
    if active_relations:
        print(f"\n  Active relations: {len(active_relations)}")
    if expired_relations:
        print(f"  Expired (time-travel accessible): {len(expired_relations)}")


def demo() -> dict:
    return {
        "capability": 3,
        "title": "Knowledge Graph v2.4 — Temporal",
        "output": """📊 3/6  DEMO — Knowledge Graph with Time Travel
────────────────────────────────────
  Entities & relations with temporal tracking:

  Zhang Yi ──→ works at ──→ Smart Photo Frame  [2026-01 ~ current]
  Zhang Yi ──→ works at ──→ ByteDance           [2026-03 ~ current]
  Zhang Yi ──→ uses ──→ Flask
  Xiao Li ──→ works at ──→ Smart Photo Frame    [2026-01 ~ 2026-03, expired]
  Boss Li ──→ manages ──→ Smart Photo Frame

  Search "Zhang Yi"            → current relations only (default)
  Search "Zhang Yi" --snapshot all  → all, including expired
  Search "Xiao Li" --snapshot 2026-02  → relations valid on 2026-02

  Time-travel accessible: 3 expired relations preserved.""",
    }


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  extract <text>                          提取关系")
        print("  search <query>                          搜索（当前有效）")
        print("  search <query> --snapshot YYYY-MM-DD    时间回溯搜索")
        print("  search <query> --snapshot all           包含历史全部")
        print("  history <entity>                        实体完整时间线")
        print("  invalidate --source X --target Y --relation Z  失效关系")
        print("  invalidate --entity E                   失效实体及所有关系")
        print("  stats                                   统计")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "extract":
        n = add_triples(" ".join(sys.argv[2:]))
        print(f"Added {n} relations to knowledge graph")
    
    elif cmd == "search":
        args = sys.argv[2:]
        snapshot = None
        query_parts = []
        i = 0
        while i < len(args):
            if args[i] == "--snapshot" and i + 1 < len(args):
                snapshot = args[i + 1]
                i += 2
            else:
                query_parts.append(args[i])
                i += 1
        query = " ".join(query_parts)
        if not query:
            print("Error: search query required")
            sys.exit(1)
        results = search(query, snapshot_at=snapshot)
        if results:
            label = f" (snapshot: {snapshot})" if snapshot else " (current only)"
            print(f"\nQuery: \"{query}\"{label}")
            print("-" * 50)
            for h in results:
                print(f"#{h['entity']}:")
                for r in h["relations"]:
                    print(f"  {r}")
                print()
        else:
            print(f"No results for \"{query}\"")
    
    elif cmd == "history":
        if len(sys.argv) < 3:
            print("Error: history <entity>")
            sys.exit(1)
        result = get_entity_history(" ".join(sys.argv[2:]))
        if result["entity"] is None:
            print(f"Entity not found: {' '.join(sys.argv[2:])}")
            sys.exit(1)
        e = result["entity"]
        status = "active" if e.get("valid_until") is None else f"expired ({e['valid_until'][:10]})"
        print(f"\nEntity: {e['name']} ({status})")
        print(f"First seen: {e.get('first_seen', '?')[:10]}  |  Appearances: {e.get('mention_count', 0)}")
        print("-" * 50)
        for entry in result["timeline"]:
            icon = "✅" if entry["status"] == "active" else "⏳"
            vu_str = entry["valid_until"][:10] if entry["valid_until"] != "current" else "current"
            print(f"  {icon} {entry['display']}")
            print(f"     {entry['valid_from'][:10]} ~ {vu_str}")
    
    elif cmd == "invalidate":
        args = sys.argv[2:]
        source = target = relation = entity = None
        reason = ""
        i = 0
        while i < len(args):
            if args[i] == "--source" and i + 1 < len(args):
                source = args[i + 1]; i += 2
            elif args[i] == "--target" and i + 1 < len(args):
                target = args[i + 1]; i += 2
            elif args[i] == "--relation" and i + 1 < len(args):
                relation = args[i + 1]; i += 2
            elif args[i] == "--entity" and i + 1 < len(args):
                entity = args[i + 1]; i += 2
            elif args[i] == "--reason" and i + 1 < len(args):
                reason = args[i + 1]; i += 2
            else:
                i += 1
        if entity:
            count = invalidate_entity(entity, reason=reason)
            print(f"Invalidated {count} items (entity + relations) for '{entity}'")
        elif source and target and relation:
            ok = invalidate(source, target, relation, reason=reason)
            print(f"Invalidated {'✅' if ok else '❌ not found'}: {source} → {relation} → {target}")
        else:
            print("Usage: invalidate --source X --target Y --relation Z [--reason ...]")
            print("       invalidate --entity E [--reason ...]")
    
    elif cmd == "stats":
        stats()
    
    else:
        print(f"Unknown command: {cmd}")
