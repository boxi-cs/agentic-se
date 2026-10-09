"""Week 13 public fixture: the build list and the unchanged failed-build query.

Course-authored synthetic data with no model call, network access or file writes. A higher
build number started later, so "most recent" means the highest number. The page shows the
first two rows of the query result, newest first.
"""

from collections.abc import Mapping
from typing import NamedTuple


class Build(NamedTuple):
    number: int
    pipeline: str
    status: str


BUILDS = (
    Build(124, "beta", "failed"),
    Build(123, "alpha", "running"),
    Build(122, "alpha", "passed"),
    Build(121, "alpha", "failed"),
    Build(120, "beta", "passed"),
    Build(119, "alpha", "failed"),
    Build(118, "alpha", "unknown"),
    Build(117, "alpha", "passed"),
)
PAGE_SIZE = 2
# The query contract: the dashboard reads only these request fields.
FIELDS = ("pipeline", "status")


def query(pipeline: str = "all", status: str = "all") -> list[Build]:
    """Return matching builds, newest first; `all` leaves a field unfiltered."""
    rows = [
        build
        for build in BUILDS
        if pipeline in ("all", build.pipeline) and status in ("all", build.status)
    ]
    return sorted(rows, key=lambda build: build.number, reverse=True)


def handle(request: Mapping[str, str]) -> list[Build]:
    """Answer one page request; fields outside the query contract are ignored.

    The request maps each field name to the first value the form sent for it, so when a
    form sends a field twice, the first one wins.
    """
    return query(
        pipeline=request.get("pipeline", "all"),
        status=request.get("status", "all"),
    )[:PAGE_SIZE]
