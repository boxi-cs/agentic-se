"""The demo's small model client: one prompt out, one reply in, and explicit work products."""

import base64
import json
import sys
from pathlib import Path


def chat(prompt: str) -> str:
    """Request text as data: print one request line and read one JSON reply from stdin."""
    print("COURSE_MODEL_REQUEST " + json.dumps({"prompt": prompt}), flush=True)
    response = json.loads(sys.stdin.readline())
    if set(response) != {"content"} or not isinstance(response["content"], str):
        raise RuntimeError("Model broker refused the request")
    return response["content"]


def emit_artifact(path: str) -> None:
    """Print a small explicit work product as one line: its name and its encoded bytes."""
    print(
        "COURSE_ARTIFACT "
        + json.dumps(
            {"path": path, "data": base64.b64encode(Path(path).read_bytes()).decode("ascii")}
        ),
        flush=True,
    )
