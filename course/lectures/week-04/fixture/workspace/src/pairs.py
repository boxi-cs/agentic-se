"""Parse one `name: value` line of a small configuration file."""


def parse_pair(line: str) -> tuple[str, str]:
    """Split a line at its first colon into a name and a value."""
    name, value = line.split(":", 1)
    return name.strip(), value
