"""A tiny dependency-free local stdio MCP server for the A2 starting point."""

from __future__ import annotations

import json
import sys
from typing import Any

TOOLS = [
    {
        "name": "lookup_note",
        "description": "Read one note by its short key from the local fixture.",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_notes",
        "description": "List the available note keys from the local fixture.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]
NOTES = {"alpha": "Verify the generated change.", "beta": "Keep the experiment local."}


def tool_error(code: str, next_step: str, *, retryable: bool = False) -> dict[str, Any]:
    """Return a tool error that an MCP client can read and recover from."""
    return {
        "content": [
            {
                "type": "text",
                "text": f"{code}; retryable: {str(retryable).lower()}; next: {next_step}",
            }
        ],
        "isError": True,
    }


def tool_result(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one listed tool; a failed input check is a tool error the model can read."""
    if name == "list_notes":
        if arguments:
            return tool_error("invalid_arguments", "call list_notes with an empty object")
        return {"content": [{"type": "text", "text": "alpha\nbeta"}]}
    key = arguments.get("key")
    if set(arguments) != {"key"} or not isinstance(key, str):
        return tool_error("invalid_arguments", "supply exactly one string key")
    if key not in NOTES:
        return tool_error(
            "not_found", "call list_notes and choose an available key", retryable=True
        )
    return {"content": [{"type": "text", "text": NOTES[key]}]}


def rpc_error(code: int, message: str, request_id: Any = None) -> dict[str, Any]:
    """Return a JSON-RPC protocol error; the id is null when the request has no usable id."""
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def valid_id(value: Any) -> bool:
    """A JSON-RPC id is a string, a number or null."""
    return value is None or (isinstance(value, str | int | float) and not isinstance(value, bool))


def reply(request: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC message; notifications produce no response."""
    request_id = request.get("id")
    if not valid_id(request_id):
        return rpc_error(-32600, "invalid request")
    method = request.get("method")
    if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return rpc_error(-32600, "invalid request", request_id)
    if "id" not in request:
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "a2-local-notes", "version": "0.1"},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params")
        if not isinstance(params, dict):
            return rpc_error(-32602, "invalid params: tools/call needs a params object", request_id)
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return rpc_error(
                -32602, "invalid params: supply a tool name and an arguments object", request_id
            )
        if name not in {tool["name"] for tool in TOOLS}:
            return rpc_error(-32602, f"unknown tool: {name}", request_id)
        result = tool_result(name, arguments)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    return rpc_error(-32601, "method not found", request_id)


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            result = rpc_error(-32700, "parse error")
        else:
            if isinstance(request, dict):
                result = reply(request)
            else:
                result = rpc_error(-32600, "invalid request")
        if result is not None:
            print(json.dumps(result, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
