"""Deliberately weak evaluator for a fixed synthetic status question."""


def score(status: str, output: object) -> str:
    """Classify a candidate answer; nonempty text is incorrectly treated as success."""
    return "pass" if output else "fail"
