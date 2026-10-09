"""Week 3 worked example: a generated tool draft and its revision, checked by calls.

In-memory and course-authored: no server, files, network or real records. It applies
the parts of the published input schema these tools use (extra and required arguments,
each argument's type, then its range) the way a validating server, such as the
workshop's scaffold, would, then makes the same four calls against both versions so the
difference is observed, not argued. To make a call of your own, add a row to `verify()`.
"""

import json

LABELS = {7: "red-blue", 9: "release-2", 12: "red-team"}

# A course-authored first draft of the kind generated for "a search and a delete tool".
DRAFT = [
    {
        "name": "search_labels",
        "description": "Search labels. limit can be up to 50.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
        },
    },
    {
        "name": "delete_label",
        "description": "Deletes a label.",
        "inputSchema": {"type": "object", "properties": {"label_id": {"type": "integer"}}},
    },
]

REVISED = [
    {
        "name": "search_labels",
        "description": "Find labels whose name contains the query. Returns label_id and name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text the name must contain."},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                    "description": "Maximum number of labels to return.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "delete_label",
        "description": "Delete one label permanently. With dry_run true (the default) "
        "nothing changes and the result shows what would be deleted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label_id": {"type": "integer", "description": "A label_id from search_labels."},
                "dry_run": {"type": "boolean", "default": True, "description": "Preview only."},
            },
            "required": ["label_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
]


def draft_handlers(store: dict) -> dict:
    def search(arguments: dict) -> dict:
        return {"labels": [name for name in store.values() if arguments["query"] in name]}

    def delete(arguments: dict) -> dict:
        return {"deleted": store.pop(arguments["label_id"])}

    return {"search_labels": search, "delete_label": delete}


def revised_handlers(store: dict) -> dict:
    def search(arguments: dict) -> dict:
        found = [
            {"label_id": key, "name": name}
            for key, name in sorted(store.items())
            if arguments["query"] in name
        ]
        shown = found[: arguments["limit"]]
        return {"labels": shown, "total": len(found), "truncated": len(found) > len(shown)}

    def delete(arguments: dict) -> dict:
        key = arguments["label_id"]
        if key not in store:
            message = "No such label; use search_labels for label_id values."
            return {"error": {"code": "not_found", "retryable": False, "message": message}}
        if arguments["dry_run"]:
            return {"dry_run": True, "would_delete": {"label_id": key, "name": store[key]}}
        return {"dry_run": False, "deleted": {"label_id": key, "name": store.pop(key)}}

    return {"search_labels": search, "delete_label": delete}


# The JSON Schema types these tools use. A JSON true/false is not an integer, although
# Python's bool is a subclass of int, so the integer check excludes it explicitly.
TYPES = {
    "integer": ("an integer", lambda value: isinstance(value, int) and not isinstance(value, bool)),
    "boolean": ("true or false", lambda value: isinstance(value, bool)),
    "string": ("a string", lambda value: isinstance(value, str)),
}


def schema_problem(schema: dict, arguments: object) -> str | None:
    """Return the first way the arguments break the schema, or None if they fit."""
    if not isinstance(arguments, dict):
        return "arguments must be an object"
    rules = schema.get("properties", {})
    if schema.get("additionalProperties") is False and set(arguments) - set(rules):
        return "unknown argument"
    for key in schema.get("required", []):
        if key not in arguments:
            return f"missing {key}"
    for key, value in arguments.items():
        rule = rules.get(key, {})
        if "type" in rule:
            wanted, matches = TYPES[rule["type"]]
            if not matches(value):
                return f"{key} must be {wanted}"
        if ("minimum" in rule and value < rule["minimum"]) or (
            "maximum" in rule and value > rule["maximum"]
        ):
            return f"{key} out of range"
    return None


def call(tools: list, handlers: dict, name: str, arguments: object) -> dict:
    """Apply the published schema as a validating server would, then call the handler.

    The server checks extra and required arguments, then each argument's type before its
    range, and refuses a mismatch with a structured error before the handler runs. It
    fills defaults, and turns an exception raised inside a handler into data so the
    draft's failure is visible in the output instead of stopping the example.
    """
    schema = next(tool["inputSchema"] for tool in tools if tool["name"] == name)
    problem = schema_problem(schema, arguments)
    if problem:
        return {"error": {"code": "invalid_argument", "retryable": False, "message": problem}}
    rules = schema.get("properties", {})
    arguments = {**{k: r["default"] for k, r in rules.items() if "default" in r}, **arguments}
    try:
        return handlers[name](arguments)
    except Exception as error:
        return {"traceback": f"{type(error).__name__}: {error}"}


def verify(tools: list, make_handlers: object) -> list[dict]:
    """Four calls, one per question; each starts from fresh records.

    Each row is (question, tool name, arguments, label ID to look for afterwards or None).
    Add a row of your own after the four below; keep these four unchanged.
    """
    rows = []
    for question, name, arguments, after in (
        ("Shaped, chainable search?", "search_labels", {"query": "red"}, None),
        ("Omitting dry_run only previews?", "delete_label", {"label_id": 7}, 7),
        ("Unknown ID is a structured error?", "delete_label", {"label_id": 99}, None),
        ("Out-of-schema limit rejected?", "search_labels", {"query": "r", "limit": 50}, None),
    ):
        store = dict(LABELS)
        result = call(tools, make_handlers(store), name, arguments)
        row = {"question": question, "call": f"{name} {json.dumps(arguments)}", "result": result}
        if after is not None:
            row["label_still_present"] = after in store
        rows.append(row)
    return rows


def main() -> int:
    for title, tools, handlers in (
        ("draft", DRAFT, draft_handlers),
        ("revised", REVISED, revised_handlers),
    ):
        print(f"# {title}")
        for row in verify(tools, handlers):
            print(json.dumps(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
