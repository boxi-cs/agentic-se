"""Course-made scorer for the A6 audit."""

from __future__ import annotations

from typing import Any


def score_attempt(attempt: dict[str, Any], expected: str) -> str:
    """Classify one recorded attempt without calling a model."""
    outcome = attempt.get("outcome")
    if outcome in {"timeout", "missing"}:
        return outcome
    return "success" if attempt.get("output") == expected else "failure"


def summarize(outcomes: list[str]) -> dict[str, int | float]:
    """Summarize outcomes and a reported rate."""
    counts = {key: outcomes.count(key) for key in ("success", "failure", "timeout", "missing")}
    completed = counts["success"] + counts["failure"]
    counts["declared"] = len(outcomes)
    counts["reported_rate"] = counts["success"] / completed if completed else 0.0
    return counts
