#!/usr/bin/env python3
"""moyu_snapshot.py — Export MOYU memory state to a read-only snapshot.

Usage:
    python3 moyu_snapshot.py                     # Create snapshot
    python3 moyu_snapshot.py --list              # List existing snapshots
    python3 moyu_snapshot.py --restore <file>    # Restore from snapshot
    python3 moyu_snapshot.py --json              # JSON output
"""

import sys
import os
import json
import shutil
from datetime import datetime

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)

from _moyu_paths import get_default_storage
STORAGE = get_default_storage()
SNAPSHOT_DIR = os.path.join(STORAGE, "snapshots")


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def create_snapshot(name: str = "") -> dict:
    """Export current memory state to a timestamped snapshot file."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    label = name or f"snapshot_{_ts()}"
    snapshot_path = os.path.join(SNAPSHOT_DIR, f"{label}.json")

    # Collect memory data
    memories = []
    mem_path = os.path.join(STORAGE, "conversation_memory.json")
    if os.path.exists(mem_path):
        try:
            with open(mem_path) as f:
                memories = json.load(f)
        except Exception:
            memories = []

    # Collect vector index summary (just counts, not full vectors)
    vec_count = 0
    vec_path = os.path.join(STORAGE, "vector_index.json")
    if os.path.exists(vec_path):
        try:
            with open(vec_path) as f:
                vec_data = json.load(f)
                vec_count = len(vec_data.get("vectors", []))
        except Exception:
            pass

    # Collect knowledge graph summary
    kg_count = 0
    kg_path = os.path.join(STORAGE, "knowledge_graph.json")
    if os.path.exists(kg_path):
        try:
            with open(kg_path) as f:
                kg = json.load(f)
                kg_count = len(kg.get("relations", []))
        except Exception:
            pass

    snapshot = {
        "snapshot_version": "1.0",
        "created_at": datetime.now().isoformat(),
        "label": label,
        "stats": {
            "memories": len(memories),
            "vectors": vec_count,
            "kg_relations": kg_count,
        },
        "memories": memories,
    }

    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    size_kb = max(1, os.path.getsize(snapshot_path) // 1024)

    return {
        "path": snapshot_path,
        "label": label,
        "size_kb": size_kb,
        "memories": len(memories),
        "vectors": vec_count,
        "kg_relations": kg_count,
    }


def list_snapshots() -> list:
    """List all available snapshots."""
    if not os.path.isdir(SNAPSHOT_DIR):
        return []

    snapshots = []
    for fname in sorted(os.listdir(SNAPSHOT_DIR), reverse=True):
        if fname.endswith(".json"):
            path = os.path.join(SNAPSHOT_DIR, fname)
            try:
                with open(path) as f:
                    data = json.load(f)
                mtime = os.path.getmtime(path)
                snapshots.append({
                    "file": fname,
                    "path": path,
                    "created": data.get("created_at", datetime.fromtimestamp(mtime).isoformat()),
                    "memories": data.get("stats", {}).get("memories", 0),
                    "size_kb": os.path.getsize(path) // 1024,
                    "label": data.get("label", fname),
                })
            except Exception:
                snapshots.append({
                    "file": fname,
                    "path": path,
                    "created": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
                    "memories": 0,
                    "size_kb": os.path.getsize(path) // 1024,
                    "label": fname,
                })
    return snapshots


def restore_snapshot(snapshot_path: str) -> dict:
    """Restore memory state from a snapshot file."""
    if not os.path.exists(snapshot_path):
        return {"ok": False, "error": f"Snapshot not found: {snapshot_path}"}

    try:
        with open(snapshot_path) as f:
            snapshot = json.load(f)
    except Exception as e:
        return {"ok": False, "error": f"Cannot read snapshot: {e}"}

    memories = snapshot.get("memories", [])
    if not memories:
        return {"ok": False, "error": "Snapshot contains no memories"}

    # Backup current state first
    backup_path = os.path.join(STORAGE, "backups", f"pre_restore_{_ts()}.json")
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    cur_path = os.path.join(STORAGE, "conversation_memory.json")
    if os.path.exists(cur_path):
        shutil.copy2(cur_path, backup_path)

    # Write restored memories
    with open(cur_path, "w") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "memories_restored": len(memories),
        "backup_path": backup_path,
        "note": "Run 'moyu index' to rebuild vector index from restored memories",
    }


def main(*args):
    json_mode = "--json" in sys.argv or ("--json" in args if args else False)
    list_mode = "--list" in sys.argv or ("--list" in args if args else False)
    restore_next = None
    for i, a in enumerate(sys.argv):
        if a == "--restore" and i + 1 < len(sys.argv):
            restore_next = sys.argv[i + 1]
    if not restore_next and args:
        for i, a in enumerate(args):
            if a == "--restore" and i + 1 < len(args):
                restore_next = args[i + 1]

    if restore_next:
        result = restore_snapshot(restore_next)
        if json_mode:
            json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
            print()
        else:
            if result.get("ok"):
                print(f"\n✅ Restored {result['memories_restored']} memories from snapshot")
                print(f"   Backup saved to: {result['backup_path']}")
                print(f"   ℹ️  {result['note']}\n")
            else:
                print(f"\n❌ Restore failed: {result.get('error')}\n")
        return

    if list_mode:
        snaps = list_snapshots()
        if json_mode:
            json.dump(snaps, sys.stdout, ensure_ascii=False, indent=2)
            print()
        else:
            if not snaps:
                print("\n📭 No snapshots found. Create one with: moyu snapshot\n")
            else:
                print(f"\n📸 Available Snapshots ({len(snaps)}):")
                print("=" * 56)
                for s in snaps:
                    print(f"  {s['created'][:19]}  {s['memories']:>4} mem  {s['size_kb']:>5} KB  {s['file']}")
                print()
                print("  Restore:  moyu snapshot --restore <filename>\n")
        return

    # Default: create snapshot
    name = ""
    for i, a in enumerate(sys.argv):
        if a == "--name" and i + 1 < len(sys.argv):
            name = sys.argv[i + 1]
    if not name and args:
        for i, a in enumerate(args):
            if a == "--name" and i + 1 < len(args):
                name = args[i + 1]

    result = create_snapshot(name)

    if json_mode:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(f"\n📸 Snapshot created: {result['label']}")
        print(f"   Path:   {result['path']}")
        print(f"   Size:   {result['size_kb']} KB")
        print(f"   Memory: {result['memories']} entries")
        if result['vectors']:
            print(f"   Vectors: {result['vectors']} indexed")
        if result['kg_relations']:
            print(f"   KG:     {result['kg_relations']} relations")
        print(f"   List:   moyu snapshot --list")
        print(f"   Restore: moyu snapshot --restore {result['label']}.json\n")


if __name__ == "__main__":
    main()
