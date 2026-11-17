-- CampusFix database schema (SQLite)
-- Existing databases are upgraded automatically by database.py (_migrate).

CREATE TABLE IF NOT EXISTS students (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    roll_no         TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    chat_ban_until  TEXT                                -- chat ban expiry (UTC ISO), NULL = not banned
);

CREATE TABLE IF NOT EXISTS staff (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    login_id       TEXT,                                -- email or staff ID (stored lower-case)
    password_hash  TEXT,
    department     TEXT,                                -- specialty: Electrician, Plumber, ...
    created_at     TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id             TEXT    NOT NULL UNIQUE,      -- CF-1001, CF-1002, ...
    category              TEXT    NOT NULL,
    wing                  TEXT    NOT NULL,
    room                  TEXT    NOT NULL,
    description           TEXT    NOT NULL,
    photo_filename        TEXT,                         -- "Before" photo (from the student)
    status                TEXT    NOT NULL DEFAULT 'Submitted',
    urgency               TEXT    NOT NULL DEFAULT 'Medium',
    assigned_to           TEXT,                         -- legacy column, no longer used
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL,
    student_id            INTEGER REFERENCES students(id),
    upvote_count          INTEGER NOT NULL DEFAULT 0,
    auto_escalated        INTEGER NOT NULL DEFAULT 0,   -- 1 once upvotes made it Critical
    assigned_staff_id     INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    after_photo_filename  TEXT,                         -- "After" proof photo (from staff)
    completed_at          TEXT,                         -- when staff uploaded the proof
    resolved_at           TEXT                          -- when the ticket became Resolved
);

CREATE TABLE IF NOT EXISTS ticket_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    status      TEXT NOT NULL,
    note        TEXT,
    timestamp   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS upvotes (
    ticket_id   TEXT    NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL,
    PRIMARY KEY (ticket_id, student_id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role        TEXT    NOT NULL,                       -- student | staff | admin
    user_id     INTEGER NOT NULL DEFAULT 0,
    name        TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_status   ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_urgency  ON tickets(urgency);
CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category);
CREATE INDEX IF NOT EXISTS idx_tickets_location ON tickets(wing, room);
CREATE INDEX IF NOT EXISTS idx_history_ticket   ON ticket_history(ticket_id);
