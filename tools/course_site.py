"""Rebuild course/ from the course repository's own English student site.

    python3 tools/course_site.py --course ~/Documents/agentic-se-course

It checks out the course repository's origin/main in a temporary git worktree, installs its locked
environment there, and runs the course's own `tools/english_site.py`. That tool publishes only the
pages in the student distribution allowlist and scans its output for teacher-only content. The
result replaces course/, and course/SOURCE records the commit it was built from.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course", type=Path, required=True)
    parser.add_argument("--ref", default="origin/main",
                        help="course commit to read; anything but origin/main is for a local preview only")
    args = parser.parse_args()
    course = args.course.resolve()
    run("git", "-C", str(course), "fetch", "-q", "origin")
    commit = run("git", "-C", str(course), "rev-parse", args.ref).strip()
    with tempfile.TemporaryDirectory(prefix="course-site-") as temporary:
        tree = Path(temporary) / "course"
        run("git", "-C", str(course), "worktree", "add", "-q", "--detach", str(tree), commit)
        try:
            python = (tree / ".python-version").read_text().strip()
            run("uv", "sync", "--locked", "--python", python, "--all-extras", "--all-packages",
                "--no-build-isolation-package", "course-llm", cwd=tree)
            run("uv", "run", "--frozen", "python", "tools/english_site.py", cwd=tree)
            target = ROOT / "course"
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(tree / "site/site", target)
            (target / "SOURCE").write_text(f"boxi-cs/agentic-se-course {commit}\n")
        finally:
            run("git", "-C", str(course), "worktree", "remove", "--force", str(tree))
    print(f"course/ rebuilt from {commit[:7]}")


if __name__ == "__main__":
    main()
