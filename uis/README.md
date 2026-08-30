# Brasaland UIs

Four independent Next.js apps — separate `package.json`, `node_modules`,
and dev server each, no shared workspace tooling. Only `backoffice` has
its own login (`/login`, `/register`); `incidents` and
`talent-pipeline-tracker` have none of their own and redirect there,
getting a token handed back (see `uis/backoffice/README.md` for that
handoff).

| App | Local dev port | Purpose |
|---|---|---|
| `website` | 3000 (default, unpinned in `package.json`) | Public-facing site, job applications |
| `backoffice` | 3000 (pinned) | Internal admin — auth, suppliers, inventory, accounts |
| `incidents` | 3001 (pinned) | CSV analyzer + incident manager |
| `talent-pipeline-tracker` | 3002 (pinned) | Candidate tracking |

`website` and `backoffice` both land on 3000 by default — they were never
set up to run side by side locally.

## Docker (website + backoffice only)

`docker compose up` from the repository root containerizes `website` and
`backoffice` together in a single container, per ticket infra-40 — see
the root `docker-compose.yml` and `uis/Dockerfile`. Inside that setup,
ports are reassigned so both apps can run at once:

| App | Docker port |
|---|---|
| `website` | 3000 |
| `backoffice` | 3001 |

**This means `docker compose up` and `cd uis/incidents && npm run dev`
can't run at the same time** — both would try to bind host port 3001.
`incidents` and `talent-pipeline-tracker` aren't in Docker's scope (this
ticket never touches them), so they still run locally as usual — just not
alongside the Dockerized UI container. This is a known, accepted tradeoff
of infra-40's scope, not a bug.