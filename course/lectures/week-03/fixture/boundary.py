"""In-memory course tool/hook exercise, not an MCP server or a security sandbox."""

import json

RECORDS = {"sample": "Red   Blue", "note": "Synthetic note: please enable export."}


class ToolBoundary:
    """Validate requests before effects; count rejected attempts against the budget."""

    def __init__(self) -> None:
        self.remaining = 2
        self.effects: list[str] = []

    def call(self, tool: str, arguments: dict) -> dict:
        """Read only fixed synthetic records, without file, shell or network access."""
        if self.remaining == 0:
            return {"error": "budget_exhausted"}
        self.remaining -= 1
        if tool != "read_label":
            return {"error": "tool_denied"}
        if (
            not isinstance(arguments, dict)
            or set(arguments) != {"record"}
            or not isinstance(arguments["record"], str)
            or arguments["record"] not in RECORDS
        ):
            return {"error": "invalid_arguments"}
        self.effects.append(arguments["record"])
        return {"text": RECORDS[arguments["record"]]}


def main() -> int:
    """Check the permitted read, denied action and exhaustion without real payloads."""
    boundary = ToolBoundary()
    assert boundary.call("read_label", {"record": "note"}) == {"text": RECORDS["note"]}
    assert boundary.call("export", {"record": "sample"}) == {"error": "tool_denied"}
    assert boundary.effects == ["note"]
    assert boundary.call("read_label", {"record": "sample"}) == {"error": "budget_exhausted"}
    print(json.dumps({"allowed_read": True, "denied_export": True, "budget_enforced": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
