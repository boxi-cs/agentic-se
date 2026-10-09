"""Public worked refactor: preserve normalization and the unknown fallback."""

LABELS = {"ok": "passed", "pass": "passed", "fail": "failed"}


def status_label(raw: str) -> str:
    """Format one status field from a synthetic build record."""
    return LABELS.get(raw.strip().lower(), "unknown")
