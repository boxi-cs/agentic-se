"""Check what a session handed back against the hand-off it was given.

Usage, from a workspace that holds this script and the named files:

    python -B check_handoff.py HANDOFF RESULT [DIFF]

HANDOFF says what one role may do: the files it may change, the only commands it may run
(each must be run), and the extra fields it must hand back. RESULT is what the session
handed back: the files it says it changed, each command it ran with its exit code, and
those fields. DIFF, if given, is the output of `git diff --name-only` for the same change;
the check then trusts the diff over the session's own list of changed files.

The script reads the named JSON and text files and never runs a command from them. It
exits 0 when the hand-back matches the hand-off and 2 when it does not or cannot be read.
A match does not prove the exit codes are true: open each launcher result yourself.
"""

import json
import sys
from pathlib import Path

MAX_BYTES = 65_536
HANDOFF_KEYS = {"task", "to", "may_change", "run", "hand_back"}
RESERVED = {"from", "changed", "ran"}


class Refused(ValueError):
    """An input this script will not check; fix it and run the check again."""


def read_named(value: str) -> str:
    """Read one ordinary file named relative to, and inside, the current directory."""
    path = Path(value)
    root = Path.cwd().resolve()
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or any(part.startswith(".") for part in path.parts)
        or path.is_symlink()
        or not path.is_file()
        or not path.resolve().is_relative_to(root)
    ):
        raise Refused(f"{value!r} is not an ordinary file inside this workspace")
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise Refused(f"{value} is larger than {MAX_BYTES} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused(f"{value} is not UTF-8 text") from None


def strings(value: object, *, allow_empty: bool = True) -> list[str] | None:
    """Return `value` if it is a list of non-empty strings, else None."""
    if not isinstance(value, list) or (not value and not allow_empty):
        return None
    if not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return value


def load_handoff(text: str) -> dict:
    """Parse and shape-check a hand-off."""
    try:
        handoff = json.loads(text)
    except ValueError:
        raise Refused("the hand-off is not JSON") from None
    if not isinstance(handoff, dict) or set(handoff) != HANDOFF_KEYS:
        raise Refused("the hand-off needs exactly: " + ", ".join(sorted(HANDOFF_KEYS)))
    if not isinstance(handoff["task"], str) or not handoff["task"].strip():
        raise Refused("the hand-off needs a task")
    if not isinstance(handoff["to"], str) or not handoff["to"].strip():
        raise Refused("the hand-off needs the role it is addressed to")
    for key in ("may_change", "run", "hand_back"):
        if strings(handoff[key]) is None:
            raise Refused(f"'{key}' in the hand-off must be a list of strings")
    if RESERVED & set(handoff["hand_back"]):
        raise Refused("'hand_back' names extra fields; from, changed and ran are always checked")
    return handoff


def load_result(text: str) -> dict:
    """Parse and shape-check a hand-back; field contents are judged in `findings`."""
    try:
        result = json.loads(text)
    except ValueError:
        raise Refused("the hand-back is not JSON") from None
    if not isinstance(result, dict):
        raise Refused("the hand-back must be a JSON object")
    if not isinstance(result.get("from"), str) or strings(result.get("changed")) is None:
        raise Refused("the hand-back needs 'from' and a 'changed' list of paths")
    ran = result.get("ran")
    if not isinstance(ran, list) or not all(
        isinstance(item, dict)
        and set(item) == {"command", "exit_code"}
        and isinstance(item["command"], str)
        and type(item["exit_code"]) is int
        for item in ran
    ):
        raise Refused("'ran' must list objects with exactly 'command' and 'exit_code'")
    return result


def findings(handoff: dict, result: dict, diff: list[str] | None) -> list[str]:
    """Every way the hand-back departs from the hand-off, in a stable order."""
    found: list[str] = []
    if result["from"] != handoff["to"]:
        found.append(f"the hand-off went to {handoff['to']!r}; this came from {result['from']!r}")
    claimed = sorted(set(result["changed"]))
    changed = claimed
    if diff is not None:
        changed = sorted(set(diff))
        if changed != claimed:
            found.append(f"says it changed {claimed}; the diff shows {changed}")
    allowed = set(handoff["may_change"])
    found += [
        f"changed {path}, which the hand-off does not allow"
        for path in changed
        if path not in allowed
    ]
    listed = set(handoff["run"])
    last: dict[str, int] = {}
    for item in result["ran"]:
        if item["command"] not in listed and item["command"] not in last:
            found.append(f"ran a command the hand-off does not list: {item['command']}")
        last[item["command"]] = item["exit_code"]
    for command in handoff["run"]:
        if command not in last:
            found.append(f"did not run: {command}")
        elif last[command] != 0:
            found.append(f"last run exited {last[command]}: {command}")
    for key in handoff["hand_back"]:
        if strings(result.get(key), allow_empty=False) is None:
            found.append(f"did not hand back '{key}' as a non-empty list")
    return found


def run(argv: list[str]) -> int:
    """Check one hand-back; print each finding and the decision."""
    if len(argv) not in (2, 3):
        print("REFUSED: usage: python -B check_handoff.py HANDOFF RESULT [DIFF]")
        return 2
    try:
        handoff = load_handoff(read_named(argv[0]))
        result = load_result(read_named(argv[1]))
        diff = None
        if len(argv) == 3:
            diff = [line.strip() for line in read_named(argv[2]).splitlines() if line.strip()]
    except Refused as error:
        print(f"REFUSED: {error}")
        return 2
    found = findings(handoff, result, diff)
    for finding in found:
        print(finding)
    if found:
        print("STOP: the hand-back does not match the hand-off")
        return 2
    source = "the diff" if diff is not None else "the session's own list (no diff given)"
    print(f"PASS: the hand-back matches the hand-off; changed files taken from {source}")
    return 0


def main() -> int:
    """Exit 0 when the hand-back matches the hand-off, 2 otherwise."""
    try:
        return run(sys.argv[1:])
    except OSError:
        print("REFUSED: a named file could not be read")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
