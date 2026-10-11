"""Public feedback only: run fixed cases against one variant beside this script."""

import argparse
import ast
import importlib
import json
from pathlib import Path

CASES = (
    ("ok", "passed"),
    ("pass", "passed"),
    ("fail", "failed"),
    ("OK", "passed"),
    (" ok ", "passed"),
    ("\tfail\n", "failed"),
    (" PASS ", "passed"),
    ("", "unknown"),
    ("pending", "unknown"),
    ("ok|fail", "unknown"),
)


def main() -> int:
    """Report fixed characterization cases and a narrow structural measure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=("before", "rejected", "refactored", "candidate"))
    args = parser.parse_args()
    module = importlib.import_module(args.variant)
    failures = []
    for raw, expected in CASES:
        try:
            actual = module.status_label(raw)
        except Exception as exc:
            actual = {"exception": type(exc).__name__}
        if actual != expected:
            failures.append({"input": raw, "expected": expected, "actual": actual})
    # The variant is imported from this folder, so its source is read from here too.
    tree = ast.parse(Path(__file__).with_name(f"{args.variant}.py").read_text())
    report = {
        "variant": args.variant,
        "cases": len(CASES),
        "passed": len(CASES) - len(failures),
        "failures": failures,
        "if_statement_count": sum(isinstance(node, ast.If) for node in ast.walk(tree)),
        "scope": "course synthetic fixture; public feedback, not a grade",
    }
    print(json.dumps(report, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
