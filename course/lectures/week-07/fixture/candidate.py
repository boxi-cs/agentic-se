"""Course-authored faulty proposal for a single-character level parser."""


def parse_level(text: str) -> int:
    """Parse a level; the implementation deliberately violates its specification."""
    if text[0] in "0123456789":
        return int(text[0])
    raise ValueError("Invalid level")
