"""Public synthetic evaluator observations, never authoritative course grades."""

from __future__ import annotations

import argparse
import json
from collections import Counter

LABELS = ("PASS", "FAIL", "UNKNOWN")
CASES = (
    ("b1", "failed", {"state": "passed", "explanation": "The build completed successfully."}),
    ("b2", "passed", {"state": "passed", "explanation": "All checks passed."}),
    ("b3", "failed", {"explanation": "A detailed report is available."}),
    ("b4", "failed", {"state": "failed", "explanation": "A check failed."}),
)
# Pinned separately from CASES: deleting a case must block the gate, not shrink it.
EXPECTED_CASES = 4
# Constructed arithmetic examples, not annotations by people or model outputs.
LABEL_PAIRS = (
    ("PASS", "PASS"),
    ("PASS", "PASS"),
    ("PASS", "PASS"),
    ("PASS", "FAIL"),
    ("FAIL", "PASS"),
    ("FAIL", "FAIL"),
    ("FAIL", "FAIL"),
    ("FAIL", "FAIL"),
    ("PASS", "UNKNOWN"),
    ("FAIL", "UNKNOWN"),
)


def score(expected: str, response: object, *, weak: bool = False) -> tuple[str, str]:
    """Compare public data with an oracle, or demonstrate a flawed fluency check."""
    if not isinstance(response, dict):
        return "UNKNOWN", "malformed_response"
    if weak:
        text = response.get("explanation")
        return (
            ("PASS", "nonempty_explanation")
            if isinstance(text, str) and text
            else (
                "UNKNOWN",
                "missing_explanation",
            )
        )
    state = response.get("state")
    if not isinstance(state, str) or state not in {"passed", "failed"}:
        return "UNKNOWN", "missing_or_invalid_state"
    return ("PASS", "state_matches") if state == expected else ("FAIL", "state_mismatch")


def gate(outcomes: list[str], *, expected_count: int) -> bool:
    """Require complete, definite success for this illustrative product gate."""
    return (
        expected_count > 0
        and len(outcomes) == expected_count
        and all(outcome == "PASS" for outcome in outcomes)
    )


def agreement(pairs: tuple[tuple[str, str], ...]) -> dict:
    """Report abstentions separately and kappa only for definite paired labels."""
    # This illustration sets UNKNOWN pairs aside before computing kappa and reports how
    # many there were.
    if any(left not in LABELS or right not in LABELS for left, right in pairs):
        raise ValueError("Invalid label")
    definite = [(left, right) for left, right in pairs if "UNKNOWN" not in (left, right)]
    n = len(definite)
    total = len(pairs)
    matrix = {left: {right: 0 for right in LABELS[:2]} for left in LABELS[:2]}
    for left, right in definite:
        matrix[left][right] += 1
    observed = expected = kappa = None
    if n:
        observed = sum(matrix[label][label] for label in LABELS[:2]) / n
        left_counts = Counter(left for left, _ in definite)
        right_counts = Counter(right for _, right in definite)
        expected = sum(left_counts[label] * right_counts[label] for label in LABELS[:2]) / n**2
        if expected != 1:
            kappa = (observed - expected) / (1 - expected)
    return {
        "n_total": total,
        "n_definite": n,
        "unknown_count": total - n,
        "unknown_rate": (total - n) / total if total else None,
        "matrix": matrix,
        "agreement": observed,
        "expected_agreement": expected,
        "kappa": kappa,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("weak", "contract", "calibration"))
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    if args.repair and args.mode != "contract":
        parser.error("--repair requires contract mode")
    if args.mode == "calibration":
        print(
            json.dumps(
                {"origin": "synthetic_label_pairs", **agreement(LABEL_PAIRS)}, sort_keys=True
            )
        )
        return 0
    outcomes = []
    for case_id, expected, original in CASES:
        response = dict(original)
        if args.repair:
            response["state"] = expected
        outcome, reason = score(expected, response, weak=args.mode == "weak")
        outcomes.append(outcome)
        print(
            json.dumps(
                {
                    "case_id": case_id,
                    "scorer": args.mode + "-v1",
                    "candidate": "repaired" if args.repair else "original",
                    "outcome": outcome,
                    "reason": reason,
                },
                sort_keys=True,
            )
        )
    passed = gate(outcomes, expected_count=EXPECTED_CASES)
    print(
        json.dumps(
            {
                "cases": len(CASES),
                "expected_cases": EXPECTED_CASES,
                "counts": {label: outcomes.count(label) for label in LABELS},
                "gate": "PASS" if passed else "BLOCK",
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
