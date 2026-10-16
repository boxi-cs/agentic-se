"""Refresh data/ from the course and video repositories (run locally; both are private).

    python3 tools/export_data.py --course ~/Documents/agentic-se-course --videos ~/Documents/agentic-se-videos

Writes data/course.json (the course's tagline and approach page, its calendar and English syllabus, read
from the course repository at its freshly fetched origin/main; the syllabus translation must match its
source) and data/episodes.json (each film's number, title, decision, length and subtitles, read from the
video repository's origin/main). Nothing else from either repository is copied. Which calendar week a
film supports, and whether it is published, is not exported: that is the hand-maintained data/films.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The public syllabus is SYLLABUS.en.md verbatim, except for these (old, new) edits for a public page; each
# must still occur in the source, or the export stops. There are none at present: the syllabus's one link
# into the course repository (the Week 0 setup page) is published under course/, and build.py points it there.
SYLLABUS_EDITS: list[tuple[str, str]] = []
WEEK_FIELDS = ("topic", "lecture", "workshop", "deliverables")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def git_bytes(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def parse_schedule(text: str) -> list[dict[str, object]]:
    """Read site/schedule.en.yaml without a YAML dependency: its weeks are flat `key: value` maps."""
    weeks: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    key = ""
    for line in text.splitlines():
        if line.startswith("- week:"):
            current = {"week": int(line.split(":", 1)[1])}
            weeks.append(current)
            continue
        if current is None or not line.startswith("  "):
            if not line.startswith(" "):
                current = None
            continue
        match = re.match(r"^  (\w+): (.*)$", line)
        if match:
            key, value = match.groups()
            current[key] = value
        elif line.startswith("    "):  # a folded continuation of the previous value
            current[key] = f"{current[key]} {line.strip()}"
    for week in weeks:
        for field, value in week.items():
            if isinstance(value, str) and len(value) > 1 and value[0] == value[-1] == "'":
                week[field] = value[1:-1].replace("''", "'")
    return weeks


def prose(text: str) -> str:
    """A page's Markdown without front matter, with each paragraph and list item on one line.

    The site's renderer starts a new paragraph at every line break, so wrapped source lines are joined.
    """
    body = text.split("---\n", 2)[2] if text.startswith("---\n") else text
    blocks = []
    for block in re.split(r"\n\s*\n", body.strip()):
        lines = block.splitlines()
        if lines[0].startswith(("#", "|")):
            blocks.append(block)
        elif lines[0].startswith("- "):
            items: list[str] = []
            for line in lines:
                if line.startswith("- "):
                    items.append(line)
                else:
                    items[-1] += " " + line.strip()
            blocks.append("\n".join(items))
        else:
            blocks.append(" ".join(line.strip() for line in lines))
    return "\n\n".join(blocks)


def tagline(text: str) -> str:
    """The course home's one-line bold tagline."""
    match = re.search(r"^\*\*(.+)\*\*$", text, re.M)
    if not match:
        raise SystemExit("course home tagline not found in site/docs/index.en.md")
    return match.group(1)


def principles(text: str) -> list[dict]:
    """The course home's principle cards: a bold title, a rule, then the card's text."""
    cards = [
        {"title": title, "text": " ".join(body.split())}
        for title, body in re.findall(r"^-   \*\*(.+?)\*\*\n\n    ---\n\n((?:    .+\n?)+)", text, re.M)
    ]
    if not cards:
        raise SystemExit("course home principle cards not found in site/docs/index.en.md")
    return cards


def decision(script: str) -> str:
    match = re.search(r"^- \*\*Decision\*\*: (.+)$", script, re.M)
    return match.group(1).strip() if match else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course", type=Path, required=True)
    parser.add_argument("--videos", type=Path, required=True)
    parser.add_argument("--ref", default="origin/main",
                        help="course commit to read; anything but origin/main is for a local preview only")
    args = parser.parse_args()

    git(args.course, "fetch", "-q", "origin")
    course_sha = git(args.course, "rev-parse", args.ref).strip()
    course = {
        "source": {"repository": "boxi-cs/agentic-se-course", "commit": course_sha},
        "title": "Agentic Software Engineering: Build, Verify, Evaluate",
        "tagline": tagline(git(args.course, "show", f"{course_sha}:site/docs/index.en.md")),
        "principles": principles(git(args.course, "show", f"{course_sha}:site/docs/index.en.md")),
        "approach": prose(git(args.course, "show", f"{course_sha}:site/docs/approach.en.md")),
        "weeks": parse_schedule(git(args.course, "show", f"{course_sha}:site/schedule.en.yaml")),
    }
    numbers = [week["week"] for week in course["weeks"]]
    if not numbers or numbers != list(range(1, len(numbers) + 1)):
        raise SystemExit(f"schedule weeks are not numbered 1..N: {numbers}")
    for week in course["weeks"]:
        if missing := [field for field in WEEK_FIELDS if not week.get(field)]:
            raise SystemExit(f"schedule week {week['week']} lacks {missing}")
    syllabus_en = git(args.course, "show", f"{course_sha}:SYLLABUS.en.md")
    _, front, body = syllabus_en.split("---\n", 2)
    meta = dict(line.split(": ", 1) for line in front.strip().splitlines() if ": " in line)
    source_digest = hashlib.sha256(git_bytes(args.course, "show", f"{course_sha}:SYLLABUS.md")).hexdigest()
    if meta.get("source") != "SYLLABUS.md" or meta.get("source_digest") != source_digest:
        raise SystemExit("SYLLABUS.en.md is stale against SYLLABUS.md; the course must update its translation first")
    body = body.strip()
    for old, new in SYLLABUS_EDITS:
        if old not in body:
            raise SystemExit(f"syllabus edit no longer applies: {old!r}")
        body = body.replace(old, new)
    course["syllabus"] = {"updated": meta.get("updated_at", ""), "markdown": body}
    (ROOT / "data/course.json").write_text(json.dumps(course, indent=2, ensure_ascii=False) + "\n")

    videos_sha = git(args.videos, "rev-parse", "origin/main").strip()
    episodes = []
    names = git(args.videos, "ls-tree", "--name-only", f"{videos_sha}:episodes").split()
    for slug in sorted(names):
        script = git(args.videos, "show", f"{videos_sha}:episodes/{slug}/script.md")
        timeline = json.loads((args.videos / "media/episodes" / slug / "Episode.json").read_text())
        subtitles = {
            lang: git(args.videos, "show", f"{videos_sha}:episodes/{slug}/subtitles/Episode/{lang}.srt")
            for lang in ("en", "zh")
        }
        episodes.append(
            {
                "number": int(slug[:2]),  # names the release asset (week-NN.mp4); data/films.json gives the week
                "slug": slug,
                "title": script.splitlines()[0].split("—", 1)[1].strip(),
                "decision": decision(script),
                "seconds": round(timeline[-1]["end"], 1),
                "subtitles": subtitles,
            }
        )
    data = {"source": {"repository": "boxi-cs/agentic-se-videos", "commit": videos_sha}, "episodes": episodes}
    (ROOT / "data/episodes.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"course {course_sha[:7]}: {len(course['weeks'])} weeks; videos {videos_sha[:7]}: {len(episodes)} episodes")


if __name__ == "__main__":
    main()
