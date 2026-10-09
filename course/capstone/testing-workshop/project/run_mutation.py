"""Run the deterministic, standard-library mutation engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import tempfile
from pathlib import Path

# python -I omits the script directory from sys.path; add only this public
# project directory so the runner remains usable in the launcher.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_runner import run_tests

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "domains" / "validation.py"
CONFIG = ROOT / "mutants.json"
MANIFEST = ROOT / "mutant_manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mutants() -> list[dict[str, str]]:
    """Load and validate the fixed mutation configuration."""
    values = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(values, list) or not values:
        raise ValueError("mutation configuration must be a non-empty list")
    for value in values:
        if not isinstance(value, dict) or set(value) != {"name", "needle", "replacement"}:
            raise ValueError("invalid mutation entry")
    if len({value["name"] for value in values}) != len(values):
        raise ValueError("mutation names must be unique")
    return values


def load_manifest() -> dict[str, dict[str, str]]:
    """Load the public equivalent/control manifest beside the config."""
    values = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(values, list):
        raise ValueError("mutation manifest must be a list")
    result: dict[str, dict[str, str]] = {}
    for value in values:
        if not isinstance(value, dict) or set(value) != {"name", "kind", "reason"}:
            raise ValueError("invalid mutation manifest entry")
        if value["kind"] not in {"behavioral", "equivalent", "control"}:
            raise ValueError("invalid mutation kind")
        result[str(value["name"])] = {
            "kind": str(value["kind"]),
            "reason": str(value["reason"]),
        }
    if set(result) != {value["name"] for value in load_mutants()}:
        raise ValueError("mutation manifest does not match configuration")
    return result


def apply_mutant(source: str, mutant: dict[str, str]) -> str:
    """Apply exactly one configured source mutation, failing closed on drift."""
    needle = mutant["needle"]
    if source.count(needle) != 1:
        raise ValueError(f"mutation target is not unique: {mutant['name']}")
    return source.replace(needle, mutant["replacement"], 1)


def _copy_work(
    test_bytes: bytes, source_bytes: bytes, mutated: bytes | None = None
) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    directory = tempfile.TemporaryDirectory(prefix="course-mutant-")
    work = Path(directory.name)
    domains = work / "domains"
    domains.mkdir()
    target = domains / "validation.py"
    target.write_bytes(mutated if mutated is not None else source_bytes)
    target.chmod(0o644)
    (domains / "__init__.py").write_text("", encoding="utf-8")
    tests = work / "tests"
    tests.mkdir()
    test_path = tests / "test_submission.py"
    test_path.write_bytes(test_bytes)
    test_path.chmod(0o644)
    return directory, work


def _outcome(test_bytes: bytes, source_bytes: bytes, mutated: bytes | None = None) -> str:
    directory, work = _copy_work(test_bytes, source_bytes, mutated)
    try:
        target = work / "domains" / "validation.py"
        before = _sha256(target)
        status = run_tests(work)
        if _sha256(target) != before:
            return "source_modified"
        return status
    finally:
        directory.cleanup()


def run(test_file: Path | None, seed: int) -> dict[str, object]:
    """Run all fixed mutants in seeded order and return deterministic evidence."""
    mutants = load_mutants()
    manifest = load_manifest()
    if test_file is None:
        return {"tool": "course-mutator", "seed": seed, "status": "error", "mutants": []}
    if not test_file.is_file() or test_file.suffix != ".py":
        raise ValueError("tests must name a Python file")
    # Read the submitted suite once; all child copies use these immutable bytes.
    test_bytes = test_file.read_bytes()
    source_bytes = SOURCE.read_bytes()
    source = source_bytes.decode("utf-8")
    fixed_hashes = {
        "source": _sha256(SOURCE),
        "config": _sha256(CONFIG),
        "manifest": _sha256(MANIFEST),
        "tests": hashlib.sha256(test_bytes).hexdigest(),
    }
    ordered = list(mutants)
    random.Random(seed).shuffle(ordered)
    baseline = _outcome(test_bytes, source_bytes)
    rows: list[dict[str, str]] = []
    for mutant in ordered:
        status = _outcome(test_bytes, source_bytes, apply_mutant(source, mutant).encode())
        rows.append(
            {
                "mutant": mutant["name"],
                "kind": manifest[mutant["name"]]["kind"],
                "reason": manifest[mutant["name"]]["reason"],
                "status": "killed"
                if status == "failed"
                else "survived"
                if status == "passed"
                else status,
            }
        )
    # A stateful suite must not alter the final baseline.
    after_baseline = _outcome(test_bytes, source_bytes)
    infrastructure = []
    if baseline != "passed":
        infrastructure.append(f"baseline:{baseline}")
    if after_baseline != "passed":
        infrastructure.append(f"baseline_after:{after_baseline}")
    infrastructure.extend(
        f"{row['mutant']}:{row['status']}"
        for row in rows
        if row["status"]
        in {"timeout", "missing_dependency", "suspicious", "no_tests", "source_modified", "crash"}
    )
    behavioural = [row for row in rows if row["kind"] == "behavioral"]
    killed = sum(row["status"] == "killed" for row in behavioural)
    return {
        "tool": "course-mutator",
        "seed": seed,
        "status": "error" if infrastructure else "ok",
        "selected": len(behavioural),
        "killed": killed,
        "survived": sum(row["status"] == "survived" for row in behavioural),
        "infrastructure_failures": sorted(infrastructure),
        "mutants": sorted(rows, key=lambda row: row["mutant"]),
        "fixed_hashes": fixed_hashes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", type=Path, help="submitted test file inside this project")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-children", type=int, default=1, help=argparse.SUPPRESS)
    args = parser.parse_args()
    test_file = args.tests.resolve() if args.tests else None
    if test_file and not test_file.is_relative_to(ROOT):
        parser.error("--tests must be inside the project workspace")
    report = run(test_file, args.seed)
    print(json.dumps(report, sort_keys=True))
    return 2 if report["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
