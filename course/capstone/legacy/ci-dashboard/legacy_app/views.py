"""Server-rendered authentication, profile, CRUD, and literal substring search."""

import secrets
import sqlite3

from flask import (
    Blueprint,
    Response,
    abort,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("core", __name__)


@bp.before_app_request
def load_user_and_check_csrf() -> None:
    """Load identity from the database and require a session-bound token on every POST."""
    g.user = (
        get_db().execute("SELECT * FROM users WHERE id=?", (session.get("user_id"),)).fetchone()
    )
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(24)
    if request.method == "POST" and not secrets.compare_digest(
        session["csrf"].encode(), request.form.get("csrf", "").encode()
    ):
        abort(400)


@bp.after_app_request
def security_headers(response: Response) -> Response:
    """Keep the template UI local and disable active inline content."""
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'none'; style-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


def require_user() -> int:
    """Require an authenticated user for data and profile operations."""
    if g.user is None:
        abort(401)
    return g.user["id"]


def form_text(name: str, maximum: int) -> str:
    """Validate bounded, nonempty text without reflecting error inputs."""
    value = request.form.get(name, "").strip()
    if not value or len(value) > maximum:
        abort(400)
    return value


@bp.route("/")
def index() -> Response:
    """Choose a local landing route without accepting redirect targets."""
    return redirect(url_for("core.items" if g.user is not None else "core.login"))


@bp.route("/login", methods=["GET", "POST"])
def login() -> str | Response:
    """Authenticate an existing local account and rotate session state."""
    if request.method == "POST":
        user = (
            get_db()
            .execute("SELECT * FROM users WHERE username=?", (form_text("username", 80),))
            .fetchone()
        )
        if user is None or not check_password_hash(
            user["password_hash"], form_text("password", 256)
        ):
            abort(401)
        session.clear()
        session["user_id"] = user["id"]
        session["csrf"] = secrets.token_hex(24)
        return redirect(url_for("core.items"))
    return render_template("login.html")


@bp.route("/register", methods=["GET", "POST"])
def register() -> str | Response:
    """Create a local account; duplicate usernames are a conflict."""
    if request.method == "POST":
        username = form_text("username", 80)
        password = form_text("password", 256)
        if len(password) < 8:
            abort(400)
        try:
            db = get_db()
            with db:
                db.execute(
                    "INSERT INTO users(username, password_hash, display_name) VALUES(?,?,?)",
                    (username, generate_password_hash(password), username),
                )
        except sqlite3.IntegrityError:
            abort(409)
        return redirect(url_for("core.login"))
    return render_template("login.html", registering=True)


@bp.post("/logout")
def logout() -> Response:
    """Clear identity only after CSRF validation."""
    session.clear()
    return redirect(url_for("core.login"))


@bp.route("/profile", methods=["GET", "POST"])
def profile() -> str | Response:
    """View and update the authenticated user's display name."""
    user_id = require_user()
    if request.method == "POST":
        value = form_text("display_name", 80)
        db = get_db()
        with db:
            db.execute("UPDATE users SET display_name=? WHERE id=?", (value, user_id))
        return redirect(url_for("core.profile"))
    return render_template("profile.html")


@bp.get("/items")
def items() -> str:
    """List only the caller's records, searching literal text through bound parameters."""
    user_id = require_user()
    query = request.args.get("q", "")
    if len(query) > 120:
        abort(400)
    rows = (
        get_db()
        .execute(
            "SELECT * FROM items WHERE owner_id=? "
            "AND (instr(title,?)>0 OR instr(body,?)>0) ORDER BY id",
            (user_id, query, query),
        )
        .fetchall()
    )
    return render_template("items.html", items=rows, query=query)


def owned_item(item_id: int) -> sqlite3.Row:
    """Use the same ownership predicate for detail, edit, and delete."""
    row = (
        get_db()
        .execute("SELECT * FROM items WHERE id=? AND owner_id=?", (item_id, require_user()))
        .fetchone()
    )
    if row is None:
        abort(404)
    return row


@bp.get("/items/<int:item_id>")
def detail(item_id: int) -> str:
    """Render one owned record."""
    return render_template("detail.html", item=owned_item(item_id))


@bp.route("/items/new", methods=["GET", "POST"])
def new_item() -> str | Response:
    """Create a record owned by the authenticated user."""
    user_id = require_user()
    if request.method == "POST":
        title, body = form_text("title", 120), form_text("body", 4000)
        db = get_db()
        with db:
            cursor = db.execute(
                "INSERT INTO items(owner_id,title,body) VALUES(?,?,?)", (user_id, title, body)
            )
        return redirect(url_for("core.detail", item_id=cursor.lastrowid))
    return render_template("form.html", item=None)


@bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(item_id: int) -> str | Response:
    """Update an owned record."""
    row = owned_item(item_id)
    if request.method == "POST":
        title, body = form_text("title", 120), form_text("body", 4000)
        db = get_db()
        with db:
            db.execute("UPDATE items SET title=?, body=? WHERE id=?", (title, body, item_id))
        return redirect(url_for("core.detail", item_id=item_id))
    return render_template("form.html", item=row)


@bp.post("/items/<int:item_id>/delete")
def delete_item(item_id: int) -> Response:
    """Delete an owned record after CSRF validation."""
    owned_item(item_id)
    db = get_db()
    with db:
        db.execute("DELETE FROM items WHERE id=?", (item_id,))
    return redirect(url_for("core.items"))
