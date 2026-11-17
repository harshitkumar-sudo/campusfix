# CampusFix

Flask + SQLite campus issue reporting and resolution tracking prototype.
All data is synthetic. No real student information is stored.

## Roles

| Role    | Sign in at        | What they can do |
|---------|-------------------|------------------|
| Student | `/login` (`/register` to sign up) | Report issues with a photo, track tickets, upvote problems, use the community chat |
| Staff   | `/staff/login`    | See only the tickets assigned to them, start work, upload an After photo as proof |
| Admin   | `/admin/login`    | Triage tickets, assign staff, verify fixes, manage staff accounts, moderate chat, export CSV |

The first page (`/`) is a landing screen with the four entry options. Each browser session holds one role at a time.

## Setup

```bash
pip install -r requirements.txt
python seed.py        # resets campusfix.db and fills it with demo data
python app.py         # http://127.0.0.1:5000
```

An existing `campusfix.db` is upgraded automatically on start (new tables and columns are added, old data is kept).
Old staff entries get the login `staff101`, `staff102`... with the password `staff123`.

## Demo logins (after `python seed.py`)

| Role    | ID                       | Password     |
|---------|--------------------------|--------------|
| Student | `STU1001` to `STU1015`   | `student123` |
| Staff   | `STAFF101` to `STAFF105` | `staff123`   |
| Admin   | `admin`                  | `admin123`   |

Things to try:
- `CF-1004` has 9 upvotes. One more student vote turns it **Critical** automatically.
- `CF-1003` has an After photo waiting in the Admin **Verification** tab.
- `STAFF101`, `STAFF102` and `STAFF104` each have an Under Review ticket they can **Start work** on.

## Resolution workflow

1. Student reports an issue (optional Before photo).
2. Admin assigns it to a staff member. A Submitted ticket moves to **Under Review**.
3. Staff presses **Start work** (**In Progress**), then uploads an **After photo** and marks it complete.
4. The ticket shows a Before | After comparison (feed, track page, admin) and waits for the admin.
5. Admin opens **Verification**, approves it (**Resolved**) or sends it back to staff.

## Community chat

Floating chat on the Home page for students, staff and admins (polling every few seconds, so it works with any number of gunicorn workers).
Admin and staff messages carry `[ADMIN]` / `[STAFF]` badges and highlighted colors.
Admin can pause or resume the chat, and ban a student for a number of days (from a message, or in the Chat Moderation tab).

## CSV export

Admin Dashboard, **Export Report (CSV)**: Ticket ID, Title, Category, Wing/Room, Status, Priority, Upvotes, Assigned Staff, Created Date, Resolved Date.

## Deploying on Render

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Environment variables: `SECRET_KEY` (any long random text), `ADMIN_USER`, `ADMIN_PASS`
- Run `python seed.py` once (Render shell) if you want the demo data.
- SQLite and uploaded photos live on the server disk. On the free plan the disk is wiped at every redeploy or restart,
  so attach a Render **Disk** (mounted at the project folder or `uploads/` and the database) if you need them to persist.

## Files

`app.py` (routes and API), `database.py` (queries, migration), `schema.sql` (tables), `seed.py` (demo data),
`templates/` (pages), `static/` (css, js, logo)
