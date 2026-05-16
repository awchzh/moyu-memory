# ==================== SQLite FTS5 Search ====================
# BM25 keyword search via SQLite FTS5 (English) + LIKE (Chinese).
# JSON files remain the primary storage. SQLite is a search-only index.
# Single memory_search.db file — backup = copy one file.

import json
import os
import re
from datetime import datetime

_DB = None  # lazy SQLite connection


def _get_db():
    """Get or create SQLite DB with FTS5 for BM25 search."""
    global _DB
    if _DB is not None:
        return _DB

    from agent_memory import _storage_path
    db_path = _storage_path("memory_search.db")
    _DB = __import__("sqlite3").connect(db_path, check_same_thread=False)
    _DB.execute("PRAGMA journal_mode=WAL")
    _DB.execute("PRAGMA synchronous=NORMAL")

    _DB.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id TEXT UNIQUE NOT NULL,
            timestamp TEXT NOT NULL,
            source TEXT DEFAULT '',
            summary TEXT NOT NULL,
            content_hash TEXT,
            scene TEXT DEFAULT '',
            demoted INTEGER DEFAULT 0,
            archived INTEGER DEFAULT 0
        )
    """)

    _DB.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            summary,
            content='memories',
            content_rowid='rowid'
        )
    """)

    _DB.executescript("""
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memory_fts(rowid, summary) VALUES (new.rowid, new.summary);
        END;
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memory_fts(memory_fts, rowid, summary) VALUES ('delete', old.rowid, old.summary);
        END;
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF summary ON memories BEGIN
            INSERT INTO memory_fts(memory_fts, rowid, summary) VALUES ('delete', old.rowid, old.summary);
            INSERT INTO memory_fts(rowid, summary) VALUES (new.rowid, new.summary);
        END;
    """)

    _DB.commit()
    return _DB


def _ensure_fts_indexed():
    """Sync all memories from JSON to SQLite FTS (called once on first use)."""
    db = _get_db()
    from agent_memory import _load_memories
    memories = _load_memories()
    if not memories:
        return

    count = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    if count >= len(memories):
        return

    existing = {r[0] for r in db.execute("SELECT memory_id FROM memories").fetchall()}
    to_insert = [m for m in memories if m.get("id") not in existing]

    for m in to_insert:
        try:
            db.execute(
                "INSERT OR IGNORE INTO memories (memory_id, timestamp, source, summary, content_hash, scene, demoted, archived) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (m.get("id", ""), m.get("timestamp", ""), m.get("source", ""),
                 m.get("summary", ""), m.get("content_hash", ""),
                 m.get("scene", ""), 1 if m.get("demoted") else 0,
                 1 if m.get("archived") else 0)
            )
        except Exception:
            pass
    db.commit()


def _fts_search(query: str, limit: int = 20) -> list:
    """BM25 search via SQLite FTS5 + LIKE for Chinese.
    Returns list of {memory_id, summary, timestamp, source, fts_rank}."""
    db = _get_db()
    _ensure_fts_indexed()

    tokens = query.strip().split()
    if not tokens:
        return []

    # Determine if query is CJK-heavy
    cjk_chars = sum(1 for c in query if '\u4e00' <= c <= '\u9fff')
    is_cjk_query = cjk_chars > len(query) * 0.3

    if is_cjk_query:
        # Chinese: SQL LIKE (reliable, handles CJK without token boundary issues)
        like_patterns = [f'%{t}%' for t in tokens if t]
        if not like_patterns:
            return []
        where_clause = " AND ".join(f"m.summary LIKE ?" for _ in like_patterns)
        try:
            rows = db.execute(
                f"""SELECT m.rowid, m.memory_id, m.summary, m.timestamp, m.source
                   FROM memories m
                   WHERE {where_clause}
                   LIMIT ?""",
                (*like_patterns, limit)
            ).fetchall()
            return [{
                "memory_id": r[1], "summary": r[2],
                "timestamp": r[3], "source": r[4], "fts_rank": -0.5
            } for r in rows]
        except Exception:
            return []

    # English/mixed: FTS5 MATCH
    parts = []
    for t in tokens:
        if not t:
            continue
        safe = t.replace('"', '""')
        parts.append(f'"{safe}"')

    fts_query = " ".join(parts)
    try:
        rows = db.execute(
            """SELECT m.rowid, m.memory_id, m.summary, m.timestamp, m.source, rank
               FROM memory_fts
               JOIN memories m ON m.rowid = memory_fts.rowid
               WHERE memory_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (fts_query, limit)
        ).fetchall()
        return [{
            "memory_id": r[1], "summary": r[2],
            "timestamp": r[3], "source": r[4], "fts_rank": r[5]
        } for r in rows]
    except Exception:
        return []
