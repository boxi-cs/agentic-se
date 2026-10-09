"""Server-rendered CI dashboard with synthetic imports and local reports."""

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request, url_for
from legacy_app.db import get_db
from legacy_app.extensions import Domain
from legacy_app.views import form_text, require_user

from . import model, reports
from .inspection import TRIAGE_MIGRATION, register_routes
from .synthetic import generate
from .validation import document, integer, text

bp = Blueprint("ci_dashboard", __name__)


@bp.errorhandler(ValueError)
def invalid_input(error: ValueError) -> tuple[Response, int]:
    """Never echo imported data or exception internals."""
    return jsonify({"error": "Invalid synthetic input"}), 400


@bp.errorhandler(LookupError)
def missing_record(error: LookupError) -> tuple[Response, int]:
    """Conceal whether an inaccessible identifier exists."""
    return jsonify({"error": "Record not found"}), 404


@bp.get("/")
def overview() -> str:
    """List the caller's projects in stable order."""
    projects = (
        get_db()
        .execute(
            "SELECT * FROM ci_dashboard_projects WHERE owner_id=? ORDER BY id", (require_user(),)
        )
        .fetchall()
    )
    return render_template("ci/overview.html", projects=projects)


@bp.route("/projects/new", methods=["GET", "POST"])
def new_project() -> str | Response:
    """Create an account-owned project through a CSRF-protected form."""
    owner = require_user()
    if request.method == "POST":
        db = get_db()
        with db:
            cursor = db.execute(
                "INSERT INTO ci_dashboard_projects(owner_id,title,description) VALUES(?,?,?)",
                (owner, form_text("title", 120), form_text("description", 1000)),
            )
        return redirect(url_for("ci_dashboard.project", project_id=cursor.lastrowid))
    return render_template("ci/project_form.html", project=None)


@bp.get("/projects/<int:project_id>")
def project(project_id: int) -> str:
    """Render owned records, pipeline controls and table-backed charts."""
    owner = require_user()
    record = model.owned_project(owner, project_id)
    pipelines = (
        get_db()
        .execute(
            "SELECT * FROM ci_dashboard_pipelines WHERE project_id=? ORDER BY id", (project_id,)
        )
        .fetchall()
    )
    summary = {
        name: reports.report(owner, name, {"project_id": project_id})
        for name in ("success_rate", "daily", "cluster", "latest", "duration", "failure_streak")
    }
    return render_template(
        "ci/project.html",
        project=record,
        pipelines=pipelines,
        builds=model.builds(owner, project_id),
        summary=summary,
    )


@bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
def edit_project(project_id: int) -> str | Response:
    """Edit descriptive fields without accepting a replacement owner."""
    record = model.owned_project(require_user(), project_id)
    if request.method == "POST":
        db = get_db()
        with db:
            db.execute(
                "UPDATE ci_dashboard_projects SET title=?,description=? WHERE id=?",
                (form_text("title", 120), form_text("description", 1000), project_id),
            )
        return redirect(url_for("ci_dashboard.project", project_id=project_id))
    return render_template("ci/project_form.html", project=record)


@bp.post("/projects/<int:project_id>/archive")
def archive_project(project_id: int) -> Response:
    """Toggle display state while retaining historical data."""
    record = model.owned_project(require_user(), project_id)
    db = get_db()
    with db:
        db.execute(
            "UPDATE ci_dashboard_projects SET archived=? WHERE id=?",
            (1 - record["archived"], project_id),
        )
    return redirect(url_for("ci_dashboard.overview"))


@bp.route("/projects/<int:project_id>/pipelines/new", methods=["GET", "POST"])
def new_pipeline(project_id: int) -> str | Response:
    """Create a pipeline without executable commands or external targets."""
    record = model.owned_project(require_user(), project_id)
    if request.method == "POST":
        db = get_db()
        with db:
            db.execute(
                "INSERT INTO ci_dashboard_pipelines(project_id,title) VALUES(?,?)",
                (project_id, form_text("title", 120)),
            )
        return redirect(url_for("ci_dashboard.project", project_id=project_id))
    return render_template("ci/pipeline_form.html", project=record)


@bp.post("/pipelines/<int:pipeline_id>/toggle")
def toggle_pipeline(pipeline_id: int) -> Response:
    """Change a local pipeline flag without starting a build process."""
    pipeline = model.owned_pipeline(require_user(), pipeline_id)
    db = get_db()
    with db:
        db.execute(
            "UPDATE ci_dashboard_pipelines SET enabled=? WHERE id=?",
            (1 - pipeline["enabled"], pipeline_id),
        )
    return redirect(url_for("ci_dashboard.project", project_id=pipeline["project_id"]))


@bp.route("/import", methods=["GET", "POST"])
def import_builds() -> str | Response:
    """Import pasted fixture JSON without opening a supplied filename or URL."""
    owner = require_user()
    if request.method == "POST":
        return jsonify(model.import_records(owner, document(request.form.get("payload", ""))))
    return render_template("ci/import.html")


@bp.get("/sample")
def sample() -> Response:
    """Generate deterministic sample data for an owned pipeline."""
    owner = require_user()
    try:
        seed = int(request.args.get("seed", "7"))
        count = int(request.args.get("count", "12"))
        pipeline_id = int(request.args.get("pipeline_id", "1"))
    except ValueError:
        abort(400)
    model.owned_pipeline(owner, pipeline_id)
    return jsonify(generate(seed, count, pipeline_id))


@bp.get("/projects/<int:project_id>/export")
def export(project_id: int) -> Response:
    """Download JSON using a fixed response filename; do not write a host path."""
    return Response(
        model.export_records(require_user(), project_id),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=synthetic-builds.json"},
    )


@bp.route("/projects/<int:project_id>/rules", methods=["GET", "POST"])
def rules(project_id: int) -> str | Response:
    """Manage fixture notification rules with integer thresholds."""
    record = model.owned_project(require_user(), project_id)
    db = get_db()
    if request.method == "POST":
        payload = document(request.form.get("payload", ""))
        if set(payload) != {"threshold", "target"} or payload["target"] != "fixture":
            raise ValueError("Unsupported target")
        value = integer(payload["threshold"], 1, 100)
        with db:
            db.execute(
                "INSERT INTO ci_dashboard_rules(project_id,threshold,target) VALUES(?,?,'fixture')",
                (project_id, value),
            )
        return redirect(url_for("ci_dashboard.rules", project_id=project_id))
    records = db.execute(
        "SELECT * FROM ci_dashboard_rules WHERE project_id=? ORDER BY id", (project_id,)
    ).fetchall()
    sent = db.execute(
        "SELECT * FROM ci_dashboard_notifications WHERE project_id=? ORDER BY id", (project_id,)
    ).fetchall()
    return render_template("ci/rules.html", project=record, rules=records, notifications=sent)


@bp.post("/projects/<int:project_id>/notify")
def notify(project_id: int) -> Response:
    """Evaluate rules and record only synthetic notification receipts."""
    owner = require_user()
    if request.form.get("target") != "fixture":
        raise ValueError("Unsupported target")
    return jsonify(reports.notify(owner, project_id))


@bp.post("/report/<operation>")
def report(operation: str) -> Response:
    """Expose report calculations through the same authenticated application."""
    return jsonify(
        reports.report(
            require_user(), text(operation, 40), document(request.form.get("payload", ""))
        )
    )


register_routes(bp)
domain = Domain("ci_dashboard", bp, model.MIGRATIONS + (TRIAGE_MIGRATION,), model.load_fixture)
