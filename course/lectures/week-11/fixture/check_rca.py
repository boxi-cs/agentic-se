"""Week 11 public fixture: summarise a request log and print the lines a draft analysis cites.

Course-authored synthetic practice with no model call, network access or file writes. It
reads request records in the deployment preview's format, one JSON object per line with
timestamp, event, request_id, method, path, status and duration_ms, and a draft root-cause
analysis whose hypotheses cite log line numbers. For each time window it prints the request
count, the number and share of 5xx responses and the 95th-percentile duration by nearest
rank. Then it prints every line each hypothesis cites. It never marks a hypothesis
confirmed, refuted or cannot tell: that judgement is the reader's.
"""

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = frozenset(("timestamp", "event", "request_id", "method", "path", "status", "duration_ms"))
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
WINDOW_CHOICES = (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60)
LARGEST_FILE_BYTES = 1_048_576
LARGEST_LINE_COUNT = 10_000
LARGEST_DURATION_MS = 3_600_000
LARGEST_HYPOTHESES = 10
LARGEST_CITES = 20
LARGEST_CLAIM = 200
SHOWN_SKIPPED = 10
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
METHOD = re.compile(r"[A-Z]{1,10}")
PATH = re.compile(r"/[\x21-\x7e]{0,511}")
HYPOTHESIS_ID = re.compile(r"[A-Za-z0-9-]{1,16}")


@dataclass(frozen=True)
class Request:
    """One request record and the log line it came from."""

    line: int
    time: datetime
    request_id: str
    method: str
    path: str
    status: int
    duration_ms: float


@dataclass(frozen=True)
class Hypothesis:
    """One claim from the draft and the log lines it cites."""

    id: str
    claim: str
    cites: tuple[int, ...]


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Refuse duplicate keys, so a record cannot say two things at once."""
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate key")
        data[key] = value
    return data


def refuse_constant(name: str) -> None:
    raise ValueError(f"{name} is not a number")


def parse_request(line: int, text: str) -> Request | None:
    """Return a request record, or None for any other line, such as startup text."""
    try:
        record = json.loads(text, object_pairs_hook=unique_object, parse_constant=refuse_constant)
        if not isinstance(record, dict) or set(record) != FIELDS or record["event"] != "request":
            return None
        time = datetime.strptime(record["timestamp"], TIME_FORMAT)
    except (TypeError, ValueError, RecursionError):
        return None
    status, duration = record["status"], record["duration_ms"]
    valid = (
        all(isinstance(record[name], str) for name in ("request_id", "method", "path"))
        and REQUEST_ID.fullmatch(record["request_id"])
        and METHOD.fullmatch(record["method"])
        and PATH.fullmatch(record["path"])
        and type(status) is int
        and 100 <= status <= 599
        and type(duration) in (int, float)
        and 0 <= duration <= LARGEST_DURATION_MS
        and math.isfinite(duration)
    )
    if not valid:
        return None
    return Request(
        line, time, record["request_id"], record["method"], record["path"], status, duration
    )


def parse_log(text: str) -> tuple[list[Request], list[int], int]:
    """Return the request records, the numbers of other lines and the line count."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) > LARGEST_LINE_COUNT:
        raise ValueError(f"the request log has more than {LARGEST_LINE_COUNT} lines")
    requests, skipped = [], []
    for number, line in enumerate(lines, 1):
        request = parse_request(number, line.removesuffix("\r"))
        if request is None:
            skipped.append(number)
        else:
            requests.append(request)
    return requests, skipped, len(lines)


def parse_draft(text: str) -> list[Hypothesis]:
    """Read the draft's hypotheses; refuse anything this script could not print plainly."""
    try:
        draft = json.loads(text, object_pairs_hook=unique_object, parse_constant=refuse_constant)
    except (ValueError, RecursionError):
        raise ValueError("the draft is not one JSON object without duplicate keys") from None
    entries = draft.get("hypotheses") if isinstance(draft, dict) else None
    if not isinstance(entries, list) or not 1 <= len(entries) <= LARGEST_HYPOTHESES:
        raise ValueError(f"the draft needs a list of 1 to {LARGEST_HYPOTHESES} hypotheses")
    hypotheses = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "claim", "cites"}:
            raise ValueError("each hypothesis has exactly an id, a claim and cites")
        identifier, claim, cites = entry["id"], entry["claim"], entry["cites"]
        if not (isinstance(identifier, str) and HYPOTHESIS_ID.fullmatch(identifier)):
            raise ValueError("a hypothesis id is letters, digits or hyphens, at most 16")
        if not (isinstance(claim, str) and 0 < len(claim) <= LARGEST_CLAIM and claim.isprintable()):
            raise ValueError(f"a claim is one printable line of at most {LARGEST_CLAIM} characters")
        if not (
            isinstance(cites, list)
            and 1 <= len(cites) <= LARGEST_CITES
            and all(type(n) is int and 1 <= n <= LARGEST_LINE_COUNT for n in cites)
        ):
            raise ValueError(f"cites is a list of 1 to {LARGEST_CITES} log line numbers")
        hypotheses.append(Hypothesis(identifier, claim, tuple(cites)))
    if len({hypothesis.id for hypothesis in hypotheses}) != len(hypotheses):
        raise ValueError("hypothesis ids must be unique")
    return hypotheses


def nearest_rank(values: list[float], percent: int = 95) -> float:
    """The smallest value with at least `percent` per cent of the values at or below it."""
    ordered = sorted(values)
    return ordered[-(-percent * len(ordered) // 100) - 1]


def clock(moment: datetime, with_date: bool) -> str:
    return moment.strftime("%Y-%m-%d %H:%M" if with_date else "%H:%M")


def window_table(requests: list[Request], minutes: int) -> list[str]:
    """One row per window: requests, 5xx responses, their share and the p95 duration."""
    width = minutes * 60
    windows: dict[int, list[Request]] = {}
    for request in requests:
        windows.setdefault(int(request.time.timestamp()) // width, []).append(request)
    with_date = len({request.time.astimezone(UTC).date() for request in requests}) > 1
    label_width = 22 if with_date else 11
    rows = [f"{'window':<{label_width}}  requests  5xx  error rate  p95 ms"]
    for key in sorted(windows):
        members = windows[key]
        start = datetime.fromtimestamp(key * width, UTC)
        end = datetime.fromtimestamp((key + 1) * width, UTC)
        label = f"{clock(start, with_date)}-{end:%H:%M}"
        errors = sum(request.status >= 500 for request in members)
        rate = f"{100 * errors / len(members):.1f}%"
        p95 = nearest_rank([request.duration_ms for request in members])
        rows.append(
            f"{label:<{label_width}}  {len(members):<8}  {errors:<3}  {rate:<10}  {p95:.1f}"
        )
    rows.append("p95: nearest rank, the ceil(0.95 x n)-th smallest duration in the window")
    return rows


def render(request: Request) -> str:
    return (
        f"{request.time.astimezone(UTC):%H:%M:%S}  {request.method:<5} {request.path:<33} "
        f"{request.status}  {request.duration_ms:>6.1f} ms  {request.request_id}"
    )


def report(log_text: str, draft_text: str, prefix: str | None, minutes: int) -> list[str]:
    """The printed report: the log summary, then each hypothesis with its cited lines."""
    requests, skipped, line_count = parse_log(log_text)
    hypotheses = parse_draft(draft_text)
    if not requests:
        raise ValueError("the request log holds no request records")
    times = sorted(request.time.astimezone(UTC) for request in requests)
    lines = [
        f"request log: {len(requests)} request records from "
        f"{times[0]:%H:%M:%S} to {times[-1]:%H:%M:%S} UTC"
    ]
    if skipped:
        shown = ", ".join(str(number) for number in skipped[:SHOWN_SKIPPED])
        more = ", ..." if len(skipped) > SHOWN_SKIPPED else ""
        noun = "line that is not a request record"
        if len(skipped) > 1:
            noun = "lines that are not request records"
        lines.append(f"skipped {len(skipped)} {noun}: {shown}{more}")
    chosen = requests
    if prefix is not None:
        chosen = [request for request in requests if request.path.startswith(prefix)]
        lines.append(f"path prefix: {prefix} ({len(chosen)} records)")
    lines.extend(window_table(chosen, minutes) if chosen else ["no request records match"])
    by_line = {request.line: request for request in requests}
    for hypothesis in hypotheses:
        lines.extend(["", f"{hypothesis.id}: {hypothesis.claim}"])
        for number in hypothesis.cites:
            if number in by_line:
                found = render(by_line[number])
            elif number <= line_count:
                found = "not a request record"
            else:
                found = "not in the log"
            lines.append(f"  line {number:<4}{found}")
    return lines


def read_text(path: Path, label: str) -> str:
    """Read a bounded UTF-8 file; never follow it anywhere but into this report."""
    try:
        if not path.is_file():
            raise ValueError(f"the {label} is not a regular file")
        if path.stat().st_size > LARGEST_FILE_BYTES:
            raise ValueError(f"the {label} is larger than {LARGEST_FILE_BYTES} bytes")
        data = path.read_bytes()
    except OSError:
        raise ValueError(f"cannot read the {label}") from None
    if len(data) > LARGEST_FILE_BYTES:
        raise ValueError(f"the {label} is larger than {LARGEST_FILE_BYTES} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"the {label} is not UTF-8 text") from None


def path_prefix(text: str) -> str:
    if not PATH.fullmatch(text):
        raise argparse.ArgumentTypeError("expected a path starting with /, without spaces")
    return text


def main(argv: list[str] | None = None) -> int:
    """Print the summary and the cited lines; exit 2 if either file cannot be read plainly."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", type=Path, default=HERE / "request_log.jsonl")
    parser.add_argument("--draft", type=Path, default=HERE / "agent_rca.json")
    parser.add_argument(
        "--path", type=path_prefix, metavar="PREFIX", help="summarise only paths with PREFIX"
    )
    parser.add_argument("--window-minutes", type=int, choices=WINDOW_CHOICES, default=5)
    args = parser.parse_args(argv)
    try:
        lines = report(
            read_text(args.log, "request log"),
            read_text(args.draft, "draft"),
            args.path,
            args.window_minutes,
        )
    except ValueError as problem:
        parser.error(str(problem))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
