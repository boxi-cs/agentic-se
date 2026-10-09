"""Public failed proposal: a shorter implementation can change behavior."""

LABELS = {"ok": "passed", "pass": "passed", "fail": "failed"}


def status_label(raw: str) -> str:
    """This deliberately drops the legacy whitespace normalization."""
    return LABELS.get(raw.lower(), "unknown")
