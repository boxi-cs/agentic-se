"""Build the static site from data/ into the repository root (served by GitHub Pages).

    python3 build.py            # writes index.html, approach/, syllabus/, weeks/NN/index.html and films/<slug>/*.vtt

Only the Python standard library is used. Text on the pages comes from data/course.json (the
course's tagline, approach page, calendar and syllabus) and data/episodes.json (the films);
the few sentences written here are labelled "Site text" in the comments. There is one page per
calendar week. data/films.json says which week each film supports and whether it is published;
a film that is not published reaches no page, and its folder under films/ is removed.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE = "https://github.com/boxi-cs/agentic-se/releases/download/videos-2026-10-13"
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
    """Render the syllabus's Markdown subset: headings, paragraphs, bullet and numbered lists, and pipe tables.

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
        elif re.match(r"\d+\. ", first):
            items = "".join(f"<li>{md_inline(line.split('. ', 1)[1])}</li>" for line in lines)
            html_parts.append(f"<ol>{items}</ol>")
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


def page(title: str, description: str, depth: int, body: str, up: str = "") -> str:
    """A page `depth` folders below the site root; `up` replaces the relative way back (the 404 page)."""
    up = up or "../" * depth or "./"
    body = re.sub(r"<main(?=[\s>])", '<main id="main"', body, count=1)  # the skip link's target
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Agentic Software Engineering">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
{FONTS}
<link rel="stylesheet" href="{up}assets/site.css">
<link rel="icon" href="{up}assets/favicon.svg" type="image/svg+xml">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
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


# Links in the course's approach page and syllabus, as pages of this site (relative to the site root).
LOCAL_LINKS = {
    "week0/setup.en.md": "course/site/docs/week0/setup.en.html",  # approach page
    "site/docs/week0/setup.en.md": "course/site/docs/week0/setup.en.html",  # syllabus
    "staff.en.md": "course/site/docs/staff.en.html",
    "../../SYLLABUS.en.md": "syllabus/",
    "schedule.en.md": "./#schedule",
}


def local_links(source: str, up: str) -> str:
    """Point course-relative links at pages of this site; other relative links keep only their text."""
    for old, new in LOCAL_LINKS.items():
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


def labelled(body: str, label: str) -> str:
    """The text of one `- **Label**: text` bullet of a section (fails loudly if the source changed)."""
    for line in body.splitlines():
        if line.startswith(f"- **{label}**: "):
            return line.split("**: ", 1)[1]
    raise SystemExit(f"bullet not found: {label!r}")


def published_films(episodes: list[dict], films: dict) -> list[dict]:
    """The published films, each with the calendar week it supports, in week order.

    data/films.json must name exactly the films of data/episodes.json; a film that is not published
    carries its reason there and reaches no page.
    """
    known = {e["slug"] for e in episodes}
    if known != set(films["films"]):
        raise SystemExit(f"data/films.json and data/episodes.json disagree on: {sorted(known ^ set(films['films']))}")
    out = []
    for e in episodes:
        entry = films["films"][e["slug"]]
        if entry["published"] is not True:
            if entry["published"] is not False or not entry.get("withheld_reason"):
                raise SystemExit(f"data/films.json: {e['slug']} needs published true, or false with a withheld_reason")
            continue
        if not isinstance(entry.get("week"), int):
            raise SystemExit(f"data/films.json: published film {e['slug']} needs a calendar week")
        # An optional plain-language summary replaces the script's decision line on the site.
        out.append({**e, "week": entry["week"], "summary": entry.get("summary", "")})
    return sorted(out, key=lambda film: (film["week"], film["number"]))


def home(course: dict, films: list[dict]) -> str:
    intro, _ = sections(local_links(course["approach"], ""))
    # Principles: the course home's four cards. The calendar, the lines of work and the checkpoints are in
    # the list above them and on the approach page.
    principles = "\n".join(
        f"""    <div class="principle"><h3>{md_inline(card['title'])}</h3><p>{md_inline(card['text'])}</p></div>"""
        for card in course["principles"]
    )
    syllabus = course["syllabus"]["markdown"]
    overview = section(syllabus, "Overview")
    shape = "".join(
        f"<li><strong>{esc(label)}:</strong> {md_inline(labelled(overview, label))}</li>"
        for label in ("Length", "Two sessions a week", "Three lines of work")
    )
    assessment = section(syllabus, "Assessment").split("\n\n")
    table_html = markdown(next(block for block in assessment if block.startswith("|")))[0]
    # The passing rule is the paragraph that names the overall threshold.
    passing = next(block for block in assessment if "60/100" in block and not block.startswith("|"))
    deadline = next(
        (sentence for sentence in re.split(r"(?<=\.)\s+", section(syllabus, "Calendar")) if sentence.startswith("The deadline")), ""
    )
    weeks = {w["week"]: w for w in course["weeks"]}
    total = sum(film["seconds"] for film in films)
    cards = "\n".join(
        f"""  <a class="card" href="weeks/{film['week']:02d}/#film-{film['slug']}">
    <img src="films/{film['slug']}/poster.jpg" alt="" loading="lazy" width="960" height="540">
    <span class="card-week">Week {film['week']} · {minutes(film['seconds'])}</span>
    <span class="card-title">{esc(film['title'])}</span>
    <span class="card-topic">{esc(weeks[film['week']]['topic'])}</span>
  </a>"""
        for film in films
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
  <ul class="shape">{shape}</ul>
  <div class="principles">
{principles}
  </div>
  <!-- Site text: what the approach page adds. -->
  <p><a href="approach/">The full approach: the three lines of work, the checkpoints and the defense →</a></p>
</section>
<section id="syllabus">
  <h2>How the work is assessed</h2>
  <div class="prose">
    {table_html}
    <p class="note">{md_inline(passing.split(". ")[0])}.</p>
  </div>
  <!-- Site text: what the syllabus page holds (its section headings). -->
  <p><a href="syllabus/">The full syllabus: learning outcomes, the calendar, assessment and resits, the assignments, the term project, open-source contributions, tools and AI use →</a></p>
</section>
<section id="schedule">
  <h2>Schedule</h2>
  <table class="schedule">
    <thead><tr><th>Week</th><th>Topic</th><th>Due</th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <!-- Site text: what the labels in the schedule stand for (the syllabus's assessment table); the deadline sentence is the syllabus's. -->
  <p class="note">A1–A6: assignments · Contribution 1–4: open-source contributions · CP1, CP2: 30-minute checkpoints on paper, without AI. {md_inline(deadline)}</p>
</section>
<section id="videos">
  <h2>Videos</h2>
  <!-- Site text: what the films are, how they attach to weeks, and their count and total length. -->
  <p class="note">Short films, each showing one decision through worked examples: generate, then verify.
  Each is made for one teaching week and is listed under it. {len(films)} films, {hours_minutes(total)} in all.</p>
  <div class="cards">
{cards}
  </div>
</section>
<section id="materials">
  <h2>Course materials</h2>
  <!-- Site text: what course/ holds (the course repository's own English student site). -->
  <p>Everything students work from is public: each week's notes, slides, activities, readings and self-check,
  the assignments, the term project, the rubrics and the assessment policy.</p>
  <ul class="facts">
    <li><a href="course/">Start here</a></li>
    <li><a href="course/lectures/week-01/notes.en.html">Week 1 notes</a></li>
    <li><a href="course/practice/README.en.html">Assignments</a></li>
    <li><a href="course/site/docs/project.en.html">Term project</a></li>
    <li><a href="course/site/docs/contributions-rubric.en.html">Contributions rubric</a></li>
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


# The course's link labels that read as build terms on a student page.
MATERIAL_LABELS = {"Slide source": "Slides (text)", "Answer guidance": "Self-check answers"}


def course_materials(week: int) -> tuple[str, list[tuple[str, str]]]:
    """The course's own overview page for a week and the lecture pages it links to, as site-root paths.

    Read from the rebuilt course/, so only pages that exist are linked (the assessment week has no lecture).
    """
    overview = ROOT / f"course/site/docs/weeks/week-{week:02d}.en.html"
    if not overview.is_file():
        raise SystemExit(f"{overview.relative_to(ROOT)} is missing; rebuild course/ with tools/course_site.py")
    article = re.search(r"<article[^>]*>(.*?)</article>", overview.read_text(), re.S)
    links = []
    for href, label in re.findall(r'<a href="([^"#]+)">([^<]+)</a>', article.group(1) if article else ""):
        target = (overview.parent / href).resolve()
        if "/lectures/" in href and target.is_file():
            links.append((target.relative_to(ROOT).as_posix(), label))
    return overview.relative_to(ROOT).as_posix(), links


def film_block(film: dict, note: str) -> str:
    asset = f"../../films/{film['slug']}"
    video = f"{RELEASE}/week-{film['number']:02d}.mp4"  # release assets are named by the first two digits of the slug
    aside = f'\n      <p class="note edition">{esc(note)}</p>' if note else ""  # data/films.json may carry an edition_note
    return f"""    <article class="film" id="film-{film['slug']}">
      <h3>{esc(film['title'])}</h3>{aside}
      <video controls preload="metadata" poster="{asset}/poster.jpg" src="{video}">
        <track kind="subtitles" srclang="en" label="English" src="{asset}/en.vtt" default>
        <track kind="subtitles" srclang="zh" label="中文" src="{asset}/zh.vtt">
      </video>
      <p class="meta">{minutes(film['seconds'])} · subtitles: <a href="{asset}/en.vtt">English</a>, <a href="{asset}/zh.vtt" lang="zh" hreflang="zh">中文</a> ·
      <a href="{video}">download</a></p>
      <p>{inline(film['summary'] or without_citations(film['decision'][0].upper() + film['decision'][1:]))}</p>
    </article>"""


def week_page(course: dict, films: list[dict], note: str, w: dict) -> str:
    last = course["weeks"][-1]["week"]
    # This page is the week's overview, so the course's own overview page is not linked again. Notes lead.
    _, lecture_pages = course_materials(w["week"])
    lecture_pages.sort(key=lambda page: page[1] != "Notes")
    lead = ' class="lead"'
    materials = "".join(
        f'\n      <li{lead if label == "Notes" else ""}><a href="../../{path}">{MATERIAL_LABELS.get(label, label)}</a></li>'
        for path, label in lecture_pages
    )
    here = [film for film in films if film["week"] == w["week"]]
    film_section = (
        f"""
  <section>
    <h2>{'Films' if len(here) > 1 else 'Film'}</h2>
{chr(10).join(film_block(film, note) for film in here)}
  </section>"""
        if here
        else ""
    )
    prev_link = f'<a href="../{w["week"] - 1:02d}/">← Week {w["week"] - 1}</a>' if w["week"] > 1 else "<span></span>"
    next_link = f'<a href="../{w["week"] + 1:02d}/">Week {w["week"] + 1} →</a>' if w["week"] < last else "<span></span>"
    body = f"""<header class="hero hero-week">
  <p class="kicker"><a href="../../">Agentic Software Engineering</a> · Week {w['week']}</p>
  <h1>{esc(w['topic'])}</h1>
</header>
<main>
  <section>
    <h2>This week</h2>
    <dl class="week">
      <dt>First session (lecture)</dt><dd>{inline(w['lecture'])}</dd>
      <dt>Second session</dt><dd>{inline(w['workshop'])}</dd>
      <dt>Due</dt><dd>{inline(w['deliverables'])}</dd>
    </dl>
  </section>
  <section>
    <h2>Materials</h2>
    {'<ul class="facts">' + materials + chr(10) + '    </ul>' if materials else '<p>The assessment week has no lecture materials.</p>'}
  </section>{film_section}
  <nav class="pager">{prev_link}<a href="../../#schedule">All weeks</a>{next_link}</nav>
</main>"""
    return page(f"Week {w['week']}: {w['topic']} · Agentic Software Engineering", w["lecture"], 2, body)


def syllabus_page(course: dict) -> str:
    source = course["syllabus"]["markdown"]  # already edited for a public page by tools/export_data.py
    body_html, contents = markdown(local_links(source, "../"))
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


# Where GitHub Pages serves the site. The 404 pages are shown at any depth, so they link from here.
BASE = "/agentic-se/"


def not_found() -> str:
    body = f"""<header class="hero hero-week">
  <p class="kicker">404</p>
  <h1>Page not found</h1>
</header>
<main>
  <p class="lede">There is no page at this address.</p>
  <p class="actions">
    <a class="button primary" href="{BASE}">Course home</a>
    <a class="button" href="{BASE}#schedule">Schedule</a>
    <a class="button" href="{BASE}course/">Course materials</a>
  </p>
</main>"""
    return page("Page not found · Agentic Software Engineering", "This page does not exist.", 0, body, up=BASE)


def check_local_links(pages: list[Path]) -> None:
    """Every local href, src and poster on a built page must resolve to a file inside the site, or a folder
    with an index. On the site's own pages (not course/) a link's "#id" must also exist on the page it
    opens, this page included (the skip link's #main)."""
    for built in pages:
        text = built.read_text()
        own = built.relative_to(ROOT).parts[0] != "course"
        for url in re.findall(r'(?:href|src|poster)="([^"]+)"', text):
            path, _, fragment = html.unescape(url).partition("#")
            path = path.split("?")[0]
            if re.match(r"[a-z]+:", path):
                continue
            if not path:
                target = built
            elif path.startswith(BASE):
                target = (ROOT / path.removeprefix(BASE)).resolve()
            else:
                target = (built.parent / path).resolve()
            if not target.is_relative_to(ROOT.resolve()):
                raise SystemExit(f"{built.relative_to(ROOT)}: link {url!r} leaves the site")
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                raise SystemExit(f"{built.relative_to(ROOT)}: broken link {url!r}")
            if own and fragment and target.suffix == ".html" and f'id="{fragment}"' not in target.read_text():
                raise SystemExit(f"{built.relative_to(ROOT)}: link {url!r} has no target on the page it opens")


def main() -> None:
    course = json.loads((ROOT / "data/course.json").read_text())
    # course/ and data/course.json must come from the same course commit (a --ref preview can mix them).
    built_from = (ROOT / "course/SOURCE").read_text().split()[-1]
    if built_from != course["source"]["commit"]:
        raise SystemExit(f"course/ is built from {built_from[:7]} but data/course.json from "
                         f"{course['source']['commit'][:7]}: run both tools at the same --ref")
    episodes = json.loads((ROOT / "data/episodes.json").read_text())["episodes"]
    mapping = json.loads((ROOT / "data/films.json").read_text())
    films = published_films(episodes, mapping)
    numbers = [w["week"] for w in course["weeks"]]
    if stray := sorted({film["week"] for film in films} - set(numbers)):
        raise SystemExit(f"data/films.json maps a film to a week that is not in the calendar: {stray}")

    # films/ holds only the published films: poster (tools/posters.py) and subtitle tracks (written here).
    (ROOT / "films").mkdir(exist_ok=True)
    for folder in (ROOT / "films").iterdir():
        if folder.name not in {film["slug"] for film in films}:
            shutil.rmtree(folder)
    for film in films:
        folder = ROOT / "films" / film["slug"]
        if not (folder / "poster.jpg").is_file():
            raise SystemExit(f"films/{film['slug']}/poster.jpg is missing; run tools/posters.py")
        for lang, srt in film["subtitles"].items():
            (folder / f"{lang}.vtt").write_text(vtt(srt))

    # weeks/ holds one index.html per calendar week and nothing else.
    for folder in (ROOT / "weeks").iterdir():
        if folder.name not in {f"{n:02d}" for n in numbers}:
            shutil.rmtree(folder)
    for w in course["weeks"]:
        folder = ROOT / "weeks" / f"{w['week']:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        for stale in folder.iterdir():
            if stale.name != "index.html":
                stale.unlink()
        (folder / "index.html").write_text(week_page(course, films, mapping.get("edition_note", ""), w))
    (ROOT / "index.html").write_text(home(course, films))
    (ROOT / "syllabus").mkdir(exist_ok=True)
    (ROOT / "syllabus/index.html").write_text(syllabus_page(course))
    (ROOT / "approach").mkdir(exist_ok=True)
    (ROOT / "approach/index.html").write_text(approach_page(course))
    # GitHub Pages shows the root 404.html for every missing path, course/ included.
    (ROOT / "404.html").write_text(not_found())

    internal = re.compile(r"PR #\d|\bT-\d{3}\b|\bD\d{2}\b|ASE-\d+|reviewed_by|instructor/|\bnotes:\d")
    withheld = [e["slug"] for e in episodes if e["slug"] not in {film["slug"] for film in films}]
    pages = [ROOT / "index.html", ROOT / "approach/index.html", ROOT / "syllabus/index.html", *sorted(ROOT.glob("weeks/*/index.html"))]
    for built in pages:
        text = built.read_text()
        if match := internal.search(text):
            raise SystemExit(f"{built.relative_to(ROOT)}: internal reference {match.group(0)!r}")
        if named := [slug for slug in withheld if slug in text]:
            raise SystemExit(f"{built.relative_to(ROOT)}: names a film that is not published: {named}")
    # The pages written here, and the course's own pages under course/ as they were copied in.
    check_local_links([*pages, ROOT / "404.html", *sorted((ROOT / "course").rglob("*.html"))])
    print(
        f"built index.html, 404.html, approach/index.html, syllabus/index.html, {len(numbers)} week pages (weeks/{numbers[0]:02d}–{numbers[-1]:02d}) "
        f"and subtitle tracks for {len(films)} published films ({len(withheld)} withheld)"
    )


if __name__ == "__main__":
    main()
