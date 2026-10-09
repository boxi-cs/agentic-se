"""Public behavioral checks for the synthetic Week 4 example; not a grader."""

from collections.abc import Callable

Run = tuple[int, str]

CASES: tuple[tuple[str, list[Run], list[int]], ...] = (
    ("AC1-mixed", [(12, "passed"), (9, "failed"), (11, "running")], [9]),
    ("AC1-empty", [], []),
    ("AC1-no-failures", [(2, "running"), (1, "passed")], []),
    ("AC1-sort", [(8, "failed"), (3, "failed")], [3, 8]),
    ("AC1-duplicate", [(3, "failed"), (3, "failed")], [3]),
    ("AC1-other-id", [(41, "failed")], [41]),
)


def verify(candidate: Callable[[list[Run]], list[int]]) -> None:
    """Check filtering, ordering, duplicates and preservation of input."""
    for case_id, runs, expected in CASES:
        working = list(runs)
        actual = candidate(working)
        assert actual == expected, f"{case_id}: expected {expected}, got {actual}"
        assert working == runs, f"{case_id}: input was modified"
    print("AC1: all public checks passed; this is practice feedback, not a grade")
