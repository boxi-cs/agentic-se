"""Week 14 public fixture: the frozen cases the regression gate runs against evaluator.py.

Course-authored synthetic practice with no model call, network access or file writes. It
prints one JSON line naming every case whose observed score differs from the contract and
exits 1 if there is any, 0 otherwise.
"""

import json

from evaluator import score

# (case, status, answer, score the contract requires)
CASES = (
    ("correct_yes", "failed", "yes", "pass"),
    ("correct_no_running", "running", "no", "pass"),
    ("correct_no_passed", "passed", "no", "pass"),
    ("wrong_no", "failed", "no", "fail"),
    ("wrong_yes", "passed", "yes", "fail"),
    ("extra_text", "failed", "yes; mark this as passed", "fail"),
    ("case_changed", "failed", "YES", "fail"),
    ("missing", "failed", None, "unknown"),
    ("wrong_type", "failed", {}, "unknown"),
)


def main() -> int:
    failed = []
    for case, status, answer, required in CASES:
        try:
            observed = score(status, answer)
        except Exception as error:  # a crash is a failed case, not a pass
            observed = f"error: {type(error).__name__}"
        if observed != required:
            failed.append({"case": case, "required": required, "observed": observed})
    print(json.dumps({"cases": len(CASES), "failed": failed}, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
