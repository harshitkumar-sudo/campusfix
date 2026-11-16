# CampusFix: Backend (Part 1)

Flask + SQLite backend for the CampusFix campus issue reporting and tracking prototype.
All data is synthetic. No real student information is stored.

## Setup

```bash
pip install -r requirements.txt
python seed.py        # creates campusfix.db with 24 synthetic tickets
python app.py         # http://127.0.0.1:5000
```

`seed.py` can be re-run any time; it resets the database. The app also creates an empty
database automatically if `campusfix.db` does not exist.

## Demo admin login

| Username | Password   |
|----------|------------|
| admin    | admin123   |

Override with the `ADMIN_USER`, `ADMIN_PASS` and `SECRET_KEY` environment variables.
Use `PORT` to change the port and `FLASK_DEBUG=0` to turn off debug mode.

## Student accounts and upvotes

- Students must register or sign in (roll number + password) before they can use the site.
- Every complaint is linked to the student who filed it. Only administrators can see who reported it.
- The home page shows a public feed of complaints. Students can upvote an issue (one vote each, not on their own complaint, not on resolved issues).
- When an issue reaches **10 upvotes** it automatically becomes **Critical** priority (noted in its history). Un-voting does not lower it; an admin can still change urgency manually.
- `python seed.py` creates 15 demo students: `STU1001` to `STU1015`, password `student123`.
  Ticket `CF-1004` has 9 upvotes, so one more vote shows the auto-Critical change.

## Pages

| Route          | Template                     |
|----------------|------------------------------|
| `/login`       | `templates/student_login.html` |
| `/register`    | `templates/student_register.html` |
| `/`            | `templates/index.html` (login required) |
| `/report`      | `templates/report.html`      |
| `/track`       | `templates/track.html` (`?id=CF-1042`) |
| `/admin/login` | `templates/admin_login.html` |
| `/admin`       | `templates/admin_dashboard.html` (login required) |

## API

Public: `GET /api/meta`, `POST /api/student/register`, `POST /api/student/login`, `POST /api/student/logout`

Student (login required): `POST /api/tickets`, `GET /api/tickets/<ticket_id>`, `GET /api/feed`,
`POST` or `DELETE /api/tickets/<ticket_id>/upvote`

Admin (session cookie, 401 if not logged in): `POST /api/admin/login`, `POST /api/admin/logout`,
`GET /api/admin/tickets`, `PATCH /api/admin/tickets/<ticket_id>`, `GET /api/admin/stats`

Uploaded photos (PNG/JPG, max 5MB) are saved in `uploads/` and served at `/uploads/<file>`.

## Files

`app.py` (routes + API), `database.py` (queries + enums), `schema.sql` (tables), `seed.py` (demo data)
