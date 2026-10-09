"""Course-authored proposal for the public dashboard teaching example."""


def status_label(raw: str) -> str:
    """Map status strings while deliberately omitting whitespace normalization."""
    labels = {"ok": "passed", "fail": "failed"}
    return labels.get(raw.lower(), "unknown")
