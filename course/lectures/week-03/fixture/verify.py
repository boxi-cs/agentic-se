"""Public formative check of answers to the overview question. Never a grade."""

import hashlib
import json
import re
import sys
from pathlib import Path

# Read from ci-dashboard itself: legacy_app/views.py's require_user aborts with 401, and
# the for/else in legacy_app/templates/ci/overview.html prints the empty-table row.
EXPECTED = {
    "signed_out_status": lambda value: value in (401, "401"),
    "signed_out_file": lambda value: isinstance(value, str) and value.strip().endswith("views.py"),
    "empty_text": lambda value: isinstance(value, str) and value.strip() == "No projects yet.",
    "empty_file": lambda value: isinstance(value, str) and value.strip().endswith("overview.html"),
}


def read_answer(text: str) -> dict:
    """Accept one JSON object, after a leading reasoning block or one code fence. Fix nothing."""
    text = re.sub(r"^\s*<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    answer = json.loads(fenced[1] if fenced else text)
    if not isinstance(answer, dict):
        raise ValueError("The answer is not one JSON object")
    return answer


def check(answer: dict) -> dict:
    """Label each field correct, wrong, abstained (an explicit null) or missing."""
    fields = {}
    for name, accept in EXPECTED.items():
        if name not in answer:
            fields[name] = "missing"
        elif answer[name] is None:
            fields[name] = "abstained"
        else:
            fields[name] = "correct" if accept(answer[name]) else "wrong"
    correct = sum(label == "correct" for label in fields.values())
    return {"fields": fields, "correct": correct, "of": len(EXPECTED)}


def replay(path: Path) -> int:
    """Check a recorded pair against the inputs in this workspace, then each arm's answer."""
    record = json.loads(path.read_text())
    for name, expected in record["inputs"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            print(json.dumps({"feedback_only": True, "input_changed": name}))
            return 2
    about = {key: record[key] for key in ("kind", "configuration", "reproduce")}
    print(json.dumps({"feedback_only": True, **about}))
    for arm in sorted(record["answers"]):
        print(json.dumps({"arm": arm, **check(record["answers"][arm])}, sort_keys=True))
    return 0


def main() -> int:
    if sys.argv[1:2] == ["--replay"] and len(sys.argv) == 3:
        return replay(Path(sys.argv[2]))
    if len(sys.argv) != 2:
        raise SystemExit("Use: verify.py ANSWER_FILE, or verify.py --replay RECORD")
    try:
        answer = read_answer(Path(sys.argv[1]).read_text())
    except ValueError:
        print(json.dumps({"feedback_only": True, "unreadable": True}))
        return 1
    report = check(answer)
    print(json.dumps({"feedback_only": True, **report}, sort_keys=True))
    return 0 if report["correct"] == report["of"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
