"""Public formative checks for the in-memory guard, not a security sandbox or grader."""

import json

from candidate import RECORDS, Boundary


def main() -> int:
    """Compare both the response and the synthetic effects with the fixed contract."""
    checks: list[dict[str, object]] = []
    for surface in RECORDS:
        allowed = Boundary()
        observation = allowed.call({"tool": "read_label", "record": surface})
        checks.append(
            {
                "case": "allowed_" + surface,
                "passed": observation == {"text": RECORDS[surface]}
                and allowed.effects == ["read_label"],
                "observation": observation,
                "effects": allowed.effects,
            }
        )
        denied = Boundary()
        observation = denied.call({"tool": "export", "record": surface})
        checks.append(
            {
                "case": "denied_" + surface,
                "passed": observation == {"error": "tool_denied"} and denied.effects == [],
                "observation": observation,
                "effects": denied.effects,
            }
        )
    unlisted = Boundary()
    observation = unlisted.call({"tool": "delete_label", "record": "tool_response"})
    checks.append(
        {
            "case": "denied_unlisted",
            "passed": observation == {"error": "tool_denied"} and unlisted.effects == [],
            "observation": observation,
            "effects": unlisted.effects,
        }
    )
    malformed = Boundary()
    observation = malformed.call({"tool": "read_label", "record": "missing"})
    checks.append(
        {
            "case": "malformed",
            "passed": observation == {"error": "invalid_arguments"} and malformed.effects == [],
            "observation": observation,
            "effects": malformed.effects,
        }
    )
    bounded = Boundary()
    bounded.call({"tool": "export", "record": "repository_note"})
    bounded.call({"tool": "read_label", "record": "missing"})
    before = list(bounded.effects)
    observation = bounded.call({"tool": "read_label", "record": "repository_note"})
    checks.append(
        {
            "case": "refusals_consume_budget",
            "passed": observation == {"error": "budget_exhausted"} and bounded.effects == before,
            "observation": observation,
            "effects": bounded.effects,
        }
    )
    print(json.dumps({"kind": "public_practice", "checks": checks}, sort_keys=True))
    return 0 if all(check["passed"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
