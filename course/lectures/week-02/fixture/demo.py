"""Run the synthetic loop from a draft copy, as the Week 1 notes show."""

import json
import re
import sys
from pathlib import Path

from loop import last_check, run
from sandbox_model import chat, emit_artifact

TASK = "Repair result.txt so it contains 4 and a newline. Run the verify check, then report."
CANDIDATE = "4\n"  # The wrong-write experiment changes only this value.
# The turn-budget experiment changes only this value. Keep it at 4 or below, the cap on
# model requests in one run.
MAX_STEPS = 4
CONTRACT = (
    "Choose the next step of a small agent. Tools: read {path}, write {path, content}, "
    "bash {command}. Only path: result.txt. Only command: verify. Reply with one JSON "
    'object only: {"content": "...", "tool_calls": [{"name": "...", "arguments": {...}}]}. '
    "Empty tool_calls when done. Messages so far:\n"
)


def call(identifier: str, name: str, **arguments: str) -> dict:
    return {"content": "", "tool_calls": [{"id": identifier, "name": name, "arguments": arguments}]}


def scripted(messages: list[dict]) -> dict:
    """A course-written proposer that picks its next step from the latest tool result."""
    if messages[-1]["role"] == "user":
        return call("c1", "read", path="result.txt")
    answered, latest = messages[-2]["tool_calls"][0]["name"], messages[-1]["content"]
    if answered == "read":
        return call("c2", "write", path="result.txt", content=CANDIDATE)
    if answered == "write" and latest == "written":
        return call("c3", "bash", command="verify")
    return {"content": f"Stopping after {answered}: {latest.strip()}", "tool_calls": []}


def parse_reply(text: str, turn: int) -> dict:
    """Read one JSON reply and number its calls, as a provider API would. Repair nothing."""
    text = re.sub(r"^\s*<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    reply = json.loads(fenced[1] if fenced else text)
    if not isinstance(reply, dict) or not isinstance(reply.get("tool_calls", []), list):
        raise ValueError("model reply is not one JSON object with a tool_calls list")
    calls = [
        {"id": f"t{turn}-{index}", "name": item.get("name"), "arguments": item.get("arguments")}
        if isinstance(item, dict)
        else item
        for index, item in enumerate(reply.get("tool_calls", []), start=1)
    ]
    content = reply.get("content")  # Providers often send null beside tool calls.
    return {"content": "" if content is None else content, "tool_calls": calls}


def hosted(messages: list[dict]) -> dict:
    """One bounded model request per turn; the request carries every earlier tool result."""
    turn = sum(message["role"] == "assistant" for message in messages) + 1
    return parse_reply(chat(CONTRACT + json.dumps(messages, separators=(",", ":"))), turn)


def main() -> int:
    """Run one task, keep the whole history and report the check apart from the stop."""
    if sys.argv[1:] not in ([], ["hosted"], ["replay"]):
        raise ValueError("Use no argument for scripted practice, or hosted/replay for a model")
    generation = "hosted-api-or-replay" if sys.argv[1:] else "scripted-practice"
    Path("result.txt").write_text("5\n")
    try:
        result = run(hosted if sys.argv[1:] else scripted, TASK, MAX_STEPS)
    except NotImplementedError:
        # The supplied stub raises before any model request is made.
        print(json.dumps({"generation": generation, "error": "write run() in loop.py first"}))
        return 1
    except ValueError as error:
        # An unusable reply is an observation to keep, not something to repair or retry.
        print(json.dumps({"generation": generation, "unusable_reply": str(error)}))
        return 1
    result.update(generation=generation, check=last_check(result["messages"]))
    Path("completion.json").write_text(json.dumps(result, indent=2) + "\n")
    summary = {key: result[key] for key in ("generation", "stop_reason", "check")}
    print(json.dumps({**summary, "messages": len(result["messages"])}, sort_keys=True))
    emit_artifact("result.txt")
    emit_artifact("completion.json")
    return 0 if result["check"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
