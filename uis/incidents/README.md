# Brasaland Incidents — Web

Next.js frontend for the Incident Manager. Talks to `services/api` over HTTP — no code is imported directly between them.

## Pages

- `/` — upload a historical CSV, view analysis, export results
- `/register` — register a new incident
- `/list` — view/filter incidents, update status
- `/summary` — aggregated metrics by status, category, origin, and branch

## Auth

This app has no login of its own. Every page requires a valid session from `uis/backoffice` — you're redirected there automatically if you don't have one, and returned here once logged in.

## Running it locally

Three services need to be running together:

```bash
# services/api (port 8000)
uv run uvicorn main:app --reload

# uis/backoffice (port 3000)
npm run dev

# uis/incidents (port 3001, pinned in package.json)
npm install
npm run dev
```

Open `http://localhost:3001`.

## GitHub Codespaces

If requests to the API fail — `net::ERR_CONNECTION_REFUSED`, or a 404 on a URL with a double slash before `api` — the frontend is pointed at the wrong host or a malformed one:

1. Copy `.env.example` to `.env.local` (gitignored — your own machine's setting, not committed).
2. Set `NEXT_PUBLIC_API_URL` to port 8000's forwarded URL from the Ports tab, **no trailing slash**.
3. Restart `npm run dev` — env files only load on startup, not live.
4. Confirm `services/api` is running and its CORS settings allow your Codespace URL (see `services/api/README.md`).