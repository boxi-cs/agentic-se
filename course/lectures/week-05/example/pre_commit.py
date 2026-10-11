"""Example pre-commit hook: check the files that a commit would add or change.

It takes one JSON event argument, as the Week 3 hook does, and exits 0 to let the
commit continue or 2 to stop it. It runs two checks. First, a commit may not change a
file that the Boundaries section of AGENTS.md protects. Second, lint: an import whose
name a Python file never uses. It reads and parses the named Python files; it never
imports or runs them. A hook is a check at an event.
"""

import ast
import json
import sys
from pathlib import Path

MAX_FILES = 50
MAX_BYTES = 262_144

# Files a feature change must not touch. Keep this set the same as the Boundaries
# section of AGENTS.md; a protected file is changed only in its own reviewed change.
PROTECTED = frozenset({"launch.py", "Dockerfile", "pyproject.toml", "uv.lock"})

# The checks this hook runs, in order: protected files, then lint.


def workspace_file(value: object) -> Path | None:
    """Accept only an ordinary .py file named relative to, and inside, the workspace."""
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    root = Path.cwd().resolve()
    if (
        path.is_absolute()
        or ".." in path.parts
        or any(part.startswith(".") for part in path.parts)
        or path.suffix != ".py"
        or not path.resolve().is_relative_to(root)
        or path.is_symlink()
        or not path.is_file()
    ):
        return None
    return path


def repository_path(value: object) -> bool:
    """Accept a non-empty relative path, as `git diff --name-only` prints it."""
    if not isinstance(value, str) or not value.strip():
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() != "."


def protected(value: str) -> bool:
    """True when `value` names a protected file, however the path is spelled."""
    return Path(value).as_posix() in PROTECTED


def annotation_names(tree: ast.AST) -> set[str]:
    """Names used only inside string annotations such as `x: "Path"`."""
    names: set[str] = set()
    annotations: list[ast.expr | None] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
    for annotation in annotations:
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                parsed = ast.parse(annotation.value, mode="eval")
            except SyntaxError:
                continue
            names |= {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}
    return names


def exported_names(tree: ast.Module) -> set[str]:
    """Strings listed in a module-level `__all__`, which count as uses."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                names |= {
                    item.value
                    for item in node.value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
    return names


def unused_imports(source: str, name: str) -> list[str]:
    """Return one `path:line: unused import 'x'` finding for each name never used.

    This is a single, coarse rule: a name counts as used if it appears anywhere in the
    file. A full linter is stricter; the rule is enough to stop an unused import.
    """
    tree = ast.parse(source, filename=name)
    imported: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.setdefault(alias.asname or alias.name.split(".")[0], node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            for alias in node.names:
                if alias.name != "*":
                    imported.setdefault(alias.asname or alias.name, node.lineno)
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used |= annotation_names(tree) | exported_names(tree)
    return [
        f"{name}:{line}: unused import '{bound}'"
        for bound, line in sorted(imported.items(), key=lambda item: (item[1], item[0]))
        if bound not in used
    ]


def run(argv: list[str]) -> int:
    """Check one `before_commit` event; print each finding and the decision."""
    try:
        event = json.loads(argv[0]) if len(argv) == 1 else None
    except ValueError:
        event = None
    if (
        not isinstance(event, dict)
        or set(event) != {"event", "paths"}
        or event["event"] != "before_commit"
        or not isinstance(event["paths"], list)
        or not 0 < len(event["paths"]) <= MAX_FILES
    ):
        print('REFUSED: expected {"event": "before_commit", "paths": ["path", ...]}')
        return 2
    findings: list[str] = []
    for value in event["paths"]:
        if not repository_path(value):
            print(f"REFUSED: {value!r} is not a relative path inside the repository")
            return 2
        if protected(value):
            findings.append(
                f"{value}: protected by AGENTS.md; change it in its own reviewed change"
            )
            continue
        if Path(value).suffix != ".py":
            continue  # Lint reads Python only; other files are checked for protection alone.
        path = workspace_file(value)
        if path is None:
            print(f"REFUSED: {value!r} is not an ordinary .py file inside this workspace")
            return 2
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            print(f"REFUSED: {value} is larger than {MAX_BYTES} bytes")
            return 2
        try:
            findings += unused_imports(data.decode("utf-8"), value)
        except (UnicodeDecodeError, SyntaxError, RecursionError, MemoryError, ValueError):
            findings.append(f"{value}: cannot be parsed as Python source")
    for finding in findings:
        print(finding)
    if findings:
        print("STOP: fix the findings above, then run the hook again")
        return 2
    print(f"PASS: no protected file and no unused import in {len(event['paths'])} file(s)")
    return 0


def main() -> int:
    """Exit 0 to let the commit continue or 2 to stop it."""
    try:
        return run(sys.argv[1:])
    except OSError:
        print("REFUSED: a named file could not be read")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
