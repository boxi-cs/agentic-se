"""Run the deterministic standard-library property suite."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_runner import run_tests

ROOT = Path(__file__).resolve().parent


def main() -> int:
    """Run only the property suite in an isolated standard-library child."""
    # test_runner expects this conventional path in its copied work directory.
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory(prefix="course-property-") as directory:
        work = Path(directory)
        (work / "domains").mkdir()
        (work / "tests").mkdir()
        shutil.copy2(ROOT / "domains" / "validation.py", work / "domains" / "validation.py")
        (work / "domains" / "__init__.py").write_text("", encoding="utf-8")
        shutil.copy2(ROOT / "tests" / "test_validation.py", work / "tests" / "test_submission.py")
        return 0 if run_tests(work) == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
