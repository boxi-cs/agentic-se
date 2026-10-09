"""Week 3 class demo: one chained request, replayed against the draft and the revised tools.

Course-synthesised. The agent is a short course-written policy, not a model: it sees only
what a model would see (the request and each tool result) and follows the five rules in
`policy`, the same rules for both servers. The script steps that fixed policy through one
server at a time: the policy picks a call, label_tools.py returns its real result, and the
policy picks again. It has no model route; a run with the course's hosted model is
recorded by the teaching team and labelled as such.
"""

import argparse
import json
import re

from label_tools import DRAFT, LABELS, REVISED, call, draft_handlers, revised_handlers

TARGET = "red-team"
SERVERS = {"draft": (DRAFT, draft_handlers), "revised": (REVISED, revised_handlers)}
STEPS = 6  # Enough for the policy to finish on either server; it makes no model request.


def request(ticket_id: int) -> str:
    return f"Delete the label {TARGET}. An old ticket gives its label_id as {ticket_id}."


def policy(text: str, steps: list[dict]) -> dict:
    """Five course-written rules, the same for both servers. It never guesses an ID.

    1. First, call delete_label with the ID the request gives.
    2. After a preview of the requested label, commit it with dry_run false.
    3. After a delete that deleted something, stop and report what was deleted.
    4. After any other delete result (an error, a traceback or a preview of another
       label), look the label up by name with search_labels, once.
    5. After a search, delete the label_id found for that exact name; if the result
       carries no label_id, stop and say so.

    Returns the next call as {"name": ..., "arguments": ...}, or {"final": text}.
    """
    if not steps:
        return {
            "name": "delete_label",
            "arguments": {"label_id": int(re.findall(r"\d+", text)[-1])},
        }
    asked, result = steps[-1]["call"]["name"], steps[-1]["result"]
    if asked == "delete_label":
        preview, deleted = result.get("would_delete"), result.get("deleted")
        if isinstance(preview, dict) and preview["name"] == TARGET:
            return {
                "name": "delete_label",
                "arguments": {"label_id": preview["label_id"], "dry_run": False},
            }
        if deleted is not None:
            name = deleted["name"] if isinstance(deleted, dict) else deleted
            return {
                "final": f"Deleted {name}." if name == TARGET else f"Deleted {name}, not {TARGET}."
            }
        if all(step["call"]["name"] != "search_labels" for step in steps):
            return {"name": "search_labels", "arguments": {"query": TARGET}}
        return {"final": f"Stopped: {TARGET} was not deleted."}
    for label in result.get("labels", []):
        if isinstance(label, dict) and label.get("name") == TARGET and "label_id" in label:
            return {"name": "delete_label", "arguments": {"label_id": label["label_id"]}}
    return {
        "final": f"Stopped: the search gave no label_id for {TARGET}, and I will not guess one."
    }


def replay(server: str, ticket_id: int, emit=None) -> dict:
    """Step the fixed policy through one server, reporting each call and result."""
    emit = emit or (lambda line: None)
    tools, make_handlers = SERVERS[server]
    store = dict(LABELS)
    handlers = make_handlers(store)
    text = request(ticket_id)
    record = {"server": server, "request": text, "steps": [], "stop_reason": "step_limit"}
    emit(f"# {server} server")
    emit(f"request    {text}")
    for number in range(1, STEPS + 1):
        choice = policy(text, record["steps"])
        if "final" in choice:
            record.update(stop_reason="final", final=choice["final"])
            emit(f"final      {choice['final']}")
            break
        result = call(tools, handlers, choice["name"], choice["arguments"])
        record["steps"].append({"call": choice, "result": result})
        emit(f"call p{number:<4} {choice['name']} {json.dumps(choice['arguments'])}")
        emit(f"result     {json.dumps(result)}")
    emit(f"stop       {record['stop_reason']}; labels left: {sorted(store.values())}")
    record["labels_left"] = store
    return record


def observe(record: dict) -> dict:
    """The three things to watch, read from the steps and the final labels.

    `recovered_from_the_wrong_id` is true when the first delete_label call hit a missing
    label or a different one (an error, a traceback, or a preview or deletion of another
    label) and the run still ended with exactly the requested label deleted.
    """
    seen_ids, carried, previewed = set(), False, set()
    for step in record["steps"]:
        made, result = step["call"], step["result"]
        if made["name"] == "delete_label":
            # A model can send a label_id that is not an integer; it carries nothing.
            label_id = made["arguments"].get("label_id")
            carried = carried or (isinstance(label_id, int) and label_id in seen_ids)
            if isinstance(result.get("would_delete"), dict):
                previewed.add(result["would_delete"]["label_id"])
        for label in result.get("labels", []):
            if isinstance(label, dict) and "label_id" in label:
                seen_ids.add(label["label_id"])
    first = next((s for s in record["steps"] if s["call"]["name"] == "delete_label"), None)
    touched = (
        first["result"].get("would_delete") or first["result"].get("deleted") if first else None
    )
    touched_name = touched.get("name") if isinstance(touched, dict) else touched
    wrong_id = first is not None and touched_name != TARGET
    target_id = next(key for key, name in LABELS.items() if name == TARGET)
    deleted = sorted(set(LABELS) - set(record["labels_left"]))
    return {
        "carried_an_id_from_a_result": carried,
        "recovered_from_the_wrong_id": wrong_id and deleted == [target_id],
        "previewed_before_deleting": bool(deleted) and set(deleted) <= previewed,
        "deleted": [LABELS[key] for key in deleted],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ticket-id", type=int, default=21)
    parser.add_argument("--summary", action="store_true", help="also print the three observations")
    args = parser.parse_args()
    print("agent: course-written policy, not a model", flush=True)
    for server in SERVERS:
        record = replay(server, args.ticket_id, lambda line: print(line, flush=True))
        if args.summary:
            print(json.dumps(observe(record)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
