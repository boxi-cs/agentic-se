"""Public reporting exercise with frozen synthetic inputs, not benchmark execution."""

import copy
import hashlib
import json
from pathlib import Path


def main() -> int:
    """Expose denominator and coverage errors while preserving the declared protocol."""
    base = Path(__file__).parent
    snapshot = json.loads((base / "snapshot.json").read_text())
    for name in ("protocol.json", "observations.json"):
        actual = hashlib.sha256((base / name).read_bytes()).hexdigest()
        if actual != snapshot["sha256"][name]:
            print(
                json.dumps({"kind": "public_practice", "error": "changed_snapshot", "file": name})
            )
            return 2
    protocol = json.loads((base / "protocol.json").read_text())
    records = json.loads((base / "observations.json").read_text())
    from candidate import summarize

    extra_attempt = copy.deepcopy(records)
    extra_attempt[0]["attempts"] = 2
    cases = [
        (
            "declared_set",
            records,
            {"status": "ok", "successes": 2, "total": 4, "timeouts": 1, "coverage": 4},
        ),
        ("missing_task", records[:-1], {"status": "invalid"}),
        ("duplicate_task", records[:-1] + [records[0]], {"status": "invalid"}),
        ("extra_attempt", extra_attempt, {"status": "invalid"}),
    ]
    checks: list[dict[str, object]] = []
    for name, rows, expected in cases:
        try:
            observed = summarize(
                copy.deepcopy(rows), list(protocol["task_ids"]), protocol["attempts_per_task"]
            )
            checks.append(
                {
                    "case": name,
                    "passed": observed == expected,
                    "expected": expected,
                    "observed": observed,
                }
            )
        except Exception as error:
            checks.append({"case": name, "passed": False, "error": type(error).__name__})
    print(
        json.dumps(
            {"kind": "public_practice", "provenance": snapshot["provenance"], "checks": checks},
            sort_keys=True,
        )
    )
    return 0 if all(check["passed"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
