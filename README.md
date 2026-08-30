# Brasaland Digital — Monorepo

Full-stack platform for Brasaland Digital (grilled-food restaurant chain,
Colombia/Florida): a FastAPI backend and four Next.js frontends,
containerized with Docker Compose.

## Running this project

```bash
cp .env.example .env   # fill in real values first
docker compose up --build
```

Website: `http://localhost:3000` · Backoffice: `http://localhost:3001` ·
API docs: `http://localhost:8000/docs`

## Structure

```
services/api/                    FastAPI backend — auth, suppliers, incidents, inventory
uis/
  website/                       Public site
  backoffice/                    Internal admin — the only app with its own login
  incidents/                     CSV analyzer + incident manager
  talent-pipeline-tracker/       Candidate tracking
packages/shared/                 Code shared across services and scripts (Python + TS types)
scripts/                         Standalone CLI scripts (analyze.py, seed_incidents.py)
```

## Documentation

- `services/api/README.md` — backend setup, endpoints, business rules
- `uis/README.md` — frontend apps, ports, Docker specifics
- `CONTEXT.md` — Brasaland's business context