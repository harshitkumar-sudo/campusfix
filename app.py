"""CampusFix backend: Flask + SQLite."""
import hmac
import os
import re
import uuid
from functools import wraps

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   send_from_directory, session)

import database as dbm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_EXT = {"png", "jpg", "jpeg"}
TICKET_RE = re.compile(r"^CF-\d+$")
ROLL_RE = re.compile(r"^[A-Z0-9][A-Z0-9_\-/]{2,19}$")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "campusfix-demo-secret-change-me"),
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,  # photo limit is enforced separately at 5MB
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
app.json.sort_keys = False

dbm.init_db()


# ---------------------------------------------------------------- helpers
def get_db():
    if "db" not in g:
        g.db = dbm.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def api_error(message, code):
    return jsonify({"error": message}), code


def current_student():
    """The logged-in student (dict) or None. A stale session (deleted student) counts as logged out."""
    if "student" not in g:
        sid = session.get("student_id")
        g.student = dbm.get_student(get_db(), sid) if sid else None
        if sid and g.student is None:
            session.pop("student_id", None)
    return g.student


def is_admin():
    return bool(session.get("admin"))


@app.context_processor
def inject_user():
    return {"current_student": current_student(), "is_admin": is_admin()}


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return api_error("Authentication required", 401)
        return fn(*args, **kwargs)
    return wrapper


def student_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_student() is None:
            return api_error("Please sign in to continue", 401)
        return fn(*args, **kwargs)
    return wrapper


def user_required(fn):
    """Logged-in student or admin."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_student() is None and not is_admin():
            return api_error("Please sign in to continue", 401)
        return fn(*args, **kwargs)
    return wrapper


def student_page(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_student() is None:
            return redirect("/login")
        return fn(*args, **kwargs)
    return wrapper


def read_photo(file):
    """Validate an uploaded photo. Returns ((bytes, ext), None) or (None, error)."""
    name = file.filename or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXT:
        return None, "Photo must be a PNG or JPG image"
    data = file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        return None, "Photo is too large (max 5MB)"
    if ext == "png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None, "File is not a valid PNG image"
    if ext in ("jpg", "jpeg") and not data.startswith(b"\xff\xd8\xff"):
        return None, "File is not a valid JPG image"
    return (data, "jpg" if ext == "jpeg" else ext), None


# ---------------------------------------------------------------- pages
@app.route("/")
@student_page
def index():
    return render_template("index.html")


@app.route("/report")
@student_page
def report_page():
    return render_template("report.html")


@app.route("/track")
@student_page
def track_page():
    return render_template("track.html")


@app.route("/login")
def student_login_page():
    if current_student():
        return redirect("/")
    return render_template("student_login.html")


@app.route("/register")
def student_register_page():
    if current_student():
        return redirect("/")
    return render_template("student_register.html")


@app.route("/admin/login")
def admin_login_page():
    if is_admin():
        return redirect("/admin")
    return render_template("admin_login.html")


@app.route("/admin")
def admin_page():
    if not is_admin():
        return redirect("/admin/login")
    return render_template("admin_dashboard.html")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    if current_student() is None and not is_admin():
        return api_error("Please sign in to continue", 401)
    return send_from_directory(UPLOAD_DIR, filename)


# ---------------------------------------------------------------- student auth API
@app.route("/api/student/register", methods=["POST"])
def api_student_register():
    data = request.get_json(silent=True) or {}
    name = " ".join(str(data.get("name") or "").split())
    roll_no = str(data.get("roll_no") or "").strip().upper()
    password = str(data.get("password") or "")

    if not 2 <= len(name) <= 60:
        return api_error("Please enter your name (2 to 60 characters)", 400)
    if not ROLL_RE.match(roll_no):
        return api_error("Enter a valid roll number (3 to 20 letters or numbers)", 400)
    if not 6 <= len(password) <= 64:
        return api_error("Password must be 6 to 64 characters", 400)

    student_id = dbm.create_student(get_db(), name, roll_no, password)
    if student_id is None:
        return api_error("This roll number is already registered. Please sign in.", 409)
    session.clear()
    session["student_id"] = student_id
    return jsonify({"ok": True, "student": {"name": name, "roll_no": roll_no}}), 201


@app.route("/api/student/login", methods=["POST"])
def api_student_login():
    data = request.get_json(silent=True) or {}
    roll_no = str(data.get("roll_no") or "").strip().upper()
    password = str(data.get("password") or "")
    student = dbm.authenticate_student(get_db(), roll_no, password)
    if student is None:
        return api_error("Invalid roll number or password", 401)
    session.clear()
    session["student_id"] = student["id"]
    return jsonify({"ok": True, "student": {"name": student["name"], "roll_no": student["roll_no"]}})


@app.route("/api/student/logout", methods=["POST"])
def api_student_logout():
    session.pop("student_id", None)
    return jsonify({"ok": True})


@app.route("/api/student/me")
@student_required
def api_student_me():
    s = current_student()
    return jsonify({"name": s["name"], "roll_no": s["roll_no"]})


# ---------------------------------------------------------------- public-ish API
@app.route("/api/meta")
def api_meta():
    return jsonify({
        "categories": dbm.CATEGORIES,
        "wings": dbm.WINGS,
        "rooms": dbm.ROOMS,
        "statuses": dbm.STATUSES,
        "urgencies": dbm.URGENCIES,
        "staff": dbm.get_staff_names(get_db()),
        "upvote_threshold": dbm.UPVOTE_THRESHOLD,
    })


@app.route("/api/tickets", methods=["POST"])
@student_required
def api_create_ticket():
    form = request.form
    category = (form.get("category") or "").strip()
    wing = (form.get("wing") or "").strip().upper()
    room = (form.get("room") or "").strip()
    description = (form.get("description") or "").strip()

    if category not in dbm.CATEGORIES:
        return api_error("Please choose a valid category", 400)
    if wing not in dbm.WINGS:
        return api_error("Please choose a valid wing", 400)
    if room not in dbm.ROOMS[wing]:
        return api_error("Please choose a valid room for the selected wing", 400)
    if not description:
        return api_error("Problem description is required", 400)
    if len(description) > 1000:
        return api_error("Description is too long (max 1000 characters)", 400)

    photo_filename = None
    file = request.files.get("photo")
    if file and file.filename:
        photo, err = read_photo(file)
        if err:
            return api_error(err, 400)
        data, ext = photo
        photo_filename = f"{uuid.uuid4().hex}.{ext}"
        with open(os.path.join(UPLOAD_DIR, photo_filename), "wb") as f:
            f.write(data)

    try:
        ticket_id = dbm.create_ticket(get_db(), current_student()["id"], category, wing, room,
                                      description, photo_filename)
    except Exception:
        if photo_filename:
            try:
                os.remove(os.path.join(UPLOAD_DIR, photo_filename))
            except OSError:
                pass
        raise
    return jsonify({"ticket_id": ticket_id, "status": "Submitted"}), 201


@app.route("/api/tickets/<ticket_id>")
@user_required
def api_get_ticket(ticket_id):
    ticket_id = ticket_id.strip().upper()
    if not TICKET_RE.match(ticket_id):
        return api_error("Ticket not found", 404)
    student = current_student()
    ticket = dbm.get_ticket(get_db(), ticket_id,
                            viewer=student["id"] if student else None, reporter=is_admin())
    if ticket is None:
        return api_error("Ticket not found", 404)
    return jsonify(ticket)


@app.route("/api/feed")
@student_required
def api_feed():
    sort = request.args.get("sort", "top")
    status = request.args.get("status", "open")
    category = request.args.get("category", "").strip()
    if sort not in ("top", "new"):
        sort = "top"
    if status not in ("open", "resolved", "all"):
        status = "open"
    if category and category not in dbm.CATEGORIES:
        return api_error("Unknown category", 400)
    mine = request.args.get("mine") in ("1", "true")
    tickets = dbm.get_feed(get_db(), current_student()["id"], sort, status, category, mine)
    return jsonify({"tickets": tickets, "threshold": dbm.UPVOTE_THRESHOLD})


@app.route("/api/tickets/<ticket_id>/upvote", methods=["POST", "DELETE"])
@student_required
def api_upvote(ticket_id):
    ticket_id = ticket_id.strip().upper()
    if not TICKET_RE.match(ticket_id):
        return api_error("Ticket not found", 404)
    fn = dbm.add_upvote if request.method == "POST" else dbm.remove_upvote
    result, err, code = fn(get_db(), ticket_id, current_student()["id"])
    if err:
        return api_error(err, code)
    result["threshold"] = dbm.UPVOTE_THRESHOLD
    return jsonify(result)


# ---------------------------------------------------------------- admin API
@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "")
    password = str(data.get("password") or "")
    ok_user = hmac.compare_digest(username.encode(), ADMIN_USER.encode())
    ok_pass = hmac.compare_digest(password.encode(), ADMIN_PASS.encode())
    if not (ok_user and ok_pass):
        return api_error("Invalid username or password", 401)
    session.clear()
    session["admin"] = True
    return jsonify({"ok": True})


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/admin/tickets")
@admin_required
def api_admin_tickets():
    tickets = dbm.list_tickets(
        get_db(),
        status=request.args.get("status", "").strip(),
        urgency=request.args.get("urgency", "").strip(),
        category=request.args.get("category", "").strip(),
        q=request.args.get("q", "").strip(),
    )
    return jsonify({"tickets": tickets})


@app.route("/api/admin/tickets/<ticket_id>", methods=["PATCH"])
@admin_required
def api_admin_update_ticket(ticket_id):
    ticket_id = ticket_id.strip().upper()
    db = get_db()
    if not TICKET_RE.match(ticket_id) or dbm.get_ticket(db, ticket_id) is None:
        return api_error("Ticket not found", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("Request body must be JSON", 400)

    changes = {}
    if "status" in data:
        if data["status"] not in dbm.STATUSES:
            return api_error("Invalid status", 400)
        changes["status"] = data["status"]
    if "urgency" in data:
        if data["urgency"] not in dbm.URGENCIES:
            return api_error("Invalid urgency", 400)
        changes["urgency"] = data["urgency"]
    if "assigned_to" in data:
        value = data["assigned_to"]
        if value in (None, ""):
            changes["assigned_to"] = None
        elif value in dbm.get_staff_names(db):
            changes["assigned_to"] = value
        else:
            return api_error("Unknown staff member", 400)
    note = data.get("note")
    note = note.strip() if isinstance(note, str) else ""
    if len(note) > 500:
        return api_error("Note is too long (max 500 characters)", 400)
    if not changes and not note:
        return api_error("Nothing to update", 400)

    return jsonify(dbm.update_ticket(db, ticket_id, changes, note))


@app.route("/api/admin/stats")
@admin_required
def api_admin_stats():
    return jsonify(dbm.get_stats(get_db()))


# ---------------------------------------------------------------- errors
@app.errorhandler(404)
def handle_404(_e):
    if request.path.startswith("/api/"):
        return api_error("Not found", 404)
    return "<h1>404 - Page not found</h1><p><a href='/'>Back to CampusFix</a></p>", 404


@app.errorhandler(405)
def handle_405(_e):
    return api_error("Method not allowed", 405)


@app.errorhandler(413)
def handle_413(_e):
    return api_error("Upload too large (photo max 5MB)", 413)


@app.errorhandler(500)
def handle_500(_e):
    if request.path.startswith("/api/"):
        return api_error("Internal server error", 500)
    return "<h1>500 - Something went wrong</h1>", 500


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "1") == "1",
    )
