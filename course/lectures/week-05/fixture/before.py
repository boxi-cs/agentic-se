"""Course-original synthetic legacy status formatter; all data is public."""


def status_label(raw: str) -> str:
    """Format one status field from a synthetic build record."""
    value = raw.strip().lower()
    if value == "ok":
        return "passed"
    if value == "pass":
        return "passed"
    if value == "fail":
        return "failed"
    return "unknown"
