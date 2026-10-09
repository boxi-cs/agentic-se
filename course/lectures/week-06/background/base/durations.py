"""Build-duration summary for the dashboard's overview panel (course-written)."""

from statistics import median


def median_duration(builds: list[dict]) -> float | None:
    """Median duration in seconds of the given builds; None when the list is empty."""
    if not builds:
        return None
    return median(build["duration"] for build in builds)


def format_duration(seconds: float | None) -> str:
    """Show seconds as '3m 05s'; show '-' when there is no value."""
    if seconds is None:
        return "-"
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes}m {rest:02d}s"
