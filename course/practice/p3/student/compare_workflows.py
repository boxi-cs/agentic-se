"""Compare two bounded workflows under one approved model contract.

This controller records protocol evidence; it never executes model text on the host. Real
workflow B records are teacher supplied and are intentionally absent from this repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

STUDENT_ROOT = Path(__file__).resolve().parent
ROOT = next(
    (
        candidate
        for candidate in (STUDENT_ROOT, *STUDENT_ROOT.parents)
        if (candidate / "practice/p3/instructor").is_dir()
    ),
    Path.cwd(),
)
sys.path.insert(0, str(STUDENT_ROOT))

from lab_runtime import require_launcher  # noqa: E402

TASKS = tuple(f"p3-t{i}" for i in range(1, 5))
ATTEMPTS = 1
FAKE_TOKEN_BUDGET = 64
TIMEOUT_SECONDS = 30
CHECK_TIMEOUT_SECONDS = 5
MODEL_REQUESTS_PER_TASK = 2
TASK_PROMPTS = {
    "p3-t1": (
        "Write Python only. Define status_counts(records) for red, green, pending statuses; "
        "return all three counts without mutation."
    ),
    "p3-t2": (
        "Write Python only. Define longest_red_streak(records) for red, green, pending "
        "statuses; return the longest consecutive red run without mutation."
    ),
    "p3-t3": (
        "Write Python only. Define slowest_jobs(jobs, k), returning k job IDs by descending "
        "duration; ties are valid and input is unchanged."
    ),
    "p3-t4": (
        "Write Python only. Define parse_duration(text) for ASCII digits in Nm, Ns or NmNs; "
        "return seconds and raise ValueError otherwise."
    ),
}


class ProtocolError(ValueError):
    """A caller attempted to change the frozen comparison protocol."""


class BrokerUnavailable(ProtocolError):
    """The admitted launcher has no usable prompt broker for this task."""


@dataclass(frozen=True)
class Protocol:
    model: str
    profile: str
    profile_digest: str
    tasks: tuple[str, ...] = TASKS
    attempts_per_task: int = ATTEMPTS
    timeout_seconds: int = TIMEOUT_SECONDS
    candidate_timeout_seconds: int = CHECK_TIMEOUT_SECONDS
    model_requests_per_task: int = MODEL_REQUESTS_PER_TASK

    def as_dict(self) -> dict:
        result = asdict(self)
        result["tasks"] = list(self.tasks)
        return result


def launcher_required() -> None:
    """Require the actual course runtime boundary before any model call."""
    try:
        require_launcher()
    except Exception as exc:
        raise ProtocolError(
            "Use the reviewed course launcher; direct host execution is refused"
        ) from exc


def protocol(profile: str = "offline") -> Protocol:
    if any(key.startswith("COURSE_LLM_") for key in os.environ):
        raise ProtocolError(
            "Remove model override environment variables before using a locked profile"
        )
    if profile not in {"approved-hosted", "offline"}:
        raise ProtocolError("Profile must be approved-hosted or offline")
    contract = (
        {"version": 3}
        if profile == "approved-hosted"
        else {"ipc": {"prompt_bytes": 1024, "request_bytes": 65536}}
    )
    identity = json.dumps(
        {
            "profile": profile,
            "model": profile,
            "contract": contract,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return Protocol(profile, profile, hashlib.sha256(identity).hexdigest())


def call_fake(task: str, workflow: str, repair: bool = False) -> dict:
    try:
        from course_llm import Budget, Client, FakeProvider
    except ImportError:
        usage = {"input_tokens": 0, "output_tokens": 0}
        cost = "0"
    else:
        prompt = f"P3 {workflow} task {task}; return a patch, never a command."
        with Client(
            FakeProvider([{"content": "FAKE practice patch"}]),
            budget=Budget(FAKE_TOKEN_BUDGET),
        ) as client:
            response = client.chat(
                [{"role": "user", "content": prompt}], max_tokens=FAKE_TOKEN_BUDGET
            )
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        cost = str(response.cost_usd) if response.cost_usd is not None else "unknown"
    return {
        "provider": "fake",
        "fake": True,
        "usage": usage,
        "cost": cost,
        "repair": repair,
    }


def call_launcher(task: str, workflow: str, route: str, repair: bool = False) -> dict:
    """Ask the launcher's broker for code; the broker selects API or replay."""
    try:
        from sandbox_model import chat
    except (ImportError, AttributeError, RuntimeError) as exc:
        raise BrokerUnavailable("Use the launcher broker for API or replay calls") from exc

    prompt = f"P3_TASK_ID={task} P3_REPAIR={int(repair)}\n{TASK_PROMPTS[task]}"
    if workflow == "b":
        prompt += " Return a small candidate that can be checked independently."
    if repair:
        prompt += " This is one bounded repair after an unsuccessful check."
    source = chat(prompt).strip()
    if source.startswith("```python") and source.endswith("```"):
        source = source[len("```python") : -3].strip()
    return {
        "provider": route,
        "fake": False,
        "source": source,
        "usage": None,
        "cost": "unknown",
        "repair": repair,
    }


def check_candidate(task: str, source: str) -> str:
    """Run returned code only inside the already admitted launcher sandbox."""
    if not source:
        return "missing"
    if len(source.encode()) > 8192:
        return "invalid"
    task_dir = Path(__file__).resolve().parent / "tasks" / task
    with tempfile.TemporaryDirectory(prefix="p3-task-") as directory:
        work = Path(directory)
        for name in ("benchmark.py", "cases.json"):
            (work / name).write_bytes((task_dir / name).read_bytes())
        (work / "candidate.py").write_text(source + "\n", encoding="utf-8")
        try:
            process = subprocess.Popen(
                [sys.executable, "-B", "benchmark.py"],
                cwd=work,
                env={
                    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                    "PYTHONNOUSERSITE": "1",
                },
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                _, _ = process.communicate(timeout=CHECK_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                return "timeout"
        except subprocess.TimeoutExpired:
            return "timeout"
    return "success" if process.returncode == 0 else "failure"


def run_task(
    which: str,
    task: str,
    *,
    fake: bool = False,
    profile: str = "approved-hosted",
    route: str = "replay",
) -> dict:
    """Run one task so a launcher invocation never needs more than two model calls."""
    launcher_required()
    if which not in {"a", "b"}:
        raise ProtocolError("Workflow must be a or b")
    if task not in TASKS:
        raise ProtocolError("Unknown P3 task")
    if fake and route == "replay":
        route = "fake"
    if (
        route not in {"api", "replay", "fake"}
        or (fake and route != "fake")
        or (not fake and route == "fake")
    ):
        raise ProtocolError("Route must be api, replay or fake")
    spec = protocol(profile)
    started = time.time()
    try:
        if fake:
            outcome = call_fake(task, which)
            category = "failure"
        else:
            outcome = call_launcher(task, which, route)
            category = check_candidate(task, outcome["source"])
            if which == "b" and category == "failure":
                repaired = call_launcher(task, which, route, repair=True)
                repaired_category = check_candidate(task, repaired["source"])
                if repaired_category == "success":
                    category = "repaired"
                    outcome = repaired
    except (BrokerUnavailable, RuntimeError, ValueError):
        outcome = {
            "provider": route,
            "fake": False,
            "usage": None,
            "cost": "unknown",
        }
        category = "missing"
    return {
        "run_id": str(uuid4()),
        "workflow": which,
        "task_id": task,
        "protocol": spec.as_dict(),
        "attempts": 1,
        "result": category,
        "started_at": started,
        "duration_seconds": max(0.0, time.time() - started),
        "usage": outcome["usage"],
        "cost": outcome["cost"],
        "fake_provider": outcome["fake"],
        "provider": outcome["provider"],
    }


def run_workflow(
    which: str,
    *,
    fake: bool = False,
    profile: str = "approved-hosted",
    route: str = "replay",
) -> dict:
    launcher_required()
    if which not in {"a", "b"}:
        raise ProtocolError("Workflow must be a or b")
    if fake and route == "replay":
        route = "fake"
    if (
        route not in {"api", "replay", "fake"}
        or (fake and route != "fake")
        or (not fake and route == "fake")
    ):
        raise ProtocolError("Route must be api, replay or fake")
    spec = protocol(profile)
    records = [
        run_task(which, task, fake=fake, profile=profile, route=route) for task in spec.tasks
    ]
    return {"schema_version": 1, "protocol": spec.as_dict(), "records": records}


def validate_records(
    report: dict,
    expected: Protocol | None = None,
    *,
    require_all: bool = True,
) -> None:
    if set(report) != {"schema_version", "protocol", "records"} or report["schema_version"] != 1:
        raise ProtocolError("Malformed workflow report")
    spec = expected or protocol(report["protocol"]["profile"])
    if report["protocol"] != spec.as_dict():
        raise ProtocolError("Profile, budget or task protocol drift")
    seen = set()
    for record in report["records"]:
        if record["task_id"] in seen or record["task_id"] not in TASKS or record["attempts"] != 1:
            raise ProtocolError("Duplicate task attempt or protocol violation")
        seen.add(record["task_id"])
        if record["protocol"] != spec.as_dict() or record["workflow"] not in {"a", "b"}:
            raise ProtocolError("Record protocol mismatch")
        if record["result"] not in {
            "success",
            "failure",
            "timeout",
            "repaired",
            "missing",
            "invalid",
        }:
            raise ProtocolError("Unknown result category")
        if not isinstance(record["fake_provider"], bool):
            raise ProtocolError("Provider provenance is required")
    if require_all and seen != set(TASKS):
        raise ProtocolError("Every required task needs exactly one raw record")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", choices=("a", "b"), required=True)
    parser.add_argument("--task", choices=TASKS)
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--profile", default="approved-hosted")
    parser.add_argument("--route", choices=("api", "replay", "fake"), default="replay")
    parser.add_argument("--out", dest="out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.task:
            spec = protocol(args.profile)
            report = {
                "schema_version": 1,
                "protocol": spec.as_dict(),
                "records": [
                    run_task(
                        args.workflow,
                        args.task,
                        fake=args.fake,
                        profile=args.profile,
                        route=args.route,
                    )
                ],
            }
        else:
            report = run_workflow(
                args.workflow, fake=args.fake, profile=args.profile, route=args.route
            )
        validate_records(report, require_all=not bool(args.task))
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        if not args.out.is_absolute() and ".." not in args.out.parts:
            try:
                from sandbox_model import emit_artifact

                emit_artifact(args.out.as_posix())
            except ImportError:
                pass
        print(
            json.dumps(
                {"status": "ok", "fake_provider": args.fake, "records": len(report["records"])}
            )
        )
        return 0
    except (ProtocolError, OSError, ValueError):
        print("ERROR: workflow protocol rejected.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
