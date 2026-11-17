"""CampusFix database layer (SQLite). All helpers take an open connection."""
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "campusfix.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

# ---- Enums (exact strings from the project contract) ----
STATUSES = ["Submitted", "Under Review", "In Progress", "Resolved"]
URGENCIES = ["Low", "Medium", "Critical"]
CATEGORIES = [
    "Wi-Fi & Connectivity",
    "AV Equipment",
    "Utilities & Power",
    "Sanitation & Facilities",
    "Infrastructure",
]
WINGS = ["A", "B", "C"]
ROOMS = {w: [f"{floor}0{n}" for floor in (1, 2, 3) for n in range(1, 6)] for w in WINGS}
DEPARTMENTS = ["Electrician", "Network Technician", "Plumber", "AV Technician",
               "Carpenter", "General Maintenance"]

# An issue with this many upvotes automatically becomes Critical priority
UPVOTE_THRESHOLD = 10
HASH_METHOD = "pbkdf2:sha256"
DEFAULT_STAFF_PASSWORD = "staff123"   # only used when upgrading an older database


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")  # better with several gunicorn workers
    except sqlite3.DatabaseError:
        pass
    return conn


# ---------------------------------------------------------------- migration
def _columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn, table, name, ddl):
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _migrate(conn):
    """Upgrade an older database in place without losing data."""
    for name, ddl in (
        ("student_id", "INTEGER REFERENCES students(id)"),
        ("upvote_count", "INTEGER NOT NULL DEFAULT 0"),
        ("auto_escalated", "INTEGER NOT NULL DEFAULT 0"),
        ("assigned_staff_id", "INTEGER REFERENCES staff(id) ON DELETE SET NULL"),
        ("after_photo_filename", "TEXT"),
        ("completed_at", "TEXT"),
        ("resolved_at", "TEXT"),
    ):
        _add_column(conn, "tickets", name, ddl)
    _add_column(conn, "students", "chat_ban_until", "TEXT")
    for name in ("login_id", "password_hash", "department", "created_at"):
        _add_column(conn, "staff", name, "TEXT")

    # old tickets stored the staff NAME in assigned_to: link them to staff ids first
    conn.execute(
        """UPDATE tickets SET assigned_staff_id = (SELECT id FROM staff WHERE staff.name = tickets.assigned_to)
           WHERE assigned_staff_id IS NULL AND assigned_to IS NOT NULL"""
    )
    # old staff rows were just names like "Amit Sharma (Network)": give them a login
    legacy = conn.execute("SELECT id, name FROM staff WHERE login_id IS NULL").fetchall()
    if legacy:
        pw = generate_password_hash(DEFAULT_STAFF_PASSWORD, method=HASH_METHOD)
        for row in legacy:
            name, dept = row["name"], "General Maintenance"
            m = re.match(r"^(.*?)\s*\((.*)\)\s*$", name)
            if m:
                name, dept = m.group(1), m.group(2)
            conn.execute(
                "UPDATE staff SET name = ?, login_id = ?, password_hash = ?, department = ?, created_at = ? WHERE id = ?",
                (name, f"staff{100 + row['id']}", pw, dept, now_iso(), row["id"]),
            )
    conn.execute(
        "UPDATE tickets SET resolved_at = updated_at WHERE status = 'Resolved' AND resolved_at IS NULL"
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_staff_login ON staff(login_id) WHERE login_id IS NOT NULL")


def init_db(reset=False):
    """Create tables and upgrade old databases. reset=True deletes the DB file first."""
    if reset:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(DB_PATH + suffix):
                os.remove(DB_PATH + suffix)
    conn = connect()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    _migrate(conn)
    conn.execute("INSERT OR IGNORE INTO chat_settings (key, value) VALUES ('paused', '0')")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- students
def create_student(db, name, roll_no, password):
    """Returns the new student id, or None if the roll number is already registered."""
    try:
        cur = db.execute(
            "INSERT INTO students (name, roll_no, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name, roll_no, generate_password_hash(password, method=HASH_METHOD), now_iso()),
        )
    except sqlite3.IntegrityError:
        return None
    db.commit()
    return cur.lastrowid


def authenticate_student(db, roll_no, password):
    row = db.execute("SELECT * FROM students WHERE roll_no = ?", (roll_no,)).fetchone()
    if row and check_password_hash(row["password_hash"], password):
        return {"id": row["id"], "name": row["name"], "roll_no": row["roll_no"]}
    return None


def get_student(db, student_id):
    row = db.execute("SELECT id, name, roll_no FROM students WHERE id = ?", (student_id,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------- staff
def _staff_dict(row):
    return {"id": row["id"], "name": row["name"], "login_id": row["login_id"],
            "department": row["department"]}


def create_staff(db, name, login_id, password, department):
    """Returns the new staff id, or None if the login ID is already used."""
    try:
        cur = db.execute(
            "INSERT INTO staff (name, login_id, password_hash, department, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, login_id.lower(), generate_password_hash(password, method=HASH_METHOD),
             department, now_iso()),
        )
    except sqlite3.IntegrityError:
        return None
    db.commit()
    return cur.lastrowid


def authenticate_staff(db, login_id, password):
    row = db.execute("SELECT * FROM staff WHERE login_id = ?", (login_id.lower(),)).fetchone()
    if row and row["password_hash"] and check_password_hash(row["password_hash"], password):
        return _staff_dict(row)
    return None


def get_staff_member(db, staff_id):
    row = db.execute("SELECT * FROM staff WHERE id = ?", (staff_id,)).fetchone()
    return _staff_dict(row) if row else None


def list_staff(db):
    rows = db.execute(
        """SELECT st.*,
                  (SELECT COUNT(*) FROM tickets t WHERE t.assigned_staff_id = st.id AND t.status != 'Resolved') AS open_tasks,
                  (SELECT COUNT(*) FROM tickets t WHERE t.assigned_staff_id = st.id AND t.status = 'Resolved') AS done_tasks
           FROM staff st ORDER BY st.name COLLATE NOCASE"""
    ).fetchall()
    return [dict(_staff_dict(r), open_tasks=r["open_tasks"], done_tasks=r["done_tasks"],
                 created_at=r["created_at"]) for r in rows]


def delete_staff(db, staff_id):
    """Remove a staff member. Their open tickets become unassigned. Returns number unassigned or None."""
    row = db.execute("SELECT * FROM staff WHERE id = ?", (staff_id,)).fetchone()
    if row is None:
        return None
    ts = now_iso()
    open_tickets = db.execute(
        "SELECT ticket_id, status FROM tickets WHERE assigned_staff_id = ? AND status != 'Resolved'",
        (staff_id,),
    ).fetchall()
    for t in open_tickets:
        db.execute(
            "INSERT INTO ticket_history (ticket_id, status, note, timestamp) VALUES (?, ?, ?, ?)",
            (t["ticket_id"], t["status"], f"{row['name']} was removed from staff. Ticket is unassigned.", ts),
        )
    db.execute("UPDATE tickets SET assigned_staff_id = NULL, updated_at = ? WHERE assigned_staff_id = ? AND status != 'Resolved'",
               (ts, staff_id))
    db.execute("UPDATE tickets SET assigned_staff_id = NULL WHERE assigned_staff_id = ?", (staff_id,))
    db.execute("DELETE FROM staff WHERE id = ?", (staff_id,))
    db.commit()
    return len(open_tickets)


# ---------------------------------------------------------------- serialisation
_BASE = """
SELECT t.*, s.name AS reporter_name, s.roll_no AS reporter_roll,
       st.name AS staff_name, st.department AS staff_department,
       EXISTS(SELECT 1 FROM upvotes u WHERE u.ticket_id = t.ticket_id AND u.student_id = :viewer) AS upvoted_by_me
FROM tickets t
LEFT JOIN students s ON s.id = t.student_id
LEFT JOIN staff st ON st.id = t.assigned_staff_id
"""


def _fetch(db, where="", params=None, order="", limit=None, viewer=None):
    p = dict(params or {})
    p["viewer"] = viewer if viewer is not None else 0
    sql = _BASE
    if where:
        sql += " WHERE " + where
    if order:
        sql += " ORDER BY " + order
    if limit:
        sql += f" LIMIT {int(limit)}"
    return db.execute(sql, p).fetchall()


def _photo(name):
    return f"/uploads/{name}" if name else None


def _ticket_dict(row, viewer=None, history=None, reporter=False):
    after = row["after_photo_filename"]
    t = {
        "ticket_id": row["ticket_id"],
        "category": row["category"],
        "wing": row["wing"],
        "room": row["room"],
        "description": row["description"],
        "photo_url": _photo(row["photo_filename"]),
        "after_photo_url": _photo(after),
        "awaiting_verification": bool(after) and row["status"] != "Resolved",
        "status": row["status"],
        "urgency": row["urgency"],
        "assigned_to": row["staff_name"],
        "assigned_staff_id": row["assigned_staff_id"],
        "assigned_department": row["staff_department"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "resolved_at": row["resolved_at"],
        "upvotes": row["upvote_count"],
        "upvoted_by_me": bool(row["upvoted_by_me"]),
        "is_mine": viewer is not None and row["student_id"] == viewer,
    }
    if reporter:  # admins only
        t["reporter"] = (
            {"name": row["reporter_name"], "roll_no": row["reporter_roll"]}
            if row["student_id"] else None
        )
    if history is not None:
        t["history"] = history
    return t


def _history(db, ticket_id):
    rows = db.execute(
        "SELECT status, note, timestamp FROM ticket_history WHERE ticket_id = ? ORDER BY id",
        (ticket_id,),
    ).fetchall()
    return [{"status": r["status"], "note": r["note"], "timestamp": r["timestamp"]} for r in rows]


def _add_history(db, ticket_id, status, note, ts):
    db.execute(
        "INSERT INTO ticket_history (ticket_id, status, note, timestamp) VALUES (?, ?, ?, ?)",
        (ticket_id, status, note, ts),
    )


# ---------------------------------------------------------------- tickets
def create_ticket(db, student_id, category, wing, room, description, photo_filename=None):
    ts = now_iso()
    cur = db.execute(
        """INSERT INTO tickets (ticket_id, category, wing, room, description, photo_filename,
                                status, urgency, created_at, updated_at, student_id)
           VALUES (?, ?, ?, ?, ?, ?, 'Submitted', 'Medium', ?, ?, ?)""",
        (uuid.uuid4().hex, category, wing, room, description, photo_filename, ts, ts, student_id),
    )
    ticket_id = f"CF-{1000 + cur.lastrowid}"  # sequential: CF-1001, CF-1002, ...
    db.execute("UPDATE tickets SET ticket_id = ? WHERE id = ?", (ticket_id, cur.lastrowid))
    _add_history(db, ticket_id, "Submitted", "Complaint submitted", ts)
    db.commit()
    return ticket_id


def get_ticket(db, ticket_id, viewer=None, reporter=False):
    rows = _fetch(db, "t.ticket_id = :tid", {"tid": ticket_id}, viewer=viewer)
    if not rows:
        return None
    return _ticket_dict(rows[0], viewer, _history(db, ticket_id), reporter)


def list_tickets(db, status="", urgency="", category="", q=""):
    """Admin listing (includes reporter details)."""
    where, params = ["1=1"], {}
    for col, val in (("status", status), ("urgency", urgency), ("category", category)):
        if val:
            where.append(f"t.{col} = :{col}")
            params[col] = val
    if q:
        params["like"] = f"%{q}%"
        where.append(
            "(t.ticket_id LIKE :like OR t.description LIKE :like OR t.category LIKE :like"
            " OR t.wing LIKE :like OR t.room LIKE :like OR (t.wing || ' ' || t.room) LIKE :like"
            " OR IFNULL(st.name,'') LIKE :like OR IFNULL(s.name,'') LIKE :like"
            " OR IFNULL(s.roll_no,'') LIKE :like)"
        )
    rows = _fetch(db, " AND ".join(where), params, order="t.created_at DESC, t.id DESC")
    return [_ticket_dict(r, reporter=True) for r in rows]


def all_tickets_for_export(db):
    rows = _fetch(db, order="t.id ASC")
    return [_ticket_dict(r) for r in rows]


def get_feed(db, viewer, sort="top", status="open", category="", mine=False):
    """Public complaint feed for logged-in users (no reporter identity)."""
    where, params = ["1=1"], {}
    if status == "open":
        where.append("t.status != 'Resolved'")
    elif status == "resolved":
        where.append("t.status = 'Resolved'")
    if category:
        where.append("t.category = :category")
        params["category"] = category
    if mine and viewer is not None:
        where.append("t.student_id = :viewer")
    order = ("t.upvote_count DESC, t.created_at DESC, t.id DESC" if sort == "top"
             else "t.created_at DESC, t.id DESC")
    rows = _fetch(db, " AND ".join(where), params, order=order, limit=60, viewer=viewer)
    return [_ticket_dict(r, viewer) for r in rows]


def update_ticket(db, ticket_id, changes, note=""):
    """Admin update. changes: validated subset of {status, urgency, assigned_staff_id}."""
    row = db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    if row is None:
        return None
    status = changes.get("status", row["status"])
    urgency = changes.get("urgency", row["urgency"])
    staff_id = changes["assigned_staff_id"] if "assigned_staff_id" in changes else row["assigned_staff_id"]
    ts = now_iso()
    parts = []

    if staff_id != row["assigned_staff_id"]:
        if staff_id is None:
            parts.append("Unassigned")
        else:
            member = get_staff_member(db, staff_id)
            parts.append(f"Assigned to {member['name']} ({member['department']})")
            if status == "Submitted" and "status" not in changes:
                status = "Under Review"  # assigned tickets move into review automatically
    status_changed = status != row["status"]
    if note:
        parts.append(note)
    if status_changed and not parts:
        parts.append(f"Status changed to {status}")

    resolved_at = row["resolved_at"]
    if status == "Resolved" and row["status"] != "Resolved":
        resolved_at = ts
    elif status != "Resolved":
        resolved_at = None

    db.execute(
        """UPDATE tickets SET status = ?, urgency = ?, assigned_staff_id = ?, resolved_at = ?, updated_at = ?
           WHERE ticket_id = ?""",
        (status, urgency, staff_id, resolved_at, ts, ticket_id),
    )
    if parts:
        _add_history(db, ticket_id, status, " | ".join(parts), ts)
    db.commit()
    return get_ticket(db, ticket_id, reporter=True)


# ---------------------------------------------------------------- staff workflow
def staff_tickets(db, staff_id):
    rows = _fetch(
        db, "t.assigned_staff_id = :sid", {"sid": staff_id},
        order="CASE t.urgency WHEN 'Critical' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, t.created_at ASC",
    )
    return [_ticket_dict(r) for r in rows]


def _assigned_row(db, ticket_id, staff_id):
    return db.execute(
        "SELECT * FROM tickets WHERE ticket_id = ? AND assigned_staff_id = ?", (ticket_id, staff_id)
    ).fetchone()


def staff_start(db, ticket_id, staff_id):
    """Under Review -> In Progress. Returns (ticket, error, http_code)."""
    row = _assigned_row(db, ticket_id, staff_id)
    if row is None:
        return None, "Ticket not found", 404
    if row["status"] != "Under Review":
        return None, "Only tickets that are Under Review can be started", 400
    member = get_staff_member(db, staff_id)
    ts = now_iso()
    db.execute("UPDATE tickets SET status = 'In Progress', updated_at = ? WHERE ticket_id = ?", (ts, ticket_id))
    _add_history(db, ticket_id, "In Progress", f"Work started by {member['name']}", ts)
    db.commit()
    return get_ticket(db, ticket_id), None, 200


def staff_complete(db, ticket_id, staff_id, after_filename, note=""):
    """Attach the After photo and mark ready for verification. Returns (ticket, error, code)."""
    row = _assigned_row(db, ticket_id, staff_id)
    if row is None:
        return None, "Ticket not found", 404
    if row["status"] != "In Progress":
        return None, "Start the work first (status must be In Progress)", 400
    member = get_staff_member(db, staff_id)
    ts = now_iso()
    db.execute(
        "UPDATE tickets SET after_photo_filename = ?, completed_at = ?, updated_at = ? WHERE ticket_id = ?",
        (after_filename, ts, ts, ticket_id),
    )
    text = f"Work completed by {member['name']}. After photo uploaded, awaiting admin verification."
    if note:
        text += f" Note: {note}"
    _add_history(db, ticket_id, "In Progress", text, ts)
    db.commit()
    return get_ticket(db, ticket_id), None, 200


# ---------------------------------------------------------------- admin verification
def verification_queue(db):
    rows = _fetch(db, "t.after_photo_filename IS NOT NULL AND t.status != 'Resolved'",
                  order="t.completed_at ASC, t.id ASC")
    return [_ticket_dict(r, reporter=True) for r in rows]


def admin_verify(db, ticket_id, approve, note=""):
    """Approve (-> Resolved) or reject the After photo. Returns (ticket, error, code)."""
    row = db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    if row is None:
        return None, "Ticket not found", 404
    if not row["after_photo_filename"] or row["status"] == "Resolved":
        return None, "This ticket has no proof waiting for verification", 400
    ts = now_iso()
    if approve:
        db.execute("UPDATE tickets SET status = 'Resolved', resolved_at = ?, updated_at = ? WHERE ticket_id = ?",
                   (ts, ts, ticket_id))
        text = "Verified by admin. Marked as Resolved."
        if note:
            text += f" Note: {note}"
        _add_history(db, ticket_id, "Resolved", text, ts)
    else:
        db.execute(
            "UPDATE tickets SET after_photo_filename = NULL, completed_at = NULL, updated_at = ? WHERE ticket_id = ?",
            (ts, ticket_id),
        )
        _add_history(db, ticket_id, row["status"],
                     "After photo rejected by admin. Please redo the work and upload a new photo."
                     + (f" Note: {note}" if note else ""), ts)
    db.commit()
    return get_ticket(db, ticket_id, reporter=True), None, 200


# ---------------------------------------------------------------- upvotes
def _after_vote(db, ticket_id, upvoted):
    """Recount votes; auto-escalate to Critical at UPVOTE_THRESHOLD (only once per ticket)."""
    count = db.execute("SELECT COUNT(*) FROM upvotes WHERE ticket_id = ?", (ticket_id,)).fetchone()[0]
    row = db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    escalated = False
    urgency = row["urgency"]
    if count >= UPVOTE_THRESHOLD and urgency != "Critical" and not row["auto_escalated"]:
        ts = now_iso()
        db.execute(
            "UPDATE tickets SET upvote_count = ?, urgency = 'Critical', auto_escalated = 1, updated_at = ? "
            "WHERE ticket_id = ?",
            (count, ts, ticket_id),
        )
        _add_history(db, ticket_id, row["status"], f"Auto-escalated to Critical priority ({count} upvotes)", ts)
        urgency, escalated = "Critical", True
    else:
        db.execute("UPDATE tickets SET upvote_count = ? WHERE ticket_id = ?", (count, ticket_id))
    db.commit()
    return {"ticket_id": ticket_id, "upvotes": count, "upvoted": upvoted,
            "urgency": urgency, "escalated": escalated}


def _vote_checks(db, ticket_id, student_id):
    row = db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    if row is None:
        return "Ticket not found", 404
    if row["student_id"] == student_id:
        return "You can't upvote your own complaint", 403
    if row["status"] == "Resolved":
        return "This issue is already resolved", 400
    return None, None


def add_upvote(db, ticket_id, student_id):
    """Returns (result, error, http_code)."""
    err, code = _vote_checks(db, ticket_id, student_id)
    if err:
        return None, err, code
    db.execute(
        "INSERT OR IGNORE INTO upvotes (ticket_id, student_id, created_at) VALUES (?, ?, ?)",
        (ticket_id, student_id, now_iso()),
    )
    return _after_vote(db, ticket_id, True), None, 200


def remove_upvote(db, ticket_id, student_id):
    err, code = _vote_checks(db, ticket_id, student_id)
    if err:
        return None, err, code
    db.execute("DELETE FROM upvotes WHERE ticket_id = ? AND student_id = ?", (ticket_id, student_id))
    return _after_vote(db, ticket_id, False), None, 200


# ---------------------------------------------------------------- chat
CHAT_KEEP = 500


def is_chat_paused(db):
    row = db.execute("SELECT value FROM chat_settings WHERE key = 'paused'").fetchone()
    return bool(row and row["value"] == "1")


def set_chat_paused(db, paused):
    db.execute("INSERT OR REPLACE INTO chat_settings (key, value) VALUES ('paused', ?)", ("1" if paused else "0",))
    db.commit()


def get_chat_ban(db, student_id):
    """Ban expiry (ISO) if the student is currently banned, else None."""
    row = db.execute("SELECT chat_ban_until FROM students WHERE id = ?", (student_id,)).fetchone()
    until = row["chat_ban_until"] if row else None
    return until if until and until > now_iso() else None


def ban_student(db, student_id, days):
    """Ban a student from chat for N days. Returns the expiry (ISO) or None if no such student."""
    if db.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone() is None:
        return None
    until = iso(datetime.now(timezone.utc) + timedelta(days=days))
    db.execute("UPDATE students SET chat_ban_until = ? WHERE id = ?", (until, student_id))
    db.commit()
    return until


def unban_student(db, student_id):
    cur = db.execute("UPDATE students SET chat_ban_until = NULL WHERE id = ?", (student_id,))
    db.commit()
    return cur.rowcount > 0


def find_student_by_roll(db, roll_no):
    row = db.execute("SELECT id FROM students WHERE roll_no = ?", (roll_no,)).fetchone()
    return row["id"] if row else None


def list_chat_bans(db):
    rows = db.execute(
        "SELECT id, name, roll_no, chat_ban_until FROM students WHERE chat_ban_until > ? ORDER BY chat_ban_until",
        (now_iso(),),
    ).fetchall()
    return [{"student_id": r["id"], "name": r["name"], "roll_no": r["roll_no"],
             "ban_until": r["chat_ban_until"]} for r in rows]


def chat_messages(db, after_id=0, limit=60):
    """New messages after after_id (oldest first). after_id=0 returns the latest `limit`."""
    if after_id > 0:
        rows = db.execute("SELECT * FROM chat_messages WHERE id > ? ORDER BY id LIMIT 200", (after_id,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM (SELECT * FROM chat_messages ORDER BY id DESC LIMIT ?) ORDER BY id",
                          (limit,)).fetchall()
    return [dict(r) for r in rows]


def last_chat_time(db, role, user_id):
    row = db.execute(
        "SELECT created_at FROM chat_messages WHERE role = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
        (role, user_id),
    ).fetchone()
    return row["created_at"] if row else None


def post_chat(db, role, user_id, name, text):
    ts = now_iso()
    cur = db.execute(
        "INSERT INTO chat_messages (role, user_id, name, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (role, user_id, name, text, ts),
    )
    db.execute("DELETE FROM chat_messages WHERE id <= ?", (cur.lastrowid - CHAT_KEEP,))
    db.commit()
    return {"id": cur.lastrowid, "role": role, "user_id": user_id, "name": name, "text": text, "created_at": ts}


# ---------------------------------------------------------------- analytics
def get_stats(db):
    total = db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]

    def grouped(col, keys):
        out = {k: 0 for k in keys}
        for r in db.execute(f"SELECT {col} AS k, COUNT(*) AS c FROM tickets GROUP BY {col}"):
            out[r["k"]] = r["c"]
        return out

    by_status = grouped("status", STATUSES)
    hotspots = [
        {"wing": r["wing"], "room": r["room"], "count": r["c"]}
        for r in db.execute(
            """SELECT wing, room, COUNT(*) AS c FROM tickets
               GROUP BY wing, room ORDER BY c DESC, wing, room LIMIT 5"""
        )
    ]
    awaiting = db.execute(
        "SELECT COUNT(*) FROM tickets WHERE after_photo_filename IS NOT NULL AND status != 'Resolved'"
    ).fetchone()[0]
    return {
        "total": total,
        "pending": total - by_status["Resolved"],
        "by_status": by_status,
        "by_category": grouped("category", CATEGORIES),
        "by_urgency": grouped("urgency", URGENCIES),
        "hotspots": hotspots,
        "awaiting_verification": awaiting,
    }
