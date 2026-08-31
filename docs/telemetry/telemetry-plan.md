# Brasaland Telemetry Plan

Design document for instrumenting the inventory management system and
surrounding backoffice. No code changes ship with this document — it is
the contract the Capture (Phase 2), Storage (Phase 3), and Report
(Phase 4) projects will build against.

---

## 1. The Event Envelope

Every event, mandatory or identified, carries the same seven fields.
Nothing outside this envelope plus each event's own `properties`
allowlist is ever sent.

| Field | Type | Nullable? | Meaning |
|---|---|---|---|
| `eventId` | string (UUID) | no | Generated at the moment of capture, not at send time. |
| `timestamp` | string (ISO 8601, UTC) | no | The moment of capture. |
| `sessionId` | string | no | Generated once when the frontend app loads — **not** at login. See note below. |
| `userId` | string \| null | key always present | The authenticated user's id. Null until login succeeds. |
| `event_type` | string | no | `entity_action` naming, e.g. `inbound_order_created`. |
| `schemaVersion` | integer | no | Starts at `1` per event type. Bump only on a breaking change to that event's `properties` allowlist (a field removed, renamed, or changed type). Adding a new optional field does not require a bump. |
| `requestId` | string (UUID) \| null | key always present | Correlates one event to one backend API call. Null for events with no single corresponding request (e.g. `section_visited`). |
| `properties` | object | no | Event-specific payload. Allow-listed per event — see Section 3. No additional keys permitted. |

**Why `sessionId` is not tied to login:** the mandatory catalogue
requires a `user_login_failed` event. A failed login happens *before*
authentication succeeds, so if `sessionId` were only generated at
login, a failed attempt would have no session to correlate against —
you'd lose the ability to see "3 failed attempts then 1 success" as
one sequence. Generating it once per app load (kept in memory,
matching the "usage data is append-only, never mixed with persistent
profile state" rule) fixes that without weakening anything the spec
asks for.

---

## 2. What "Mandatory" Actually Means Here

`CONTEXT-brasaland.md` gives 6 mandatory `event_type`s. Checking each
against the actual code in this fork (not the aspirational company
brief) shows only 2 of the 6 are instrumentable today without first
changing the data model. This plan documents all 6 as mandatory —
per the brief, they are a floor regardless of what exists yet — but
marks each one's real status honestly rather than pretending a event
is ready when the data it needs doesn't exist.

**A cross-cutting blocker affects all 6:** every mandatory event needs
`country` (to derive `currency`), and there is currently no reliable
way to get from inventory's `location_id` (a bare `int`, "not a FK,
location data lives elsewhere" per `inventory_models.py:44`) to a
country. The incidents feature already has a real, authoritative
14-location list (`COL-01`–`COL-10`, `FLA-01`–`FLA-04`, see
`scripts/seed_incidents.py:67-82`) — but inventory's `location_id`
was never wired to it, and the existing seed data (`location_id=8`
receiving a Miami delivery, `seed_inventory.py:69`) doesn't fit any
simple numeric range split either. Rather than invent a mapping that
could quietly be wrong, this plan treats `country` as **nullable at
capture time**, populated only once inventory adopts the existing
`COL-NN`/`FLA-NN` codes as its location identifier — recommended,
since building a second, competing scheme would make this worse, not
better. Until then, `country` (and `currency`, derived from it) is
`null`, and downstream consumers (Report, later the exec dashboard)
must treat null as "not yet resolvable," not "unknown location."

| `event_type` | Ready today? | What's missing |
|---|---|---|
| `inbound_order_created` | Yes | — |
| `outbound_order_created` | Yes | — |
| `stock_waste_registered` | Partial | Needs a new optional `waste_reason` field on `IngredientExitCreate` (`inventory_schemas.py:44`) — `expired`/`kitchen_error`/`theft_suspected`. Must default to `None` so existing "waste" exits without a subtype keep working. |
| `stock_threshold_triggered` | No | Needs a new optional `minimum_stock` field on `Ingredient` (`inventory_models.py:25`), default `None`. Event only evaluates for ingredients where it's set. |
| `direct_stock_edit_rejected` | No | No endpoint accepts a stock-modifying field to reject — today the rule is enforced by that field simply not existing in `IngredientCreate`. Firing this event requires a future endpoint that explicitly accepts and rejects one. |
| `ingredient_price_variance_detected` | No | No cost data is captured anywhere — needs a new optional `unit_cost` field on `IngredientEntryCreate`, plus a stored or computed historical average per product+supplier to compare against. |

Every new field above is proposed as **optional with a `None`
default**, specifically so `seed_inventory.py`'s existing constructor
calls keep working unmodified.

---

## 3. Full Event Catalogue

Standard inventory `properties` (per `CONTEXT-brasaland.md` Section
3): `location_id`, `country`, `product_id`, `product_category`,
`quantity`, `unit`, `currency`. No employee names or customer data in
any event — these describe products and locations, not people.

### 3.1 Mandatory (6)

**`inbound_order_created`** — batch — `routes/inventory.py:104-121`
*We capture this because we need to know how much and what is being
purchased, by location and supplier, which lets us consolidate
purchasing across locations to negotiate better prices (Lucía).*
Properties: `location_id`, `country` (nullable, see §2), `product_id`,
`product_category`, `quantity`, `unit`, `currency` (nullable),
`supplier_name`.

**`outbound_order_created`** — batch — `routes/inventory.py:124-151`,
`reason="consumption"`
*We capture this because we need to know which ingredients are
consumed most, and at what rate, by location, which lets us adjust
the automatic supplier order suggestion (Felipe).*
Properties: `location_id`, `country` (nullable), `product_id`,
`product_category`, `quantity`, `unit`.

**`stock_waste_registered`** — batch — same endpoint,
`reason="waste"`
*We capture this because we need to know how much product is lost,
why, and at which location, which lets us prioritise waste audits at
the worst-performing locations (Felipe).*
Properties: `location_id`, `country` (nullable), `product_id`,
`product_category`, `quantity`, `unit`, `waste_reason` (nullable
until the schema addition in §2 ships).

**`stock_threshold_triggered`** — stream (Felipe needs to reorder
before a stockout hits service) — blocked, see §2
*We capture this because we need to know how often a location runs
short of a key ingredient, which lets us adjust the minimum threshold
or replenishment frequency for that product.*
Properties: `location_id`, `country` (nullable), `product_id`,
`product_category`, `current_stock`, `minimum_stock`.

**`direct_stock_edit_rejected`** — batch (compliance review, not
urgent) — blocked, see §2
*We capture this because we need to know if staff are attempting to
bypass traceability controls, which lets us reinforce training or
permissions at the locations where this happens most (Jake).*
Properties: `location_id`, `country` (nullable), `product_id`,
`attempted_field`, `attempted_value`.

**`ingredient_price_variance_detected`** — stream (price spikes need
to surface before more orders are placed at the bad price) — blocked,
see §2
*We capture this because we need to know when a key ingredient rises
in price abnormally, which lets us alert Lucía and Mariana to
renegotiate or find an alternate supplier.*
Properties: `location_id`, `country` (nullable), `product_id`,
`product_category`, `supplier_name`, `unit_cost`,
`historical_avg_cost`, `variance_pct`, `currency` (nullable).

### 3.2 Identified — Business (1)

**`product_created`** — batch — `routes/inventory.py:82-93`
*We capture this because we need to know how often new SKUs are
added, which lets us tell whether catalogue growth is deliberate or
ad hoc, and whether a formal product-approval step is worth adding.*
Properties: `product_id`, `product_category`, `country` (this one
comes directly from `Ingredient.country` — the product's own sourcing
market, a real field that already exists; see the note below on why
this is a *different* `country` than the inventory events above).

> **Note:** `Ingredient.country` (`inventory_models.py:31`) is the
> product's own sourcing market (e.g. brisket is always seeded as
> `"CO"`) — it is not the selling location's country and must never
> be used to derive currency for an order event. This is exactly the
> kind of same-name-different-meaning trap this plan exists to catch
> before instrumentation code is written.

### 3.3 Identified — Authentication (4)

**`user_login_succeeded`** — stream — `routes/auth.py:40-49`
*We capture this because we need to know login volume/patterns over
time, which feeds the `auth_failure_rate` metric in the Report
project.* No properties beyond the envelope (`userId` already
identifies who).

**`user_login_failed`** — stream — `routes/auth.py:43-46`
*We capture this because we need to know how often auth fails and
why, which lets us spot brute-force attempts or login-UX friction.*
Properties: `failure_reason` (`invalid_credentials` /
`session_expired` / `network_error`). **Never** the email or password
value entered.

**`password_reset_requested`** — batch — `routes/auth.py:69-79`
*We capture this because we need to know how often users need
password recovery, which signals a login/memorability UX problem if
it spikes.* No properties (no email — see PII note in §4).

**`password_changed`** — batch — `routes/auth.py:92-102`
*We capture this as a low-priority hygiene baseline.* No properties.

### 3.4 Identified — Cross-Cutting Technical Baseline (3)

These three are explicitly required by the Capture project regardless
of depth elsewhere, so they're locked into the Plan now rather than
left as an afterthought.

**`frontend_error_occurred`** — stream (errors should surface fast on
a live system) — from `window.onerror` / `unhandledrejection`
*We capture this because we need to know how often and where uncaught
errors happen, which lets us prioritise bug triage by frequency and
location.*
Properties: `error_message` (truncated, sanitised — never a raw stack
trace that could contain user input), `page_path`.

**`api_latency_recorded`** — batch — after any backend call completes
*We capture this because we need to know which endpoints are slow and
whether that changes by time or location, which lets us prioritise
performance work.*
Properties: `endpoint`, `duration_ms`, `status_code`.

**`section_visited`** — batch — on backoffice route change
*We capture this because we need to know which sections operators
actually use, which lets us invest UX effort where it matters and
deprioritise unused features.*
Properties: `route`.

---

## 4. Delivery Strategy

Stream (real time): `stock_threshold_triggered`,
`ingredient_price_variance_detected`, `user_login_succeeded`,
`user_login_failed`, `frontend_error_occurred`. Justification for
each is stated inline above — all five feed a decision that loses
value if it waits (a stockout, a bad price locked into more orders, a
security signal, an active bug).

Batch (periodic): everything else. These feed trend analysis
(purchasing patterns, waste audits, UX prioritisation) where seeing
one event instantly adds no decision value over seeing it within the
next flush cycle.

**Throttle/debounce:** `frontend_error_occurred` is deduplicated
client-side — the same `error_message` + `page_path` firing
repeatedly (e.g. a render-loop bug) is capped rather than sent on
every occurrence, so one bug doesn't flood the batch. `api_latency_recorded`
is captured at 100% today given current traffic volume; sampling
should be revisited if call volume grows enough to make every-request
capture expensive.

---

## 5. Risks and Exclusions

- **Location/country resolution is unresolved** (§2). Three mandatory
  events are fully blocked and three more carry a nullable `country`
  until inventory adopts the `COL-NN`/`FLA-NN` scheme the incidents
  feature already established. This is the single biggest open item
  in this plan.
- **No PII.** No employee names, emails, or passwords in any
  `properties` object. `user_login_failed` captures *why* a login
  failed, never *what* was typed. `frontend_error_occurred` messages
  must be sanitised before capture, since a raw stack trace can
  contain form input.
- **Sales, loyalty, HR, and training systems don't exist yet.**
  Per the tech lead's message, this plan is scoped to the inventory
  system and the rest of the backoffice that's actually in
  production — not the aspirational systems described in the general
  Brasaland company brief.
- **Any future Storage implementation must not raise when
  `DATABASE_URL` is unset.** `init_inventory_db()`
  (`database.py:56-68`) deliberately no-ops in that case, specifically
  because the full test suite boots the app via `TestClient(app)`
  without setting it (`tests/conftest.py:75-77`). A telemetry table
  setup that raises instead of skipping would break every existing
  auth/user/profile test, not just telemetry.
- **Pandas is not yet a project dependency.** The Report project will
  need it added to `pyproject.toml`; not a concern for this plan, but
  worth knowing ahead of time.
