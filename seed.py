"""Reset the database and insert synthetic demo data (no real personal data).

Usage:  python seed.py

Creates: 15 demo students, 5 demo staff, 24 tickets (some with Before/After photos),
upvotes and a few chat messages. Demo images are generated into uploads/.
"""
import os
import struct
import zlib
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

import database as db

UPLOAD_DIR = os.path.join(db.BASE_DIR, "uploads")
DEMO_PASSWORD = "student123"
STAFF_PASSWORD = "staff123"

STUDENT_NAMES = [
    "Aarav Mehta", "Diya Nair", "Kabir Sethi", "Ishita Rao", "Rohan Das",
    "Meera Joshi", "Vihaan Gupta", "Anaya Iyer", "Arjun Reddy", "Saanvi Kulkarni",
    "Yash Malhotra", "Tara Bose", "Dev Chauhan", "Riya Menon", "Neil Fernandes",
]
# (name, login ID, department). Staff ids are 1..5 in this order.
STAFF_SEED = [
    ("Amit Sharma", "STAFF101", "Network Technician"),
    ("Pooja Mehta", "STAFF102", "AV Technician"),
    ("Neha Singh", "STAFF103", "Electrician"),
    ("Suresh Yadav", "STAFF104", "Plumber"),
    ("Rakesh Patel", "STAFF105", "Carpenter"),
]
STAFF_FOR_CATEGORY = {
    "Wi-Fi & Connectivity": 1, "AV Equipment": 2, "Utilities & Power": 3,
    "Sanitation & Facilities": 4, "Infrastructure": 5,
}

DESCRIPTIONS = {
    "Wi-Fi & Connectivity": [
        "Wi-Fi keeps dropping every few minutes during lectures.",
        "No internet connectivity in the computer lab since morning.",
        "Access point seems offline; signal is very weak in the back rows.",
        "Wi-Fi login page loads but the internet never connects.",
        "Frequent disconnections while running online quizzes.",
    ],
    "AV Equipment": [
        "Projector shows no display even though the laptop is connected.",
        "Smart board touch is not responding in the classroom.",
        "Projector image is flickering and has a green tint.",
        "Speakers produce no sound during presentations.",
        "HDMI port on the podium is loose and the display cuts out.",
    ],
    "Utilities & Power": [
        "Tube lights in the second row are not working.",
        "Power sockets near the front desk are dead.",
        "Frequent power surges tripping the fan regulator.",
        "Flickering lights and a buzzing sound from the ceiling panel.",
        "Socket sparks when plugging in a charger.",
    ],
    "Sanitation & Facilities": [
        "Washroom tap is leaking and the floor stays wet.",
        "No water supply in the washroom since yesterday.",
        "Washroom needs urgent cleaning and refilling of supplies.",
        "Water cooler near the corridor is not dispensing water.",
        "Flush system is not working in the washroom.",
    ],
    "Infrastructure": [
        "Two benches in the lecture hall have broken legs.",
        "Classroom door lock is jammed and the door will not close.",
        "Window latch is broken and the glass is cracked.",
        "Whiteboard is falling off the wall at one corner.",
        "Ceiling plaster is peeling off above the seating area.",
    ],
}

# Ticket i has category CATEGORIES[i % 5]. Repeated locations create "hotspots".
LOCATIONS = [
    ("A", "302"), ("B", "204"), ("C", "101"), ("A", "105"), ("B", "301"),
    ("A", "302"), ("B", "204"), ("C", "203"), ("B", "105"), ("C", "304"),
    ("B", "202"), ("B", "204"), ("A", "201"), ("A", "105"), ("A", "303"),
    ("A", "302"), ("C", "305"), ("C", "101"), ("C", "102"), ("B", "301"),
    ("C", "205"), ("A", "104"), ("B", "303"), ("A", "105"),
]
# 9 Resolved, 6 In Progress, 5 Under Review, 4 Submitted
STATUS_PLAN = [
    "Resolved", "Resolved", "In Progress", "Under Review", "Resolved", "Resolved",
    "In Progress", "Submitted", "Under Review", "In Progress", "Resolved", "Under Review",
    "Resolved", "In Progress", "Submitted", "Under Review", "Resolved", "In Progress",
    "Resolved", "Submitted", "Under Review", "Resolved", "In Progress", "Submitted",
]
URGENCY_PLAN = [
    "Critical", "Medium", "Low", "Medium", "Low", "Critical", "Critical", "Medium",
    "Low", "Medium", "Low", "Critical", "Medium", "Medium", "Low", "Critical",
    "Low", "Critical", "Medium", "Low", "Medium", "Low", "Medium", "Critical",
]
# ticket index -> number of upvotes (index 3 = CF-1004 is one vote away from Critical)
SPECIAL_VOTES = {3: 9, 6: 11}
# Under Review tickets that are already assigned (staff can press "Start work")
ASSIGNED_UNDER_REVIEW = {3, 11, 20}
BEFORE_PHOTO = {0, 2, 4, 6, 9, 12}   # students attached a photo
AFTER_PHOTO = {2, 4, 12}             # staff uploaded proof (index 2 is waiting for admin verification)

CHAT_SEED = [
    (180, "admin", 0, "Admin", "Welcome to the CampusFix community chat! Please keep it respectful and on topic."),
    (150, "staff", 1, "Amit Sharma", "Network team here: we are checking the Wi-Fi access points in Wing A today."),
    (140, "student", 1, "Aarav Mehta", "Thanks! Wi-Fi in A-302 has been dropping a lot."),
    (130, "student", 2, "Diya Nair", "Upvoted that one. Same issue in the lab."),
    (60, "staff", 2, "Pooja Mehta", "AV team: the projector in B-204 is being looked at."),
    (30, "admin", 0, "Admin", "Reminder: upvote issues that affect you. 10 upvotes makes an issue Critical."),
]


def make_png(path, w, h, pixel):
    """Write a small RGB PNG using only the standard library."""
    raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h))

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def make_demo_images():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    w, h = 320, 200

    def before(x, y):   # dull red-brown with dark diagonal "damage" stripes
        base = (120 - y // 4, 54 + x // 16, 48)
        return (40, 24, 24) if (x + y) % 46 < 5 else base

    def after(x, y):    # clean teal-to-green gradient
        return (20 + x // 12, 150 + y // 5, 150 - x // 8)

    make_png(os.path.join(UPLOAD_DIR, "demo_before.png"), w, h, before)
    make_png(os.path.join(UPLOAD_DIR, "demo_after.png"), w, h, after)


def main():
    db.init_db(reset=True)
    make_demo_images()
    conn = db.connect()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # ---- students ----
    pw_hash = generate_password_hash(DEMO_PASSWORD, method=db.HASH_METHOD)
    for n, name in enumerate(STUDENT_NAMES, start=1):
        conn.execute(
            "INSERT INTO students (id, name, roll_no, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (n, name, f"STU{1000 + n}", pw_hash, db.iso(now - timedelta(days=14))),
        )

    # ---- staff ----
    staff_hash = generate_password_hash(STAFF_PASSWORD, method=db.HASH_METHOD)
    for n, (name, login_id, dept) in enumerate(STAFF_SEED, start=1):
        conn.execute(
            "INSERT INTO staff (id, name, login_id, password_hash, department, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (n, name, login_id.lower(), staff_hash, dept, db.iso(now - timedelta(days=20))),
        )
    staff_name = {n: s[0] for n, s in enumerate(STAFF_SEED, start=1)}

    # ---- tickets ----
    for i in range(24):
        category = db.CATEGORIES[i % 5]
        wing, room = LOCATIONS[i]
        description = DESCRIPTIONS[category][(i // 5) % 5]
        status, urgency = STATUS_PLAN[i], URGENCY_PLAN[i]
        staff_id = STAFF_FOR_CATEGORY[category]
        assigned = staff_id if (status in ("In Progress", "Resolved") or i in ASSIGNED_UNDER_REVIEW) else None
        who = staff_name[staff_id]

        owner = (i % len(STUDENT_NAMES)) + 1
        votes = SPECIAL_VOTES.get(i, (i * 3) % 7)
        escalated = 1 if i == 6 else 0
        before_photo = "demo_before.png" if i in BEFORE_PHOTO else None
        after_photo = "demo_after.png" if i in AFTER_PHOTO else None

        created = now - timedelta(days=12 - i // 2, hours=(i * 5) % 24)
        stages = db.STATUSES[: db.STATUSES.index(status) + 1]
        ticket_id = f"CF-{1001 + i}"
        completed_at = None
        resolved_at = None
        last_ts = created
        history = []

        for k, stage in enumerate(stages):
            last_ts = created + timedelta(hours=5 * k + (i % 3))
            if stage == "Submitted":
                note = "Complaint submitted"
            elif stage == "Under Review":
                note = f"Assigned to {who} ({STAFF_SEED[staff_id - 1][2]})" if assigned else "Reviewed by admin and prioritized"
            elif stage == "In Progress":
                note = f"Work started by {who}" if assigned else f"Maintenance staff dispatched to Wing {wing}, Room {room}"
            else:
                note = "Verified by admin. Marked as Resolved." if after_photo else "Issue fixed and verified on site"
                resolved_at = last_ts
            history.append((stage, note, last_ts))
            if escalated and k == 0:
                history.append((stage, "Auto-escalated to Critical priority (10 upvotes)", created + timedelta(hours=3)))
            if stage == "In Progress" and after_photo:
                completed_at = last_ts + timedelta(hours=1)
                history.append((stage, f"Work completed by {who}. After photo uploaded, awaiting admin verification.",
                                completed_at))
                last_ts = completed_at
        if status == "Resolved":
            last_ts = history[-1][2]

        conn.execute(
            """INSERT INTO tickets (id, ticket_id, category, wing, room, description, photo_filename,
                                    status, urgency, created_at, updated_at, student_id, upvote_count,
                                    auto_escalated, assigned_staff_id, after_photo_filename,
                                    completed_at, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (i + 1, ticket_id, category, wing, room, description, before_photo, status, urgency,
             db.iso(created), db.iso(last_ts), owner, votes, escalated, assigned, after_photo,
             db.iso(completed_at) if completed_at else None,
             db.iso(resolved_at) if resolved_at else None),
        )
        for stage, note, ts in history:
            conn.execute(
                "INSERT INTO ticket_history (ticket_id, status, note, timestamp) VALUES (?, ?, ?, ?)",
                (ticket_id, stage, note, db.iso(ts)),
            )

        voters = [n for n in range(1, len(STUDENT_NAMES) + 1) if n != owner]
        voters = voters[i % len(voters):] + voters[:i % len(voters)]
        for n in voters[:votes]:
            conn.execute(
                "INSERT INTO upvotes (ticket_id, student_id, created_at) VALUES (?, ?, ?)",
                (ticket_id, n, db.iso(created + timedelta(hours=1 + n % 5))),
            )

    # ---- chat ----
    for mins, role, uid, name, text in CHAT_SEED:
        conn.execute(
            "INSERT INTO chat_messages (role, user_id, name, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (role, uid, name, text, db.iso(now - timedelta(minutes=mins))),
        )

    conn.commit()
    counts = {r["status"]: r["c"] for r in conn.execute("SELECT status, COUNT(*) c FROM tickets GROUP BY status")}
    conn.close()
    print("Seeded 24 synthetic tickets (CF-1001 to CF-1024):", counts)
    print(f"Students : STU1001 to STU{1000 + len(STUDENT_NAMES)}  | password: {DEMO_PASSWORD}")
    print(f"Staff    : STAFF101 to STAFF{100 + len(STAFF_SEED)}   | password: {STAFF_PASSWORD}")
    print("Admin    : admin / admin123")
    print("Tips     : CF-1004 has 9 upvotes (one more = auto-Critical).")
    print("           CF-1003 has an After photo waiting in the Admin 'Verification' tab.")
    print("           STAFF101 / STAFF104 / STAFF102 each have a ticket to 'Start work'.")


if __name__ == "__main__":
    main()
