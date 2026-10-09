"""Synchronous SQLite domain storage with explicit ownership checks."""

import json
import sqlite3

from legacy_app.db import get_db
from werkzeug.security import generate_password_hash

from .metrics import retry_merge
from .synthetic import generate
from .validation import build

MIGRATIONS = (
    """
CREATE TABLE ci_dashboard_projects (
 id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
 title TEXT NOT NULL, description TEXT NOT NULL,
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))
);
CREATE TABLE ci_dashboard_pipelines (
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES ci_dashboard_projects(id),
 title TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
CREATE TABLE ci_dashboard_builds (
 id INTEGER PRIMARY KEY, pipeline_id INTEGER NOT NULL REFERENCES ci_dashboard_pipelines(id),
 external_id TEXT NOT NULL, branch TEXT NOT NULL, status TEXT NOT NULL,
 started_at TEXT NOT NULL, duration_ms INTEGER NOT NULL, attempt INTEGER NOT NULL,
 message TEXT NOT NULL, UNIQUE(pipeline_id,external_id)
);
CREATE TABLE ci_dashboard_rules (
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES ci_dashboard_projects(id),
 threshold INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
 target TEXT NOT NULL CHECK(target='fixture')
);
CREATE TABLE ci_dashboard_notifications (
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES ci_dashboard_projects(id),
 message TEXT NOT NULL, signature TEXT NOT NULL
);
CREATE TABLE ci_dashboard_imports (
 id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
 record_count INTEGER NOT NULL, source TEXT NOT NULL CHECK(source='fixture')
);
""",
)


def insert_build(db: sqlite3.Connection, row: dict) -> None:
    """Insert validated data using only bound parameters."""
    db.execute(
        "INSERT INTO ci_dashboard_builds(pipeline_id,external_id,branch,"
        "status,started_at,duration_ms,attempt,message) VALUES(?,?,?,?,?,?,?,?)",
        tuple(
            row[k]
            for k in (
                "pipeline_id",
                "external_id",
                "branch",
                "status",
                "started_at",
                "duration_ms",
                "attempt",
                "message",
            )
        ),
    )


def load_fixture(db: sqlite3.Connection) -> None:
    """Idempotently load two synthetic accounts and sample records."""
    db.execute(
        "INSERT OR IGNORE INTO users VALUES(2,?,?,?)",
        ("fixture_peer", generate_password_hash("CHANGEME"), "Synthetic peer"),
    )
    for row in (
        (1, 1, "Widget checks", "Synthetic compiler and test results"),
        (2, 2, "Peer private project", "Synthetic access-boundary example"),
    ):
        db.execute(
            "INSERT OR IGNORE INTO ci_dashboard_projects(id,owner_id,tit"
            "le,description) VALUES(?,?,?,?)",
            row,
        )
    for row in ((1, 1, "Main validation"), (2, 1, "Documentation"), (3, 2, "Peer pipeline")):
        db.execute(
            "INSERT OR IGNORE INTO ci_dashboard_pipelines(id,project_id,title) VALUES(?,?,?)", row
        )
    db.execute("INSERT OR IGNORE INTO ci_dashboard_rules VALUES(1,1,2,1,'fixture')")
    if not db.execute("SELECT 1 FROM ci_dashboard_builds").fetchone():
        for row in generate(7)["builds"]:
            insert_build(db, row)


def owned_project(owner: int, project_id: int) -> dict:
    """Protect mutation routes independently from report detail policy."""
    row = (
        get_db()
        .execute(
            "SELECT * FROM ci_dashboard_projects WHERE id=? AND owner_id=?", (project_id, owner)
        )
        .fetchone()
    )
    if row is None:
        raise LookupError("Project not found")
    return dict(row)


def owned_pipeline(owner: int, pipeline_id: int) -> dict:
    """Resolve a pipeline through its owning project."""
    row = (
        get_db()
        .execute(
            "SELECT p.* FROM ci_dashboard_pipelines p JOIN ci_dashboard_"
            "projects x ON x.id=p.project_id WHERE p.id=? AND x.owner_id=?",
            (pipeline_id, owner),
        )
        .fetchone()
    )
    if row is None:
        raise LookupError("Pipeline not found")
    return dict(row)


def builds(owner: int, project_id: int) -> list[dict]:
    """List only owned build data in stable internal import order."""
    owned_project(owner, project_id)
    return [
        dict(row)
        for row in get_db().execute(
            "SELECT b.* FROM ci_dashboard_builds b JOIN ci_dashboard_pip"
            "elines p ON b.pipeline_id=p.id WHERE p.project_id=? ORDER BY b.id",
            (project_id,),
        )
    ]


def import_records(owner: int, payload: dict) -> dict:
    """Validate all rows first, then merge retries in a single transaction."""
    if set(payload) != {"target", "builds"} or payload["target"] != "fixture":
        raise ValueError("Only synthetic fixture imports are supported")
    if not isinstance(payload["builds"], list) or not 1 <= len(payload["builds"]) <= 30:
        raise ValueError("Expected 1 to 30 builds")
    incoming = [build(row) for row in payload["builds"]]
    for row in incoming:
        owned_pipeline(owner, row["pipeline_id"])
    db = get_db()
    keys = sorted({(row["pipeline_id"], row["external_id"]) for row in incoming})
    previous = []
    for pipeline_id, external_id in keys:
        old = db.execute(
            "SELECT * FROM ci_dashboard_builds WHERE pipeline_id=? AND external_id=?",
            (pipeline_id, external_id),
        ).fetchone()
        if old is not None:
            previous.append(dict(old))
    merged = retry_merge.calculate(previous + incoming)
    with db:
        for pipeline_id, external_id in keys:
            db.execute(
                "DELETE FROM ci_dashboard_builds WHERE pipeline_id=? AND external_id=?",
                (pipeline_id, external_id),
            )
        for row in merged:
            insert_build(db, row)
        db.execute(
            "INSERT INTO ci_dashboard_imports(owner_id,record_count,source) VALUES(?,?,'fixture')",
            (owner, len(incoming)),
        )
    return {"imported": len(incoming)}


def export_records(owner: int, project_id: int) -> str:
    """Return portable JSON without opening a user-named output file."""
    rows = builds(owner, project_id)
    for row in rows:
        row.pop("id", None)
    return json.dumps({"target": "fixture", "builds": rows}, sort_keys=True, indent=2)
