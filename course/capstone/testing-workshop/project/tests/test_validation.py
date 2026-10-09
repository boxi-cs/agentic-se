"""One deterministic student property; add a second property from an M1 claim."""

import importlib.util
import random
from pathlib import Path

SOURCE = Path("domains/validation.py")
if not SOURCE.is_file():
    SOURCE = Path("capstone/testing-workshop/project/domains/validation.py")
SPEC = importlib.util.spec_from_file_location("workshop_validation", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
text = MODULE.text


def test_text_round_trips_printable_text() -> None:
    """The supplied example leaves the empty/type boundary for the student."""
    rng = random.Random(17)
    for _ in range(64):
        length = rng.randrange(1, 121)
        value = "".join(chr(rng.randrange(32, 127)) for _ in range(length))
        if value.strip():
            assert text(value) == value.strip()
