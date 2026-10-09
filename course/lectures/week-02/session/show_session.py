"""Print a recorded agent session request by request. Offline and read-only.

It reads two kinds of JSONL file:

* A session recording. The first line is a header
  (``{"kind": "header", "format": "course-session", ...}``); every later line is one
  model request and its response in chat-completions form
  (``{"kind": "exchange", "seq": N, "request": {...}, "response": {...}}``).
* A course trajectory (``"schema_version": "1"``), such as P1's ``trajectory.jsonl``
  or a launcher ``--trace`` file. It holds roles, lengths and tool names, not text.

Usage::

    python3 show_session.py RECORD.jsonl              # one summary per request
    python3 show_session.py RECORD.jsonl --request 4  # everything sent and returned
    python3 show_session.py RECORD.jsonl --check      # publication check for teachers

The script uses only the standard library. It never runs anything found in a record
and never uses the network. The same input always gives the same output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = "course-session"
PROVENANCES = ("course-made-sample", "teacher-recording")
HEADER_FIELDS = (
    "format",
    "format_version",
    "provenance",
    "agent",
    "agent_version",
    "agent_license",
    "recorded_on",
    "configuration",
    "wire",
    "response_assembled_from_stream",
    "task",
    "redactions",
)
ROLES = ("system", "developer", "user", "assistant", "tool")
PREVIEW = 72
MAX_BYTES = 20_000_000

# Text that must not appear in a published recording. A match is a finding to resolve
# by redaction with a visible [REDACTED: ...] marker, not by silent deletion.
SENSITIVE = (
    ("key-like token", re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")),
    ("key-like token", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer credential", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("credential field", re.compile(r"(?i)\b(?:authorization|x-api-key|api[_-]?key)\b\s*[:=]")),
    ("email address", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")),
    ("home directory path", re.compile(r"(?:/Users/|/home/)(?!\[REDACTED)[^/\s\"']+")),
    ("home directory path", re.compile(r"(?i)[A-Z]:\\\\?Users\\\\?(?!\[REDACTED)[^\\\s\"']+")),
)


class RecordError(ValueError):
    """A record that cannot be read as either supported format."""


@dataclass(frozen=True)
class Message:
    """One message as sent to the model, reduced to what the summary compares."""

    role: str
    text: str
    size: int
    calls: tuple[tuple[str, str, str], ...] = ()
    call_id: str = ""
    known_text: bool = True

    def key(self) -> tuple:
        return (self.role, self.text, self.size, self.calls, self.call_id)

    def label(self) -> str:
        unit = "chars" if self.known_text else "bytes"
        if self.role == "assistant":
            parts = []
            if self.size:
                parts.append(f"text {self.size} {unit}")
            if self.calls:
                count = len(self.calls)
                names = ", ".join(name for _, name, _ in self.calls)
                parts.append(f"{count} tool call{'s' if count > 1 else ''}: {names}")
            return "assistant (" + ("; ".join(parts) or "empty") + ")"
        if self.role == "tool":
            target = f" for {self.call_id}" if self.call_id else ""
            return f"tool result{target} ({self.size} {unit})"
        return f"{self.role} ({self.size} {unit})"


@dataclass
class Exchange:
    """One model request and what came back."""

    number: int
    messages: list[Message]
    response: Message | None
    finish: str
    tools: list[dict] = field(default_factory=list)
    body_bytes: int | None = None
    usage: tuple[int, int] | None = None
    note: str = ""
    raw_request: dict | None = None
    raw_response: dict | None = None


@dataclass
class Record:
    kind: str
    header: dict
    exchanges: list[Exchange]


def _text(content: object) -> str:
    """Chat-completions content is a string, null or a list of typed parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                pieces.append(part["text"])
            else:
                pieces.append("[non-text part]")
        return "\n".join(pieces)
    raise RecordError("message content must be a string, null or a list of parts")


def _chat_message(raw: object, where: str) -> Message:
    if not isinstance(raw, dict) or raw.get("role") not in ROLES:
        raise RecordError(f"{where}: each message needs a known role")
    text = _text(raw.get("content"))
    calls = []
    for item in raw.get("tool_calls") or []:
        function = item.get("function") if isinstance(item, dict) else None
        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
            raise RecordError(f"{where}: a tool call needs a function name")
        arguments = function.get("arguments", "")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, sort_keys=True)
        calls.append((str(item.get("id", "")), function["name"], arguments))
    call_id = raw.get("tool_call_id", "")
    if raw["role"] == "tool" and not isinstance(call_id, str):
        raise RecordError(f"{where}: tool_call_id must be a string")
    return Message(raw["role"], text, len(text), tuple(calls), call_id or "")


def _session(lines: list[tuple[int, dict]]) -> Record:
    number, header = lines[0]
    missing = [name for name in HEADER_FIELDS if name not in header]
    if missing:
        raise RecordError(f"line {number}: header is missing {', '.join(missing)}")
    if header["format_version"] != 1 or header["wire"] != "chat-completions":
        raise RecordError(f"line {number}: only format_version 1 with chat-completions is read")
    if header["provenance"] not in PROVENANCES:
        raise RecordError(f"line {number}: provenance must be one of {', '.join(PROVENANCES)}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(header["recorded_on"])):
        raise RecordError(f"line {number}: recorded_on must be YYYY-MM-DD")
    if not isinstance(header["redactions"], list):
        raise RecordError(f"line {number}: redactions must be a list")
    exchanges = []
    for expected, (number, line) in enumerate(lines[1:], 1):
        where = f"line {number}"
        if line.get("kind") != "exchange" or line.get("seq") != expected:
            raise RecordError(f"{where}: expected exchange with seq {expected}")
        request, response = line.get("request"), line.get("response")
        if not isinstance(request, dict) or not isinstance(request.get("messages"), list):
            raise RecordError(f"{where}: request.messages must be a list")
        if not isinstance(response, dict) or not response.get("choices"):
            raise RecordError(f"{where}: response.choices must be a nonempty list")
        choice = response["choices"][0]
        if not isinstance(choice, dict):
            raise RecordError(f"{where}: response choice must be an object")
        tools = request.get("tools") or []
        if not isinstance(tools, list):
            raise RecordError(f"{where}: request.tools must be a list")
        usage = response.get("usage")
        tokens = None
        if isinstance(usage, dict):
            tokens = (int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
        body = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        exchanges.append(
            Exchange(
                number=expected,
                messages=[
                    _chat_message(item, f"{where} message {index}")
                    for index, item in enumerate(request["messages"])
                ],
                response=_chat_message(choice.get("message"), f"{where} response"),
                finish=str(choice.get("finish_reason")),
                tools=tools,
                body_bytes=len(body.encode("utf-8")),
                usage=tokens,
                raw_request=request,
                raw_response=response,
            )
        )
    if not exchanges:
        raise RecordError("the recording holds no requests")
    return Record("session", header, exchanges)


def _field_size(value: object, where: str) -> int:
    if not isinstance(value, dict) or not isinstance(value.get("length"), int):
        raise RecordError(f"{where}: expected a field with a length")
    return value["length"]


def _trace_message(step: object, where: str) -> Message:
    if not isinstance(step, dict) or step.get("role") not in ROLES:
        raise RecordError(f"{where}: each step needs a known role")
    calls = tuple(("", str(call.get("name", "?")), "") for call in step.get("tool_calls") or [])
    # The trace stores the length of the JSON-encoded content; drop a string's two quotes.
    size = max(0, _field_size(step.get("content"), where) - 2)
    return Message(step["role"], "", size, calls, "", known_text=False)


def _trajectory(lines: list[tuple[int, dict]]) -> Record:
    exchanges = []
    first = lines[0][1].get("run", {})
    for expected, (number, line) in enumerate(lines, 1):
        where = f"line {number}"
        run, steps = line.get("run"), line.get("steps")
        if line.get("schema_version") != "1" or not isinstance(run, dict):
            raise RecordError(f"{where}: expected a course trajectory record")
        if not isinstance(steps, list) or not steps:
            raise RecordError(f"{where}: steps must be a nonempty list")
        messages = [_trace_message(step, f"{where} step {i}") for i, step in enumerate(steps)]
        response, usage = None, None
        last = steps[-1]
        if run.get("status") == "ok" and isinstance(last.get("usage"), dict):
            response = messages.pop()
            usage = (
                int(last["usage"].get("input_tokens", 0)),
                int(last["usage"].get("output_tokens", 0)),
            )
        note = f"run sequence {run.get('sequence')}, status {run.get('status')}"
        if run.get("id") != first.get("id"):
            note += ", different run"
        exchanges.append(
            Exchange(
                number=expected,
                messages=messages,
                response=response,
                finish="" if response else "no response recorded",
                usage=usage,
                note=note,
            )
        )
    header = {
        "provider": first.get("provider"),
        "model": first.get("model"),
        "trace_policy": first.get("trace_policy"),
    }
    return Record("trajectory", header, exchanges)


def load(path: Path) -> Record:
    """Read either supported format; raise RecordError with a line number otherwise."""
    try:
        if path.stat().st_size > MAX_BYTES:
            raise RecordError("the file is larger than this viewer reads")
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise RecordError(f"cannot read the file ({error.__class__.__name__})") from None
    lines = []
    for number, text in enumerate(raw_lines, 1):
        if not text.strip():
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            raise RecordError(f"line {number}: not valid JSON") from None
        if not isinstance(value, dict):
            raise RecordError(f"line {number}: each line must be a JSON object")
        lines.append((number, value))
    if not lines:
        raise RecordError("the file is empty")
    try:
        if lines[0][1].get("kind") == "header" and lines[0][1].get("format") == FORMAT:
            return _session(lines)
        if lines[0][1].get("schema_version") == "1":
            return _trajectory(lines)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, RecordError):
            raise
        raise RecordError(f"unexpected structure ({error.__class__.__name__})") from None
    raise RecordError("not a course session recording or course trajectory")


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= PREVIEW else flat[: PREVIEW - 3] + "..."


def _tool_names(tools: list[dict]) -> list[str]:
    names = []
    for tool in tools:
        function = tool.get("function") if isinstance(tool, dict) else None
        names.append(str(function.get("name")) if isinstance(function, dict) else "?")
    return names


def compare(previous: Exchange | None, current: Exchange) -> tuple[list[int], list[int], int]:
    """Return (changed earlier indices, new indices, dropped count) against the last request.

    Earlier messages are those the previous request already sent. A shorter history means
    messages were removed or merged.
    """
    if previous is None:
        return [], list(range(len(current.messages))), 0
    old = len(previous.messages)
    shared = min(old, len(current.messages))
    changed = [i for i in range(shared) if previous.messages[i].key() != current.messages[i].key()]
    return changed, list(range(old, len(current.messages))), max(0, old - len(current.messages))


def _instructions(exchange: Exchange) -> list[Message]:
    return [m for m in exchange.messages if m.role in ("system", "developer")]


def _setup_lines(previous: Exchange | None, exchange: Exchange) -> list[str]:
    """Whether the instructions and tool definitions were sent again, changed or new."""
    system = _instructions(exchange)
    if not system:
        state = "none in this request"
    elif previous is None:
        state = f"{len(system)} message(s), {sum(m.size for m in system)} chars"
    elif [m.key() for m in system] == [m.key() for m in _instructions(previous)]:
        state = "re-sent unchanged"
    else:
        state = "changed since the previous request"
    names = _tool_names(exchange.tools)
    if previous is None:
        tools = f"{len(names)}: {', '.join(names) or 'none'}"
    elif exchange.tools == previous.tools:
        tools = f"re-sent unchanged ({len(names)})"
    else:
        tools = f"changed, now {len(names)}: {', '.join(names) or 'none'}"
    return [f"  instructions: {state}", f"  tools offered: {tools}"]


def _history_lines(previous: Exchange | None, exchange: Exchange) -> list[str]:
    """New messages, and earlier messages that differ from what was sent before."""
    changed, new, dropped = compare(previous, exchange)
    out = [f"  messages sent: {len(exchange.messages)}; new since previous request:"]
    for index in new:
        message = exchange.messages[index]
        line = f"    [{index}] {message.label()}"
        if previous is not None and previous.response is not None and index == new[0]:
            if message.key() == previous.response.key():
                line += ", the previous response sent back"
            elif message.role == "assistant":
                line += ", differs from the previous response"
        if message.known_text and message.text and message.role not in ("system", "developer"):
            line += f' "{_preview(message.text)}"'
        out.append(line)
    if not new:
        out.append("    none")
    if previous is None:
        return out
    out.append("  changed earlier messages:" + ("" if changed else " none"))
    for index in changed:
        now = exchange.messages[index]
        line = f"    [{index}] {now.label()}, was {previous.messages[index].size}"
        if now.known_text and now.text:
            line += f' now "{_preview(now.text)}"'
        out.append(line)
    if dropped:
        out.append(f"  history is shorter than in the previous request by {dropped} message(s)")
    return out


def summary(record: Record) -> str:
    out = []
    header = record.header
    if record.kind == "session":
        source = (
            "course-made sample, not a recording of a product"
            if header["provenance"] == "course-made-sample"
            else "recording by the teaching team"
        )
        out += [
            f"Session: {source}",
            f"Agent: {header['agent']} (version: {header['agent_version']})",
            f"Recorded on: {header['recorded_on']}; configuration: {header['configuration']}",
            f"Task: {header['task']}",
        ]
        if header["redactions"]:
            out.append("Redactions: " + "; ".join(str(item) for item in header["redactions"]))
    else:
        out += [
            f"Course trajectory: provider {header['provider']}, model {header['model']}",
            "Text is not collected in this trace: you see roles, approximate sizes in bytes",
            "and tool names.",
            "Compare messages by role and size only; read the text in the run's own output.",
        ]
    out.append(f"Requests: {len(record.exchanges)}")
    previous = None
    for exchange in record.exchanges:
        out.append("")
        title = f"Request {exchange.number}"
        if exchange.body_bytes is not None:
            title += f"  [request body {exchange.body_bytes} bytes"
            if previous is not None and previous.body_bytes is not None:
                title += f", {exchange.body_bytes - previous.body_bytes:+d}"
            title += "]"
        if exchange.note:
            title += f"  [{exchange.note}]"
        out.append(title)
        if record.kind == "session":
            out += _setup_lines(previous, exchange)
        out += _history_lines(previous, exchange)
        reply = exchange.response
        if reply is None:
            out.append(f"  response: {exchange.finish}")
        else:
            out.append(
                "  response:" + (f" finish_reason={exchange.finish}" if exchange.finish else "")
            )
            if reply.known_text and reply.text:
                out.append(f'    text: "{_preview(reply.text)}"')
            elif reply.size:
                out.append(f"    text: {reply.size} bytes (not collected)")
            else:
                out.append("    text: none")
            for identifier, name, arguments in reply.calls:
                label = f"{identifier} " if identifier else ""
                shown = f" {_preview(arguments)}" if arguments else ""
                out.append(f"    tool call: {label}{name}{shown}")
        if exchange.usage is not None:
            out.append(f"  usage: {exchange.usage[0]} input / {exchange.usage[1]} output tokens")
        previous = exchange
    out.append("")
    out.append("End of record")
    last = record.exchanges[-1]
    if last.response is None:
        out.append("  the last request has no recorded response")
    elif last.response.calls:
        out.append(
            "  the last response still asks for tools: the record stops before the loop ends"
        )
    else:
        out.append(
            "  the last response has no tool calls"
            + (f" (finish_reason={last.finish})" if last.finish else "")
            + ": the loop ends here"
        )
    counts: dict[str, int] = {}
    for exchange in record.exchanges:
        for _, name, _ in exchange.response.calls if exchange.response else ():
            counts[name] = counts.get(name, 0) + 1
    listed = ", ".join(f"{name} {counts[name]}" for name in sorted(counts)) or "none"
    out.append(f"  tool calls by name: {listed}")
    return "\n".join(out) + "\n"


def detail(record: Record, number: int) -> str:
    """Everything sent in one request and everything returned, in full."""
    if not 1 <= number <= len(record.exchanges):
        raise RecordError(f"request {number} does not exist (1-{len(record.exchanges)})")
    exchange = record.exchanges[number - 1]
    out = [f"Request {number} of {len(record.exchanges)}"]
    if record.kind != "session":
        out.append("This trace holds no text. Roles, sizes and tool names:")
        for index, message in enumerate(exchange.messages):
            out.append(f"  [{index}] {message.label()}")
        if exchange.response:
            out.append(f"  response: {exchange.response.label()}")
        return "\n".join(out) + "\n"
    request = dict(exchange.raw_request or {})
    settings = {k: v for k, v in request.items() if k not in ("messages", "tools")}
    out += ["", "== Request settings ==", json.dumps(settings, indent=2, sort_keys=True)]
    out += ["", f"== Tools offered ({len(exchange.tools)}) =="]
    for tool in exchange.tools:
        out.append(json.dumps(tool, indent=2, ensure_ascii=False))
    out += ["", f"== Messages sent ({len(exchange.messages)}) =="]
    for index, message in enumerate(exchange.messages):
        out.append(f"--- [{index}] {message.label()}")
        if message.text:
            out.append(message.text)
        for identifier, name, arguments in message.calls:
            out.append(f"tool call {identifier}: {name} {arguments}")
    out += ["", "== Response =="]
    out.append(json.dumps(exchange.raw_response, indent=2, ensure_ascii=False, sort_keys=True))
    return "\n".join(out) + "\n"


def _strings(value: object, path: str = "$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield f"{path}.{key}", str(key)
            yield from _strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _strings(item, f"{path}[{index}]")


def check(path: Path) -> list[str]:
    """Problems that block publishing a recording. An empty list is not a review."""
    record = load(path)
    if record.kind != "session":
        return ["only session recordings are checked for publication"]
    findings = []
    header = record.header
    if header["provenance"] == "teacher-recording":
        for name in ("agent", "agent_version", "agent_license", "configuration"):
            value = str(header.get(name, "")).strip().lower()
            if not value or value in ("not applicable", "unknown", "n/a"):
                findings.append(f"header: {name} must name the actual value")
    lines = path.read_text(encoding="utf-8").splitlines()
    for number, text in enumerate(lines, 1):
        if not text.strip():
            continue
        for where, value in _strings(json.loads(text)):
            if where.endswith((".headers", ".Headers")):
                findings.append(f"line {number} {where}: HTTP headers must not be recorded")
            for label, pattern in SENSITIVE:
                if pattern.search(value):
                    findings.append(f"line {number} {where}: possible {label}")
    for exchange in record.exchanges:
        offered = set(_tool_names(exchange.tools))
        if exchange.response:
            for _, name, _ in exchange.response.calls:
                if offered and name not in offered:
                    findings.append(
                        f"request {exchange.number}: response calls {name}, which was not offered"
                    )
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("record", type=Path, help="session recording or course trajectory")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--request", type=int, metavar="N", help="show request N in full")
    group.add_argument("--check", action="store_true", help="publication check for teachers")
    args = parser.parse_args(argv)
    try:
        if args.check:
            findings = check(args.record)
            for finding in findings:
                print(finding)
            print(f"{len(findings)} finding(s)")
            return 1 if findings else 0
        record = load(args.record)
        text = summary(record) if args.request is None else detail(record, args.request)
    except RecordError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
