# Brasaland Digital — Backend API (`services/api/`)

Single FastAPI app (`main:app`) covering user accounts, suppliers, and
after-sales incident analysis for Brasaland Digital.

## Setup

```bash
uv sync
uv run uvicorn main:app --reload
```

Seeds supplier data automatically on first run if empty. Interactive docs
at `http://localhost:8000/docs`.

### Environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `JWT_SECRET_KEY` | Signs session tokens — never commit a real value |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session token lifetime |
| `RESEND_API_KEY` | Sends password reset emails via [Resend](https://resend.com) |
| `RESEND_FROM_EMAIL` | Defaults to `onboarding@resend.dev` (can only deliver to your own Resend account's email without a verified domain) |
| `FRONTEND_URL` | Backoffice's own URL — used to build the link inside reset emails |
| `PASSWORD_RESET_EXPIRE_MINUTES` | Reset token lifetime (default 30) |

### Running in GitHub Codespaces

If `uis/backoffice` (or any other frontend) is accessed via a forwarded
`*.app.github.dev` URL rather than `localhost`, port 8000 must be set to
**Public** in the Ports tab — a Private port blocks browser `fetch` calls
behind a GitHub auth wall, which surfaces as a CORS error even though the
real cause is port visibility. CORS itself already allows any
`*.app.github.dev` origin (see `main.py`), so no code change is needed.

---

## Authentication

JWT-based. `POST /users` registers (public); everything else under
`/users` requires a token. `/auth/login` issues one; `/auth/me` returns
the caller's own account.

| Method | Path | Notes |
|---|---|---|
| POST | `/users` | Register (public) |
| GET / PUT / DELETE | `/users`, `/users/{id}` | Protected; `PUT` restricted to self or admin |
| POST | `/auth/login` | Public, returns a token |
| GET | `/auth/me` | Protected |
| GET / PUT | `/profiles/me` | Protected, owner only |

## Password reset and change

Reset tokens are random strings, not JWTs — only their hash is stored, and
each is invalidated after one use (or when the password changes any other
way).

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/forgot-password` | Public. Always returns 200 — never reveals whether the email is registered |
| POST | `/auth/reset-password` | Public. Takes the emailed token + new password; 400 if invalid/expired/already used |
| POST | `/auth/change-password` | Protected. Requires the current password |

---

## Suppliers

Replaces Procurement's shared spreadsheet — FastAPI + TinyDB, paired with
`uis/backoffice/app/(protected)/suppliers/`.

**Business rules:** currency must match country (Colombia → COP, USA →
USD); `categories` needs at least one of 8 fixed values; `rate_per_unit` >
0; suppliers are suspended, not deleted, in normal use; every rate change
stamps `updated_at`. All routes require a session token.

| Method | Path | Description |
|---|---|---|
| POST | `/suppliers` | Create |
| GET | `/suppliers` | List (`?country=`, `?category=` filters) |
| GET | `/suppliers/{id}` | One (404 if missing) |
| PATCH | `/suppliers/{id}/rate` | Update rate, stamps `updated_at` |
| PATCH | `/suppliers/{id}/status` | Activate/suspend (422 on invalid value) |
| DELETE | `/suppliers/{id}` | Correct bad data (404 if missing) |

### Manual test commands

```bash
curl http://localhost:8000/suppliers
curl "http://localhost:8000/suppliers?country=USA"
curl -i http://localhost:8000/suppliers/999          # expect 404

curl -X POST http://localhost:8000/suppliers \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Co","country":"USA","categories":["bebidas"],"rate_per_unit":5.0,"currency":"USD","status":"active"}'
```
(All require `-H "Authorization: Bearer <token>"` now — get one via `/auth/login`.)

---

## Incidents

Reuses the validation/metrics logic from `scripts/analyze.py` directly
(see `app/incidents/controller.py`) — no duplicated rules. All routes
require a session token.

| Method | Path | Description |
|---|---|---|
| POST | `/api/incidents/analyze` | Multipart CSV upload (field `file`); 400 if empty/unreadable |
| GET | `/api/incidents/results/export` | Downloads the last analysis as CSV; 404 if none yet |

No database — the last analysis lives in memory and resets on restart.

---

## Project structure

```
services/api/
├── main.py                # Single FastAPI entry point (uvicorn main:app)
├── database.py            # TinyDB connection + all tables
├── security.py            # Password hashing, JWT, reset-token hashing
├── email_service.py       # Resend integration
├── dependencies.py        # get_current_user
├── user_models.py         # Pydantic models (User, Profile, auth requests)
├── user_service.py        # User/Profile business logic
├── password_service.py    # Password reset/change business logic
├── models.py              # Supplier Pydantic models
├── seed.py                # Loads suppliers from CONTEXT-brasaland.md
├── routes/
│   ├── auth.py            # /auth/*
│   ├── users.py           # /users/*
│   ├── profiles.py        # /profiles/*
│   └── suppliers.py       # /suppliers/*
├── app/
│   └── incidents/
│       ├── controller.py  # Imports scripts/analyze.py directly
│       └── routes.py      # /api/incidents/*
└── db.json                # TinyDB data file (generated, gitignored)
```