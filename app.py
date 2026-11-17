"""CampusFix backend: Flask + SQLite. Roles: student, staff, admin."""
import csv
import hmac
import io
import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import (Flask, Response, g, jsonify, redirect, render_template, request,
                   send_from_directory, session)

import database as dbm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_EXT = {"png", "jpg", "jpeg"}
TICKET_RE = re.compile(r"^CF-\d+$")
ROLL_RE = re.compile(r"^[A-Z0-9][A-Z0-9_\-/]{2,19}$")
LOGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@\-]{2,59}$")
MAX_CHAT_LEN = 300

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "campusfix-demo-secret-change-me"),
    MAX_CONTENT_LENGTH=7 * 1024 * 1024,  # photo limit (5MB) is enforced separately
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


# ---- who is logged in (one role per browser session) ----
def current_student():
    if "student" not in g:
        sid = session.get("student_id")
        g.student = dbm.get_student(get_db(), sid) if sid else None
        if sid and g.student is None:
            session.pop("student_id", None)
    return g.student


def current_staff():
    """The logged-in staff member, or None. A removed staff member is logged out automatically."""
    if "staff" not in g:
        sid = session.get("staff_id")
        g.staff = dbm.get_staff_member(get_db(), sid) if sid else None
        if sid and g.staff is None:
            session.pop("staff_id", None)
    return g.staff


def is_admin():
    return bool(session.get("admin"))


def current_role():
    if is_admin():
        return "admin"
    if current_staff():
        return "staff"
    if current_student():
        return "student"
    return None


def current_user_name():
    role = current_role()
    if role == "admin":
        return "Admin"
    if role == "staff":
        return current_staff()["name"]
    if role == "student":
        return current_student()["name"]
    return None


@app.context_processor
def inject_user():
    return {
        "current_student": current_student(),
        "current_staff": current_staff(),
        "is_admin": is_admin(),
        "role": current_role(),
        "user_name": current_user_name(),
    }


# ---- access decorators ----
def _api_guard(allowed):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if current_role() not in allowed:
                return api_error("Please sign in to continue", 401)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


student_required = _api_guard({"student"})
staff_required = _api_guard({"staff"})
admin_required = _api_guard({"admin"})
user_required = _api_guard({"student", "staff", "admin"})


def page_guard(allowed, redirect_to):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if current_role() not in allowed:
                return redirect(redirect_to)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---- photos ----
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


def save_photo(data, ext):
    filename = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        f.write(data)
    return filename


def remove_upload(filename):
    if filename:
        try:
            os.remove(os.path.join(UPLOAD_DIR, filename))
        except OSError:
            pass


# ---------------------------------------------------------------- pages
@app.route("/")
def index():
    if current_role() is None:
        return render_template("landing.html")
    return render_template("index.html")


@app.route("/report")
@page_guard({"student"}, "/")
def report_page():
    return render_template("report.html")


@app.route("/track")
@page_guard({"student", "staff", "admin"}, "/")
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


@app.route("/staff/login")
def staff_login_page():
    if current_staff():
        return redirect("/staff/dashboard")
    return render_template("staff_login.html")


@app.route("/staff/dashboard")
@page_guard({"staff"}, "/staff/login")
def staff_dashboard_page():
    return render_template("staff_dashboard.html")


@app.route("/admin/login")
def admin_login_page():
    if is_admin():
        return redirect("/admin")
    return render_template("admin_login.html")


@app.route("/admin")
@page_guard({"admin"}, "/admin/login")
def admin_page():
    return render_template("admin_dashboard.html")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    if current_role() is None:
        return api_error("Please sign in to continue", 401)
    return send_from_directory(UPLOAD_DIR, filename)


# ---------------------------------------------------------------- sessions
@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- student auth
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
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/student/me")
@student_required
def api_student_me():
    s = current_student()
    return jsonify({"name": s["name"], "roll_no": s["roll_no"]})


# ---------------------------------------------------------------- staff auth + workflow
@app.route("/api/staff/login", methods=["POST"])
def api_staff_login():
    data = request.get_json(silent=True) or {}
    login_id = str(data.get("login_id") or "").strip()
    password = str(data.get("password") or "")
    member = dbm.authenticate_staff(get_db(), login_id, password) if login_id else None
    if member is None:
        return api_error("Invalid staff ID or password", 401)
    session.clear()
    session["staff_id"] = member["id"]
    return jsonify({"ok": True, "staff": {"name": member["name"], "department": member["department"]}})


@app.route("/api/staff/logout", methods=["POST"])
def api_staff_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/staff/tickets")
@staff_required
def api_staff_tickets():
    me = current_staff()
    return jsonify({"staff": me, "tickets": dbm.staff_tickets(get_db(), me["id"])})


@app.route("/api/staff/tickets/<ticket_id>/start", methods=["POST"])
@staff_required
def api_staff_start(ticket_id):
    ticket_id = ticket_id.strip().upper()
    if not TICKET_RE.match(ticket_id):
        return api_error("Ticket not found", 404)
    ticket, err, code = dbm.staff_start(get_db(), ticket_id, current_staff()["id"])
    if err:
        return api_error(err, code)
    return jsonify(ticket)


@app.route("/api/staff/tickets/<ticket_id>/complete", methods=["POST"])
@staff_required
def api_staff_complete(ticket_id):
    ticket_id = ticket_id.strip().upper()
    if not TICKET_RE.match(ticket_id):
        return api_error("Ticket not found", 404)
    db, me = get_db(), current_staff()

    file = request.files.get("after_photo")
    if not file or not file.filename:
        return api_error("Please attach the After photo as proof of the fix", 400)
    note = " ".join((request.form.get("note") or "").split())
    if len(note) > 300:
        return api_error("Note is too long (max 300 characters)", 400)

    # check ownership/status BEFORE saving the file
    row = db.execute("SELECT status FROM tickets WHERE ticket_id = ? AND assigned_staff_id = ?",
                     (ticket_id, me["id"])).fetchone()
    if row is None:
        return api_error("Ticket not found", 404)
    if row["status"] != "In Progress":
        return api_error("Start the work first (status must be In Progress)", 400)

    photo, err = read_photo(file)
    if err:
        return api_error(err, 400)
    filename = save_photo(*photo)
    old = db.execute("SELECT after_photo_filename FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()[0]
    ticket, err, code = dbm.staff_complete(db, ticket_id, me["id"], filename, note)
    if err:
        remove_upload(filename)
        return api_error(err, code)
    if old and old != filename:
        remove_upload(old)
    return jsonify(ticket)


# ---------------------------------------------------------------- tickets / feed / upvotes
@app.route("/api/meta")
def api_meta():
    return jsonify({
        "categories": dbm.CATEGORIES,
        "wings": dbm.WINGS,
        "rooms": dbm.ROOMS,
        "statuses": dbm.STATUSES,
        "urgencies": dbm.URGENCIES,
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
        photo_filename = save_photo(*photo)

    try:
        ticket_id = dbm.create_ticket(get_db(), current_student()["id"], category, wing, room,
                                      description, photo_filename)
    except Exception:
        remove_upload(photo_filename)
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
@user_required
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
    student = current_student()
    tickets = dbm.get_feed(get_db(), student["id"] if student else None, sort, status, category, mine)
    return jsonify({"tickets": tickets, "threshold": dbm.UPVOTE_THRESHOLD, "role": current_role()})


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


# ---------------------------------------------------------------- chat
def chat_identity():
    """(role, user_id, display name) of the logged-in chat user, or None."""
    if is_admin():
        return "admin", 0, "Admin"
    staff = current_staff()
    if staff:
        return "staff", staff["id"], staff["name"]
    student = current_student()
    if student:
        return "student", student["id"], student["name"]
    return None


@app.route("/api/chat/messages")
@user_required
def api_chat_get():
    role, uid, _name = chat_identity()
    db = get_db()
    after = request.args.get("after", default=0, type=int) or 0
    paused = dbm.is_chat_paused(db)
    banned_until = dbm.get_chat_ban(db, uid) if role == "student" else None
    messages = []
    for m in dbm.chat_messages(db, after):
        item = {"id": m["id"], "role": m["role"], "name": m["name"], "text": m["text"],
                "created_at": m["created_at"], "mine": (m["role"], m["user_id"]) == (role, uid)}
        if role == "admin" and m["role"] == "student":
            item["student_id"] = m["user_id"]   # lets the admin ban from a message
        messages.append(item)
    return jsonify({
        "messages": messages,
        "paused": paused,
        "banned_until": banned_until,
        "can_post": role == "admin" or (not paused and not banned_until),
        "role": role,
    })


@app.route("/api/chat/messages", methods=["POST"])
@user_required
def api_chat_post():
    role, uid, name = chat_identity()
    db = get_db()
    data = request.get_json(silent=True) or {}
    text = " ".join(str(data.get("text") or "").split())
    if not text:
        return api_error("Type a message first", 400)
    if len(text) > MAX_CHAT_LEN:
        return api_error(f"Message is too long (max {MAX_CHAT_LEN} characters)", 400)
    if role != "admin":
        if dbm.is_chat_paused(db):
            return api_error("Chat is currently paused by Admin", 403)
        if role == "student":
            until = dbm.get_chat_ban(db, uid)
            if until:
                return api_error("You are banned from chat until " + until.replace("T", " ").replace("Z", " UTC"), 403)
    if dbm.last_chat_time(db, role, uid) == dbm.now_iso():
        return api_error("You're sending messages too fast", 429)
    msg = dbm.post_chat(db, role, uid, name, text)
    return jsonify({"id": msg["id"]}), 201


# ---------------------------------------------------------------- admin auth
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


# ---------------------------------------------------------------- admin: tickets
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
    if "assigned_staff_id" in data:
        value = data["assigned_staff_id"]
        if value in (None, ""):
            changes["assigned_staff_id"] = None
        else:
            try:
                value = int(value)
            except (TypeError, ValueError):
                return api_error("Unknown staff member", 400)
            if dbm.get_staff_member(db, value) is None:
                return api_error("Unknown staff member", 400)
            changes["assigned_staff_id"] = value
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


# ---------------------------------------------------------------- admin: verification
@app.route("/api/admin/verification")
@admin_required
def api_admin_verification():
    return jsonify({"tickets": dbm.verification_queue(get_db())})


@app.route("/api/admin/tickets/<ticket_id>/verify", methods=["POST"])
@admin_required
def api_admin_verify(ticket_id):
    ticket_id = ticket_id.strip().upper()
    if not TICKET_RE.match(ticket_id):
        return api_error("Ticket not found", 404)
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in ("approve", "reject"):
        return api_error("Action must be approve or reject", 400)
    note = " ".join(str(data.get("note") or "").split())
    if len(note) > 300:
        return api_error("Note is too long (max 300 characters)", 400)
    ticket, err, code = dbm.admin_verify(get_db(), ticket_id, action == "approve", note)
    if err:
        return api_error(err, code)
    return jsonify(ticket)


# ---------------------------------------------------------------- admin: staff management
@app.route("/api/admin/staff")
@admin_required
def api_admin_staff_list():
    return jsonify({"staff": dbm.list_staff(get_db()), "departments": dbm.DEPARTMENTS})


@app.route("/api/admin/staff", methods=["POST"])
@admin_required
def api_admin_staff_add():
    data = request.get_json(silent=True) or {}
    name = " ".join(str(data.get("name") or "").split())
    login_id = str(data.get("login_id") or "").strip()
    password = str(data.get("password") or "")
    department = " ".join(str(data.get("department") or "").split())

    if not 2 <= len(name) <= 60:
        return api_error("Please enter the staff member's name (2 to 60 characters)", 400)
    if not LOGIN_ID_RE.match(login_id):
        return api_error("Login ID / email must be 3 to 60 characters (letters, numbers, . _ @ -)", 400)
    if not 6 <= len(password) <= 64:
        return api_error("Password must be 6 to 64 characters", 400)
    if not 2 <= len(department) <= 40:
        return api_error("Please enter a department / specialty", 400)

    staff_id = dbm.create_staff(get_db(), name, login_id, password, department)
    if staff_id is None:
        return api_error("A staff member with this login ID already exists", 409)
    return jsonify({"ok": True, "id": staff_id}), 201


@app.route("/api/admin/staff/<int:staff_id>", methods=["DELETE"])
@admin_required
def api_admin_staff_remove(staff_id):
    unassigned = dbm.delete_staff(get_db(), staff_id)
    if unassigned is None:
        return api_error("Staff member not found", 404)
    return jsonify({"ok": True, "unassigned": unassigned})


# ---------------------------------------------------------------- admin: chat moderation
def moderation_state(db):
    return {"paused": dbm.is_chat_paused(db), "banned": dbm.list_chat_bans(db)}


@app.route("/api/admin/chat/moderation")
@admin_required
def api_admin_chat_state():
    return jsonify(moderation_state(get_db()))


@app.route("/api/admin/chat/pause", methods=["POST"])
@admin_required
def api_admin_chat_pause():
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("paused"), bool):
        return api_error("Send {\"paused\": true} or {\"paused\": false}", 400)
    dbm.set_chat_paused(get_db(), data["paused"])
    return jsonify(moderation_state(get_db()))


@app.route("/api/admin/chat/ban", methods=["POST"])
@admin_required
def api_admin_chat_ban():
    data = request.get_json(silent=True) or {}
    db = get_db()
    try:
        days = int(data.get("days"))
    except (TypeError, ValueError):
        return api_error("Enter the number of days (1 to 365)", 400)
    if not 1 <= days <= 365:
        return api_error("Days must be between 1 and 365", 400)

    student_id = data.get("student_id")
    if student_id in (None, ""):
        roll = str(data.get("roll_no") or "").strip().upper()
        student_id = dbm.find_student_by_roll(db, roll) if roll else None
    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return api_error("Student not found", 404)
    until = dbm.ban_student(db, student_id, days)
    if until is None:
        return api_error("Student not found", 404)
    return jsonify(dict(moderation_state(db), ban_until=until))


@app.route("/api/admin/chat/ban/<int:student_id>", methods=["DELETE"])
@admin_required
def api_admin_chat_unban(student_id):
    if not dbm.unban_student(get_db(), student_id):
        return api_error("Student not found", 404)
    return jsonify(moderation_state(get_db()))


# ---------------------------------------------------------------- admin: CSV export
def _csv_safe(value):
    """Stop spreadsheet formula injection (cells starting with = + - @)."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def _csv_date(iso_value):
    if not iso_value:
        return ""
    return iso_value.replace("T", " ").replace("Z", "")[:16]


@app.route("/api/admin/export.csv")
@admin_required
def api_admin_export():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Ticket ID", "Title", "Category", "Wing/Room", "Status", "Priority",
                     "Upvotes", "Assigned Staff", "Created Date", "Resolved Date"])
    for t in dbm.all_tickets_for_export(get_db()):
        title = " ".join(t["description"].split())
        if len(title) > 80:
            title = title[:77] + "..."
        writer.writerow([
            t["ticket_id"], _csv_safe(title), t["category"], f"Wing {t['wing']} / Room {t['room']}",
            t["status"], t["urgency"], t["upvotes"], _csv_safe(t["assigned_to"] or "Unassigned"),
            _csv_date(t["created_at"]), _csv_date(t["resolved_at"]),
        ])
    filename = "campusfix_report_" + datetime.now(timezone.utc).strftime("%Y%m%d") + ".csv"
    # utf-8 BOM so Excel opens it correctly
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


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
