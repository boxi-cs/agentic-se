"""Week 11 public fixture: check replayed portal, gateway, cost and routing records.

Course-authored synthetic practice with no model call, network access or file writes. Each
command reads one JSON file, prints one line per call, run, change or task, and ends with a
`result:` line:

- `portal FILE` replays an agent's tool calls through the portal's grants and compares what
  each grant can reach with the repositories the task needs.
- `gateway FILE` replays each run through the gateway policy: a request cap, a token cap that
  each request reserves before it is sent, a route list and a fallback. It also looks for the
  key in the sandbox-side log.
- `cost FILE` adds every run and every review minute behind the accepted changes and divides
  by the number accepted, beside the trace total of one run.
- `route FILE` checks each route choice against the frozen evaluator results: a cheaper route
  is supported only if it passes every case the current route passes, on the revision in use.

Exit 0 when the records agree with the rule they are checked against, 1 when they do not, and
2 when the file cannot be read. The units are course-made numbers, not prices.
"""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

Lines = list[str]


def _n(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


class Unreadable(ValueError):
    """The file does not have the shape this command reads."""


def _field(record: object, name: str, kind: type | tuple[type, ...], where: str) -> object:
    if not isinstance(record, dict) or name not in record:
        raise Unreadable(f"{where}: missing field {name!r}")
    value = record[name]
    if not isinstance(value, kind) or isinstance(value, bool) and kind is not bool:
        raise Unreadable(f"{where}: field {name!r} has the wrong type")
    return value


def _count(record: object, name: str, where: str) -> int:
    value = _field(record, name, int, where)
    assert isinstance(value, int)
    if value < 0:
        raise Unreadable(f"{where}: field {name!r} must not be negative")
    return value


def _names(items: object, where: str) -> list[str]:
    if not isinstance(items, list) or not all(isinstance(x, str) and x for x in items):
        raise Unreadable(f"{where}: expected a list of names")
    return items


def _list(record: object, name: str, where: str) -> list:
    value = _field(record, name, list, where)
    assert isinstance(value, list)
    return value


def _text(record: object, name: str, where: str) -> str:
    value = _field(record, name, str, where)
    assert isinstance(value, str)
    return value


def portal(data: dict) -> tuple[int, Lines]:
    """Replay each call through the grants; flag any grant that reaches beyond the task."""
    needed = set(_names(_field(data, "task", dict, "task").get("repositories"), "task"))
    visibility = _field(data, "repositories", dict, "file")
    known = sorted(visibility)
    unknown = needed - set(known)
    if not needed or unknown:
        raise Unreadable("task: names no repository, or one the file does not list")
    grants = []
    for index, grant in enumerate(_list(data, "grants", "file"), 1):
        where = f"grant {index}"
        repos = _names(_field(grant, "repositories", list, where), where)
        if not set(repos) <= set(known) | {"*"}:
            raise Unreadable(f"{where}: names a repository the file does not list")
        reach = known if "*" in repos else sorted(set(repos))
        grants.append((_text(grant, "id", where), _text(grant, "tool", where), reach))

    def label(repo: str) -> str:
        return f"{repo} (private)" if visibility.get(repo) == "private" else repo

    lines = [f"task repositories: {', '.join(sorted(needed))}"]
    allowed_outside, denied = 0, 0
    for index, call in enumerate(_list(data, "session", "file"), 1):
        where = f"call {index}"
        tool, repo = _text(call, "tool", where), _text(call, "repository", where)
        if repo not in visibility:
            raise Unreadable(f"{where}: names a repository the file does not list")
        line = f"call {index} {tool} {label(repo)}: "
        for_tool = [g for g in grants if g[1] == tool]
        covering = [g for g in for_tool if repo in g[2]]
        if covering:
            line += f"allowed by {covering[0][0]}"
            allowed_outside += repo not in needed
        else:
            denied += 1
            missing = "this repository" if for_tool else "this tool"
            line += f"denied, no grant covers {missing}; the tool did not run"
        lines.append(line + ("; outside the task" if repo not in needed else ""))
    wide = 0
    for grant_id, tool, reach in grants:
        line = f"{grant_id} {tool} reaches: {', '.join(label(r) for r in reach)}"
        beyond = [r for r in reach if r not in needed]
        if beyond:
            wide += 1
            line += f"; beyond the task: {', '.join(beyond)}"
        lines.append(line)
    if wide:
        lines.append(
            f"result: OVER-BROAD - grants reaching beyond the task: {wide}; "
            f"calls outside the task that a grant allowed: {allowed_outside}"
        )
        return 1, lines
    lines.append(
        "result: WITHIN THE TASK - every grant reaches only the task's repositories; "
        f"{_n(denied, 'call')} denied"
    )
    return 0, lines


def gateway(data: dict) -> tuple[int, Lines]:
    """Replay each run through the policy and search the sandbox-side log for the key."""
    policy = _field(data, "policy", dict, "policy")
    request_cap = _count(policy, "requests_per_run", "policy")
    token_cap = _count(policy, "tokens_per_run", "policy")
    routes = _names(_field(policy, "routes", list, "policy"), "policy")
    fallback = _text(policy, "fallback", "policy")
    key = _text(policy, "key", "policy")
    if not key:
        raise Unreadable("policy: the key must not be empty")
    lines = [
        f"policy: at most {request_cap} requests and {token_cap} tokens per run, each request "
        f"reserving its worst case before it is sent; routes: {', '.join(sorted(routes))}; "
        f"fallback: {fallback}"
    ]
    differ, leaks = [], []
    for index, run in enumerate(_list(data, "runs", "file"), 1):
        where = f"run {index}"
        name, route = _text(run, "run", where), _text(run, "route", where)
        requests = _list(run, "requests", where)
        if not requests:
            raise Unreadable(f"{where}: no requests")
        problem, note, used, sent, stop = "", "", 0, 0, len(requests)
        for number, request in enumerate(requests, 1):
            at = f"{where} request {number}"
            reserve, spent = _count(request, "reserve", at), _count(request, "used", at)
            decision, provider = _text(request, "gateway", at), _text(request, "provider", at)
            if decision not in ("sent", "refused") or provider not in ("ok", "unavailable"):
                raise Unreadable(f"{at}: unknown gateway decision or provider state")
            if spent > reserve:
                raise Unreadable(f"{at}: used more than it reserved")
            expected, why = "sent", "the policy allows it"
            if route not in routes:
                expected = "refused"
                why = "the policy refuses every request on a route it does not list"
            elif number > request_cap:
                expected = "refused"
                why = f"the policy refuses it before sending (request cap {request_cap})"
            elif used + reserve > token_cap:
                expected, why = "refused", f"{used} used + {reserve} reserved > {token_cap}"
            stop = number
            if decision != expected:
                problem = f"request {number} was {decision}; {why}"
                break
            if decision == "refused":
                note = f"request {number} refused before sending ({why})"
                break
            sent += 1
            if provider == "unavailable":
                actual = _field(run, "fallback", (str, type(None)), where)
                note = f"provider unavailable at request {number}; fallback {actual} used"
                if actual != fallback:
                    problem, note = f"{note}, not {fallback}", ""
                break
            used += spent
        if not problem and stop < len(requests):
            extra = _n(len(requests) - stop, "request")
            problem = f"{extra} recorded after request {stop} ended the run"
        if problem:
            differ.append(name)
            lines.append(f"{name} {route}: {problem}; DIFFERS")
        else:
            note = note or f"{_n(sent, 'request')} sent, {used} tokens used"
            lines.append(f"{name} {route}: {note}; matches the policy")
        for number, line in enumerate(_list(run, "sandbox_log", where), 1):
            if not isinstance(line, str):
                raise Unreadable(f"{where}: sandbox_log must hold text lines")
            if key in line:
                leaks.append(name)
                lines.append(f"sandbox-side log: the key appears in {name} line {number}")
    if differ or leaks:
        parts = []
        if differ:
            parts.append(f"{_n(len(differ), 'run')} differ from the policy ({', '.join(differ)})")
        if leaks:
            runs = sorted(set(leaks))
            parts.append(f"the key reached the sandbox side in {', '.join(runs)}")
        lines.append("result: POLICY NOT ENFORCED - " + "; ".join(parts))
        return 1, lines
    lines.append(
        "result: ENFORCED - every run matches the policy and no sandbox-side line holds the key"
    )
    return 0, lines


def _amount(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{float(value):.1f}"


def cost(data: dict) -> tuple[int, Lines]:
    """Total every run and review minute, then divide by the accepted changes."""
    decisions: dict[str, tuple[str, int]] = {}
    for index, change in enumerate(_list(data, "changes", "file"), 1):
        where = f"change {index}"
        name, decision = _text(change, "change", where), _text(change, "decision", where)
        if decision not in ("accepted", "rejected") or name in decisions:
            raise Unreadable(f"{where}: unknown decision or repeated change")
        decisions[name] = (decision, _count(change, "review_minutes", where))
    runs: dict[str, list[tuple[str, int, str]]] = {name: [] for name in decisions}
    units_by_run: dict[str, int] = {}
    for index, run in enumerate(_list(data, "runs", "file"), 1):
        where = f"run {index}"
        name, change = _text(run, "run", where), _text(run, "change", where)
        if change not in runs or name in units_by_run:
            raise Unreadable(f"{where}: unknown change or repeated run")
        units = _count(run, "units", where)
        units_by_run[name] = units
        runs[change].append((name, units, _text(run, "outcome", where)))
    example = _text(data, "trace_example", "file")
    if example not in units_by_run:
        raise Unreadable("trace_example: names no run in the file")
    lines = []
    for name, (decision, minutes) in decisions.items():
        listed = ", ".join(
            f"{run} {units}" + ("" if outcome == "checks passed" else f" ({outcome})")
            for run, units, outcome in runs[name]
        )
        total = sum(units for _, units, _ in runs[name])
        lines.append(
            f"change {name} {decision}: runs {listed or 'none'}; {total} units; "
            f"review {minutes} minutes"
        )
    all_units = sum(units_by_run.values())
    all_minutes = sum(minutes for _, minutes in decisions.values())
    accepted = sum(decision == "accepted" for decision, _ in decisions.values())
    lines.append(
        f"all runs: {len(units_by_run)} runs, {all_units} units; review: {all_minutes} minutes; "
        f"accepted changes: {accepted}"
    )
    lines.append(f"trace total of one run, for comparison: {example} {units_by_run[example]} units")
    if not accepted:
        lines.append("result: NO ACCEPTED CHANGE - cost per accepted change is undefined")
        return 1, lines
    lines.append(
        f"result: cost per accepted change is {_amount(Fraction(all_units, accepted))} units of "
        f"model use and {_amount(Fraction(all_minutes, accepted))} review minutes"
    )
    return 0, lines


def route(data: dict) -> tuple[int, Lines]:
    """Support a route choice only if it loses no case the current route passes."""
    routes = _field(data, "routes", dict, "file")
    revision = {name: _text(r, "revision", f"route {name}") for name, r in routes.items()}
    units = {name: _count(r, "units_per_request", f"route {name}") for name, r in routes.items()}
    lines = [f"policy: {_text(data, 'policy', 'file')}"]
    supported, tasks = 0, _list(data, "tasks", "file")
    for index, task in enumerate(tasks, 1):
        where = f"task {index}"
        name, cases = _text(task, "task", where), _count(task, "cases", where)
        current, chosen = _text(task, "current_route", where), _text(task, "chosen_route", where)
        results = _field(task, "results", dict, where)
        if not cases or current not in routes or chosen not in routes:
            raise Unreadable(f"{where}: no cases, or a route the file does not list")
        lines.append(
            f"{name}: {cases} frozen cases; current route {current}; chosen route {chosen}"
        )
        failed: dict[str, set[int]] = {}
        for route_name, result in results.items():
            at = f"{where} route {route_name}"
            numbers = _list(result, "failed", at)
            if route_name not in routes or not all(
                isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= cases for n in numbers
            ):
                raise Unreadable(f"{at}: unknown route or a case number out of range")
            failed[route_name] = set(numbers)
            fails = sorted(failed[route_name])
            listed = f"; fails case{'s' if len(fails) > 1 else ''} {', '.join(map(str, fails))}"
            lines.append(
                f"  {route_name} {_text(result, 'revision', at)}: {cases - len(fails)} of {cases}"
                + (listed if fails else "")
            )
        stale = [
            r for r in (current, chosen) if r in results and results[r]["revision"] != revision[r]
        ]
        if chosen not in results or current not in results:
            verdict = "NOT SUPPORTED - no evaluator result for this route"
        elif stale:
            r = stale[0]
            verdict = (
                f"NOT SUPPORTED - the results for {r} are for {results[r]['revision']} and the "
                f"route is now {revision[r]}; rerun the frozen cases"
            )
        elif lost := sorted(failed[chosen] - failed[current]):
            verdict = (
                f"NOT SUPPORTED - fails case{'s' if len(lost) > 1 else ''} "
                f"{', '.join(map(str, lost))}, which {current} passes"
            )
        else:
            supported += 1
            verdict = (
                f"supported - passes every case {current} passes, at {_n(units[chosen], 'unit')} "
                f"per request instead of {units[current]}"
            )
        lines.append(f"  {chosen}: {verdict}")
    lines.append(f"result: {supported} of {len(tasks)} route choices supported by the evaluator")
    return (0 if tasks and supported == len(tasks) else 1), lines


COMMANDS = {"portal": portal, "gateway": gateway, "cost": cost, "route": route}


def main(argv: list[str] | None = None) -> int:
    """Run one check on one file and print its lines."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("file", type=Path, help="a JSON file, such as org-portal.json")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise Unreadable("the file must hold one JSON object")
        code, lines = COMMANDS[args.command](data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"cannot read {args.file}: {error.__class__.__name__}", file=sys.stderr)
        return 2
    except Unreadable as error:
        print(f"cannot check {args.file}: {error}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
