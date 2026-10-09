"""Small standard-library test runner used inside mutation sandboxes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# The target suite is data-only; one second per fresh child keeps the complete
# twelve-mutant run below the launcher budget while still catching hangs.
TIMEOUT_SECONDS = 1.0

_CHILD = r"""
import importlib.util
import json
import os
import pathlib
import sys
import unittest

path = pathlib.Path(sys.argv[1]).resolve()
work = path.parent.parent.resolve()
target_root = (work / "domains").resolve()

def deny_target_writes(event, args):
    candidate = None
    if event in {"open", "os.open"} and args:
        candidate = args[0]
        mode = args[1] if len(args) > 1 else "r"
        if mode is None:
            mode = args[2] if len(args) > 2 else 0
        if isinstance(mode, int):
            writable = mode & (
                os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC | os.O_EXCL
            )
        else:
            writable = any(flag in mode for flag in ("w", "a", "+", "x"))
        if not writable:
            return
    elif event in {"os.rename", "os.replace", "os.remove", "os.unlink"} and args:
        candidate = args[0]
    if candidate is not None:
        try:
            inside_target = pathlib.Path(candidate).resolve().is_relative_to(target_root)
        except (OSError, RuntimeError):
            return
        if inside_target:
            raise PermissionError("mutation target is read-only during tests")

sys.addaudithook(deny_target_writes)
sys.path.insert(0, str(work))
spec = importlib.util.spec_from_file_location("student_tests", path)
if spec is None or spec.loader is None:
    print(json.dumps({"status": "missing_dependency", "detail": "test module"}))
    raise SystemExit(3)
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
except ModuleNotFoundError as exc:
    print(json.dumps({"status": "missing_dependency", "detail": str(exc)}))
    raise SystemExit(3)
except BaseException as exc:
    print(json.dumps({"status": "crash", "detail": f"import: {exc}"}))
    raise SystemExit(1)

suite = unittest.TestSuite()
suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
for name in dir(module):
    candidate = getattr(module, name)
    if name.startswith("test_") and callable(candidate):
        suite.addTest(unittest.FunctionTestCase(candidate))
count = suite.countTestCases()
if count == 0:
    print(json.dumps({"status": "no_tests", "tests": 0}))
    raise SystemExit(2)
result = unittest.TestResult()
suite.run(result)
if result.skipped:
    status = "suspicious"
elif result.errors or result.failures:
    status = "failed"
else:
    status = "passed"
print(json.dumps({
    "status": status,
    "tests": count,
    "passed": count - len(result.errors) - len(result.failures) - len(result.skipped),
    "failed": len(result.errors) + len(result.failures),
    "skipped": len(result.skipped),
}))
raise SystemExit(0 if status == "passed" else 1)
"""


def run_tests(work: Path) -> str:
    """Run the copied submission and return a stable outcome label."""
    env = {"PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C"}
    try:
        result = subprocess.run(
            [
                sys.executable or "python3",
                "-I",
                "-B",
                "-S",
                "-c",
                _CHILD,
                "tests/test_submission.py",
            ],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return "crash"
    try:
        report = json.loads(lines[-1])
    except json.JSONDecodeError:
        return "crash"
    return str(report.get("status", "failed"))
