"""Build the static site from data/ into the repository root (served by GitHub Pages).

    python3 build.py            # writes index.html, weeks/NN/index.html and subtitle tracks

Only the Python standard library is used. Text on the pages comes from data/course.json (the
course's public English overview and schedule) and data/episodes.json (the weekly videos);
the few sentences written here are labelled in the comments.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE = "https://github.com/boxi-cs/agentic-se/releases/download/videos-2026-10-08"
FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1'
    '&family=Inter:wght@400;500;600&family=JetBrains+Mono&display=swap" media="print" onload="this.media=\'all\'">'
)


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def inline(text: str) -> str:
    """Escape text, then render `code` spans."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", esc(text))


def minutes(seconds: float) -> str:
    whole = round(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def hours_minutes(seconds: float) -> str:
    whole = round(seconds / 60)
    return f"{whole // 60} h {whole % 60} min"


def vtt(srt: str) -> str:
    return "WEBVTT\n\n" + re.sub(r"(\d\d:\d\d:\d\d),(\d\d\d)", r"\1.\2", srt.strip()) + "\n"


def page(title: str, description: str, depth: int, body: str) -> str:
    up = "../" * depth
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
{FONTS}
<link rel="stylesheet" href="{up}assets/site.css">
<link rel="icon" href="{up}assets/favicon.svg" type="image/svg+xml">
</head>
<body>
{body}
<footer class="foot">
  <p>Videos: English narration in a draft synthetic voice (LJ Speech, public domain), with English and
  Chinese subtitles. Every example in them is course-authored and synthetic.</p>
  <p>Contact: <a href="mailto:boxi.yu@ul.ie">boxi.yu@ul.ie</a> ·
  <a href="https://github.com/boxi-cs/agentic-se">Source for this site</a> · Boxi CS</p>
</footer>
</body>
</html>
"""


def sentence(paragraphs: list[str], start: str) -> str:
    """One sentence from the course overview, taken verbatim (fails loudly if the source changed)."""
    for paragraph in paragraphs:
        for part in re.split(r"(?<=\.)\s+", paragraph):
            if part.startswith(start):
                return part
    raise SystemExit(f"overview sentence not found: {start!r}")


def home(course: dict, episodes: list[dict]) -> str:
    text = course["overview"]
    lede = " ".join(
        sentence(text, s)
        for s in ("Learn to enter an unfamiliar repository", "The teacher's CI dashboard case", "Each student works")
    )
    weeks = {w["week"]: w for w in course["weeks"]}
    total = sum(e["seconds"] for e in episodes)
    cards = "\n".join(
        f"""  <a class="card" href="weeks/{e['week']:02d}/">
    <img src="weeks/{e['week']:02d}/poster.jpg" alt="" loading="lazy" width="960" height="540">
    <span class="card-week">Week {e['week']} · {minutes(e['seconds'])}</span>
    <span class="card-title">{esc(e['title'])}</span>
    <span class="card-topic">{esc(weeks[e['week']]['topic'])}</span>
  </a>"""
        for e in episodes
    )
    rows = "\n".join(
        f"""    <tr><td>{w['week']}</td><td><a href="weeks/{w['week']:02d}/">{esc(w['topic'])}</a></td>"""
        f"""<td>{inline(w['deliverables'])}</td></tr>"""
        for w in course["weeks"]
    )
    body = f"""<header class="hero">
  <p class="kicker">Boxi CS · Course</p>
  <h1>Agentic Software Engineering<span>Build, <em>verify</em>, evaluate.</span></h1>
  <p class="lede">{inline(lede)}</p>
  <ul class="facts">
    <li><b>14</b> weeks</li>
    <li><b>3</b> personal practices</li>
    <li><b>5</b> project workshops</li>
    <li><b>1</b> repository, <code>ci-dashboard</code></li>
  </ul>
</header>
<main>
<section>
  <h2>Weekly videos</h2>
  <!-- Site text: what the videos are, and their total length. -->
  <p class="note">One short film per week shows that week's central decision through worked examples:
  generate, then verify. {len(episodes)} films, {hours_minutes(total)} in all.</p>
  <div class="cards">
{cards}
  </div>
</section>
<section>
  <h2>Schedule</h2>
  <table class="schedule">
    <thead><tr><th>Week</th><th>Topic</th><th>Deliverables</th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <!-- Site text: what the labels in the schedule stand for (SYLLABUS.md and the schedule's own wording). -->
  <p class="note">P1–P3: personal practices · M0–M4: project milestones · CP1, CP2: 30-minute individual checkpoints.</p>
</section>
<section>
  <h2>Contact</h2>
  <!-- Site text: the contact the maintainer gave. -->
  <p>Questions about the course: <a href="mailto:boxi.yu@ul.ie">boxi.yu@ul.ie</a></p>
</section>
</main>"""
    return page(course["title"], lede, 0, body)


def week_page(course: dict, episodes: list[dict], index: int) -> str:
    e = episodes[index]
    w = next(w for w in course["weeks"] if w["week"] == e["week"])
    number = f"{e['week']:02d}"
    prev_link = (
        f'<a href="../{episodes[index - 1]["week"]:02d}/">← Week {episodes[index - 1]["week"]}</a>' if index else "<span></span>"
    )
    next_link = (
        f'<a href="../{episodes[index + 1]["week"]:02d}/">Week {episodes[index + 1]["week"]} →</a>'
        if index + 1 < len(episodes)
        else "<span></span>"
    )
    body = f"""<header class="hero hero-week">
  <p class="kicker"><a href="../../">Agentic Software Engineering</a> · Week {e['week']}</p>
  <h1>{esc(e['title'])}</h1>
  <p class="lede">{esc(w['topic'])}</p>
</header>
<main>
  <video controls preload="metadata" poster="poster.jpg" src="{RELEASE}/week-{number}.mp4">
    <track kind="subtitles" srclang="en" label="English" src="en.vtt" default>
    <track kind="subtitles" srclang="zh" label="中文" src="zh.vtt">
  </video>
  <p class="meta">{minutes(e['seconds'])} · subtitles: <a href="en.vtt">English</a>, <a href="zh.vtt" lang="zh" hreflang="zh">中文</a> ·
  <a href="{RELEASE}/week-{number}.mp4">download</a></p>
  <section>
    <h2>The idea</h2>
    <p>{inline(e['decision'][0].upper() + e['decision'][1:])}</p>
  </section>
  <section>
    <h2>This week</h2>
    <dl class="week">
      <dt>Lecture</dt><dd>{inline(w['lecture'])}</dd>
      <dt>Workshop</dt><dd>{inline(w['workshop'])}</dd>
      <dt>Deliverables</dt><dd>{inline(w['deliverables'])}</dd>
    </dl>
  </section>
  <nav class="pager">{prev_link}<a href="../../">All weeks</a>{next_link}</nav>
</main>"""
    return page(f"Week {e['week']}: {e['title']} · Agentic Software Engineering", w["topic"], 2, body)


def main() -> None:
    course = json.loads((ROOT / "data/course.json").read_text())
    episodes = json.loads((ROOT / "data/episodes.json").read_text())["episodes"]
    (ROOT / "index.html").write_text(home(course, episodes))
    for index, e in enumerate(episodes):
        folder = ROOT / "weeks" / f"{e['week']:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(week_page(course, episodes, index))
        for lang, srt in e["subtitles"].items():
            (folder / f"{lang}.vtt").write_text(vtt(srt))
    print(f"built index.html and {len(episodes)} week pages")


if __name__ == "__main__":
    main()
