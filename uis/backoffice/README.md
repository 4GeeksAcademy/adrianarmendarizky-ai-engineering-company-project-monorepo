# Brasaland Back Office

Internal admin app — also hosts the shared login/account views used by
Incidents and Talent Pipeline Tracker (they redirect here when a session
is missing).

Requires `NEXT_PUBLIC_API_URL` in `.env.local`, pointing at `services/api`
(defaults to `http://localhost:8000` if unset, so this is optional for
local dev against a default-port backend).

| Route | Access |
|---|---|
| `/login`, `/register`, `/forgot-password`, `/reset-password` | Public |
| `/`, `/suppliers`, `/account/profile`, `/account/change-password` | Protected |
| `/inventory/products` | Protected — ingredients with live, color-coded stock |
| `/inventory/orders/inbound` | Protected — log a delivery |
| `/inventory/orders/outbound` | Protected — log consumption/waste |
| `/inventory/orders` | Protected — read-only order history |

Every protected route is covered by `app/(protected)/layout.tsx`'s route
guard — nothing page-specific needed for auth. All network calls go
through `lib/api.ts` (auth, profile, password) or `lib/inventory.ts`
(inventory) — no component calls `fetch()` directly.

## Getting started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Requires
`services/api` running (see its own README) — every page here depends on
that backend.

Running via `docker compose up` instead? This app answers on port 3001
there, not 3000 — see `uis/README.md` for why.