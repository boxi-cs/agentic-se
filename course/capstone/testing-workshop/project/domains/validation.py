"""Bounded data-only validation for synthetic imports and reports."""

import json
import re
from datetime import datetime

STATUSES = ("passed", "failed", "canceled", "running")


def text(value: object, maximum: int = 120) -> str:
    """Require printable nonempty text without control characters."""
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("Invalid text")
    if any(ord(c) < 32 for c in value):
        raise ValueError("Control characters are forbidden")
    return value.strip()


def integer(value: object, minimum: int = 0, maximum: int = 1000000) -> int:
    """Reject booleans, fractional values and out-of-range integers."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid integer")
    return value


def timestamp(value: object) -> str:
    """Require a canonical UTC second."""
    # Offsets are long enough to reach the grammar check and be rejected there.
    value = text(value, 25)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError("Expected a UTC timestamp")
    datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    return value


def object_pairs(pairs: list) -> dict:
    """Reject duplicate keys instead of silently replacing imported values."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    """Reject nonfinite JSON extensions."""
    raise ValueError("Nonfinite JSON value")


def document(raw: str) -> dict:
    """Read one bounded object; never follow a filename or URL."""
    if not isinstance(raw, str) or len(raw.encode()) > 12000:
        raise ValueError("Import size exceeded")
    result = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=reject_constant)
    if not isinstance(result, dict):
        raise ValueError("Expected an object")
    return result


def build(value: object) -> dict:
    """Validate all build fields before any database mutation."""
    fields = {
        "external_id",
        "pipeline_id",
        "branch",
        "status",
        "started_at",
        "duration_ms",
        "attempt",
        "message",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Invalid build fields")
    result = {
        "external_id": text(value["external_id"], 80),
        "pipeline_id": integer(value["pipeline_id"], 1),
        "branch": text(value["branch"], 80),
        "status": text(value["status"], 16),
        "started_at": timestamp(value["started_at"]),
        "duration_ms": integer(value["duration_ms"], 0, 86400000),
        "attempt": integer(value["attempt"], 1, 100),
        "message": text(value["message"], 300),
    }
    if result["status"] not in STATUSES:
        raise ValueError("Unknown status")
    return result
