"""Deterministic local stdio MCP fixture; it never opens a network socket."""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Mapping


TOOLS = [
    {
        "name": "echo",
        "description": "Return one local text value.",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string", "maxLength": 4096}},
            "required": ["message"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_fixture",
        "description": "List deterministic local fixture record identifiers.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "read_fake_record",
        "description": "Read one deterministic local fixture record.",
        "inputSchema": {
            "type": "object",
            "properties": {"record_id": {"type": "string", "enum": ["alpha", "beta"]}},
            "required": ["record_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "calculate",
        "description": "Calculate the sum of two local numbers.",
        "inputSchema": {
            "type": "object",
            "properties": {"left": {"type": "number"}, "right": {"type": "number"}},
            "required": ["left", "right"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "set_fixture_note",
        "description": "Change a note in this fixture server process only.",
        "inputSchema": {
            "type": "object",
            "properties": {"note": {"type": "string", "maxLength": 256}},
            "required": ["note"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "slow_echo",
        "description": "Delay locally to exercise client timeout handling.",
        "inputSchema": {
            "type": "object",
            "properties": {"delay_ms": {"type": "integer", "minimum": 0, "maximum": 2000}},
            "required": ["delay_ms"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
]
RECORDS = {
    "alpha": {"id": "alpha", "kind": "fixture", "value": 7},
    "beta": {"id": "beta", "kind": "fixture", "value": 11},
}


def _response(request_id: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": dict(result)}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _tool_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _call_tool(name: str, arguments: Mapping[str, Any], state: dict[str, str]) -> dict[str, Any]:
    if name == "echo":
        return _tool_result({"echo": str(arguments.get("message", ""))})
    if name == "list_fixture":
        return _tool_result({"records": sorted(RECORDS)})
    if name == "read_fake_record":
        record = RECORDS.get(str(arguments.get("record_id", "")))
        return _tool_result(record or {"error": "record not found"}, is_error=record is None)
    if name == "calculate":
        return _tool_result({"sum": arguments.get("left", 0) + arguments.get("right", 0)})
    if name == "set_fixture_note":
        state["note"] = str(arguments.get("note", ""))
        return _tool_result({"note": state["note"], "changed": True})
    if name == "slow_echo":
        time.sleep(int(arguments.get("delay_ms", 0)) / 1000)
        return _tool_result({"delayed": int(arguments.get("delay_ms", 0))})
    return _tool_result({"error": f"unknown tool: {name}"}, is_error=True)


def serve() -> None:
    state: dict[str, str] = {"note": ""}
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(request, Mapping):
            continue
        method = request.get("method")
        request_id = request.get("id")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            payload = _response(request_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agonionce-local-fixture", "version": "1.0"},
            })
        elif method == "tools/list":
            payload = _response(request_id, {"tools": TOOLS})
        elif method == "tools/call":
            params = request.get("params", {})
            if not isinstance(params, Mapping):
                payload = _error(request_id, -32602, "tools/call params must be an object")
            else:
                payload = _response(
                    request_id,
                    _call_tool(str(params.get("name", "")), params.get("arguments", {}), state),
                )
        else:
            payload = _error(request_id, -32601, f"unsupported method: {method}")
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    serve()
