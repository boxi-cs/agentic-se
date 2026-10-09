"""Bounded, synthetic testing demonstrations; execute through course-sandbox."""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Callable

from candidate import parse_level

Parser = Callable[[str], int]
DIGITS = "0123456789"


def repaired(text: str) -> int:
    """Implement the public classroom contract, not a hidden assessment answer."""
    if len(text) == 1 and text in DIGITS:
        return int(text)
    raise ValueError("Invalid level")


def weak_checks(parser: Parser) -> None:
    """These synthetic AI-style assertions intentionally provide no useful oracle."""
    result = parser("3")
    assert result == result
    assert parser
    assert result or True


def unit_checks(parser: Parser) -> None:
    """Use explicit expected values and reject the wrong exception type."""
    assert parser("3") == 3
    for text in ("", "12", "x"):
        try:
            parser(text)
        except ValueError:
            continue
        raise AssertionError(f"Expected ValueError for {text!r}")


def property_checks(parser: Parser) -> None:
    """Check every member of the small valid-input domain."""
    for number in range(10):
        result = parser(str(number))
        assert type(result) is int
        assert 0 <= result <= 9
        assert str(result) == str(number)


def mismatch(parser: Parser, text: str) -> str | None:
    """Compare observed behavior with the public contract's explicit finite oracle."""
    expected = dict(zip(DIGITS, range(10), strict=True))
    try:
        result = parser(text)
    except ValueError:
        return "rejected_valid_input" if text in expected else None
    except Exception as error:
        return f"unexpected_{type(error).__name__}"
    if text not in expected:
        return "accepted_invalid_input"
    if type(result) is not int or result != expected[text]:
        return "wrong_value"
    return None


def corpus(seed: int) -> list[str]:
    """Keep boundary seeds and a fixed-size, reproducible synthetic search budget."""
    rng = random.Random(seed)
    boundaries = ["", "0", "9", "12", "x", " ", "-1", "\n", "\u0663"]
    alphabet = DIGITS + "x -\n" + "\u0663"
    return boundaries + [
        "".join(rng.choice(alphabet) for _ in range(rng.randrange(5))) for _ in range(100)
    ]


def fuzz(parser: Parser, seed: int) -> list[dict[str, str]]:
    """Collect mismatches; recording an error never makes the target pass."""
    findings = []
    for text in corpus(seed):
        if reason := mismatch(parser, text):
            findings.append({"text": text, "reason": reason})
    return findings


def zero_mutant(text: str) -> int:
    """Replace every valid result with zero."""
    repaired(text)
    return 0


def nine_mutant(text: str) -> int:
    """Corrupt only the upper valid boundary."""
    result = repaired(text)
    return 0 if result == 9 else result


def trailing_mutant(text: str) -> int:
    """Accept a digit prefix even when trailing characters are present."""
    return repaired(text[:1])


def mutation_report(check: Callable[[Parser], None]) -> dict:
    """Require a passing original before counting these three non-equivalent mutants."""
    check(repaired)
    outcomes = {}
    for name, parser in (
        ("all_zero", zero_mutant),
        ("nine_to_zero", nine_mutant),
        ("accept_trailing", trailing_mutant),
    ):
        try:
            check(parser)
        except AssertionError:
            outcomes[name] = "killed"
        else:
            outcomes[name] = "survived"
    return {"killed": list(outcomes.values()).count("killed"), "total": 3, "mutants": outcomes}


def strong_checks(parser: Parser) -> None:
    """Combine example/error checks with the valid-domain property."""
    unit_checks(parser)
    property_checks(parser)


def main() -> int:
    """Run one bounded experiment and return a failing status for target failures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("weak", "unit", "property", "mutation", "fuzz", "replay"))
    parser.add_argument("--implementation", choices=("candidate", "repaired"), default="candidate")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--text", default="")
    args = parser.parse_args()
    target = parse_level if args.implementation == "candidate" else repaired
    report = {
        "exercise": "course-synthetic",
        "mode": args.mode,
        "implementation": args.implementation,
    }
    failed = False
    if args.mode == "mutation":
        report.update(weak=mutation_report(weak_checks), strong=mutation_report(strong_checks))
        report["implementation"] = "repaired original plus three fixed mutants"
    elif args.mode == "fuzz":
        findings = fuzz(target, args.seed)
        report.update(seed=args.seed, cases=len(corpus(args.seed)), findings=findings)
        failed = bool(findings)
    elif args.mode == "replay":
        reason = mismatch(target, args.text)
        report.update(text=args.text, mismatch=reason)
        failed = reason is not None
    else:
        try:
            {"weak": weak_checks, "unit": unit_checks, "property": property_checks}[args.mode](
                target
            )
        except (AssertionError, ValueError, IndexError) as error:
            report["failure"] = type(error).__name__
            failed = True
    report["target_checks_passed"] = not failed
    print(json.dumps(report, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
