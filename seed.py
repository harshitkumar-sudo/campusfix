"""Reset the database and insert ~24 synthetic tickets (no real personal data).

Usage:  python seed.py
"""
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

import database as db

DEMO_PASSWORD = "student123"
STUDENT_NAMES = [
    "Aarav Mehta", "Diya Nair", "Kabir Sethi", "Ishita Rao", "Rohan Das",
    "Meera Joshi", "Vihaan Gupta", "Anaya Iyer", "Arjun Reddy", "Saanvi Kulkarni",
    "Yash Malhotra", "Tara Bose", "Dev Chauhan", "Riya Menon", "Neil Fernandes",
]
# ticket index -> number of upvotes (index 3 = CF-1004 is one vote away from Critical)
SPECIAL_VOTES = {3: 9, 6: 11}

STAFF_BY_CATEGORY = {
    "Wi-Fi & Connectivity": db.STAFF[0],
    "AV Equipment": db.STAFF[1],
    "Utilities & Power": db.STAFF[2],
    "Sanitation & Facilities": db.STAFF[3],
    "Infrastructure": db.STAFF[4],
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


def stage_note(status, wing, room):
    return {
        "Submitted": "Complaint submitted",
        "Under Review": "Reviewed by admin and prioritized",
        "In Progress": f"Maintenance staff dispatched to Wing {wing}, Room {room}",
        "Resolved": "Issue fixed and verified on site",
    }[status]


def main():
    db.init_db(reset=True)
    conn = db.connect()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    pw_hash = generate_password_hash(DEMO_PASSWORD, method=db.HASH_METHOD)
    for n, name in enumerate(STUDENT_NAMES, start=1):
        conn.execute(
            "INSERT INTO students (id, name, roll_no, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (n, name, f"STU{1000 + n}", pw_hash, db.iso(now - timedelta(days=14))),
        )

    for i in range(24):
        category = db.CATEGORIES[i % 5]
        wing, room = LOCATIONS[i]
        description = DESCRIPTIONS[category][(i // 5) % 5]
        status, urgency = STATUS_PLAN[i], URGENCY_PLAN[i]
        assigned = STAFF_BY_CATEGORY[category] if status in ("In Progress", "Resolved") else None

        created = now - timedelta(days=12 - i // 2, hours=(i * 5) % 24)
        stages = db.STATUSES[: db.STATUSES.index(status) + 1]
        last_ts = created
        ticket_id = f"CF-{1001 + i}"

        owner = (i % len(STUDENT_NAMES)) + 1
        votes = SPECIAL_VOTES.get(i, (i * 3) % 7)
        escalated = 1 if i == 6 else 0
        conn.execute(
            """INSERT INTO tickets (id, ticket_id, category, wing, room, description, photo_filename,
                                    status, urgency, assigned_to, created_at, updated_at,
                                    student_id, upvote_count, auto_escalated)
               VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (i + 1, ticket_id, category, wing, room, description, status, urgency, assigned,
             db.iso(created), db.iso(created), owner, votes, escalated),
        )
        voters = [n for n in range(1, len(STUDENT_NAMES) + 1) if n != owner]
        voters = voters[i % len(voters):] + voters[:i % len(voters)]
        for n in voters[:votes]:
            conn.execute(
                "INSERT INTO upvotes (ticket_id, student_id, created_at) VALUES (?, ?, ?)",
                (ticket_id, n, db.iso(created + timedelta(hours=1 + n % 5))),
            )
        for k, stage in enumerate(stages):
            last_ts = created + timedelta(hours=5 * k + (i % 3))
            conn.execute(
                "INSERT INTO ticket_history (ticket_id, status, note, timestamp) VALUES (?, ?, ?, ?)",
                (ticket_id, stage, stage_note(stage, wing, room), db.iso(last_ts)),
            )
            if escalated and k == 0:
                conn.execute(
                    "INSERT INTO ticket_history (ticket_id, status, note, timestamp) VALUES (?, ?, ?, ?)",
                    (ticket_id, stage, "Auto-escalated to Critical priority (10 upvotes)",
                     db.iso(created + timedelta(hours=3))),
                )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE ticket_id = ?", (db.iso(last_ts), ticket_id))

    conn.commit()
    counts = {r["status"]: r["c"] for r in conn.execute("SELECT status, COUNT(*) c FROM tickets GROUP BY status")}
    conn.close()
    print("Seeded 24 synthetic tickets (CF-1001 to CF-1024):", counts)
    print(f"Seeded {len(STUDENT_NAMES)} demo students: STU1001 to STU{1000 + len(STUDENT_NAMES)}, password: {DEMO_PASSWORD}")
    print("Tip: CF-1004 has 9 upvotes. Register a new student and upvote it to see auto-Critical.")


if __name__ == "__main__":
    main()
