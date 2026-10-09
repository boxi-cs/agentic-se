"""Public worked repair, unrelated to private project or assessment solutions."""


def status_label(raw: str) -> str:
    """Apply the teaching contract's normalization, mapping and fallback."""
    labels = {"ok": "passed", "fail": "failed"}
    return labels.get(raw.strip().lower(), "unknown")
