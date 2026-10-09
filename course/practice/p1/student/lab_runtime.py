"""Supplied standard-library adapters for the reviewed Week 0 launcher."""

import copy
import hashlib
import hmac
import json
import os
import secrets
import shlex
import stat
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4


class SafetyError(RuntimeError):
    """A safe diagnostic without input paths, command text or environment values."""


def require_launcher() -> Path:
    """Refuse host execution; the security boundary remains the launcher's kernel policy."""
    try:
        root = Path("/workspace")
        status = Path("/proc/self/status").read_text()
        mounts = Path("/proc/mounts").read_text().splitlines()
        workspace = next(line.split() for line in mounts if line.split()[1] == "/workspace")
        if (
            os.getuid() == 0
            or Path.cwd().resolve() != root
            or workspace[2] != "tmpfs"
            or "NoNewPrivs:\t1" not in status
            or "CapEff:\t0000000000000000" not in status
            or not Path("/bootstrap.py").is_file()
        ):
            raise ValueError
        return root
    except (OSError, ValueError, StopIteration):
        raise SafetyError("Use the reviewed scripts/course-sandbox launcher") from None


class Tool(Protocol):
    def __call__(self, **arguments: str) -> str: ...


class Model(Protocol):
    def chat(self, messages: list[dict]) -> dict: ...


@dataclass
class Trajectory:
    messages: list[dict]
    stop_reason: str


def compact(messages: list[dict], limit: int) -> list[dict]:
    """Keep the task and whole latest action/result groups; bound oversized observations."""
    result = copy.deepcopy(messages)
    for message in result[1:]:
        if message["role"] == "tool" and len(message["content"].encode()) > 256:
            message["content"] = (
                message["content"].encode()[:220].decode(errors="ignore") + " [truncated]"
            )
    while len(json.dumps(result).encode()) > limit:
        if len(result) <= 1:
            raise ValueError("Task exceeds context limit")
        end = 2
        while end < len(result) and result[end]["role"] == "tool":
            end += 1
        del result[1:end]
    return result


class WorkspaceTools:
    def __init__(self) -> None:
        self.root = require_launcher()

    def _open(self, path: str, flags: int) -> int:
        """Hold parent descriptors so link swaps cannot redirect file operations."""
        relative = Path(path)
        if not path or relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise SafetyError("Tool path must stay inside the workspace")
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in relative.parts[:-1]:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
                )
                os.close(descriptor)
                descriptor = child
            target = os.open(
                relative.name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=descriptor
            )
            info = os.fstat(target)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                os.close(target)
                raise SafetyError("Tool requires a plain workspace file")
            return target
        except OSError:
            raise SafetyError("Tool refused a file boundary or unavailable path") from None
        finally:
            os.close(descriptor)

    def read(self, path: str) -> str:
        with os.fdopen(self._open(path, os.O_RDONLY), "r") as source:
            return source.read(8192)

    def write(self, path: str, content: str) -> str:
        if len(content.encode()) > 8192:
            raise SafetyError("Tool content exceeds its bound")
        # Truncate only after validating the opened inode, including its link count.
        with os.fdopen(self._open(path, os.O_WRONLY | os.O_CREAT), "w") as destination:
            destination.truncate(0)
            destination.write(content)
        return "written"

    def bash(self, command: str) -> str:
        """A narrow bash capability: run one workspace Python file, without shell syntax."""
        require_launcher()
        arguments = shlex.split(command)
        if len(arguments) < 3 or arguments[:2] != ["python", "-B"]:
            raise SafetyError("Bash accepts only python -B workspace-file.py [plain arguments]")
        if any(
            not value or any(char in value for char in "/\\;$`|&<>\n\r") for value in arguments[3:]
        ):
            raise SafetyError("Bash argument contains a path or shell operation")
        descriptor = self._open(arguments[2], os.O_RDONLY)
        os.close(descriptor)
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-c", "exec " + shlex.join(arguments)],
            cwd=self.root,
            env={
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": "/workspace",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            capture_output=True,
            timeout=3,
            check=False,
        )
        return json.dumps(
            {"exit_code": result.returncode, "stdout": result.stdout[:512].decode(errors="replace")}
        )

    def registry(self) -> dict[str, Tool]:
        return {"read": self.read, "write": self.write, "bash": self.bash}


class IPCTools:
    """Supply call IDs without changing the student's named-tool interface."""

    def __init__(self) -> None:
        self.pending: list[dict] = []

    def bind(self, calls: list[dict]) -> None:
        if self.pending:
            raise SafetyError("Complete the current tool calls before requesting another turn")
        self.pending = copy.deepcopy(calls)

    def _call(self, name: str, arguments: dict[str, str]) -> str:
        require_launcher()
        from sandbox_model import call_tool

        if not self.pending:
            raise SafetyError("No model tool call is pending")
        call = self.pending[0]
        if call["name"] != name or call["arguments"] != arguments:
            raise SafetyError("Tool call differs from the next model action")
        result = call_tool(call["id"], name, arguments)
        self.pending.pop(0)
        return result

    def registry(self) -> dict[str, Tool]:
        return {
            "read": lambda path: self._call("read", {"path": path}),
            "write": lambda path, content: self._call("write", {"path": path, "content": content}),
            "bash": lambda command: self._call("bash", {"command": command}),
        }


class IPCModel:
    def __init__(self, tools: IPCTools | None = None) -> None:
        self.tools = tools if tools is not None else IPCTools()

    def chat(self, messages: list[dict]) -> dict:
        require_launcher()
        from sandbox_model import chat

        response = json.loads(chat(json.dumps(messages)))
        self.tools.bind(response["tool_calls"])
        return response


class Replay:
    """Fixed course-authored response data for public loop practice; no inference."""

    def __init__(self, responses: list[dict]) -> None:
        self.responses = iter(responses)

    def chat(self, messages: list[dict]) -> dict:
        return copy.deepcopy(next(self.responses))


def write_trace(messages: list[dict], path: str, run_id: str, sequence: int) -> None:
    """Project one FAKE/replay turn to the shared minimal JSONL schema, without text."""
    key = secrets.token_bytes(32)

    def field(value: object) -> dict:
        data = json.dumps(value, sort_keys=True).encode()
        return {
            "state": "not_collected",
            "length": len(data),
            "hash_algorithm": "hmac-sha256",
            "sha256": hmac.new(key, data, hashlib.sha256).hexdigest(),
        }

    steps = []
    for message in messages:
        calls = [
            {
                "id": field(call["id"]),
                "name": call["name"] if call["name"] in {"read", "write", "bash"} else "[REDACTED]",
                "arguments": field(call["arguments"]),
            }
            for call in message.get("tool_calls", [])
        ]
        results = (
            [{"tool_call_id": field(message["tool_call_id"]), "content": field(message["content"])}]
            if message["role"] == "tool"
            else []
        )
        steps.append(
            {
                "role": message["role"],
                "content": field(message.get("content", "")),
                "tool_calls": calls,
                "tool_results": results,
                "usage": None,
                "latency_ms": None,
            }
        )
    steps[-1]["usage"] = {"input_tokens": 0, "output_tokens": 0}
    steps[-1]["latency_ms"] = 0
    record = {
        "schema_version": "1",
        "run": {
            "id": run_id,
            "sequence": sequence,
            "model": "fake-v1",
            "provider": "fake",
            "cost": "0",
            "cost_status": "known",
            "started_at": datetime.now(UTC).isoformat(),
            "trace_policy": "minimal",
            "redaction_version": "1",
            "status": "ok",
        },
        "steps": steps,
    }
    with Path(path).open("a") as stream:
        stream.write(json.dumps(record) + "\n")


class TraceModel:
    """Trace replay responses only; live IPC provenance belongs to the broker's tracer."""

    def __init__(self, model: Replay, path: str = "trajectory.jsonl") -> None:
        if not isinstance(model, Replay):
            raise TypeError("TraceModel requires Replay; use the broker's tracer for live IPC")
        self.model, self.path = model, path
        self.run_id, self.sequence = str(uuid4()), 0

    def chat(self, messages: list[dict]) -> dict:
        response = self.model.chat(messages)
        write_trace(
            [*messages, {"role": "assistant", **response}], self.path, self.run_id, self.sequence
        )
        self.sequence += 1
        return response
