"""Small student-side launcher admission check for the P3 bundle."""

from __future__ import annotations

import os
from pathlib import Path


class SafetyError(RuntimeError):
    """The command is outside the reviewed course launcher boundary."""


def require_launcher() -> Path:
    """Require the T-104 container markers before model or candidate execution."""
    try:
        workspace = Path("/workspace")
        status = Path("/proc/self/status").read_text(encoding="utf-8")
        mounts = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
        mount = next(line.split() for line in mounts if line.split()[1] == "/workspace")
        if (
            os.getuid() == 0
            or Path.cwd().resolve() != workspace
            or mount[2] != "tmpfs"
            or "NoNewPrivs:\t1" not in status
            or "CapEff:\t0000000000000000" not in status
            or not Path("/bootstrap.py").is_file()
        ):
            raise ValueError
        return workspace
    except (OSError, StopIteration, ValueError):
        raise SafetyError("Use the reviewed scripts/course-sandbox launcher") from None
