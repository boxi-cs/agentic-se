"""Run the public scripted Week 1 example through the course launcher only."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import candidate
import repaired
from sandbox_model import emit_artifact

CASES = (
    ("ordinary-ok", "ok", "passed"),
    ("ordinary-fail", "fail", "failed"),
    ("padded-ok", " OK ", "passed"),
    ("mixed-whitespace-fail", "\tfAiL\n", "failed"),
    ("unknown-status", "cancelled", "unknown"),
    ("empty", "", "unknown"),
)


def observe(function: Callable[[str], str]) -> list[dict[str, str | bool]]:
    """Evaluate both candidates against the same independently stated cases."""
    rows = []
    for case_id, raw, expected in CASES:
        actual = function(raw)
        rows.append(
            {
                "id": case_id,
                "input": raw,
                "expected": expected,
                "actual": actual,
                "passed": actual == expected,
            }
        )
    return rows


def main() -> None:
    """Reject an unexpected matrix and export source-bound public observations."""
    original = observe(candidate.status_label)
    fixed = observe(repaired.status_label)
    expected_original = ["passed", "failed", "unknown", "unknown", "unknown", "unknown"]
    if [row["actual"] for row in original] != expected_original:
        raise AssertionError("Candidate results differ from the lesson's expected failures")
    if not all(row["passed"] for row in fixed):
        raise AssertionError("The repair violates at least one public contract case")
    root = Path(__file__).resolve().parent
    result = {
        "generation": "scripted-course-candidates",
        "model_requests": 0,
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("candidate.py", "repaired.py", "demo.py")
        },
        "candidate": original,
        "repaired": fixed,
    }
    Path("observations.json").write_text(json.dumps(result, indent=2) + "\n")
    emit_artifact("observations.json")
    print("generation: scripted-course-candidates")
    print("candidate / ordinary: 2/2 passed")
    print("candidate / contract: 4/6 passed")
    print("repaired  / contract: 6/6 passed")
    print("regression: original cases retained")


if __name__ == "__main__":
    main()
