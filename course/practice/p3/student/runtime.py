"""Trusted host controller: generated code runs only in the existing T-104 launcher."""

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from course_sandbox import lock_profile, run  # noqa: E402
from sandbox_broker import prompt_from_request  # noqa: E402

from course_llm import Client, FakeProvider  # noqa: E402

from .bundle import ROOT as PUBLIC  # noqa: E402
from .bundle import TASKS, loads, read, require  # noqa: E402


def admitted(profile: str, version: int, digest: str) -> dict:
    return lock_profile(profile, version, digest)["contract"]


class FakeBroker:
    """Explicit FAKE data; the learner still sees genuine sandbox checks of this text."""

    def __init__(self, model: dict, tracer: object) -> None:
        self.model, self.tracer = model, tracer

    def __call__(self, raw: bytes, seconds: float) -> str:
        require(seconds > 0)
        prompt = prompt_from_request(raw, self.model)
        # Deliberately unimplemented: a passing FAKE transport is not a solved task.
        source = "raise NotImplementedError('FAKE protocol rehearsal')"
        with Client(FakeProvider([{"content": source}]), tracer=self.tracer) as client:
            return client.chat([{"role": "user", "content": prompt}]).content


def generate(prompt: str, broker: object, deadline: float) -> str:
    replies = []

    def observed(raw: bytes, seconds: float) -> str:
        require(not replies and loads(raw) == {"prompt": prompt})
        reply = broker(raw, seconds)
        replies.append(reply)
        return reply

    with tempfile.TemporaryDirectory(prefix="p3-generate-") as directory:
        workspace = Path(directory).resolve()
        (workspace / "prompt.json").write_text(json.dumps(prompt))
        result = run(
            workspace,
            [
                "python",
                "-c",
                "import json,sandbox_model; sandbox_model.chat(json.load(open('prompt.json')))",
            ],
            observed,
            deadline=deadline,
        )
        require(result["exit_code"] == 0 and result["model_requests"] == 1 and len(replies) == 1)
    text = replies[0].strip()
    if text.startswith("```python\n") and text.endswith("```"):
        text = text[len("```python\n") : -3]
    require(len(text.encode()) <= 8192 and bool(text.strip()))
    return text


def evaluate(source: str, task: str, deadline: float | None = None) -> dict:
    """Only source and public inputs enter the container; expected values stay outside."""
    require(task in TASKS)
    suite = loads(read(PUBLIC / "tasks" / task / "cases.json"))
    command = """import copy, json, candidate
rows = json.load(open("inputs.json"))
outputs = []
for args in rows:
    before = copy.deepcopy(args)
    try:
        value = getattr(candidate, FUNCTION)(*args)
    except ValueError:
        value = {"raises": "ValueError"}
    outputs.append({"value": value, "unchanged": args == before})
print(json.dumps(outputs, allow_nan=False))
""".replace("FUNCTION", repr(suite["function"]))
    with tempfile.TemporaryDirectory(prefix="p3-check-") as directory:
        workspace = Path(directory).resolve()
        (workspace / "candidate.py").write_text(source)
        (workspace / "inputs.json").write_text(json.dumps([c["args"] for c in suite["cases"]]))
        result = run(workspace, ["python", "-c", command], deadline=deadline)
    if result["exit_code"] != 0:
        return {"passed": False, "reason": "candidate_error"}
    try:
        outputs = loads(result["stdout"])
        expected = [{"value": c["expected"], "unchanged": True} for c in suite["cases"]]
        return {"passed": outputs == expected, "reason": "public_comparison"}
    except ValueError:
        return {"passed": False, "reason": "invalid_output"}


def remaining(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise TimeoutError("P3 task deadline reached")
