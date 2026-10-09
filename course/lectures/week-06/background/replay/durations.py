"""Build-duration summary for the dashboard's overview panel (course-written)."""

from statistics import median


def median_duration(builds: list[dict]) -> float | None:
    """Median duration in seconds of finished builds; None when none has finished."""
    finished = [build["duration"] for build in builds if build["duration"] is not None]
    if not finished:
        return None
    return median(finished)


def format_duration(seconds: float | None) -> str:
    """Show seconds as '3:05'; show '-' when there is no value."""
    if seconds is None:
        return "-"
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes}:{rest:02d}"
