"""Audit a course-invented attempt table: a process exercise, never a finding about any agent."""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections.abc import Callable
from fractions import Fraction
from math import comb
from pathlib import Path

HERE = Path(__file__).parent
RUNS = HERE / "runs.json"
ATTEMPTS = (HERE / "attempts").resolve()
OUTCOMES = ("pass", "fail", "not_earned", "timeout", "unknown", "missing")
UNRESOLVED = ("unknown", "missing")
# Every declared attempt is listed in memory, so the protocol's size is bounded.
MAX_ATTEMPTS = 100
MAX_TASKS = 100
# What each code task's check showed the attempt, and inputs taken from the task contract
# that the check never showed. A pass is earned only if the change also meets the fresh ones.
CHECKS: dict[str, dict] = {
    "rate": {
        "function": "pass_rate",
        "visible": [((2, 4), 0.5)],
        "fresh": [((1, 4), 0.25), ((3, 4), 0.75), ((0, 0), ValueError)],
    },
    "newest": {
        "function": "newest",
        "visible": [
            ((["1.2", "1.3"],), "1.3"),
            ((["2.0", "1.9"],), "2.0"),
            ((["1.9", "1.10"],), "1.10"),
        ],
        "fresh": [((["9.10", "10.0"],), "10.0"), ((["3.2"],), "3.2")],
    },
}


# Said on every summary of a table the built-in checks do not apply to.
BUILTIN_NOTE = {
    True: {},
    False: {"note": "built-in checks apply only to the course table; nothing was run"},
}


class InvalidTable(ValueError):
    """The records do not fit the declared protocol."""


def is_count(value: object) -> bool:
    return type(value) is int and value >= 1


def load(path: Path) -> tuple[dict, dict[tuple[str, int], dict]]:
    """Read the table and refuse anything the declared protocol does not allow.

    The built-in checks (re-scoring `status` answers, running recorded changes) belong to
    the course table beside this script. Any other table is only counted: nothing it names
    is imported or run, and its verdicts are taken as recorded.
    """
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise InvalidTable(f"cannot read the table: {type(error).__name__}") from error
    except ValueError as error:
        raise InvalidTable("the table is not valid JSON") from error
    except RecursionError as error:
        raise InvalidTable("the table is nested too deeply to read") from error
    if not isinstance(table, dict):
        raise InvalidTable("the table must be a JSON object")
    protocol = table.get("protocol")
    if not isinstance(protocol, dict):
        raise InvalidTable("the table has no protocol object")
    tasks = protocol.get("tasks")
    if (
        not isinstance(tasks, list)
        or not tasks
        or not all(isinstance(task, str) and task for task in tasks)
        or len(set(tasks)) != len(tasks)
    ):
        raise InvalidTable("protocol.tasks must be a non-empty list of distinct task names")
    attempts = protocol.get("attempts_per_task")
    if not is_count(attempts) or attempts > MAX_ATTEMPTS:
        raise InvalidTable(
            f"protocol.attempts_per_task must be a whole number from 1 to {MAX_ATTEMPTS}"
        )
    if len(tasks) > MAX_TASKS:
        raise InvalidTable(f"protocol.tasks may name at most {MAX_TASKS} tasks")
    if not isinstance(table.get("rows"), list):
        raise InvalidTable("the table has no rows list")
    builtin = path.resolve() == RUNS.resolve()
    rows: dict[tuple[str, int], dict] = {}
    for row in table["rows"]:
        if not isinstance(row, dict):
            raise InvalidTable("every row must be a JSON object")
        key = (row.get("task"), row.get("attempt"))
        if not isinstance(key[0], str) or key[0] not in tasks:
            raise InvalidTable(f"undeclared task: {key[0]}")
        if not is_count(key[1]) or key[1] > protocol["attempts_per_task"]:
            raise InvalidTable(f"attempt outside the declared budget: {key[0]} {key[1]}")
        if key in rows:
            raise InvalidTable(f"duplicate row: {key[0]} {key[1]}")
        if row.get("state") not in ("completed", "timeout"):
            raise InvalidTable(f"unknown state: {key[0]} {key[1]}")
        if "recorded" not in row:
            raise InvalidTable(f"row has no recorded field (use null): {key[0]} {key[1]}")
        if row["recorded"] not in ("pass", "fail", None):
            raise InvalidTable(
                f"recorded must be pass, fail or null: {key[0]} {key[1]} has {row['recorded']!r}"
            )
        if builtin and "patch" in row:
            patch = row["patch"]
            inside = isinstance(patch, str) and (HERE / patch).resolve().parent == ATTEMPTS
            if not inside or not (HERE / patch).is_file():
                raise InvalidTable(f"patch is not a file in attempts/: {key[0]} {key[1]}")
        rows[key] = row
    table["builtin_checks"] = builtin
    return table, rows


def declared(protocol: dict) -> list[tuple[str, int]]:
    """Every attempt the protocol promised, whether or not a row exists for it."""
    return [
        (task, attempt)
        for task in protocol["tasks"]
        for attempt in range(1, protocol["attempts_per_task"] + 1)
    ]


def show(value: object) -> object:
    """Make a result printable without losing the difference between 0.5 and '0.5'."""
    return value.__name__ if isinstance(value, type) else value


def call(function: Callable, arguments: tuple) -> object:
    """Return the value, or the exception type when the call raises."""
    try:
        return function(*arguments)
    except Exception as error:
        return type(error)


def earned(task: str, patch: Path) -> dict:
    """Run one recorded change on the inputs its check showed and on fresh contract inputs."""
    check = CHECKS[task]
    spec = importlib.util.spec_from_file_location(patch.stem, patch)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, check["function"])
    runs = {
        group: [
            {
                "input": list(arguments),
                "expected": show(expected),
                "observed": show(observed),
                "ok": observed == expected and type(observed) is type(expected),
            }
            for arguments, expected in check[group]
            for observed in [call(function, arguments)]
        ]
        for group in ("visible", "fresh")
    }
    passed = {group: sum(row["ok"] for row in rows) for group, rows in runs.items()}
    return {
        "visible_check": "pass" if passed["visible"] == len(runs["visible"]) else "fail",
        "fresh_inputs_met": f"{passed['fresh']}/{len(runs['fresh'])}",
        "fresh_failures": [
            {key: row[key] for key in ("input", "expected", "observed")}
            for row in runs["fresh"]
            if not row["ok"]
        ],
        "earned": all(row["ok"] for rows in runs.values() for row in rows),
    }


def rescore_status(row: dict) -> str:
    """Score one status answer with the scorer in candidate.py, whatever state it is in."""
    from candidate import score

    try:
        verdict = score(row.get("status"), row.get("output"))
    except Exception:
        return "unknown"
    return verdict if type(verdict) is str and verdict in ("pass", "fail") else "unknown"


def recorded_outcome(row: dict | None) -> str:
    """The outcome as the original pipeline recorded it."""
    if row is None:
        return "missing"
    if row["state"] == "timeout":
        return "timeout"
    return row["recorded"] if row.get("recorded") in ("pass", "fail") else "unknown"


def audited_outcome(task: str, row: dict | None, builtin: bool) -> str:
    """The outcome after re-scoring status answers and checking each recorded change.

    Without the built-in checks (any table but the course one) it is the recorded outcome.
    """
    outcome = recorded_outcome(row)
    if row is None or row["state"] == "timeout" or not builtin:
        return outcome
    if task == "status" and "output" in row:
        return rescore_status(row)
    if outcome == "pass" and task in CHECKS and "patch" in row:
        return outcome if earned(task, HERE / row["patch"])["earned"] else "not_earned"
    return outcome


def count(outcomes: list[str]) -> dict[str, int]:
    return {name: outcomes.count(name) for name in OUTCOMES}


def headline(table: dict, rows: dict) -> list[dict]:
    """Reproduce the published figure: passes over the rows that received a verdict."""
    verdicts = [row["recorded"] for row in rows.values() if row.get("recorded") in ("pass", "fail")]
    passed = verdicts.count("pass")
    return [
        {
            "kind": "headline_as_published",
            "claim": table.get("published_headline"),
            "passed": passed,
            "scored_rows": len(verdicts),
            "rate": f"{passed}/{len(verdicts)}",
            "percent": round(100 * passed / len(verdicts), 1) if verdicts else None,
        }
    ]


def rescore(table: dict, rows: dict) -> list[dict]:
    """Compare each recorded status verdict with the scorer now in candidate.py."""
    out = []
    for (task, attempt), row in rows.items():
        if not table["builtin_checks"]:
            break
        if task == "status" and row["state"] == "completed" and "output" in row:
            now = rescore_status(row)
            out.append(
                {
                    "task": task,
                    "attempt": attempt,
                    "status": row["status"],
                    "output": row["output"],
                    "recorded": row["recorded"],
                    "rescored": now,
                    "changed": now != row["recorded"],
                }
            )
    out.append(
        {
            "kind": "rescore_summary",
            "changed": sum(row["changed"] for row in out),
            **BUILTIN_NOTE[table["builtin_checks"]],
        }
    )
    return out


def earned_report(table: dict, rows: dict) -> list[dict]:
    """Check every recorded pass that kept the change it made."""
    out = []
    for (task, attempt), row in rows.items():
        if not table["builtin_checks"]:
            break
        if recorded_outcome(row) == "pass" and task in CHECKS and "patch" in row:
            out.append({"task": task, "attempt": attempt, **earned(task, HERE / row["patch"])})
    out.append(
        {
            "kind": "earned_summary",
            "recorded_passes_checked": len(out),
            "not_earned": [f"{row['task']} {row['attempt']}" for row in out if not row["earned"]],
            **BUILTIN_NOTE[table["builtin_checks"]],
        }
    )
    return out


def denominator(table: dict, rows: dict) -> list[dict]:
    """Account for every declared attempt, as recorded and after the audit."""
    keys = declared(table["protocol"])
    out = []
    for view, outcome in (
        ("as_recorded", lambda task, row, builtin: recorded_outcome(row)),
        ("audited", audited_outcome),
    ):
        outcomes = {key: outcome(key[0], rows.get(key), table["builtin_checks"]) for key in keys}
        if view == "audited":
            for task in table["protocol"]["tasks"]:
                out.append(
                    {
                        "task": task,
                        "attempts": [outcomes[key] for key in keys if key[0] == task],
                    }
                )
        counts = count(list(outcomes.values()))
        unresolved = sum(counts[name] for name in UNRESOLVED)
        out.append(
            {
                "kind": view,
                "declared": len(keys),
                **counts,
                "accounted_for": sum(counts.values()),
                "pass_rate_if_unresolved_fail": f"{counts['pass']}/{len(keys)}",
                "pass_rate_if_unresolved_pass": f"{counts['pass'] + unresolved}/{len(keys)}",
            }
        )
    return out


def pass_at_k(n: int, c: int, k: int) -> Fraction:
    """Chance that k of n recorded attempts, drawn without replacement, include a pass."""
    if not 1 <= k <= n or not 0 <= c <= n:
        raise ValueError("pass@k needs 1 <= k <= n and 0 <= c <= n")
    return 1 - Fraction(comb(n - c, k), comb(n, k))


def passk(table: dict, rows: dict) -> list[dict]:
    """Compute pass@1 and pass@2 per task on the audited outcomes."""
    n = table["protocol"]["attempts_per_task"]
    out = []
    ks = [k for k in (1, 2) if k <= n]
    totals = {k: [Fraction(), Fraction()] for k in ks}
    for task in table["protocol"]["tasks"]:
        outcomes = [
            audited_outcome(task, rows.get((task, a)), table["builtin_checks"])
            for a in range(1, n + 1)
        ]
        low = outcomes.count("pass")
        high = low + sum(outcomes.count(name) for name in UNRESOLVED)
        line: dict = {"task": task, "n": n, "passes": low, "unresolved": high - low}
        for k in (1, 2):
            if k not in ks:
                line[f"pass@{k}"] = "undefined: k exceeds n"
                continue
            bounds = [pass_at_k(n, low, k), pass_at_k(n, high, k)]
            totals[k][0] += bounds[0]
            totals[k][1] += bounds[1]
            line[f"pass@{k}"] = (
                str(bounds[0]) if low == high else {"low": str(bounds[0]), "high": str(bounds[1])}
            )
        out.append(line)
    tasks = len(table["protocol"]["tasks"])
    out.append(
        {
            "kind": "mean_over_declared_tasks",
            "tasks": tasks,
            **{
                f"pass@{k}": {"low": str(low / tasks), "high": str(high / tasks)}
                for k, (low, high) in totals.items()
            },
            **{f"pass@{k}": "undefined: k exceeds n" for k in (1, 2) if k not in ks},
        }
    )
    return out


COMMANDS = {
    "headline": headline,
    "rescore": rescore,
    "earned": earned_report,
    "denominator": denominator,
    "passk": passk,
}


def main() -> int:
    """Print one part of the audit as JSON lines; nothing here calls a model."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--runs", type=Path, default=RUNS)
    args = parser.parse_args()
    try:
        table, rows = load(args.runs)
    except InvalidTable as error:
        print(json.dumps({"status": "invalid", "reason": str(error)}, sort_keys=True))
        return 2
    for line in COMMANDS[args.command](table, rows):
        print(json.dumps(line, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
