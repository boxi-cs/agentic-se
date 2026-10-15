"""Replay a recorded agent session through the agent-side hook, offline.

`session/steps.json` holds course-written steps: tool calls and attempts to end the turn.
No model runs. For each step the replay sends one event to `agent_hook.py`, prints the
hook's decision and carries it out on a scratch copy of `workspace/`. An allowed write is
written and a blocked one is not. A blocked end of turn goes back to the agent, which goes
on with the next recorded step; an allowed one ends the turn.

Then the replay checks the result itself instead of trusting the hook: the files under
`tests/` must be unchanged, and the original focused test from `workspace/` must pass on
the final code. It exits 0 when the turn ended and both checks hold, 1 when they do not,
and 2 when the session cannot be read. `steps.json` and each step's content must be regular
files directly in `session/`, never symbolic links. The hook and the check run with no
environment beyond what Python needs. Every line the replay prints, the recorded messages
and paths and the hook's and the check's output among them, passes through `redact` from
`redaction.py`. The replay writes no file whose path `redact` would change or whose content
holds a key format or a quoted value under a credential name, as `holds_credential` decides;
code that only names a key, such as `key=lambda p: p[0]`, is written. The scratch copies are
deleted afterwards; nothing in this directory changes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Importing redaction.py must not leave a __pycache__ folder beside this file.
sys.dont_write_bytecode = True
from redaction import holds_credential, redact  # noqa: E402

HERE = Path(__file__).resolve().parent
HOOK = HERE / "agent_hook.py"
SESSION = HERE / "session"
WORKSPACE = HERE / "workspace"
FOCUSED_TEST = "tests/check_pairs.py"
TIMEOUT = 60
# The same limit as agent_hook.py: the code under test sees only what Python needs.
ENV_KEYS = ("PATH", "SYSTEMROOT")


def show(line: str) -> None:
    """Print one line of the replay with every credential-shaped part redacted."""
    print(redact(line))


def plain_env() -> dict[str, str]:
    """Only the variables Python needs to start; keys in this environment stay here."""
    return {key: os.environ[key] for key in ENV_KEYS if key in os.environ}


def session_text(name: str) -> str:
    """The text of a regular file directly in session/; a link or any other path is refused."""
    path = SESSION / name
    if (
        Path(name).name != name
        or path.is_symlink()
        or not path.is_file()
        or path.resolve().parent != SESSION
    ):
        raise ValueError(f"{name!r} is not a regular file in session/")
    return path.read_text(encoding="utf-8")


def load_steps() -> list[dict]:
    """The recorded steps, each a tool call with its content read or an end of turn."""
    steps = json.loads(session_text("steps.json"))["steps"]
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("every step must be an object")
        if step.get("kind") == "end_of_turn":
            if not isinstance(step.get("message"), str):
                raise ValueError("an end of turn needs its message")
        elif step.get("kind") == "tool_call":
            if not all(isinstance(step.get(key), str) for key in ("tool", "path", "content_file")):
                raise ValueError("a tool call needs tool, path and content_file")
            step["content"] = session_text(step["content_file"])
        else:
            raise ValueError("kind must be tool_call or end_of_turn")
    return steps


def call_hook(event: dict, workspace: Path) -> tuple[int, list[str]]:
    """Run the hook on one event in the scratch workspace; a crash or a timeout blocks."""
    try:
        result = subprocess.run(
            [sys.executable, "-B", str(HOOK)],
            input=json.dumps(event),
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
            env=plain_env(),
        )
    except subprocess.TimeoutExpired:
        return 2, [f"(no decision within {TIMEOUT} s)"]
    # The replay redacts the hook's output itself instead of trusting the hook to.
    lines = redact(result.stdout).splitlines()
    if result.returncode not in (0, 2):
        lines += redact(result.stderr).splitlines()[-1:]
    return result.returncode, lines


def write_in(workspace: Path, path: str, content: str) -> str:
    """Carry out an allowed write, but never outside the scratch workspace or with a key."""
    root = workspace.resolve()
    target = (workspace / path).resolve()
    if target == root or not target.is_relative_to(root):
        return f"the replay does not write {path!r}: it is outside the workspace"
    if redact(path) != path or holds_credential(content):
        # The path comes last: a redacted key block may take the rest of the line with it.
        return (
            "the path or content holds text shaped like a credential; "
            f"the replay does not write {path!r}"
        )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError:
        return f"the replay could not write {path!r}"
    return f"the call runs and writes {path}"


def tests_snapshot(workspace: Path) -> dict[str, bytes]:
    """Every file under tests/, by relative path."""
    folder = workspace / "tests"
    return {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def original_test(workspace: Path) -> subprocess.CompletedProcess[str]:
    """Run the fixture's own focused test on the final code, in a separate scratch copy."""
    check = workspace.parent / "check"
    shutil.copytree(workspace, check, ignore=shutil.ignore_patterns("__pycache__"))
    tests = check / "tests"
    if tests.is_dir() and not tests.is_symlink():
        shutil.rmtree(tests)
    else:
        tests.unlink(missing_ok=True)
    shutil.copytree(WORKSPACE / "tests", tests, ignore=shutil.ignore_patterns("__pycache__"))
    return subprocess.run(
        [sys.executable, "-B", FOCUSED_TEST],
        cwd=check,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
        env=plain_env(),
    )


def replay(steps: list[dict], workspace: Path) -> int:
    """Replay every step until the turn ends, then check the workspace independently."""
    before = tests_snapshot(workspace)
    blocked = allowed = 0
    ended_at = 0
    for number, step in enumerate(steps, 1):
        if step["kind"] == "tool_call":
            content = step["content"]
            arguments = {"path": step["path"], "content": content}
            event = {"event": "before_tool_call", "tool": step["tool"], "arguments": arguments}
            show(f"step {number} tool call: {step['tool']} {step['path']}")
        else:
            event = {"event": "end_of_turn"}
            show(f'step {number} end of turn: "{step["message"]}"')
        code, lines = call_hook(event, workspace)
        for line in lines:
            show(f"  hook: {line}")
        if code == 0:
            allowed += 1
        else:
            blocked += 1
        if step["kind"] == "tool_call":
            if code != 0:
                outcome = "the call is refused and no file changes"
            elif step["tool"] == "write_file":
                outcome = write_in(workspace, step["path"], content)
            else:
                outcome = "the call runs; this replay carries out only write_file"
        elif code == 0:
            outcome = "the turn ends"
            ended_at = number
        else:
            outcome = "the turn goes on, and the agent receives the hook's message"
        show(f"  exit {code}: {outcome}")
        if ended_at:
            break
    if ended_at and ended_at < len(steps):
        show(f"turn ended at step {ended_at}; steps {ended_at + 1}-{len(steps)} were not replayed")

    after = tests_snapshot(workspace)
    changed = sorted(
        name for name in before.keys() | after.keys() if before.get(name) != after.get(name)
    )
    if changed:
        show(f"replay check: changed under tests/: {', '.join(changed)}")
    else:
        show("replay check: tests/ unchanged")
    test = original_test(workspace)
    # Redact the whole output before taking its last line, so that a key block goes as one.
    output = redact(test.stdout).splitlines() or redact(test.stderr).splitlines()
    last = output[-1] if output else "no output"
    show(f"replay check: original {FOCUSED_TEST} on the final code: exit {test.returncode}, {last}")

    problems = []
    if not ended_at:
        problems.append("the turn never ended")
    if changed:
        problems.append("files under tests/ changed")
    if test.returncode != 0:
        problems.append("the original focused test fails")
    if problems:
        show(f"FAIL: {'; '.join(problems)}")
        return 1
    show(
        f"PASS: {blocked} events blocked, {allowed} allowed; "
        "the turn ended with tests/ unchanged and the test passing"
    )
    return 0


def main() -> int:
    """Replay the session on a scratch copy of the workspace."""
    try:
        steps = load_steps()
    except (OSError, ValueError, KeyError, TypeError) as error:
        show(f"ERROR: cannot read session/steps.json: {error}")
        return 2
    with tempfile.TemporaryDirectory() as scratch:
        workspace = Path(scratch) / "workspace"
        shutil.copytree(WORKSPACE, workspace, ignore=shutil.ignore_patterns("__pycache__"))
        return replay(steps, workspace)


if __name__ == "__main__":
    raise SystemExit(main())
