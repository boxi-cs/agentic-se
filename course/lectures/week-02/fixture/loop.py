"""Course-authored synthetic loop in P1's message protocol; you write run().

Execute only through course-sandbox.
"""

import subprocess
from collections.abc import Callable
from pathlib import Path

CHECK = "from pathlib import Path; assert Path('result.txt').read_text() == '4\\n'"
ARGUMENTS = {"read": {"path"}, "write": {"path", "content"}, "bash": {"command"}}


def tool(name: str, arguments: dict) -> str:
    """Expose one synthetic file and one fixed check; refuse anything else before effects."""
    if ARGUMENTS.get(name) != set(arguments) or arguments.get("path", "result.txt") != "result.txt":
        return "refused: tool, argument or path outside the contract"
    if name == "read":
        return Path("result.txt").read_text()
    if name == "write":
        content = arguments["content"]
        try:  # Encode first: text that cannot be written must not truncate the file.
            data = content.encode() if isinstance(content, str) and len(content) <= 32 else None
        except UnicodeEncodeError:
            data = None
        if data is None:
            return "refused: content must be text of at most 32 characters"
        Path("result.txt").write_bytes(data)
        return "written"
    if arguments["command"] != "verify":
        return "refused: bash runs only the fixed verify command"
    result = subprocess.run(
        ["bash", "-c", 'python -c "$1"', "verify", CHECK],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )
    return "verified" if result.returncode == 0 else "check_failed"


def checked(reply: object) -> dict:
    """Refuse a reply whose calls cannot each be answered by ID, before any tool runs."""
    calls = reply.get("tool_calls") if isinstance(reply, dict) else None
    if not isinstance(calls, list) or not isinstance(reply.get("content"), str):
        raise ValueError("malformed assistant message")
    for call in calls:
        if (
            not isinstance(call, dict)
            or set(call) != {"id", "name", "arguments"}
            or not all(isinstance(call[key], str) for key in ("id", "name"))
            or not isinstance(call["arguments"], dict)
        ):
            raise ValueError("malformed tool call")
    if len({call["id"] for call in calls}) != len(calls):
        raise ValueError("duplicate tool call id")
    return {"content": reply["content"], "tool_calls": calls}


def run(chat: Callable[[list[dict]], dict], task: str, max_steps: int = 4) -> dict:
    """You write this in the Week 2 workshop; verify_loop.py's public checks are its target.

    The instructor builds steps 1-3 on screen; steps 4-5 are yours. The contract, in the
    order the notes give it:
    1. Start the history with one user message holding the task.
    2. Each turn, send a copy of the whole history to chat. Check the reply with checked(),
       and raise ValueError for a call ID that an earlier call already used.
    3. Append the reply as an assistant message. With no tool calls, return a dict whose
       stop_reason is "final" and whose messages are the whole history.
    4. Otherwise answer every call with one tool message: role "tool", the call's own
       tool_call_id, and tool()'s result as content. A missing file or a timed-out check
       (OSError, subprocess.TimeoutExpired) becomes a "failed: ..." result.
    5. When max_steps turns are spent, return stop_reason "step_limit" with the history.
    """
    raise NotImplementedError("Write run() first: see the Week 2 activity, minutes 5-20.")


def last_check(messages: list[dict]) -> str:
    """Return the newest result of a verify call that ran, or not_run if a write came later."""
    calls = {call["id"]: call for message in messages for call in message.get("tool_calls", [])}
    result = "not_run"
    for message in messages:
        call = calls.get(message.get("tool_call_id"))
        if call is None:
            continue
        # Only the exact verify call runs the check; any other bash call was refused.
        if call["name"] == "bash" and call["arguments"] == {"command": "verify"}:
            result = message["content"]
        elif call["name"] == "write" and message["content"] == "written":
            result = "not_run"
    return result
