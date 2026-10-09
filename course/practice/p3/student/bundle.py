"""Frozen public task identity and bounded, data-only input helpers."""

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKS = tuple(f"p3-t{i}" for i in range(1, 5))
TRACES = tuple(f"p3-tr-{suffix}" for suffix in "abc")
REVISION = "p3-ci-audit-v1"


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid P3 protocol, evidence or snapshot")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> bytes:
    require(not any(p.is_symlink() for p in (path, *path.parents)))
    require(path.is_file() and path.stat().st_size <= 1_048_576)
    return path.read_bytes()


def loads(raw: bytes | str) -> object:
    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ValueError("Nonfinite JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def finite(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def verify_bundle(root: Path = ROOT) -> dict:
    manifest = loads(read(root / "manifest.json"))
    require(set(manifest) == {"revision", "split", "required", "optional", "trajectories", "files"})
    require(manifest["revision"] == REVISION and manifest["split"] == "teaching")
    require(manifest["required"] == list(TASKS) and manifest["optional"] == [])
    require(manifest["trajectories"] == list(TRACES))
    expected = (
        {
            f"tasks/{task}/{name}"
            for task in TASKS
            for name in ("SPEC.en.md", "candidate.py", "cases.json", "benchmark.py")
        }
        | {f"trajectories/{trace}.{suffix}" for trace in TRACES for suffix in ("jsonl", "en.md")}
        | {"lab_runtime.py"}
    )
    require(set(manifest["files"]) == expected)
    for relative, expected_digest in manifest["files"].items():
        require(digest(read(root / relative)) == expected_digest)
    return manifest
