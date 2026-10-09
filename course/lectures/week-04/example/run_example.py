"""Generate or verify a candidate through the course sandbox.

All data is course-authored synthetic data. ``model`` exports its candidate and
leaves acceptance verification to the next launcher invocation so a person can
inspect the code between stages.
"""

import argparse
from pathlib import Path

from acceptance import Run, verify


def broken(runs: list[Run]) -> list[int]:
    """An intentionally wrong interpretation of 'needs attention'."""
    return sorted({run_id for run_id, status in runs if status != "passed"})


def repaired(runs: list[Run]) -> list[int]:
    """The public worked example implements only the agreed failure filter."""
    return sorted({run_id for run_id, status in runs if status == "failed"})


def main() -> int:
    """Generate a candidate or select the worked example."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("broken", "repaired", "model"))
    args = parser.parse_args()
    if args.mode != "model":
        verify(broken if args.mode == "broken" else repaired)
        return 0

    from sandbox_model import chat, emit_artifact

    response = chat(
        "Return only Python defining failed_ids(runs) in candidate.py. runs is a list "
        "of (integer id, status) pairs; statuses are passed, failed, running. Return "
        "ascending unique ids whose status equals failed. Return [] if none. Do not "
        "modify runs. Write only the function: no imports, Markdown, examples or "
        "explanation. Do not change acceptance.py; it is read-only."
    )
    # Strip only a Python code fence; malformed or truncated code must fail Test.
    code = response.strip()
    if code.startswith("```python\n") and code.endswith("```"):
        code = code[len("```python\n") : -3].strip()
    Path("candidate.py").write_text(code + "\n", encoding="utf-8")
    emit_artifact("candidate.py")
    # Stop after Implement so a person can read the candidate as text before Test.
    # Verification is a separate launcher invocation documented in the notes.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
