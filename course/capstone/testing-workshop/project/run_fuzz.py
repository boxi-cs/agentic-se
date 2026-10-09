"""Run a bounded corpus through document(raw) and the independent build oracle."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# ``python -I`` omits the script directory from sys.path.  Add only this
# public project directory before importing the teaching snapshot.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from domains.validation import build, document  # noqa: E402


def observe(raw: str, known_bad: bool = False) -> bool:
    """Return whether the complete validation pipeline accepts a raw document."""
    parsed = document(raw)
    if known_bad:
        # Deliberate teaching defect: skipping build accepts an unknown status.
        return isinstance(parsed, dict)
    build(parsed)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--implementation", choices=("repaired", "known_bad"), default="repaired")
    args = parser.parse_args()
    payload = json.loads((ROOT / "fuzz-corpus.json").read_text(encoding="utf-8"))
    cases = list(payload["cases"])
    random.Random(args.seed).shuffle(cases)
    findings = []
    for case in cases:
        accepted = False
        try:
            accepted = observe(case["raw"], args.implementation == "known_bad")
        except (ValueError, TypeError, KeyError):
            accepted = False
        if accepted != case["valid"]:
            findings.append({"raw": case["raw"], "expected": case["valid"], "accepted": accepted})
    print(
        json.dumps(
            {
                "seed": args.seed,
                "cases": len(cases),
                "implementation": args.implementation,
                "findings": findings,
            },
            sort_keys=True,
        )
    )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
