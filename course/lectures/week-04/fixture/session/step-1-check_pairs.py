"""Focused test for parse_pair: print each failing case, then exit 1 if any case failed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pairs import parse_pair  # noqa: E402

CASES = [
    ("name:sample", ("name", "sample")),
    ("port: 8080", ("port", " 8080")),
]


def main() -> int:
    """Run every case and print one summary line."""
    failed = 0
    for line, expected in CASES:
        actual = parse_pair(line)
        if actual != expected:
            failed += 1
            print(f"FAIL parse_pair({line!r}) returned {actual!r}; expected {expected!r}")
    print(f"{len(CASES) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
