"""Refresh data/ from the course and video repositories (run locally; both are private).

    python3 tools/export_data.py --course ~/Documents/agentic-se-course --videos ~/Documents/agentic-se-videos

Writes data/course.json (the public English overview and 14-week schedule, read from the course
repository's student site at its origin/main) and data/episodes.json (each weekly episode's title,
decision, length and subtitles, read from the video repository's origin/main). Nothing else from
either repository is copied.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


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


def overview(text: str) -> list[str]:
    """The paragraphs of site/docs/index.en.md after its front matter and heading."""
    body = text.split("---", 2)[2]
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip() and not p.strip().startswith("#")]
    return paragraphs


def decision(script: str) -> str:
    match = re.search(r"^- \*\*Decision\*\*: (.+)$", script, re.M)
    return match.group(1).strip() if match else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course", type=Path, required=True)
    parser.add_argument("--videos", type=Path, required=True)
    args = parser.parse_args()

    course_sha = git(args.course, "rev-parse", "origin/main").strip()
    course = {
        "source": {"repository": "boxi-cs/agentic-se-course", "commit": course_sha},
        "title": "Agentic Software Engineering: Build, Verify, Evaluate",
        "overview": overview(git(args.course, "show", f"{course_sha}:site/docs/index.en.md")),
        "weeks": parse_schedule(git(args.course, "show", f"{course_sha}:site/schedule.en.yaml")),
    }
    (ROOT / "data/course.json").write_text(json.dumps(course, indent=2, ensure_ascii=False) + "\n")

    videos_sha = git(args.videos, "rev-parse", "origin/main").strip()
    episodes = []
    names = git(args.videos, "ls-tree", "--name-only", f"{videos_sha}:episodes").split()
    for slug in sorted(names):
        script = git(args.videos, "show", f"{videos_sha}:episodes/{slug}/script.md")
        week = int(slug[:2])
        timeline = json.loads((args.videos / "media/episodes" / slug / "Episode.json").read_text())
        subtitles = {
            lang: git(args.videos, "show", f"{videos_sha}:episodes/{slug}/subtitles/Episode/{lang}.srt")
            for lang in ("en", "zh")
        }
        episodes.append(
            {
                "week": week,
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
