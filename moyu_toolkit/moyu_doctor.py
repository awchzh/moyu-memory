#!/usr/bin/env python3
"""moyu_doctor.py — MOYU Memory Health Check

One-command diagnostic:
  1. Memory redundancy (minhash approximate dedup)
  2. Stale knowledge graph relations
  3. Broken cross-session references
  4. Missing integrity manifest
  5. Security event summary (recent blocks, burst triggers)
  6. Overall health score

Usage:
    python3 moyu_doctor.py
    python3 moyu_doctor.py --quick    # Skip heavy checks
    python3 moyu_doctor.py --json     # Machine-readable
"""

import sys
import os
import json
import hashlib
import time
from datetime import datetime

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)

from _moyu_paths import get_default_storage
STORAGE = get_default_storage()


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _load_json(filename, default=None):
    path = os.path.join(STORAGE, filename)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return default or []
    return default or []


# ═══════════════════════════════════════════════════════════════
# Check 1: Memory Redundancy
# ═══════════════════════════════════════════════════════════════

def _minhash_sig(text: str, num_hashes: int = 5) -> list:
    """Compute minhash signature for a text string."""
    # Simple word-level shingling
    words = text.lower().split()
    if len(words) < 3:
        return []
    sig = [float('inf')] * num_hashes
    for i in range(len(words) - 2):
        shingle = ' '.join(words[i:i+3])
        for j in range(num_hashes):
            h = int(hashlib.md5(f"{j}:{shingle}".encode()).hexdigest()[:8], 16)
            if h < sig[j]:
                sig[j] = h
    return sig


def _jaccard_similarity(sig1: list, sig2: list) -> float:
    """Estimate Jaccard similarity from minhash signatures."""
    if not sig1 or not sig2:
        return 0.0
    matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
    return matches / len(sig1)


def check_redundancy(threshold: float = 0.7, quick: bool = False) -> dict:
    """Find highly similar memory pairs."""
    memories = _load_json("conversation_memory.json")
    if not memories:
        return {"count": 0, "pairs": [], "message": "No memories to check"}
    
    if len(memories) < 2:
        return {"count": 0, "pairs": [], "message": "Only 1 memory, no redundancy possible"}
    
    # Sample if quick mode
    mems = memories[:50] if quick else memories
    
    # Compute signatures
    sigs = []
    for m in mems:
        summary = m.get("summary", "")
        sig = _minhash_sig(summary)
        sigs.append(sig)
    
    # Compare pairs (limited)
    max_pairs = 20 if quick else min(100, len(mems) * 2)
    pairs = []
    compared = 0
    for i in range(len(mems)):
        for j in range(i + 1, len(mems)):
            if compared >= max_pairs:
                break
            sim = _jaccard_similarity(sigs[i], sigs[j])
            if sim >= threshold:
                pairs.append({
                    "id1": mems[i].get("id", "?")[:16],
                    "id2": mems[j].get("id", "?")[:16],
                    "summary1": mems[i].get("summary", "")[:50],
                    "summary2": mems[j].get("summary", "")[:50],
                    "similarity": round(sim, 3),
                })
            compared += 1
        if compared >= max_pairs:
            break
    
    return {
        "count": len(pairs),
        "total_memories": len(mems),
        "pairs": pairs[:10],  # limit display
        "note": "Redundancy detected" if len(pairs) > 3 else "OK",
    }


# ═══════════════════════════════════════════════════════════════
# Check 2: Stale KG Relations
# ═══════════════════════════════════════════════════════════════

def check_knowledge_graph() -> dict:
    """Check knowledge graph for stale/expired relations."""
    kg_path = os.path.join(STORAGE, "knowledge_graph.json")
    if not os.path.exists(kg_path):
        return {"status": "no_graph", "message": "No knowledge graph found"}
    try:
        with open(kg_path) as f:
            kg = json.load(f)
    except Exception:
        return {"status": "corrupted", "message": "Knowledge graph file is corrupted"}
    
    relations = kg.get("relations", [])
    total = len(relations)
    expired = sum(1 for r in relations if r.get("expired"))
    active = total - expired
    
    # Find very old active relations (>30 days since created)
    old_active = 0
    now = time.time()
    for r in relations:
        if not r.get("expired"):
            created = r.get("created_at", 0)
            if created and isinstance(created, (int, float)) and now - created > 30 * 86400:
                old_active += 1
    
    return {
        "status": "ok",
        "total_relations": total,
        "active": active,
        "expired": expired,
        "old_active": old_active,
        "suggestion": "Consider archiving" if old_active > 5 else "OK",
    }


# ═══════════════════════════════════════════════════════════════
# Check 3: Broken References
# ═══════════════════════════════════════════════════════════════

def check_references() -> dict:
    """Check for broken cross-session or working-memory references."""
    issues = []
    
    # Check working memory for references to deleted memories
    wm_path = os.path.join(STORAGE, "active_context.json")
    if os.path.exists(wm_path):
        try:
            with open(wm_path) as f:
                wm = json.load(f) if os.path.getsize(wm_path) > 0 else {}
        except Exception:
            wm = {}
        
        refs = wm.get("refs", []) or wm.get("references", [])
        if refs:
            # Check if referenced memories still exist
            memories = _load_json("conversation_memory.json")
            mem_ids = {m.get("id", "") for m in memories}
            missing = [r for r in refs if r not in mem_ids]
            if missing:
                issues.append(f"Working memory references {len(missing)} deleted memory(-ies)")
    
    # Check compression refs
    ref_path = os.path.join(STORAGE, "refs")
    if os.path.isdir(ref_path):
        ref_count = len([f for f in os.listdir(ref_path) if f.endswith('.json')])
    else:
        ref_count = 0
    
    return {
        "broken_refs": len(issues),
        "issues": issues[:5],
        "total_compressed_refs": ref_count,
        "note": "OK" if not issues else f"{len(issues)} broken reference(s)",
    }


# ═══════════════════════════════════════════════════════════════
# Check 4: Integrity
# ═══════════════════════════════════════════════════════════════

def check_integrity() -> dict:
    """Check if integrity manifest exists and covers key files."""
    manifest_path = os.path.join(STORAGE, "manifest.json")
    if not os.path.exists(manifest_path):
        return {
            "manifest": False,
            "protected_files": 0,
            "note": "Run 'moyu init' to set up file integrity protection",
        }
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        files = manifest.get("files", {}) or manifest
        return {
            "manifest": True,
            "protected_files": len(files),
            "note": "OK" if len(files) >= 3 else "Only {} files protected, consider adding more".format(len(files)),
        }
    except Exception:
        return {"manifest": "corrupted", "protected_files": 0, "note": "Manifest corrupted, re-run 'moyu init'"}


# ═══════════════════════════════════════════════════════════════
# Check 5: Security Events
# ═══════════════════════════════════════════════════════════════

def check_security_events(days: int = 7) -> dict:
    """Summarize recent security events."""
    log = _load_json("security_log.json", [])
    if not log:
        return {"events": 0, "message": "No security events logged"}
    
    cutoff = time.time() - days * 86400
    def _to_ts(v):
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            try:
                return float(v)
            except (ValueError, TypeError):
                return None
        return None

    recent = [e for e in log if (ts := _to_ts(e.get("timestamp"))) is not None and ts >= cutoff]
    
    blocks = sum(1 for e in recent if "block" in str(e.get("event", "")).lower() or "拦截" in str(e.get("event", "")))
    bursts = sum(1 for e in recent if "burst" in str(e.get("event", "")).lower() or "爆发" in str(e.get("event", "")))
    
    return {
        "events": len(recent),
        "blocks": blocks,
        "bursts": bursts,
        "total_logged": len(log),
        "note": "OK" if bursts == 0 else f"{bursts} burst trigger(s) in past {days} days",
    }


# ═══════════════════════════════════════════════════════════════
# Check 6: Storage Health
# ═══════════════════════════════════════════════════════════════

def check_storage() -> dict:
    """Check storage directory and file integrity."""
    issues = []
    
    # Expected files
    expected = {
        "conversation_memory.json": "Memory data",
        "vector_index.json": "Vector index",
    }
    
    for fname, desc in expected.items():
        path = os.path.join(STORAGE, fname)
        if not os.path.exists(path):
            issues.append(f"{desc} ({fname}) not found")
        elif os.path.getsize(path) == 0:
            issues.append(f"{desc} ({fname}) is empty")
    
    # Backup check
    backup_dir = os.path.join(STORAGE, "backups")
    if os.path.isdir(backup_dir):
        backups = [f for f in os.listdir(backup_dir) if f.endswith('.json')]
    else:
        backups = []
    
    return {
        "issues": issues,
        "storage_path": STORAGE,
        "backup_count": len(backups),
        "last_backup": max([os.path.getmtime(os.path.join(backup_dir, f)) for f in backups]) if backups else None,
        "note": "OK" if not issues else "; ".join(issues),
    }


# ═══════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════

def compute_health_score(checks: dict) -> tuple:
    """Compute overall health score and grade."""
    score = 100
    
    # Deduct for issues
    if checks.get("redundancy", {}).get("count", 0) > 3:
        score -= 10
    if checks.get("redundancy", {}).get("count", 0) > 10:
        score -= 5
    
    kg = checks.get("knowledge_graph", {})
    if kg.get("expired", 0) > 10:
        score -= 5
    if kg.get("old_active", 0) > 10:
        score -= 5
    
    refs = checks.get("references", {})
    if refs.get("broken_refs", 0) > 0:
        score -= 10 * refs["broken_refs"]
    
    integrity = checks.get("integrity", {})
    if not integrity.get("manifest"):
        score -= 15
    
    sec = checks.get("security", {})
    if sec.get("bursts", 0) > 0:
        score -= 10 * min(sec["bursts"], 3)
    
    storage = checks.get("storage", {})
    if storage.get("issues"):
        score -= 5 * len(storage["issues"])
    
    score = max(0, min(100, score))
    
    if score >= 90:
        grade = "A (Healthy)"
    elif score >= 75:
        grade = "B (Good)"
    elif score >= 60:
        grade = "C (Fair)"
    elif score >= 40:
        grade = "D (Poor)"
    else:
        grade = "F (Critical)"
    
    return score, grade


def print_report(checks: dict, score: int, grade: str):
    """Print formatted health report."""
    print()
    print("=" * 56)
    print("  🏥  MOYU Memory Doctor")
    print("=" * 56)
    
    # Health score
    score_bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
    print(f"  Health:     {score_bar}  {score}/100  {grade}")
    print()
    
    # 1. Redundancy
    red = checks.get("redundancy", {})
    rcount = red.get("count", 0)
    rtotal = red.get("total_memories", 0)
    if rcount == 0:
        red_status = "✅ No redundancy detected"
    elif rcount <= 3:
        red_status = f"ℹ️  {rcount} similar pair(s) found (minor)"
    else:
        red_status = f"⚠️  {rcount} similar pair(s) found in {rtotal} memories"
    print(f"  📋 Memory Redundancy:  {red_status}")
    for p in red.get("pairs", [])[:3]:
        print(f"       ~{p['similarity']:.0%}  \"{p['summary1'][:30]}\"  ↔  \"{p['summary2'][:30]}\"")
    print()
    
    # 2. Knowledge graph
    kg = checks.get("knowledge_graph", {})
    if kg.get("status") == "no_graph":
        print(f"  📊 Knowledge Graph:    ℹ️  Not in use")
    elif kg.get("status") == "corrupted":
        print(f"  📊 Knowledge Graph:    ❌ Corrupted")
    else:
        print(f"  📊 Knowledge Graph:    {kg.get('active', 0)} active, {kg.get('expired', 0)} expired, {kg.get('old_active', 0)} old")
        if kg.get("expired", 0) > 0:
            print(f"       Tip: Run 'moyu kg stats' to review expired relations")
    print()
    
    # 3. References
    refs = checks.get("references", {})
    br = refs.get("broken_refs", 0)
    if br == 0:
        ref_status = "✅ Clean"
    else:
        ref_status = f"⚠️  {br} broken reference(s)"
    print(f"  🔗 Cross-References:   {ref_status}")
    for issue in refs.get("issues", []):
        print(f"       • {issue}")
    print(f"       Compressed refs: {refs.get('total_compressed_refs', 0)}")
    print()
    
    # 4. Integrity
    integ = checks.get("integrity", {})
    if integ.get("manifest") is True:
        print(f"  🛡️  Integrity:          ✅ Manifest OK ({integ.get('protected_files', 0)} files)")
    else:
        print(f"  🛡️  Integrity:          ⚠️  {integ.get('note', 'Not set up')}")
    print()

    # 4b. Signatures (optional)
    sig = checks.get("signatures", {})
    if sig.get("enabled"):
        if sig.get("failed", 0) == 0:
            print(f"  ✍️  Signatures:         ✅ All {sig['ok']}/{sig['total']} files OK")
        else:
            print(f"  ✍️  Signatures:         ⚠️  {sig['failed']}/{sig['total']} files FAILED — {sig.get('message', '')}")
    else:
        print(f"  ✍️  Signatures:         ℹ️  Disabled (set MOYU_SIGN_KEY to enable)")
    print()

    # 5. Security events
    sec = checks.get("security", {})
    print(f"  🔔 Security Events:    {sec.get('events', 0)} events in 7 days")
    print(f"       Blocks: {sec.get('blocks', 0)}  |  Burst triggers: {sec.get('bursts', 0)}")
    if sec.get("bursts", 0) > 0:
        print(f"       ⚠️  Write bursts detected — check your memory write patterns")
    print()
    
    # 6. Storage
    st = checks.get("storage", {})
    print(f"  💾 Storage:            {st.get('storage_path', '?')}")
    print(f"       Backups: {st.get('backup_count', 0)}  |  Issues: {st.get('issues', []) or 'None'}")
    if st.get("last_backup"):
        lb = datetime.fromtimestamp(st["last_backup"]).strftime("%Y-%m-%d %H:%M")
        print(f"       Last backup: {lb}")
    print()
    
    # Summary
    print("  ── Summary ──")
    if score >= 90:
        print("  ✅ All systems healthy. No action needed.")
    elif score >= 75:
        print("  ℹ️  Minor issues detected. Review suggestions above.")
    elif score >= 60:
        print("  ⚠️  Several issues found. Recommend reviewing within the week.")
    else:
        print("  ❌ Critical issues detected. Immediate attention recommended.")
    print()
    print("=" * 56)
    print()


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def diagnose(quick: bool = False) -> dict:
    """Run all checks and return structured results."""
    checks = {}
    checks["redundancy"] = check_redundancy(quick=quick)
    checks["knowledge_graph"] = check_knowledge_graph()
    checks["references"] = check_references()
    checks["integrity"] = check_integrity()
    checks["signatures"] = _check_signatures()
    checks["security"] = check_security_events()
    checks["storage"] = check_storage()
    return checks


def _check_signatures() -> dict:
    """Check memory digital signatures (optional)."""
    try:
        from moyu_toolkit.defense_toolkit.signature import verify_memory_files, is_enabled
        if not is_enabled():
            return {"enabled": False, "message": "Signing disabled (set MOYU_SIGN_KEY)"}
        result = verify_memory_files()
        return {
            "enabled": True,
            "ok": result["ok"],
            "failed": result["failed"],
            "total": result["checked"],
            "message": "All signatures OK" if result["failed"] == 0 else f"{result['failed']}/{result['checked']} files have mismatched signatures",
        }
    except Exception as e:
        return {"enabled": False, "message": f"Signatures unavailable: {e}"}


def main(*args):
    flags = set(sys.argv[1:])
    quick = "--quick" in flags
    json_mode = "--json" in flags
    fix_mode = "--fix" in flags

    if fix_mode:
        _run_fix()
        return

    checks = diagnose(quick)
    score, grade = compute_health_score(checks)

    if json_mode:
        report = {"score": score, "grade": grade, "checks": checks}
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print_report(checks, score, grade)


def _run_fix():
    """Run signature verification and auto-recovery."""
    print()
    print("=" * 56)
    print("  🔧  Memory Integrity — Verify & Auto-Recovery")
    print("=" * 56)
    try:
        from moyu_toolkit.defense_toolkit.signature import verify_and_recover, is_enabled
        if not is_enabled():
            print("  ℹ️  Signatures disabled. Set MOYU_SIGN_KEY to enable.")
            return
        result = verify_and_recover()
        print(f"  Checked: {result['checked']} files")
        print(f"  Recovered: {result['recovered']} files")
        if result['unrecoverable'] > 0:
            print(f"  ⚠️  Unrecoverable: {result['unrecoverable']} files — manual attention needed")
            print(f"  Status: {result['status']}")
        else:
            print(f"  ✅ All files healthy")
        print()
    except Exception as e:
        print(f"  ❌ Error: {e}")
        print()


if __name__ == "__main__":
    main()
