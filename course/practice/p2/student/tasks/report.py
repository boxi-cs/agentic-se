"""Course-authored review candidate: a member's activity report."""

SEPARATOR = ","


def report(rows: list[dict], viewer: str, minimum: int = 30) -> str:
    """Return a report from validated activity records."""
    selected = []
    for row in rows:
        if row["minutes"] > minimum:
            selected.append(row)

    ordered = sorted(selected, key=lambda row: row["minutes"])
    lines = [SEPARATOR.join(("title", "minutes", "same_title"))]
    for row in ordered:
        count = sum(other["title"] == row["title"] for other in selected)
        lines.append(",".join((row["title"], str(row["minutes"]), str(count))))
    return "\n".join(lines)
