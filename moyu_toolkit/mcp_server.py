#!/usr/bin/env python3
"""
mcp_server.py — MOYU as Model Context Protocol (MCP) Server

Exposes MOYU memory/search/defense capabilities as MCP tools
over stdin/stdout (Stdio transport).

Usage:
    uvx moyu-mcp
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
from moyu_toolkit.defense_toolkit.integrity_checker import content_scan
from moyu_toolkit.moyu_doctor import diagnose

# ── MCP Protocol Helpers ──────────────────────────────────────


def _rpc_error(id: Any, code: int, message: str) -> Dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _rpc_result(id: Any, result: Any) -> Dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


# ── Tool Definitions ──────────────────────────────────────────

TOOLS: List[Dict] = [
    {
        "name": "search_memory",
        "description": (
            "Search MOYU memory using semantic + keyword (TEMPR) hybrid retrieval. "
            "Returns top-k matching memories with relevance scores."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {
                    "type": "integer",
                    "description": "Number of results (1-20, default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_memory",
        "description": (
            "Add a new memory to MOYU. Automatically deduplicated by content hash. "
            "Returns the memory ID of the stored entry."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Memory content"},
                "source": {
                    "type": "string",
                    "description": "Source label (default: 'user')",
                    "default": "user",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "memory_stats",
        "description": "Get MOYU memory statistics — total count, storage size, embedding status, and index health.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "defense_scan",
        "description": (
            "Scan text for injection attacks, prompt leaks, and other security threats. "
            "Returns safe/unsafe status and list of detected threat patterns."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to scan for threats"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "memory_doctor",
        "description": (
            "Run MOYU health check — diagnoses memory integrity, redundancy, "
            "security events, knowledge graph status, and storage health. "
            "Returns detailed per-category check results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "quick": {
                    "type": "boolean",
                    "description": "Quick check — skip deep analysis (default: false)",
                    "default": False,
                },
            },
            "required": [],
        },
    },
]


# ── Tool Handlers ─────────────────────────────────────────────


def _handle_call(name: str, args: Dict) -> Dict:
    if name == "search_memory":
        query = args["query"]
        top_k = min(int(args.get("top_k", 5)), 20)
        results = mem.search(query, top_k=top_k)
        return {"results": results}

    elif name == "add_memory":
        text = args["text"]
        source = args.get("source", "user")
        entry = mem.add_memory(text, source=source)
        if entry is None:
            return {"status": "duplicate_or_blocked", "memory_id": None}
        return {"status": "ok", "memory_id": entry.get("id", "unknown")}

    elif name == "memory_stats":
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = mem.stats()
            output = buf.getvalue().strip()
            if result is not None:
                return result
            return {"raw": output, "note": "stats printed to stdout"}
        except Exception as e:
            return {"error": str(e), "status": "stats_unavailable"}

    elif name == "defense_scan":
        text = args["text"]
        hits = content_scan(text)
        safe = len(hits) == 0
        return {
            "safe": safe,
            "threats": hits,
            "summary": "No threats detected" if safe else f"Found {len(hits)} threat(s)",
        }

    elif name == "memory_doctor":
        quick = bool(args.get("quick", False))
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diagnose(quick=quick)
            output = buf.getvalue().strip()
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

        # ── Initialize ──
        if method == "initialize":
            _write(_rpc_result(msg_id, server_info))
            initialized = True
            continue

        # ── Initialized notification ──
        if method in ("notifications/initialized", "initialized"):
            continue

        if not initialized:
            _log(f"Rejecting method {method} before initialize")
            _write(_rpc_error(msg_id, -32000, "Server not initialized"))
            continue

        # ── tools/list ──
        if method == "tools/list":
            _write(_rpc_result(msg_id, {"tools": TOOLS}))
            continue

        # ── tools/call ──
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

        # ── ping / health ──
        if method == "ping":
            _write(_rpc_result(msg_id, {}))
            continue

        # Unknown method — spec says servers must respond with method not found
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
