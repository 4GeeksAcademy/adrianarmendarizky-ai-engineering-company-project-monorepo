# Progress — Brasaland Monorepo

_Update this file every time the project evolves: new decisions, completed features, problems encountered. A memory bank that is not kept current stops being useful within days._

Last updated: 2026-10-20 (capstone submission).

## Current state

The Brasaland Backoffice Suite is complete. The 5-minute pitch video is recorded and delivered. The live defense is on Friday 2026-10-23.

## Completed

- **Foundations:** public website (`uis/website`), TypeScript business-logic layer (`src/`), Talent Pipeline Tracker, agent infrastructure (memory bank, `AGENTS.md`, `.agents/`).
- **Backend and login:** FastAPI app (`services/api`) with JWT login, roles (admin, manager, user), password reset, and unit tests.
- **Everyday tools:** suppliers directory, incident analysis and incident manager, inventory (Supabase Postgres), weekly cost and waste Reporting page fed by a data pipeline, event telemetry.
- **Platform:** Docker Compose (api, ui, redis, qdrant, worker, flower), background jobs (Celery and Redis), nightly export job, error-handling audit.
- **AI features:**
  - Knowledge Base (RAG over four manuals, 30 chunks in Qdrant) and a LangGraph support agent with memory, guardrails, and a read-only MCP client.
  - RFP workflow: intake, drafting with automatic checks, and approvals by team owners and the CEO.
  - Revenue forecast: Random Forest model with evaluation (`data/eval/`).
- **Real time:** live RFP notifications (SSE) and streaming chat (WebSocket).
- **Security:** NIST secure-practices report and OWASP Top 10 audit (`docs/`).

## Capstone work (branch `feature/capstone-final`)

- Codespaces setup: `.devcontainer/`, `scripts/codespace-up.sh`, two `.dockerignore` files, `docker-compose.yml` changes.
- Backoffice: RFP file-input styling, dashboard key-metric cards (Menu items card replaced by Total revenue, "out of N locations").
- `src/types/models.ts`: sample data expanded (14 locations, 58 sales) for the demo.
- Root `README.md` rewritten for the Brasaland Backoffice Suite, with the demo video folder link.
- Reporting demo rows were inserted directly into the database (not in git).

## Known limits and watch-items

- The MCP server is not part of `docker-compose.yml`, so ticket and inventory lookups in the support agent are not available in the compose setup.
- The knowledge base must be reloaded into Qdrant after a rebuild that clears it.
- The input guard is a blocklist (English and Spanish); a new phrasing could slip past it. The relevance cutoff (0.27) was measured on 10 questions.
- The Reporting pipeline only maps locations 1 (Colombia) and 8 (USA). Re-running it for a week overwrites rows for the same location and week.
- The RFP workflow never invents prices and does not check venue capacity.
- Root `node_modules/` is tracked in git. It should be removed from tracking and added to `.gitignore`.

## Next steps

- Live defense on Friday 2026-10-23.
- Proposed, not built: supplier-ordering assistant, matching each RFP to a location by capacity and date, holiday signals and per-location ingredient forecasts.