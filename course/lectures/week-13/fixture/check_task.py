"""Week 13 public fixture: try the neutral task on one page the way a keyboard user would.

Course-authored practice with no model call, network access or file writes. The check reads
an HTML page as text and never runs it. Its simulated user follows one narrow, stated
strategy:

1. Press Tab from the top of the page. Content inside a closed disclosure is not reached.
2. Open a disclosure, or choose a select option, only when its text shares a word with the
   task. Links are not followed.
3. Activate the first reachable submit button. The form then sends its named fields, as a
   browser would, and the unchanged dashboard query answers. When a field is sent more than
   once, the dashboard reads its first value; the output lists such fields.

The task is completed when the first row shown is the most recent failed build in pipeline
Alpha and every control reached has an accessible name. A completed run shows that this
strategy works on this page. It does not show that people understand the page; that still
needs an observed session on the same revision.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path

_DASHBOARD_PATH = Path(__file__).resolve().with_name("dashboard.py")
_DASHBOARD_SPEC = importlib.util.spec_from_file_location("week13_dashboard", _DASHBOARD_PATH)
if _DASHBOARD_SPEC is None or _DASHBOARD_SPEC.loader is None:  # pragma: no cover
    raise ImportError(f"cannot load {_DASHBOARD_PATH}")
dashboard = importlib.util.module_from_spec(_DASHBOARD_SPEC)
_WRITE_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True  # keep the promise of no file writes, cache included
try:
    _DASHBOARD_SPEC.loader.exec_module(dashboard)
finally:
    sys.dont_write_bytecode = _WRITE_BYTECODE

TASK = "Find the most recent failed build in pipeline Alpha."
STOPWORDS = {"find", "the", "most", "recent", "in"}
TASK_WORDS = frozenset(re.findall(r"[a-z]+", TASK.lower())) - STOPWORDS
# The answer comes from the data, not from any page.
EXPECTED = max(b.number for b in dashboard.BUILDS if (b.pipeline, b.status) == ("alpha", "failed"))
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}


class Node:
    """One element of the parsed page; children are nodes or text."""

    def __init__(self, tag: str, attrs: list[tuple[str, str | None]], parent: Node | None):
        self.tag = tag
        self.attrs = {name: value or "" for name, value in attrs}
        self.parent = parent
        self.children: list[Node | str] = []

    def walk(self) -> Iterator[Node]:
        """Yield this node and every element below it, in document order."""
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def ancestors(self) -> Iterator[Node]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def text(self, skip: Node | None = None) -> str:
        """Return the visible text below this node, leaving out one subtree if asked."""
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child is not skip:
                parts.append(child.text(skip))
        return " ".join(" ".join(parts).split())


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document", [], None)
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.current.children.append(Node(tag, attrs, self.current))

    def handle_endtag(self, tag: str) -> None:
        for node in (self.current, *self.current.ancestors()):
            if node.tag == tag and node.parent is not None:
                self.current = node.parent
                return

    def handle_data(self, data: str) -> None:
        self.current.children.append(data)


def parse(html: str) -> Node:
    """Parse a page whose elements are explicitly closed."""
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root


def _summary(details: Node) -> Node | None:
    return next((c for c in details.children if isinstance(c, Node) and c.tag == "summary"), None)


def closed_disclosure(node: Node, opened: set[int]) -> Node | None:
    """Return the closed disclosure that hides this node, if any."""
    chain = [node, *node.ancestors()]
    for index, element in enumerate(chain):
        if element.tag != "details" or "open" in element.attrs or id(element) in opened:
            continue
        summary = _summary(element)
        if summary is None or summary not in chain[:index]:
            return element
    return None


def hidden(node: Node) -> bool:
    """Return whether the page does not render this node at all."""
    return any("hidden" in element.attrs for element in (node, *node.ancestors()))


def silent(node: Node) -> bool:
    """Return whether assistive technology is told to ignore this node."""
    return any(element.attrs.get("aria-hidden") == "true" for element in (node, *node.ancestors()))


def focusable(node: Node) -> bool:
    """Return whether Tab reaches this element when it is not hidden."""
    if "disabled" in node.attrs:
        return False
    tabindex = node.attrs.get("tabindex")
    if tabindex is not None and re.fullmatch(r"-?\d+", tabindex) and int(tabindex) < 0:
        return False
    if node.tag == "a":
        return "href" in node.attrs
    if node.tag in {"button", "select", "textarea"}:
        return True
    if node.tag == "input":
        return node.attrs.get("type", "text") != "hidden"
    if node.tag == "summary":
        return node.parent is not None and node.parent.tag == "details"
    return tabindex is not None and re.fullmatch(r"\d+", tabindex) is not None


def role(node: Node) -> str:
    if node.tag == "summary":
        return "disclosure"
    if node.tag == "a":
        return "link"
    if node.tag == "input":
        kind = node.attrs.get("type", "text")
        return "button" if kind in {"submit", "button"} else kind
    return node.tag if node.tag in {"button", "select", "textarea"} else "control"


def accessible_name(node: Node, root: Node) -> str:
    """Name a control the way assistive technology would, for the cases this page uses."""
    if silent(node):
        return ""
    by_id = {n.attrs["id"]: n for n in root.walk() if "id" in n.attrs}
    if node.attrs.get("aria-labelledby"):
        ids = node.attrs["aria-labelledby"].split()
        return " ".join(by_id[i].text() for i in ids if i in by_id).strip()
    if node.attrs.get("aria-label", "").strip():
        return node.attrs["aria-label"].strip()
    if node.tag in {"select", "input", "textarea"}:
        if node.tag == "input" and role(node) == "button" and node.attrs.get("value"):
            return node.attrs["value"].strip()
        control_id = node.attrs.get("id")
        for label in root.walk():
            if label.tag == "label" and control_id and label.attrs.get("for") == control_id:
                return label.text()
        wrapper = next((a for a in node.ancestors() if a.tag == "label"), None)
        if wrapper is not None:
            return wrapper.text(skip=node)
    elif node.tag in {"a", "button", "summary"} or node.attrs.get("tabindex"):
        if node.text():
            return node.text()
    return node.attrs.get("title", "").strip()


def task_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower())) & TASK_WORDS


def _options(select: Node) -> list[tuple[str, str, bool]]:
    """Return (value, text, selected) for each option of a select."""
    return [
        (o.attrs.get("value", o.text()), o.text(), "selected" in o.attrs)
        for o in select.walk()
        if o.tag == "option"
    ]


def _default(select: Node) -> str:
    options = _options(select)
    chosen = [value for value, _, selected in options if selected]
    return chosen[0] if chosen else (options[0][0] if options else "")


def form_request(form: Node, choices: dict[int, str]) -> list[tuple[str, str]]:
    """Return the name=value pairs a browser sends for this form."""
    pairs: list[tuple[str, str]] = []
    for node in form.walk():
        name = node.attrs.get("name")
        if not name or "disabled" in node.attrs:
            continue
        if node.tag == "select":
            pairs.append((name, choices.get(id(node), _default(node))))
        elif node.tag == "textarea":
            pairs.append((name, node.text()))
        elif node.tag == "input":
            kind = node.attrs.get("type", "text")
            if kind in {"checkbox", "radio"} and "checked" not in node.attrs:
                continue
            if kind not in {"submit", "button", "reset", "image"}:
                pairs.append((name, node.attrs.get("value", "")))
    return pairs


def _rows(rows: list) -> str:
    return ", ".join(f"#{row.number} {row.status}" for row in rows) or "(none)"


def _first_values(pairs: list[tuple[str, str]]) -> dict[str, str]:
    request: dict[str, str] = {}
    for name, value in pairs:
        request.setdefault(name, value)
    return request


def view(html: str) -> list[str]:
    """Describe what a keyboard user meets when the page loads, without trying the task."""
    root = parse(html)
    title = next((n.text() for n in root.walk() if n.tag == "h1"), "(no heading)")
    lines = [f"page: {title}", "Tab order when the page loads:"]
    stop = 0
    for node in root.walk():
        if focusable(node) and not hidden(node) and closed_disclosure(node, set()) is None:
            stop += 1
            label = accessible_name(node, root) or "(no accessible name)"
            extra = ""
            if node.tag == "summary" and node.parent is not None:
                extra = " (open)" if "open" in node.parent.attrs else " (closed)"
            if node.tag == "select":
                extra = f" (shows {_default_text(node)})"
            lines.append(f'  {stop}. {role(node)} "{label}"{extra}')
    form = next((n for n in root.walk() if n.tag == "form"), None)
    rows = dashboard.handle(_first_values(form_request(form, {}))) if form else []
    lines.append(f"rows shown: {_rows(rows)}")
    return lines


def _default_text(select: Node) -> str:
    value = _default(select)
    return next((text for v, text, _ in _options(select) if v == value), value)


def attempt(html: str) -> dict[str, object]:
    """Try the task once with the stated strategy and return the observations."""
    root = parse(html)
    opened: set[int] = set()
    choices: dict[int, str] = {}
    steps: list[str] = []
    unnamed: list[str] = []
    submitter: Node | None = None
    stop = 0
    for node in root.walk():
        if not focusable(node) or hidden(node) or closed_disclosure(node, opened):
            continue
        stop += 1
        name = accessible_name(node, root)
        if not name:
            unnamed.append(f"{role(node)} at stop {stop}")
        shown = f'{role(node)} "{name or "(no accessible name)"}"'
        if node.tag == "summary" and node.parent is not None:
            if "open" in node.parent.attrs:
                steps.append(f"{stop}. {shown} (open): already open")
            elif task_words(name):
                opened.add(id(node.parent))
                steps.append(f"{stop}. {shown} (closed): opened; shares a task word")
            else:
                steps.append(f"{stop}. {shown} (closed): not opened; no task word")
        elif node.tag == "select":
            heard = [] if silent(node) else _options(node)
            match = next((o for o in heard if task_words(o[1])), None)
            if match is None:
                steps.append(f"{stop}. {shown}: left at its default; no option has a task word")
            else:
                choices[id(node)] = match[0]
                steps.append(f'{stop}. {shown}: chose "{match[1]}"')
        elif role(node) == "button" and node.attrs.get("type", "submit") == "submit":
            submitter = submitter or node
            steps.append(f"{stop}. {shown}: submit button")
        elif node.tag == "a":
            steps.append(f"{stop}. {shown}: not followed; the strategy does not follow links")
        else:
            steps.append(f"{stop}. {shown}: not used by this strategy")
    not_reached = [
        f'{role(node)} "{accessible_name(node, root) or "(no accessible name)"}" inside closed '
        f'disclosure "{accessible_name(_summary(details), root)}"'
        for node in root.walk()
        if focusable(node)
        and not hidden(node)
        and (details := closed_disclosure(node, opened)) is not None
        and _summary(details) is not None
    ]
    form = next((a for a in submitter.ancestors() if a.tag == "form"), None) if submitter else None
    pairs = form_request(form, choices) if form is not None else []
    request = _first_values(pairs)
    rows = dashboard.handle(request) if form is not None else []
    ignored = sorted(name for name in request if name not in dashboard.FIELDS)
    names = [name for name, _ in pairs]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if form is None:
        reason = "no reachable submit button inside a form"
    elif unnamed:
        reason = "a reached control has no accessible name: " + "; ".join(unnamed)
    elif not rows or rows[0].number != EXPECTED:
        first = f"#{rows[0].number} {rows[0].status}" if rows else "no row"
        reason = f"the first row shown is {first}, not #{EXPECTED} failed"
    else:
        reason = f"the first row shown is #{EXPECTED} failed"
    completed = form is not None and not unnamed and bool(rows) and rows[0].number == EXPECTED
    return {
        "steps": steps,
        "not_reached": not_reached,
        "unnamed": unnamed,
        "request": "&".join(f"{name}={value}" for name, value in pairs) or "(not sent)",
        "ignored": ignored,
        "repeated": repeated,
        "rows": rows,
        "completed": completed,
        "reason": reason,
    }


def query_check() -> tuple[bool, str]:
    """Check the unchanged query against the data, independently of any page."""
    observed = [build.number for build in dashboard.query(pipeline="alpha", status="failed")]
    expected = sorted(
        (b.number for b in dashboard.BUILDS if (b.pipeline, b.status) == ("alpha", "failed")),
        reverse=True,
    )
    shown = ", ".join(f"#{number}" for number in observed)
    return observed == expected, f"query(pipeline=alpha, status=failed) returns {shown}"


def report(path: Path, html: str) -> tuple[int, list[str]]:
    result = attempt(html)
    passed, detail = query_check()
    lines = [
        f"page: {path.name}",
        f"task: {TASK}",
        f"unchanged query check: {'pass' if passed else 'FAIL'}; {detail}",
        "keyboard walk from the top of the page:",
        *(f"  {step}" for step in result["steps"]),
        "not reached: " + ("; ".join(result["not_reached"]) or "nothing"),
        "reached controls without an accessible name: " + (", ".join(result["unnamed"]) or "none"),
        f"request sent: {result['request']}",
        "fields the dashboard ignores: " + (", ".join(result["ignored"]) or "none"),
        "fields sent more than once: "
        + (
            ", ".join(result["repeated"]) + " (the dashboard reads the first value)"
            if result["repeated"]
            else "none"
        ),
        f"rows shown: {_rows(result['rows'])}",
        f"expected first row: #{EXPECTED} failed",
        ("result: COMPLETED - " if result["completed"] else "result: NOT COMPLETED - ")
        + str(result["reason"]),
    ]
    return (0 if result["completed"] and passed else 1), lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("page", type=Path, help="an HTML page, such as current.html")
    parser.add_argument(
        "--view",
        action="store_true",
        help="only describe what a keyboard user meets on load; do not try the task",
    )
    args = parser.parse_args(argv)
    try:
        html = args.page.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"cannot read {args.page}: {error.__class__.__name__}", file=sys.stderr)
        return 2
    if args.view:
        print("\n".join(view(html)))
        return 0
    code, lines = report(args.page, html)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
