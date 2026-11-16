-- CampusFix database schema (SQLite)

CREATE TABLE IF NOT EXISTS students (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    roll_no        TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id       TEXT    NOT NULL UNIQUE,            -- CF-1001, CF-1002, ...
    category        TEXT    NOT NULL,
    wing            TEXT    NOT NULL,
    room            TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    photo_filename  TEXT,
    status          TEXT    NOT NULL DEFAULT 'Submitted',
    urgency         TEXT    NOT NULL DEFAULT 'Medium',
    assigned_to     TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    student_id      INTEGER REFERENCES students(id),    -- who reported it
    upvote_count    INTEGER NOT NULL DEFAULT 0,
    auto_escalated  INTEGER NOT NULL DEFAULT 0          -- 1 once upvotes made it Critical
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

CREATE TABLE IF NOT EXISTS staff (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_tickets_status   ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_urgency  ON tickets(urgency);
CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category);
CREATE INDEX IF NOT EXISTS idx_tickets_location ON tickets(wing, room);
CREATE INDEX IF NOT EXISTS idx_history_ticket   ON ticket_history(ticket_id);
