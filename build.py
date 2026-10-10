"""Build the static site from data/ into the repository root (served by GitHub Pages).

    python3 build.py            # writes index.html, approach/, syllabus/, weeks/NN/index.html and subtitle tracks

Only the Python standard library is used. Text on the pages comes from data/course.json (the
course's tagline, approach page, schedule and syllabus) and data/episodes.json (the weekly videos);
the few sentences written here are labelled in the comments.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE = "https://github.com/boxi-cs/agentic-se/releases/download/videos-2026-10-10"
# Site text: the instructor, as given by the maintainer and on https://boxiyu.github.io/.
INSTRUCTOR = {
    "name": "Boxi Yu",
    "role": "Instructor · Senior Research Fellow, Lero",
    "homepage": "https://boxiyu.github.io/",
    "photo": "https://boxiyu.github.io/assets/img/prof_pic.jpg",
    "email": "boxi.yu@ul.ie",
}
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


def md_inline(text: str) -> str:
    """Escape, then render `code`, **bold** and links (a link into the private repository keeps only its text)."""
    out = esc(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)

    def link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        if url.startswith("site:"):  # a link local_links() pointed at a page of this site
            return f'<a href="{url[5:]}">{label}</a>'
        return f'<a href="{url}">{label}</a>' if url.startswith("https://") else label

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, out)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def markdown(source: str) -> tuple[str, list[tuple[str, str]]]:
    """Render the syllabus's Markdown subset: headings, paragraphs, bullet lists and pipe tables.

    Returns the HTML and the (id, title) of each level-2 heading, for a contents list.
    """
    html_parts: list[str] = []
    contents: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n", source.strip()):
        lines = block.splitlines()
        first = lines[0]
        if first.startswith("## "):
            title = first[3:].strip()
            contents.append((slug(title), title))
            html_parts.append(f'<h2 id="{slug(title)}">{md_inline(title)}</h2>')
            lines = lines[1:]
            if not lines:
                continue
            first = lines[0]
        if first.startswith("# "):
            continue  # the page has its own title
        if first.startswith("|"):
            rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
            if any(len(row) != len(rows[0]) for row in rows):
                raise SystemExit(f"table rows differ in cell count: {first!r}")
            align = [' class="num"' if cell.endswith(":") else "" for cell in rows[1]]
            head = "".join(f"<th{a}>{md_inline(c)}</th>" for c, a in zip(rows[0], align))
            body = "".join(
                "<tr>" + "".join(f"<td{a}>{md_inline(c)}</td>" for c, a in zip(row, align)) + "</tr>" for row in rows[2:]
            )
            html_parts.append(f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
        elif first.startswith("- "):
            items = "".join(f"<li>{md_inline(line[2:])}</li>" for line in lines)
            html_parts.append(f"<ul>{items}</ul>")
        else:
            for line in lines:  # a hard line break in the source starts a new paragraph
                html_parts.append(f"<p>{md_inline(line)}</p>")
    return "\n".join(html_parts), contents


def minutes(seconds: float) -> str:
    whole = round(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def hours_minutes(seconds: float) -> str:
    whole = round(seconds / 60)
    return f"{whole // 60} h {whole % 60} min"


def vtt(srt: str) -> str:
    return "WEBVTT\n\n" + re.sub(r"(\d\d:\d\d:\d\d),(\d\d\d)", r"\1.\2", srt.strip()) + "\n"


def page(title: str, description: str, depth: int, body: str) -> str:
    up = "../" * depth or "./"
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
<nav class="top">
  <a class="brand" href="{up}">Agentic Software Engineering</a>
  <span><a href="{up}approach/">Approach</a><a href="{up}syllabus/">Syllabus</a><a href="{up}#schedule">Schedule</a><a href="{up}#videos">Videos</a><a href="{up}course/">Course materials</a><a href="{INSTRUCTOR['homepage']}">Instructor</a></span>
</nav>
{body}
<footer class="foot">
  <p>Videos: English narration in a draft synthetic voice (LJ Speech, public domain), with English and
  Chinese subtitles. Every example in them is course-authored and synthetic.</p>
  <p>Contact: <a href="mailto:{INSTRUCTOR['email']}">{INSTRUCTOR['email']}</a> ·
  <a href="https://github.com/boxi-cs/agentic-se">Source for this site</a> · Boxi CS</p>
</footer>
</body>
</html>
"""


# Links in the course's approach page, as pages of this site (relative to the site root).
APPROACH_LINKS = {
    "week0/setup.en.md": "course/site/docs/week0/setup.en.html",
    "../../SYLLABUS.en.md": "syllabus/",
    "schedule.en.md": "./#schedule",
}


def local_links(source: str, up: str) -> str:
    """Point the approach page's course-relative links at this site; other relative links keep only their text."""
    for old, new in APPROACH_LINKS.items():
        source = source.replace(f"]({old})", f"](site:{up}{new})")
    return source


def sections(source: str) -> tuple[str, list[tuple[str, str]]]:
    """Split Markdown into its text before the first level-2 heading and (title, body) per level-2 section."""
    parts = re.split(r"^## (.+)$", source, flags=re.M)
    intro = "\n".join(line for line in parts[0].strip().splitlines() if not line.startswith("# ")).strip()
    return intro, [(parts[k].strip(), parts[k + 1].strip()) for k in range(1, len(parts), 2)]


def section(source: str, title: str) -> str:
    """The body of one level-2 section (fails loudly if the source changed)."""
    for heading, body in sections(source)[1]:
        if heading == title:
            return body
    raise SystemExit(f"section not found: {title!r}")


def lead(body: str, count: int = 2) -> str:
    """The first sentences of a section's first paragraph."""
    return " ".join(re.split(r"(?<=[.!?])\s+", body.split("\n\n")[0])[:count])


def home(course: dict, episodes: list[dict]) -> str:
    intro, parts = sections(local_links(course["approach"], ""))
    # Principles: the opening two sentences of each short approach section; the stage table, the closing
    # links and the rest of each section stay on the approach page.
    principles = "\n".join(
        f"""    <div class="principle"><h3>{md_inline(title)}</h3><p>{md_inline(lead(body))}</p></div>"""
        for title, body in parts
        if "|" not in body and not body.startswith("- ")
    )
    syllabus = course["syllabus"]["markdown"]
    outcomes = "".join(
        f"<li>{md_inline(line[2:])}</li>" for line in section(syllabus, "Learning outcomes").splitlines() if line.startswith("- ")
    )
    assessment = section(syllabus, "Assessment").split("\n\n")
    table_html = markdown(next(block for block in assessment if block.startswith("|")))[0]
    passing = next(block for block in assessment if block.startswith("Passing requires"))
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
  <p class="tagline">{inline(course['tagline'])}</p>
  <p class="lede">{md_inline(intro)}</p>
  <p class="actions">
    <a class="button primary" href="syllabus/">Read the syllabus</a>
    <a class="button" href="approach/">How this course works</a>
    <a class="button" href="course/">Course materials</a>
  </p>
</header>
<main>
<section id="approach">
  <h2>How this course works</h2>
  <div class="principles">
{principles}
  </div>
  <p><a href="approach/">The full approach, with the four stages of the term →</a></p>
</section>
<section id="syllabus">
  <h2>Syllabus at a glance</h2>
  <div class="glance">
    <div>
      <h3>What you will be able to do</h3>
      <ul class="outcomes">{outcomes}</ul>
    </div>
    <div class="prose">
      <h3>How the work is assessed</h3>
      {table_html}
      <p class="note">{md_inline(passing.split(". ")[0])}.</p>
    </div>
  </div>
  <p><a href="syllabus/">The full syllabus: weekly route, feedback and resits, the project, open-source contributions, workload and AI use →</a></p>
</section>
<section id="schedule">
  <h2>Schedule</h2>
  <table class="schedule">
    <thead><tr><th>Week</th><th>Topic</th><th>Deliverables</th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <!-- Site text: what the labels in the schedule stand for (SYLLABUS.md and the schedule's own wording). -->
  <p class="note">P1–P3: personal practices · M0–M4: project milestones · C1, C2: open-source contributions · CP1, CP2: 30-minute individual checkpoints.</p>
</section>
<section id="videos">
  <h2>Weekly videos</h2>
  <!-- Site text: what the videos are, and their total length. -->
  <p class="note">One short film per week shows that week's central decision through worked examples:
  generate, then verify. {len(episodes)} films, {hours_minutes(total)} in all.</p>
  <div class="cards">
{cards}
  </div>
</section>
<section id="materials">
  <h2>Course materials</h2>
  <!-- Site text: what course/ holds (the course repository's own English student site). -->
  <p>Everything students work from is public: each week's notes, slides, activities, readings and self-check,
  the three personal practices, the project instructions and kit, the rubrics and the course policies.</p>
  <ul class="facts">
    <li><a href="course/">Start here</a></li>
    <li><a href="course/lectures/week-01/notes.en.html">Week 1 notes</a></li>
    <li><a href="course/practice/README.en.html">Personal practices</a></li>
    <li><a href="course/site/docs/project.en.html">Project</a></li>
    <li><a href="course/site/docs/glossary.en.html">Glossary</a></li>
  </ul>
</section>
<section>
  <h2>Teaching team</h2>
  <div class="people">
    <a class="person" href="{INSTRUCTOR['homepage']}">
      <img src="{INSTRUCTOR['photo']}" alt="{esc(INSTRUCTOR['name'])}" width="120" height="120" loading="lazy">
      <span><b>{esc(INSTRUCTOR['name'])}</b><br>{esc(INSTRUCTOR['role'])}<br><span class="note">{esc(INSTRUCTOR['homepage'].removeprefix('https://').rstrip('/'))}</span></span>
    </a>
  </div>
  <p>Questions about the course: <a href="mailto:{INSTRUCTOR['email']}">{INSTRUCTOR['email']}</a></p>
</section>
</main>"""
    return page(course["title"], course["tagline"], 0, body)


def approach_page(course: dict) -> str:
    body_html, contents = markdown(local_links(course["approach"], "../"))
    body = f"""<header class="hero hero-week">
  <p class="kicker"><a href="../">Agentic Software Engineering</a> · Approach</p>
  <h1>How this course works</h1>
  <p class="lede">{inline(course['tagline'])}</p>
</header>
<main class="prose">
{body_html}
</main>"""
    return page(f"Approach · {course['title']}", course["tagline"], 1, body)


CITATION = re.compile(r"\s*\(`[\w./-]*:\d[^)]*\)|\s*\(scenes? \d+(?:[–-]\d+)?\)")


def without_citations(text: str) -> str:
    """Drop the script's source citations and scene pointers, such as (`notes:56-68`) or (scene 15)."""
    return CITATION.sub("", text)


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
    <p>{inline(without_citations(e['decision'][0].upper() + e['decision'][1:]))}</p>
  </section>
  <section>
    <h2>Materials</h2>
    <ul class="facts">
      <li><a href="../../course/lectures/week-{number}/notes.en.html">Notes</a></li>
      <li><a href="../../course/lectures/week-{number}/slides.en.html">Slides</a></li>
      <li><a href="../../course/lectures/week-{number}/activities.en.html">Activities</a></li>
      <li><a href="../../course/lectures/week-{number}/readings.en.html">Readings</a></li>
      <li><a href="../../course/lectures/week-{number}/selfcheck.en.html">Self-check</a></li>
    </ul>
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


def syllabus_page(course: dict) -> str:
    source = course["syllabus"]["markdown"]  # already edited for a public page by tools/export_data.py
    body_html, contents = markdown(source)
    toc = "".join(f'<li><a href="#{anchor}">{esc(title)}</a></li>' for anchor, title in contents)
    body = f"""<header class="hero hero-week">
  <p class="kicker"><a href="../">Agentic Software Engineering</a> · Syllabus</p>
  <h1>Syllabus</h1>
  <p class="meta">Last updated {esc(course['syllabus']['updated'])}</p>
</header>
<main class="prose">
  <nav class="toc"><ul>{toc}</ul></nav>
{body_html}
</main>"""
    return page(f"Syllabus · {course['title']}", "Learning outcomes, schedule, assessment and policies.", 1, body)


def main() -> None:
    course = json.loads((ROOT / "data/course.json").read_text())
    episodes = json.loads((ROOT / "data/episodes.json").read_text())["episodes"]
    (ROOT / "index.html").write_text(home(course, episodes))
    (ROOT / "syllabus").mkdir(exist_ok=True)
    (ROOT / "syllabus/index.html").write_text(syllabus_page(course))
    (ROOT / "approach").mkdir(exist_ok=True)
    (ROOT / "approach/index.html").write_text(approach_page(course))
    for index, e in enumerate(episodes):
        folder = ROOT / "weeks" / f"{e['week']:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(week_page(course, episodes, index))
        for lang, srt in e["subtitles"].items():
            (folder / f"{lang}.vtt").write_text(vtt(srt))
    internal = re.compile(r"PR #\d|\bT-\d{3}\b|\bD\d{2}\b|ASE-\d+|reviewed_by|instructor/|\bnotes:\d")
    pages = [ROOT / "index.html", ROOT / "approach/index.html", ROOT / "syllabus/index.html"]
    for built in [*pages, *sorted(ROOT.glob("weeks/*/index.html"))]:
        if match := internal.search(built.read_text()):
            raise SystemExit(f"{built.relative_to(ROOT)}: internal reference {match.group(0)!r}")
    print(f"built index.html, approach/index.html, syllabus/index.html and {len(episodes)} week pages")


if __name__ == "__main__":
    main()
