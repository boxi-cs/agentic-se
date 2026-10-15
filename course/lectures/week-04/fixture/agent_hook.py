"""Example agent-side hook: allow or block one event from the agent's own loop.

The hook reads one JSON event on standard input and exits 0 to allow it or 2 to block it.
It handles two events:

- `before_tool_call`: the agent is about to call a tool. A write under `tests/` or to a
  protected file is blocked before anything changes. A read inside the workspace is
  allowed. A shell command is allowed only when it is the focused test, because the hook
  cannot tell from a command's text which files it will write. Any other tool is blocked.
- `end_of_turn`: the agent is about to finish. The hook runs the focused test itself and
  blocks the end of the turn while the test fails. The test runs on code the agent wrote,
  so it gets no environment beyond what Python needs.

Every line the hook prints passes through `redact` from `redaction.py` beside it, so text
shaped like a credential in a path, a tool name or the test's output reaches the agent as
[REDACTED]; copy both files together.

The event names and fields are this course example's own. A real agent names its events
and passes their fields as its documentation describes; read that before you adapt this
file. The hook never runs a command that the agent proposed: at the end of a turn it runs
only the focused test named below, in the directory it was started from.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import PurePosixPath

# Importing redaction.py must not leave a __pycache__ folder beside this file.
sys.dont_write_bytecode = True
from redaction import redact  # noqa: E402

MAX_EVENT_BYTES = 1_048_576
MAX_OUTPUT_LINES = 20
TEST_TIMEOUT = 30

# Paths the agent may not write. Keep these the same as the Stop rule of your AGENTS.md.
PROTECTED_DIRS = ("tests",)
PROTECTED_FILES = frozenset({"Dockerfile", "pyproject.toml", "uv.lock"})

READ_TOOLS = frozenset({"read_file"})
WRITE_TOOLS = frozenset({"write_file", "edit_file"})
SHELL_TOOL = "run_shell"
FOCUSED_TEST = "tests/check_pairs.py"
ALLOWED_COMMANDS = frozenset({f"python {FOCUSED_TEST}"})

# The only variables the focused test sees: a key in the agent's environment stays there.
TEST_ENV_KEYS = ("PATH", "SYSTEMROOT")
TOOL_NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
REFUSED = (
    'REFUSED: expected one JSON event, {"event": "end_of_turn"} or '
    '{"event": "before_tool_call", "tool": "<name>", "arguments": {...}}'
)


def relative_path(value: object) -> PurePosixPath | None:
    """A plain relative path inside the workspace, or None."""
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return None
    return path


def protection(path: PurePosixPath) -> str | None:
    """Why the agent may not write this path, or None when it may."""
    if path.parts[0].casefold() in {name.casefold() for name in PROTECTED_DIRS}:
        return f"{path.parts[0]}/ is protected; fix the code, not its test"
    if path.as_posix().casefold() in {name.casefold() for name in PROTECTED_FILES}:
        return f"{path} is protected by AGENTS.md; change it in its own reviewed change"
    return None


def before_tool_call(tool: str, arguments: dict) -> tuple[int, str]:
    """Decide one proposed tool call from its name and arguments alone."""
    if tool in READ_TOOLS | WRITE_TOOLS:
        path = relative_path(arguments.get("path"))
        if path is None:
            # Redact before shortening, so that no cut-off key is left unrecognised.
            shown = redact(repr(arguments.get("path")))[:80]
            return 2, f"BLOCK {tool}: {shown} is not a relative path inside the workspace"
        reason = protection(path) if tool in WRITE_TOOLS else None
        if reason:
            return 2, f"BLOCK {tool} {path}: {reason}"
        return 0, f"ALLOW {tool} {path}"
    if tool == SHELL_TOOL:
        command = arguments.get("command")
        if isinstance(command, str) and command.strip() in ALLOWED_COMMANDS:
            return 0, f"ALLOW {tool} {command.strip()}"
        return 2, (
            f"BLOCK {tool}: only the focused test may run; "
            "a command's text does not show what it writes"
        )
    return 2, f"BLOCK {tool}: this hook has no rule for the tool; add one before you allow it"


def end_of_turn() -> tuple[int, list[str]]:
    """Run the focused test and allow the end of the turn only when it passes."""
    try:
        result = subprocess.run(
            [sys.executable, "-B", FOCUSED_TEST],
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT,
            check=False,
            env={key: os.environ[key] for key in TEST_ENV_KEYS if key in os.environ},
        )
    except subprocess.TimeoutExpired:
        return 2, [f"BLOCK end_of_turn: the focused test ran over {TEST_TIMEOUT} s; keep working"]
    except OSError:
        return 2, ["BLOCK end_of_turn: the focused test could not be started; keep working"]
    # Redact the whole output before splitting it, so that a key block spread over several
    # lines goes as one.
    output = redact(result.stdout).splitlines() or redact(result.stderr).splitlines()[-1:]
    if result.returncode == 0:
        summary = output[-1] if output else "no output"
        return 0, [f"ALLOW end_of_turn: the focused test passes ({summary})"]
    return 2, [
        "BLOCK end_of_turn: the focused test fails; keep working",
        *(f"  {line}" for line in output[:MAX_OUTPUT_LINES]),
    ]


def decide(raw: str) -> tuple[int, list[str]]:
    """Return the exit code and the lines to print for one raw event."""
    try:
        event = json.loads(raw)
    except (ValueError, RecursionError):
        event = None
    if not isinstance(event, dict):
        return 2, [REFUSED]
    if event == {"event": "end_of_turn"}:
        return end_of_turn()
    if (
        event.get("event") == "before_tool_call"
        and set(event) == {"event", "tool", "arguments"}
        and isinstance(event["tool"], str)
        and TOOL_NAME.fullmatch(event["tool"])
        and isinstance(event["arguments"], dict)
    ):
        code, line = before_tool_call(event["tool"], event["arguments"])
        return code, [line]
    return 2, [REFUSED]


def main() -> int:
    """Exit 0 to allow the event or 2 to block it."""
    try:
        raw = sys.stdin.read(MAX_EVENT_BYTES + 1)
    except (OSError, ValueError):
        raw = ""
    code, lines = decide(raw) if len(raw) <= MAX_EVENT_BYTES else (2, [REFUSED])
    for line in lines:
        print(redact(line))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
