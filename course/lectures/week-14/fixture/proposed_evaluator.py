"""Week 14 public fixture: an agent's proposed change to evaluator.py.

Course-authored replay; no model wrote it. The reply that came with it said: "Made scoring
robust to formatting. Answers are trimmed and lower-cased, and an answer that starts with the
expected word now counts." Copy it over `evaluator.py` in a practice workspace and run the
regression gate before trusting that claim.
"""


def score(status: str, output: object) -> str:
    """Classify one answer as pass, fail or unknown."""
    if not isinstance(output, str):
        return "unknown"
    expected = "yes" if status == "failed" else "no"
    return "pass" if output.strip().lower().startswith(expected) else "fail"
