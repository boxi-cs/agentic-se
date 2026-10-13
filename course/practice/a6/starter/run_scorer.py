"""Print the starter scorer's result for the supplied synthetic instance."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scorer import score_attempt, summarize


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python run_scorer.py instance.json", file=sys.stderr)
        return 2
    instance = json.loads(Path(sys.argv[1]).read_text())
    expected = {row["id"]: row["expected"] for row in instance["inputs"]}
    outcomes = [
        score_attempt(attempt, expected[attempt["input_id"]])
        for attempt in instance["declared_attempts"]
    ]
    print(json.dumps(summarize(outcomes), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
