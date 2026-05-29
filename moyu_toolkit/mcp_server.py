#!/usr/bin/env python3
"""
mcp_server.py — MOYU as Model Context Protocol (MCP) Server

Exposes MOYU memory/search/defense capabilities as MCP tools
over stdin/stdout (Stdio transport).

Usage:
    uvx --from moyu-memory@latest moyu-mcp
    # or
    python3 -m moyu_toolkit.mcp_server

Protocol: JSON-RPC 2.0 over stdio (standard MCP stdio transport).
Zero external dependencies — uses Python stdlib only.
"""

import json
import sys
import traceback
import io
from contextlib import redirect_stdout
from importlib.metadata import version as _pkg_version
from typing import Any, Dict, List, Optional

# ── MOYU imports ──────────────────────────────────────────────

from moyu_toolkit import agent_memory as mem
from moyu_toolkit.defense_toolkit.integrity_checker import content_scan, forensic_analysis, verify as integrity_verify
from moyu_toolkit.defense_toolkit.pii_redactor import redact as pii_redact
from moyu_toolkit.defense_toolkit.defense_log import get_recent as defense_log_recent, status as defense_log_status
from moyu_toolkit.defense_toolkit.signature import verify_memory_files, is_enabled as sig_is_enabled
from moyu_toolkit.frequency_guard import guard_stats, is_write_locked, write_lock_remaining
from moyu_toolkit import knowledge_graph as kg
from moyu_toolkit import knowledge_base as kb
from moyu_toolkit import self_reflection as sr
from moyu_toolkit import forgetting_curve as fc
from moyu_toolkit import memory_merge as mm
from moyu_toolkit import learner as ln
from moyu_toolkit.active_context import status as ac_status
from moyu_toolkit.moyu_doctor import diagnose


# ── MCP Protocol Helpers ──────────────────────────────────────

def _rpc_error(id: Any, code: int, message: str) -> Dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _rpc_result(id: Any, result: Any) -> Dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


# ── Tool Definitions ──────────────────────────────────────────

TOOLS: List[Dict] = [
    # ═══ 记忆与检索 ═══
    {
        "name": "search_memory",
        "description": "TEMPR semantic + keyword + recency + entity hybrid search. Returns top-k matching memories with relevance scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "description": "Number of results (1-20, default 5)", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_memory",
        "description": "Store a new memory. Automatically deduplicated by content hash, passed through content security gate and PII redaction. Returns memory ID or blocked status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Memory content"},
                "source": {"type": "string", "description": "Source label (default: 'user')", "default": "user"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_memory",
        "description": "Retrieve a single memory by its ID, including full content if available.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Memory ID (e.g. mem_20260529...)"},
            },
            "required": ["memory_id"],
        },
    },
    {
        "name": "list_memories",
        "description": "List all stored memories with pagination. Returns summaries with IDs and timestamps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "offset": {"type": "integer", "description": "Zero-based offset (default: 0)", "default": 0},
                "limit": {"type": "integer", "description": "Max entries to return (1-100, default: 50)", "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "memory_stats",
        "description": "MOYU memory statistics — total count, storage size, embedding status, source distribution, and index health.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "heat_rank",
        "description": "Show memory heat rankings — which memories are HOT, WARM, or COLD. Useful for understanding what MOYU considers important.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "top_k": {"type": "integer", "description": "Number of top entries (default: 20)", "default": 20},
            },
            "required": [],
        },
    },

    # ═══ 安全防御 ═══
    {
        "name": "defense_scan",
        "description": "Scan text for injection attacks, prompt leaks, and other security threats at the content gate. Returns safe/unsafe status and detected patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to scan for threats"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "forensic_scan",
        "description": "Run forensic analysis on a memory file — detect injection patterns, JSON corruption, file tampering. Returns detailed findings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to file to analyze (relative to storage dir)"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "integrity_check",
        "description": "Verify file integrity — check SHA256 checksums of all managed files against stored manifest. Returns pass/fail per file.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "pii_redact",
        "description": "Redact PII from text — phone numbers, ID cards, bank cards, emails, SSNs, IPs, API Keys (Chinese + English). Returns redacted text and detected PII types.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to redact"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "guard_status",
        "description": "Check write burst protection status — whether MOYU is currently in lockdown, remaining lock time, and recent write activity statistics.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "defense_log",
        "description": "View recent security events — signature failures, PII redactions, content blocks, burst rollbacks, loop detections. Returns last N events.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Number of events (default: 10)", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "signature_status",
        "description": "Check HMAC-SHA256 memory signature status — whether signing is enabled, and verify all memory files' signatures.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    # ═══ 知识图谱 ═══
    {
        "name": "kg_search",
        "description": "Search the knowledge graph — entities, relationships, and temporal snapshots. Returns matching triples.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Entity name or keyword to search"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kg_entity_history",
        "description": "Get the full timeline history of a specific entity — when it was mentioned, what relations changed over time.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "Entity name"},
            },
            "required": ["entity_name"],
        },
    },
    {
        "name": "kg_stats",
        "description": "Knowledge graph statistics — total entities, relations, scenes, and cross-scene tunnels.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    # ═══ 知识库 ═══
    {
        "name": "kb_search",
        "description": "Search the knowledge base — Markdown files indexed as working knowledge. Returns top-k matches.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword"},
                "top_k": {"type": "integer", "description": "Number of results (default: 3)", "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kb_list",
        "description": "List all files in the knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "kb_read",
        "description": "Read a specific knowledge base file by its filename.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Exact filename from kb_list"},
            },
            "required": ["filename"],
        },
    },

    # ═══ 遗忘与生命周期 ═══
    {
        "name": "forget_run",
        "description": "Run the forgetting curve demotion cycle — demotes stale memories from HOT→WARM→COLD based on access patterns. Returns summary of changes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context_pressure": {"type": "boolean", "description": "Accelerate under context pressure (default: false)", "default": False},
            },
            "required": [],
        },
    },
    {
        "name": "forget_protect",
        "description": "Protect a memory from being forgotten — pinned, immune to demotion cycle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Memory ID to protect"},
            },
            "required": ["memory_id"],
        },
    },
    {
        "name": "forget_unprotect",
        "description": "Remove protection from a memory — allowing it to be naturally demoted again.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Memory ID to unprotect"},
            },
            "required": ["memory_id"],
        },
    },
    {
        "name": "forget_stats",
        "description": "Forgetting curve statistics — protected count, tier distribution, last demotion cycle results.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "merge_run",
        "description": "Run memory merge cycle — detect related memories and merge them with LLM-synthesized summaries (original content preserved). Returns merge report.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "description": "Preview only, no actual merge (default: false)", "default": False},
            },
            "required": [],
        },
    },

    # ═══ 自我反思 ═══
    {
        "name": "reflect",
        "description": "Run self-reflection — detect contradictions across memories, find hidden connections, and identify topic shifts. Returns insights.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "compact": {"type": "boolean", "description": "Compact mode — fewer results (default: false)", "default": False},
            },
            "required": [],
        },
    },

    # ═══ 学习器 ═══
    {
        "name": "detect_signals",
        "description": "Detect user correction signals in text — identify patterns where the user is correcting the AI. Returns detected corrections.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to analyze for correction signals"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "learner_status",
        "description": "Learner status — learned behavior rules, correction stats, and signal history.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    # ═══ 工作记忆 ═══
    {
        "name": "active_context",
        "description": "Check active context status — current session task, accumulated context, working memory state.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    # ═══ 诊断 ═══
    {
        "name": "memory_doctor",
        "description": "Full MOYU health check — memory integrity, redundancy detection, knowledge graph status, security events, storage health. Returns categorized report with health score.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "quick": {"type": "boolean", "description": "Quick check — skip deep analysis (default: false)", "default": False},
            },
            "required": [],
        },
    },
]


# ── Tool Handlers ─────────────────────────────────────────────

def _capture(fn, *args, **kwargs):
    """Run a function that may print to stdout, capture both return value and output."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = fn(*args, **kwargs)
    output = buf.getvalue().strip()
    return result, output


def _handle_call(name: str, args: Dict) -> Dict:
    # ── 记忆与检索 ──
    if name == "search_memory":
        top_k = min(int(args.get("top_k", 5)), 20)
        results = mem.search(args["query"], top_k=top_k)
        return {"results": results}

    elif name == "add_memory":
        entry = mem.add_memory(args["text"], source=args.get("source", "user"))
        if entry is None:
            return {"status": "duplicate_or_blocked", "memory_id": None}
        return {"status": "ok", "memory_id": entry.get("id", "unknown")}

    elif name == "get_memory":
        m = mem.get_memory(args["memory_id"])
        if m is None:
            return {"error": f"Memory not found: {args['memory_id']}"}
        return {"memory": m}

    elif name == "list_memories":
        offset = int(args.get("offset", 0))
        limit = min(int(args.get("limit", 50)), 100)
        memories = mem._load_memories()
        # Sort newest first
        memories.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        page = memories[offset:offset + limit]
        return {
            "total": len(memories),
            "offset": offset,
            "limit": limit,
            "items": [{
                "id": m.get("id"),
                "timestamp": m.get("timestamp"),
                "source": m.get("source"),
                "summary": m.get("summary", "")[:200],
                "heat_tier": m.get("heat_tier"),
            } for m in page],
        }

    elif name == "memory_stats":
        try:
            result, output = _capture(mem.stats)
            if result is not None:
                if isinstance(result, dict):
                    result["_output"] = output
                    return result
                return {"stats": result, "_output": output}
            return {"raw": output}
        except Exception as e:
            return {"error": str(e), "status": "stats_unavailable"}

    elif name == "heat_rank":
        top_k = min(int(args.get("top_k", 20)), 100)
        memories = mem._load_memories()
        # Sort by heat
        memories.sort(key=lambda x: x.get("heat", 0), reverse=True)
        ranked = memories[:top_k]
        mem._recalc_heat_tiers()
        return {"top_k": top_k, "items": [{
            "id": m.get("id"),
            "heat": m.get("heat", 0),
            "heat_tier": m.get("heat_tier", "cold"),
            "summary": m.get("summary", "")[:120],
            "source": m.get("source"),
            "last_accessed": m.get("last_accessed"),
        } for m in ranked]}

    # ── 安全防御 ──
    elif name == "defense_scan":
        hits = content_scan(args["text"])
        safe = len(hits) == 0
        return {
            "safe": safe,
            "threats": hits,
            "summary": "No threats detected" if safe else f"Found {len(hits)} threat(s)",
        }

    elif name == "forensic_scan":
        try:
            result = forensic_analysis(args["file_path"])
            return {"findings": result} if isinstance(result, dict) else {"report": str(result)}
        except Exception as e:
            return {"error": str(e)}

    elif name == "integrity_check":
        try:
            result, output = _capture(integrity_verify)
            if isinstance(result, dict):
                result["_output"] = output
                return result
            return {"report": str(result) if result else output}
        except Exception as e:
            return {"error": str(e)}

    elif name == "pii_redact":
        redacted, pii_types = pii_redact(args["text"])
        return {
            "redacted_text": redacted,
            "detected_types": pii_types,
            "was_redacted": len(pii_types) > 0,
        }

    elif name == "guard_status":
        stats = guard_stats()
        stats["is_write_locked"] = is_write_locked()
        stats["write_lock_remaining_seconds"] = write_lock_remaining()
        return stats

    elif name == "defense_log":
        count = min(int(args.get("count", 10)), 50)
        events = defense_log_recent(count)
        log_status = defense_log_status()
        return {"events": events, "total_events": log_status.get("total_entries", 0)}

    elif name == "signature_status":
        enabled = sig_is_enabled()
        result = {"signing_enabled": enabled}
        if enabled:
            verify_result, output = _capture(verify_memory_files)
            result["verify"] = verify_result
            if output:
                result["_output"] = output
        return result

    # ── 知识图谱 ──
    elif name == "kg_search":
        try:
            results = kg.search(args["query"])
            return {"results": results}
        except Exception as e:
            return {"error": str(e)}

    elif name == "kg_entity_history":
        try:
            history = kg.get_entity_history(args["entity_name"])
            return {"entity": args["entity_name"], "history": history}
        except Exception as e:
            return {"error": str(e)}

    elif name == "kg_stats":
        try:
            result, output = _capture(kg.stats)
            return {"stats": result if result else output}
        except Exception as e:
            return {"error": str(e)}

    # ── 知识库 ──
    elif name == "kb_search":
        try:
            results = kb.search(args["query"], top_k=int(args.get("top_k", 3)))
            return {"results": results}
        except Exception as e:
            return {"error": str(e)}

    elif name == "kb_list":
        try:
            files = kb.list_files()
            return {"files": files}
        except Exception as e:
            return {"error": str(e)}

    elif name == "kb_read":
        try:
            content = kb.read(args["filename"])
            if content is None:
                return {"error": f"File not found: {args['filename']}"}
            return {"filename": args["filename"], "content": content}
        except Exception as e:
            return {"error": str(e)}

    # ── 遗忘与生命周期 ──
    elif name == "forget_run":
        try:
            pressure = bool(args.get("context_pressure", False))
            result, output = _capture(fc.run, context_pressure=pressure)
            return {"result": result if result else output}
        except Exception as e:
            return {"error": str(e)}

    elif name == "forget_protect":
        try:
            ok = fc.protect(args["memory_id"])
            return {"protected": ok, "memory_id": args["memory_id"]}
        except Exception as e:
            return {"error": str(e)}

    elif name == "forget_unprotect":
        try:
            ok = fc.unprotect(args["memory_id"])
            return {"unprotected": ok, "memory_id": args["memory_id"]}
        except Exception as e:
            return {"error": str(e)}

    elif name == "forget_stats":
        try:
            result, output = _capture(fc.stats)
            protected = fc.protected_ids()
            return {
                "protected_count": len(protected),
                "protected_ids": protected,
                "stats": result if result else output,
            }
        except Exception as e:
            return {"error": str(e)}

    elif name == "merge_run":
        try:
            dry_run = bool(args.get("dry_run", False))
            result, output = _capture(mm.run, dry_run=dry_run)
            return {"result": result if result else output, "dry_run": dry_run}
        except Exception as e:
            return {"error": str(e)}

    # ── 自我反思 ──
    elif name == "reflect":
        try:
            compact = bool(args.get("compact", False))
            if compact:
                result, output = _capture(sr.run_compact)
            else:
                result, output = _capture(sr.run)
            contradictions = sr.find_contradictions()
            connections = sr.find_connections()
            return {
                "result": result if result else output,
                "contradictions": len(contradictions),
                "connections": len(connections),
            }
        except Exception as e:
            return {"error": str(e)}

    # ── 学习器 ──
    elif name == "detect_signals":
        try:
            corrections = ln.detect_corrections(args["text"])
            return {"signals": corrections, "count": len(corrections)}
        except Exception as e:
            return {"error": str(e)}

    elif name == "learner_status":
        try:
            rules = ln.format_behavior_rules()
            stats = ln.stats()
            signals = ln.signals()
            return {
                "behavior_rules": rules,
                "stats": stats if isinstance(stats, dict) else {"raw": str(stats)},
                "signals": signals,
            }
        except Exception as e:
            return {"error": str(e)}

    # ── 工作记忆 ──
    elif name == "active_context":
        try:
            status = ac_status()
            return status if isinstance(status, dict) else {"status": str(status)}
        except Exception as e:
            return {"error": str(e)}

    # ── 诊断 ──
    elif name == "memory_doctor":
        quick = bool(args.get("quick", False))
        try:
            result, output = _capture(diagnose, quick=quick)
            if isinstance(result, dict):
                result["_output"] = output
                return result
            return {"report": str(result) if result else output}
        except Exception as e:
            return {"error": str(e), "status": "diagnose_failed"}

    return {"error": f"Unknown tool: {name}"}


# ── Main Event Loop ───────────────────────────────────────────

def main():
    """MCP stdio server main loop — reads JSON-RPC 2.0 from stdin,
    writes responses to stdout. Logging goes to stderr."""
    _log("MOYU MCP Server starting...")

    server_info = {
        "protocolVersion": "2025-03-26",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "moyu-memory", "version": _pkg_version("moyu-memory")},
    }

    initialized = False

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _log(f"Invalid JSON received: {line[:200]}")
            continue

        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            _write(_rpc_result(msg_id, server_info))
            initialized = True
            continue

        if method in ("notifications/initialized", "initialized"):
            continue

        if not initialized:
            _log(f"Rejecting method {method} before initialize")
            _write(_rpc_error(msg_id, -32000, "Server not initialized"))
            continue

        if method == "tools/list":
            _write(_rpc_result(msg_id, {"tools": TOOLS}))
            continue

        if method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            try:
                result = _handle_call(name, arguments)
                content = [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, indent=2),
                    }
                ]
                _write(_rpc_result(msg_id, {"content": content}))
            except Exception as e:
                tb = traceback.format_exc()
                _log(f"Error calling tool '{name}': {e}\n{tb}")
                _write(_rpc_error(msg_id, -32603, str(e)))
            continue

        if method == "ping":
            _write(_rpc_result(msg_id, {}))
            continue

        _log(f"Unknown method: {method}")
        _write(_rpc_error(msg_id, -32601, f"Method not found: {method}"))


def _log(msg: str):
    """Log to stderr — doesn't interfere with stdio MCP protocol."""
    print(f"[mcp] {msg}", file=sys.stderr, flush=True)


def _write(msg: Dict):
    """Write a JSON-RPC message to stdout, one JSON object per line."""
    line = json.dumps(msg, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
