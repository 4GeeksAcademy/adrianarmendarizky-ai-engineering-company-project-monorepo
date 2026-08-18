# Testing — Authentication API (AUTH-088)

Unit tests for `services/api`'s authentication surface: registration, login,
token validation, `/users` CRUD, `/profiles/me`, and password reset/change.
Tests assert business logic (status codes, response data, side effects) —
not HTTP serialization or framework internals.

## How to run

```bash
cd services/api
uv sync                      # installs pytest, pytest-cov, httpx (added as dev deps)
uv run pytest                # run the suite
uv run pytest --cov          # run with coverage
```

No `.env` is needed to run the tests — `tests/conftest.py` sets a throwaway
`JWT_SECRET_KEY` and points TinyDB at an in-memory store before the app is
imported, so the suite never touches the real `db.json` or a real email
provider.

## Isolation strategy

Two things made this app hard to test as-is, both handled in
`tests/conftest.py`:

1. **`JWT_SECRET_KEY` is required at import time** (`security.py` raises if
   it's unset). `conftest.py` sets a dummy value as the very first thing it
   does, before any app module is imported.
2. **`database.py` is a single global `TinyDB(DB_PATH)` instance**, and
   `user_service.py` / `password_service.py` import its tables directly
   (`from database import users_table`) — patching `database.users_table`
   after the fact wouldn't reach those already-bound references. Instead,
   `conftest.py` monkeypatches `tinydb.TinyDB.__init__` itself to always use
   `tinydb.storages.MemoryStorage`, before `database.py` (or anything that
   imports it) is ever imported. Every table created anywhere in the app
   then lives in memory for the life of the test process. A function-scoped
   autouse fixture calls `database.db.drop_tables()` before each test so
   tests don't see each other's data.

`email_service.send_password_reset_email` is monkeypatched to a no-op in
the password-reset tests — there's no network access to Resend in the test
environment, and the point of these tests is the token lifecycle, not
whether a real email provider is reachable.

## Test plan

### `test_register.py` — `POST /users`
- **Happy path**: valid email + password (+ optional profile fields) → 201,
  response is `UserPublic` shape (no `hashed_password` in the body), linked
  profile created with the submitted fields.
- **Edge case**: registering with no optional profile fields → 201, profile
  still created with `name`/`phone`/`address` all `None` (not skipped).
- **Failure modes**: password under 8 chars → 422; missing required field
  (`email` or `password` omitted) → 422; registering the same email twice →
  409.

### `test_login.py` — `POST /auth/login`
- **Happy path**: correct email + password → 200, `access_token` +
  `token_type: bearer`; the returned token works immediately on a protected
  route.
- **Edge case**: wrong password and unknown email return the *same* 401
  detail message — confirms the "don't leak which emails are registered"
  behavior actually holds.
- **Failure mode**: wrong password → 401.

### `test_token.py` — token validation via `GET /auth/me` and `get_current_user`
- **Happy path**: valid bearer token → 200 with email/role/profile.
- **Edge case**: token is well-formed and unexpired but points to a user
  that's since been deleted → 401 (not a 500).
- **Failure modes**: no `Authorization` header → 401; malformed/garbage
  token → 401; expired token (built with a negative expiry) → 401.

### `test_users.py` — `/users` CRUD (list, get, update, delete)
- **Happy path**: authenticated `GET /users` and `GET /users/{id}` return
  expected data; a user updating their own email via `PUT /users/{id}`
  succeeds.
- **Edge case**: an admin can update another user's record; updating your
  *own* email to one already registered to someone else is 409, not 403 —
  the ownership check passes (it's your own record), it's the
  duplicate-email check that fails.
- **Failure modes**: no token on any of the four routes → 401; non-owner,
  non-admin `PUT` on someone else's record → 403; `GET`/`PUT`/`DELETE` on a
  nonexistent id → 404.

### `test_profiles.py` — `/profiles/me`
- **Happy path**: `GET /profiles/me` returns the profile created at
  registration; `PUT /profiles/me` with one field updates only that field.
- **Edge case**: `PUT` with an empty body leaves the profile unchanged.
- **Failure mode**: either route with no token → 401.

### `test_password_reset.py` — `POST /auth/forgot-password`, `POST /auth/reset-password`
- **Happy path**: `forgot-password` for a real email generates a reset
  token and triggers the (mocked) email; `reset-password` with that token
  actually changes the password — confirmed by logging in with the new
  password.
- **Edge case**: `forgot-password` for an email that doesn't exist returns
  the exact same 200 message and does **not** trigger an email — confirms
  the anti-enumeration behavior.
- **Failure modes**: `reset-password` with a garbage token → 400;
  `reset-password` with a token that's already been consumed once → 400
  (can't be reused).

### `test_change_password.py` — `POST /auth/change-password`
- **Happy path**: correct current password + valid new password → 200,
  can log in with the new password afterward.
- **Edge case**: new password under 8 chars → 422 (rejected before the
  handler even runs).
- **Failure modes**: wrong current password → 400; no token → 401.

## AI-assisted workflow notes

Test cases above were identified by walking each route's actual logic
(status codes, service-layer exceptions, and the specific edge cases the
code comments call out — e.g. the identical 401 message for unknown-email
vs. wrong-password, the 403-vs-409 ordering in `PUT /users/{id}`) rather
than guessing from the endpoint names alone. Test boilerplate (fixtures,
`TestClient` setup) was AI-generated and reviewed before being committed.

No bugs were found by the test suite as of this writing — every case above
was written to confirm existing, already-correct behavior (auth status
codes were explicitly re-confirmed rather than "fixed," per the codebase's
own comments that they're correct as-is). If a test reveals an actual bug
during review, it will be noted here alongside the fix.

## Coverage

Target: ≥70% on the authentication module. Current result from
`uv run pytest --cov` (auth-relevant files only — `routes/auth.py`,
`routes/users.py`, `routes/profiles.py`, `security.py`, `dependencies.py`,
`user_service.py`, `password_service.py`, `user_models.py`, `database.py`):

| File | Coverage |
|---|---|
| `routes/auth.py` | 100% |
| `routes/users.py` | 100% |
| `routes/profiles.py` | 83% |
| `security.py` | 96% |
| `dependencies.py` | 95% |
| `user_service.py` | 95% |
| `password_service.py` | 100% |
| `user_models.py` | 100% |
| `database.py` | 100% |

Weighted average across those files: ~95%, well above the 70% target.
`suppliers`/`incidents` modules show lower coverage in the full report —
expected, since they're out of scope for this ticket (see API-042, deferred).
`email_service.py` sits at 50%: the reset-email trigger path is exercised,
but the internal Resend-calling branch isn't, since that's infrastructure
plumbing rather than authentication business logic and there's no network
access to a real provider in this environment.

## Deferred (extra credit, not part of this deliverable)

`API-042` (pytest tests for ≥2 non-auth backoffice endpoint groups) and
`FE-019` (Jest tests for ≥3 frontend utility functions) are separate,
low-priority tickets on the same board. Deliberately not started yet —
picking these up after AUTH-088 is done.
