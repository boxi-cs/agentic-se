"""Compaction comparison for the Week 2 notes: the same next step from four versions of a history.

Course-synthesised. `long-session.json` is a session the course team wrote by hand in
the message format of the Week 1 loop: an agent repairing the dashboard's status label
has read five files, tried one fix and seen it fail. No model wrote it. This script
builds the context the next request would carry, in one of four ways:

- `full`: every message, as your Week 1 loop sends it;
- `auto`: the supplied mechanical compaction. It keeps the task, every assistant message
  and the newest call/result group, and clears every older tool result longer than 80
  bytes to a one-line stub. It writes no summary;
- `summary FILE`: the task, your summary from FILE in place of every older message, and
  the newest group: compaction by summary;
- `fresh FILE`: the task and FILE only: a restart from a written handoff.

A short course-written policy then picks the next edit from that context alone, and the
same six-case acceptance check runs on the result. The policy is not a model. It reads the
text of each message it is given, line by line, and follows two rules:

1. Edit `status.py` when a line names `view.py` and says not to change it (with not,
   n't, never, read-only, unchanged, frozen or leave). Otherwise edit `view.py`, where
   the wrong label shows, so that `unknown` displays as `passed`.
2. In `status.py`, write `raw.strip().lower()` when a line mentions strip and a failure
   (any word starting with fail). Otherwise write `raw.strip()`, the first idea for " OK ".

No model is called, nothing is read from the network and no file is written. The script
runs only the course-written files below, never text from your summary; a write in the
session must match one of them. The output is formative feedback, never a grade.
"""

import argparse
import json
import re
import sys
from pathlib import Path

BUDGET = 5500  # Bytes of context: the compact JSON of the messages a request would carry.
SUMMARY_LIMIT = 600  # Bytes of your summary or handoff file.
STUB_OVER = 80  # The supplied compaction clears older tool results longer than this.
SESSION = "long-session.json"
SUMMARY_HEADER = "Summary of the earlier turns, written at compaction:\n"
HANDOFF_HEADER = "Handoff from an earlier session, which has ended:\n"

STATUS_SHIPPED = '''"""Map a build's raw status to the label the dashboard shows."""

LABELS = {"ok": "passed", "fail": "failed"}


def label(raw):
    return LABELS.get(raw.lower(), "unknown")
'''
VIEW_SHIPPED = '''"""Render one row of the build table."""


def row(name, label):
    return f"{name}: {label}"
'''
# The three edits the policy can choose, each a whole new file.
CANDIDATES = {
    "view-unknown-as-passed": (
        "view.py",
        VIEW_SHIPPED.replace(
            "    return f", '    if label == "unknown":\n        label = "passed"\n    return f'
        ),
    ),
    "status-strip": ("status.py", STATUS_SHIPPED.replace("raw.lower()", "raw.strip()")),
    "status-strip-lower": (
        "status.py",
        STATUS_SHIPPED.replace("raw.lower()", "raw.strip().lower()"),
    ),
}
CASES = (
    ("build-1", " OK ", "passed"),
    ("build-2", "OK", "passed"),
    ("build-3", "ok", "passed"),
    ("build-4", "fail", "failed"),
    ("build-5", "queued", "unknown"),
)
DO_NOT_CHANGE = re.compile(r"\bnot\b|n't\b|\bnever\b|read-only|unchanged|frozen|\bleave\b", re.I)


def load(source: str, name: str) -> object:
    """Define the one function a course-written candidate file holds."""
    namespace: dict = {"__builtins__": {}}
    exec(compile(source, name, "exec"), namespace)  # Course-written text only, never input.
    return namespace["label" if name == "status.py" else "row"]


def check(files: dict[str, str]) -> list[str]:
    """The six acceptance cases, reported one line each, as check_status.py prints them."""
    label, row = load(files["status.py"], "status.py"), load(files["view.py"], "view.py")
    lines = []
    for name, raw, expected in CASES:
        shown, wanted = row(name, label(raw)), f"{name}: {expected}"
        line = f"{json.dumps(raw)} shows {json.dumps(shown)}"
        lines.append(f"PASS  {line}" if shown == wanted else f"FAIL  {line}, expected {expected}")
    shipped = files["view.py"] == VIEW_SHIPPED
    lines.append(("PASS" if shipped else "FAIL") + "  view.py is the file the mobile app uses")
    failed = sum(line.startswith("FAIL") for line in lines)
    return [f"check_status.py: {len(lines)} cases, {failed} failed", *lines]


def groups(messages: list[dict]) -> list[int]:
    """The index at which each assistant message and the tool results answering it start."""
    return [index for index, message in enumerate(messages) if message["role"] == "assistant"]


def build(mode: str, messages: list[dict], note: str | None) -> tuple[list[dict], dict]:
    """The context the next request would carry, and which messages it kept or replaced."""
    newest = groups(messages)[-1]
    older = range(1, newest)
    if mode == "full":
        return messages, {"kept": list(range(len(messages))), "replaced": []}
    if mode == "auto":
        context, cleared = [messages[0]], []
        for index in older:
            message = dict(messages[index])
            if message["role"] == "tool" and len(message["content"].encode()) > STUB_OVER:
                size = len(message["content"].encode())
                message["content"] = f"[cleared: {size} bytes of an earlier tool result]"
                cleared.append(index)
            context.append(message)
        kept = [i for i in range(len(messages)) if i not in cleared]
        return context + messages[newest:], {"kept": kept, "cleared": cleared}
    header = SUMMARY_HEADER if mode == "summary" else HANDOFF_HEADER
    written = {"role": "user", "content": header + note}
    if mode == "summary":
        kept = [0, *range(newest, len(messages))]
        return [messages[0], written, *messages[newest:]], {"kept": kept, "replaced": list(older)}
    return [messages[0], written], {"kept": [0], "replaced": list(range(1, len(messages)))}


def policy(context: list[dict]) -> tuple[str, dict]:
    """Pick the next edit from the context alone, with the first line found for each rule."""
    lines = [line for message in context for line in message["content"].splitlines()]
    found = {
        "view_py_off_limits": next(
            (line for line in lines if "view.py" in line and DO_NOT_CHANGE.search(line)), None
        ),
        "strip_only_failed": next(
            (line for line in lines if "strip" in line.lower() and "fail" in line.lower()), None
        ),
    }
    if found["view_py_off_limits"] is None:
        return "view-unknown-as-passed", found
    return ("status-strip-lower" if found["strip_only_failed"] else "status-strip"), found


def current_files(messages: list[dict]) -> dict[str, str]:
    """The workspace when the session stops: the shipped files plus every write it made."""
    files = {"status.py": STATUS_SHIPPED, "view.py": VIEW_SHIPPED}
    known = {*files.items(), *CANDIDATES.values()}
    for message in messages:
        for call in message.get("tool_calls", []):
            if call["name"] == "write":
                written = (call["arguments"]["path"], call["arguments"]["content"])
                if written not in known:
                    raise ValueError("the session writes a file this script does not know")
                files[written[0]] = written[1]
    return files


def compare(mode: str, messages: list[dict], note: str | None = None) -> dict:
    """Build one context, take the policy's next edit and run the acceptance check on it."""
    context, provenance = build(mode, messages, note)
    size = len(json.dumps(context, separators=(",", ":")).encode())
    result = {"feedback_only": True, "mode": mode, "context_bytes": size, "budget": BUDGET}
    if size > BUDGET:
        return {**result, "over_budget": True}
    choice, found = policy(context)
    path, content = CANDIDATES[choice]
    report = check({**current_files(messages), path: content})
    failed = [line for line in report if line.startswith("FAIL")]
    return {
        **result,
        "messages": len(context),
        **provenance,
        "next_edit": {"path": path, "candidate": choice},
        "policy_found": found,
        "check": "failed" if failed else "passed",
        "failures": failed,
    }


def show(context: list[dict]) -> None:
    """Print every message of a context with its index, role and size."""
    for index, message in enumerate(context):
        calls = message.get("tool_calls", [])
        size = len(json.dumps(message, separators=(",", ":")).encode())
        about = f"[{index}] {message['role']} ({size} bytes)"
        if "tool_call_id" in message:
            about += f" answering {message['tool_call_id']}"
        print(about)
        for line in message["content"].splitlines():
            print(f"    {line}")
        for call in calls:
            arguments = {k: v for k, v in call["arguments"].items() if k != "content"}
            written = " (writes a new file)" if "content" in call["arguments"] else ""
            print(f"    call {call['id']} {call['name']} {json.dumps(arguments)}{written}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("full", "auto", "summary", "fresh"))
    parser.add_argument("file", nargs="?", help="your summary or handoff, for summary or fresh")
    parser.add_argument("--show", action="store_true", help="print the context first")
    args = parser.parse_args()
    if (args.file is None) != (args.mode in ("full", "auto")):
        parser.error("summary and fresh need FILE; full and auto take none")
    note = None
    if args.file is not None:
        try:
            note = Path(args.file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            print(json.dumps({"feedback_only": True, "unreadable": args.file}))
            return 2
        if len(note.encode()) > SUMMARY_LIMIT:
            size = len(note.encode())
            print(json.dumps({"feedback_only": True, "file_bytes": size, "limit": SUMMARY_LIMIT}))
            return 2
    messages = json.loads(Path(SESSION).read_text(encoding="utf-8"))["messages"]
    print("agent: course-written policy, not a model")
    if args.show:
        show(build(args.mode, messages, note)[0])
    result = compare(args.mode, messages, note)
    print(json.dumps(result))
    if result.get("over_budget"):
        return 2
    return 0 if result["check"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
