"""Deliberately incomplete summary of synthetic reporting records."""


def summarize(
    records: list[dict[str, object]], task_ids: list[str], budget: int
) -> dict[str, object]:
    """Return a report; the starter drops timeouts and does not validate the protocol."""
    completed = [row for row in records if row["result"] != "timeout"]
    return {
        "status": "ok",
        "successes": sum(row["result"] == "pass" for row in records),
        "total": len(completed),
        "timeouts": sum(row["result"] == "timeout" for row in records),
        "coverage": len(records),
    }
