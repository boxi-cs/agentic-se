"""Week 14 public fixture: the current evaluator for the Week 10 status contract.

Course-authored synthetic practice with no model call, network access or file writes.
Contract: answer whether a supplied status is exactly `failed`. The exact string `yes` is
correct for `failed` and the exact string `no` for any other status. A missing or non-string
answer is `unknown`; any other string, including extra text, is `fail`.
"""


def score(status: str, output: object) -> str:
    """Classify one answer as pass, fail or unknown."""
    if not isinstance(output, str):
        return "unknown"
    expected = "yes" if status == "failed" else "no"
    return "pass" if output == expected else "fail"
