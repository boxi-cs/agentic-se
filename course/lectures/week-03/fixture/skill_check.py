"""Check a SKILL.md and its trigger test as data; nothing in them is executed.

Run from the course root (it reads files only):

    uv run --locked python lectures/week-03/fixture/skill_check.py \
        "$PROJECT_ROOT/A3-work/skills/my-workflow/SKILL.md" \
        "$PROJECT_ROOT/A3-work/trigger-test.yaml"

It checks structure and consistency, never whether an agent "really" selected the
skill: you record that observation.
"""

import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

import yaml

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
OPTIONAL_KEYS = {"license", "compatibility", "metadata", "allowed-tools"}
SECTIONS = {
    "Steps": ("steps",),
    "Judgement": ("judgement", "judgment"),
    "Verification": ("verification",),
}
EXAMPLE = "verify-change"
MAX_BODY_LINES = 500
LIST_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+\S")
LINK = re.compile(r"\]\(([^)\s]+)\)")
STOPWORDS = {
    "this",
    "that",
    "with",
    "from",
    "when",
    "what",
    "your",
    "into",
    "have",
    "them",
    "then",
    "they",
    "will",
    "would",
    "should",
    "about",
    "which",
    "there",
    "their",
    "where",
    "does",
    "skill",
    "using",
    "used",
    "make",
    "need",
    "want",
    "please",
}


def normalize(text: str) -> str:
    """Drop a leading byte-order mark and use LF line endings, as any editor may save."""
    return text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def decode(raw: bytes) -> str:
    """The one way this check reads a file, whatever editor saved it."""
    return normalize(raw.decode("utf-8"))


def split_front_matter(text: str) -> tuple[object, str]:
    """Return the parsed front matter and the Markdown body."""
    text = normalize(text)
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with a '---' front matter line.")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("Front matter must close with a '---' line.")
    return yaml.safe_load(text[4:end]), text[end + 5 :]


def sections(body: str) -> dict[str, str]:
    """Map each level-two heading (casefolded) to the text below it."""
    found: dict[str, list[str]] = {}
    current = None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip().casefold()
            found.setdefault(current, [])
        elif current is not None:
            found[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in found.items()}


def check_skill(
    text: str, directory: str, supporting: set[str], example_body: str | None = None
) -> tuple[dict, list[str]]:
    """Return the front matter and every problem found in one SKILL.md."""
    problems: list[str] = []
    try:
        front, body = split_front_matter(text)
    except (ValueError, yaml.YAMLError) as error:
        return {}, [str(error).splitlines()[0]]
    if not isinstance(front, dict):
        return {}, ["Front matter must be a YAML mapping."]
    unknown = sorted(set(front) - {"name", "description"} - OPTIONAL_KEYS)
    if unknown:
        problems.append(f"Unknown front matter field: {unknown[0]}.")
    name, description = front.get("name"), front.get("description")
    if not isinstance(name, str) or not NAME.fullmatch(name) or len(name) > 64:
        problems.append("name: 1-64 lowercase letters, digits and single hyphens.")
    elif name != directory:
        problems.append(f"name '{name}' must match its directory '{directory}'.")
    elif name == EXAMPLE:
        problems.append("Write your own skill; the course example does not count.")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        problems.append("description: 1-1024 characters.")
    else:
        if len(description.split()) < 8:
            problems.append("description: say what the skill does, in at least eight words.")
        if not re.search(r"\bwhen\b", description, flags=re.IGNORECASE):
            problems.append("description: say when to use it (include 'when').")
    if len(body.splitlines()) > MAX_BODY_LINES:
        problems.append(f"Body exceeds {MAX_BODY_LINES} lines; move reference material out.")
    if example_body is not None and body.strip() == example_body.strip():
        problems.append("Body copies the course example.")
    found = sections(body)
    for title, keys in SECTIONS.items():
        content = next((found[key] for key in keys if key in found), None)
        if not content:
            problems.append(f"Missing or empty '## {title}' section.")
        elif title == "Steps" and sum(bool(LIST_ITEM.match(x)) for x in content.splitlines()) < 2:
            problems.append("Steps: list at least two concrete steps.")
        elif title == "Judgement" and not re.search(r"\b(if|unless|when)\b", content, re.I):
            problems.append("Judgement: name at least one decision ('if ...', 'unless ...').")
        elif title == "Verification" and "`" not in content:
            problems.append("Verification: give the exact command or check in backticks.")
    for target in LINK.findall(body):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        problem = link_problem(unquote(target.split("#", 1)[0]), supporting)
        if problem:
            problems.append(problem)
    return front, problems


def link_problem(path: str, supporting: set[str]) -> str | None:
    """A link must name an existing file inside the skill directory, relative to it."""
    if path.startswith("/"):
        return f"Link '{path}' is absolute; link relative to the skill directory."
    parts = PurePosixPath(path).parts
    if ".." in parts:
        return f"Link '{path}' leaves the skill directory."
    if str(PurePosixPath(*parts)) not in supporting:
        return f"Linked supporting file '{path}' does not exist in the skill directory."
    return None


def names_skill(prompt: str, name: str) -> bool:
    """'trace-request', 'trace request', 'trace_request' and 'TraceRequest' all name it."""
    words = r"[\s_-]*".join(re.escape(word) for word in name.split("-"))
    return re.search(words, prompt.casefold()) is not None


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def check_triggers(data: object, skill: dict) -> list[str]:
    """Structure and internal consistency of a recorded trigger test."""
    if not isinstance(data, dict):
        return ["The trigger test must be a YAML mapping."]
    problems = []
    allowed = {"skill", "observer", "observer_detail", "prompts", "revision"}
    if set(data) - allowed:
        problems.append(f"Unknown field: {sorted(set(data) - allowed)[0]}.")
    name = skill.get("name")
    if data.get("skill") != name:
        problems.append("'skill' must equal the SKILL.md name.")
    if data.get("observer") not in ("agent", "peer"):
        problems.append("'observer' must be 'agent' or 'peer'.")
    detail = data.get("observer_detail")
    if not isinstance(detail, str) or not 1 <= len(detail.strip()) <= 200:
        problems.append("'observer_detail': who or what selected skills (1-200 characters).")
    prompts = data.get("prompts")
    if not isinstance(prompts, list) or not 4 <= len(prompts) <= 12:
        return [*problems, "'prompts': list 4-12 entries."]
    keys = {"id", "prompt", "should_trigger", "predicted", "observed"}
    ids, texts, mismatches = set(), set(), []
    positives = negatives = 0
    description = normalized(skill.get("description") or "")
    for entry in prompts:
        if not isinstance(entry, dict) or set(entry) != keys:
            problems.append(f"Each prompt has exactly: {sorted(keys)}.")
            continue
        prompt = entry["prompt"]
        if not isinstance(entry["id"], str) or not entry["id"] or entry["id"] in ids:
            problems.append("Prompt ids must be distinct nonempty strings.")
        ids.add(entry["id"])
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 300:
            problems.append(f"{entry['id']}: prompt must have 1-300 characters.")
            continue
        if normalized(prompt) in texts:
            problems.append(f"{entry['id']}: duplicate prompt.")
        texts.add(normalized(prompt))
        if description and description in normalized(prompt):
            problems.append(f"{entry['id']}: do not paste the description as a prompt.")
        flags = [entry[key] for key in ("should_trigger", "predicted", "observed")]
        if not all(isinstance(flag, bool) for flag in flags):
            problems.append(f"{entry['id']}: should_trigger, predicted, observed are true/false.")
            continue
        if entry["should_trigger"]:
            positives += isinstance(name, str) and not names_skill(prompt, name)
        else:
            negatives += 1
        if entry["observed"] != entry["should_trigger"]:
            mismatches.append(entry["id"])
    if positives < 3:
        problems.append("Give at least three should-trigger prompts that do not name the skill.")
    if negatives < 1:
        problems.append("Give at least one near-miss prompt that should not trigger.")
    revision = data.get("revision")
    if mismatches or revision is not None:
        if not isinstance(revision, dict) or set(revision) != {"description_change", "rechecked"}:
            return [*problems, "A mismatch needs 'revision' with description_change, rechecked."]
        change = revision["description_change"]
        if not isinstance(change, str) or not change.strip():
            problems.append("revision.description_change: say what you changed.")
        rechecked = revision["rechecked"]
        if not isinstance(rechecked, list) or not all(
            isinstance(item, dict)
            and set(item) == {"id", "observed"}
            and isinstance(item["observed"], bool)
            for item in rechecked
        ):
            problems.append("revision.rechecked: entries with id and observed.")
        elif sorted(item["id"] for item in rechecked) != sorted(mismatches):
            problems.append("revision.rechecked must list exactly the mismatched prompt ids.")
    return problems


def overlap(prompt: str, description: str) -> list[str]:
    """Advisory only: content words a prompt shares with the description."""

    def words(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-z]{4,}", text.casefold()) if w not in STOPWORDS}

    return sorted(words(prompt) & words(description))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    skill_path, trigger_path = Path(argv[1]), Path(argv[2])
    directory = skill_path.parent
    supporting = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path != skill_path
    }
    example = Path(__file__).with_name("skills") / EXAMPLE / "SKILL.md"
    example_body = split_front_matter(decode(example.read_bytes()))[1] if example.exists() else None
    texts = {}
    for path in (skill_path, trigger_path):
        try:
            texts[path] = decode(path.read_bytes())
        except UnicodeDecodeError:
            print(f"FAIL {path}: not UTF-8 text. Save it as UTF-8 and run the check again.")
            return 1
    front, problems = check_skill(texts[skill_path], directory.name, supporting, example_body)
    trigger = yaml.safe_load(texts[trigger_path])
    problems += check_triggers(trigger, front)
    for problem in problems:
        print("FAIL", problem)
    if isinstance(trigger, dict) and isinstance(trigger.get("prompts"), list):
        print("\nAdvisory: words each prompt shares with your description")
        for entry in trigger["prompts"]:
            if isinstance(entry, dict) and isinstance(entry.get("prompt"), str):
                shared = overlap(entry["prompt"], str(front.get("description", "")))
                print(f"  {entry.get('id')}: {', '.join(shared) or '(none)'}")
    print("\nStructure checked." if not problems else f"\n{len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
