"""CampusFix database layer (SQLite). All helpers take an open connection."""
import os
import sqlite3
import uuid
from datetime import datetime, timezone

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

# Synthetic maintenance staff (no real people)
STAFF = [
    "Amit Sharma (Network)",
    "Pooja Mehta (AV Technician)",
    "Neha Singh (Electrician)",
    "Suresh Yadav (Plumber)",
    "Rakesh Patel (Carpenter)",
]

# An issue with this many upvotes automatically becomes Critical priority
UPVOTE_THRESHOLD = 10
HASH_METHOD = "pbkdf2:sha256"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn):
    """Upgrade an older database (before student login) without losing data."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(tickets)")}
    for name, ddl in (
        ("student_id", "INTEGER REFERENCES students(id)"),
        ("upvote_count", "INTEGER NOT NULL DEFAULT 0"),
        ("auto_escalated", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE tickets ADD COLUMN {name} {ddl}")


def init_db(reset=False):
    """Create tables (and seed the staff list). reset=True deletes the DB file first."""
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = connect()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    _migrate(conn)
    if conn.execute("SELECT COUNT(*) FROM staff").fetchone()[0] == 0:
        conn.executemany("INSERT INTO staff (name) VALUES (?)", [(n,) for n in STAFF])
    conn.commit()
    conn.close()


def get_staff_names(db):
    return [r["name"] for r in db.execute("SELECT name FROM staff ORDER BY id")]


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


# ---------------------------------------------------------------- serialisation
_BASE = """
SELECT t.*, s.name AS reporter_name, s.roll_no AS reporter_roll,
       EXISTS(SELECT 1 FROM upvotes u WHERE u.ticket_id = t.ticket_id AND u.student_id = :viewer) AS upvoted_by_me
FROM tickets t LEFT JOIN students s ON s.id = t.student_id
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


def _ticket_dict(row, viewer=None, history=None, reporter=False):
    t = {
        "ticket_id": row["ticket_id"],
        "category": row["category"],
        "wing": row["wing"],
        "room": row["room"],
        "description": row["description"],
        "photo_url": f"/uploads/{row['photo_filename']}" if row["photo_filename"] else None,
        "status": row["status"],
        "urgency": row["urgency"],
        "assigned_to": row["assigned_to"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
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
    db.execute(
        "INSERT INTO ticket_history (ticket_id, status, note, timestamp) VALUES (?, 'Submitted', ?, ?)",
        (ticket_id, "Complaint submitted", ts),
    )
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
            " OR IFNULL(t.assigned_to,'') LIKE :like OR IFNULL(s.name,'') LIKE :like"
            " OR IFNULL(s.roll_no,'') LIKE :like)"
        )
    rows = _fetch(db, " AND ".join(where), params, order="t.created_at DESC, t.id DESC")
    return [_ticket_dict(r, reporter=True) for r in rows]


def get_feed(db, viewer, sort="top", status="open", category="", mine=False):
    """Public complaint feed for logged-in students (no reporter identity)."""
    where, params = ["1=1"], {}
    if status == "open":
        where.append("t.status != 'Resolved'")
    elif status == "resolved":
        where.append("t.status = 'Resolved'")
    if category:
        where.append("t.category = :category")
        params["category"] = category
    if mine:
        where.append("t.student_id = :viewer")
    order = ("t.upvote_count DESC, t.created_at DESC, t.id DESC" if sort == "top"
             else "t.created_at DESC, t.id DESC")
    rows = _fetch(db, " AND ".join(where), params, order=order, limit=60, viewer=viewer)
    return [_ticket_dict(r, viewer) for r in rows]


def update_ticket(db, ticket_id, changes, note=""):
    """changes: validated subset of {status, urgency, assigned_to}. Returns updated ticket or None."""
    row = db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    if row is None:
        return None
    status = changes.get("status", row["status"])
    urgency = changes.get("urgency", row["urgency"])
    assigned = changes["assigned_to"] if "assigned_to" in changes else row["assigned_to"]
    status_changed = status != row["status"]
    ts = now_iso()
    db.execute(
        "UPDATE tickets SET status = ?, urgency = ?, assigned_to = ?, updated_at = ? WHERE ticket_id = ?",
        (status, urgency, assigned, ts, ticket_id),
    )
    if status_changed or note:
        db.execute(
            "INSERT INTO ticket_history (ticket_id, status, note, timestamp) VALUES (?, ?, ?, ?)",
            (ticket_id, status, note or f"Status changed to {status}", ts),
        )
    db.commit()
    return get_ticket(db, ticket_id, reporter=True)


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
        db.execute(
            "INSERT INTO ticket_history (ticket_id, status, note, timestamp) VALUES (?, ?, ?, ?)",
            (ticket_id, row["status"], f"Auto-escalated to Critical priority ({count} upvotes)", ts),
        )
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
    return {
        "total": total,
        "pending": total - by_status["Resolved"],
        "by_status": by_status,
        "by_category": grouped("category", CATEGORIES),
        "by_urgency": grouped("urgency", URGENCIES),
        "hotspots": hotspots,
    }
