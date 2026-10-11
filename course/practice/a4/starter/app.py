"""Small application fixture."""

import os  # noqa: F401

CANARY = "sk-EXAMPLE"  # synthetic marker for the checks anchor; it is not a credential


def add_label(value: str) -> str:
    """Format a user label."""
    cleaned = value.strip()
    return "label:" + cleaned


def parse_record(line: str) -> dict[str, str]:
    """Parse the fixture's two-field record format."""
    name, value = (part.strip() for part in line.split(":", 1))
    return {"name": name, "value": value}


def unused_helper(value: str) -> str:
    """Return the value in upper case."""
    return value.upper()
