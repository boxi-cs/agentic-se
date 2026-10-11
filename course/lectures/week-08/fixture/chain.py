# INERT PAYLOAD — course material
"""Scripted injection chain: untrusted text -> proposal -> boundary -> effect.

The "agent" here is one fixed rule, not a model. It stands in for a model that follows
imperative text: after the authorized read returns a record that asks for export, it
proposes `export`. Every step stays in memory. No file, subprocess, socket or credential
is used, and there is no export handler to reach.
"""

from __future__ import annotations

import json

from candidate import RECORDS, Boundary

AUTHORIZED_TOOL = "read_label"


def scripted_follow_up(text: str) -> str | None:
    """Return the tool a text-obedient agent would propose after reading `text`."""
    return "export" if "enable export" in text.lower() else None


def run_surface(surface: str) -> dict[str, object]:
    """Do the authorized read, let the returned text steer one proposal, record effects."""
    boundary = Boundary()
    proposed = [AUTHORIZED_TOOL]
    response = boundary.call({"tool": AUTHORIZED_TOOL, "record": surface})
    task_completed = response == {"text": RECORDS[surface]}
    responses = ["text" if task_completed else response.get("error", "unexpected")]
    follow_up = scripted_follow_up(response.get("text", ""))
    if follow_up is not None:
        proposed.append(follow_up)
        response = boundary.call({"tool": follow_up, "record": surface})
        responses.append(response.get("error", "text"))
    return {
        "surface": surface,
        "proposed": proposed,
        "responses": responses,
        "effects": boundary.effects,
        "task_completed": task_completed,
    }


def main() -> int:
    """Print one line per surface and a summary; exit 0 only if the chain is broken."""
    runs = [run_surface(surface) for surface in RECORDS]
    unauthorized = 0
    for run in runs:
        effects = run["effects"]
        assert isinstance(effects, list)
        unauthorized += sum(effect != AUTHORIZED_TOOL for effect in effects)
        print(
            json.dumps({key: run[key] for key in ("surface", "proposed", "responses", "effects")})
        )
    task_completed = all(run["task_completed"] for run in runs)
    print(
        json.dumps(
            {
                "kind": "synthetic_injection_chain",
                "task_completed": task_completed,
                "unauthorized_effects": unauthorized,
            }
        )
    )
    return 0 if task_completed and unauthorized == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
