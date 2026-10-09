"""Score submitted tests for formative mutation feedback."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_mutation import (
    CONFIG,
    MANIFEST,
    ROOT,
    SOURCE,
    _outcome,
    apply_mutant,
    load_manifest,
    load_mutants,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-children", type=int, default=1, help=argparse.SUPPRESS)
    args = parser.parse_args()
    test_path = args.tests.resolve()
    if not test_path.is_file() or test_path.suffix != ".py" or not test_path.is_relative_to(ROOT):
        parser.error("--tests must be a Python file inside the project workspace")

    # Freeze every grading input and read the submitted suite exactly once.
    test_bytes = test_path.read_bytes()
    source_bytes = SOURCE.read_bytes()
    source = source_bytes.decode("utf-8")
    mutants = load_mutants()
    manifest = load_manifest()
    fixed_hashes = {
        "source": _sha256(SOURCE),
        "mutants": _sha256(CONFIG),
        "manifest": _sha256(MANIFEST),
        "tests": hashlib.sha256(test_bytes).hexdigest(),
    }
    infrastructure: list[str] = []
    ordered = list(mutants)
    random.Random(args.seed).shuffle(ordered)
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
    after_baseline = _outcome(test_bytes, source_bytes)
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
    if fixed_hashes != {
        "source": _sha256(SOURCE),
        "mutants": _sha256(CONFIG),
        "manifest": _sha256(MANIFEST),
        "tests": hashlib.sha256(test_bytes).hexdigest(),
    }:
        infrastructure.append("grading_input_modified")

    identity_probe = baseline == "passed" and any(
        row["kind"] in {"equivalent", "control"} and row["status"] == "killed" for row in rows
    )
    if identity_probe:
        infrastructure.append("identity_probe")
    behavioural = [row for row in rows if row["kind"] == "behavioral"]
    killed = sum(row["status"] == "killed" for row in behavioural)
    invalid = bool(infrastructure)
    report = {
        "tool": "course-mutator",
        "use": "feedback",
        "seed": args.seed,
        "status": "error" if invalid else "ok",
        "selected": len(behavioural),
        "killed": killed,
        "survived": sum(row["status"] == "survived" for row in behavioural),
        "equivalent": sorted(row["mutant"] for row in rows if row["kind"] == "equivalent"),
        "equivalent_reasons": {
            row["mutant"]: row["reason"] for row in rows if row["kind"] == "equivalent"
        },
        "controls": sorted(row["mutant"] for row in rows if row["kind"] == "control"),
        "feedback_score": None if invalid else (killed / len(behavioural) if behavioural else 0.0),
        "identity_probe": identity_probe,
        "suspicious": ["identity_probe"] if identity_probe else [],
        "infrastructure_failure": bool(infrastructure),
        "infrastructure_failures": sorted(infrastructure),
        "mutants": sorted(rows, key=lambda row: row["mutant"]),
        "fixed_hashes": fixed_hashes,
    }
    print(json.dumps(report, sort_keys=True))
    return 2 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
