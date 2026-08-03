# Brasaland Incidents — Web

Next.js frontend for the after-sales incident analysis feature. Uploads a CSV to the
`services/api` backend, shows the summary on screen, and lets you download the results as CSV.

## Running it locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`. The `services/api` backend needs to be running separately
(see `services/api/README.md`) — this app talks to it over HTTP, it doesn't import any of
its code directly.

## Running in GitHub Codespaces

If the browser can't reach `http://localhost:8000` (shows as `net::ERR_CONNECTION_REFUSED`
on the `analyze` request in the Network tab), it's because the Codespace forwards ports to a
public URL rather than true `localhost`. Fix:

1. Copy `.env.example` to `.env.local` (this file is gitignored — it's your own machine's
   setting, not something to commit).
2. In the Ports tab, copy the forwarded URL for port 8000.
3. Set `NEXT_PUBLIC_API_URL` in `.env.local` to that URL.
4. Restart `npm run dev` — env files are only read on startup, not live.
5. Make sure `services/api` is running and its CORS settings allow your Codespace's URL
   (see the note in `services/api/README.md`).
