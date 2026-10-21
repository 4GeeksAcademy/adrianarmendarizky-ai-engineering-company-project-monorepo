# Technical Context — Brasaland Monorepo

## Repository shape

A single monorepo that is the technical core of Brasaland Digital. All deliverables live here, so shared code is imported, not duplicated.

```text
├── CONTEXT.md              # Assigned company scenario (Brasaland)
├── AGENTS.md               # Agent operating protocol
├── memory-bank/            # Persistent project context for agents
├── .agents/                # Agent rules and skills
├── src/                    # TypeScript business-logic layer (types, collections, transformations)
├── services/api/           # FastAPI backend (auth, suppliers, inventory, reporting, agent, RFP)
├── uis/                    # backoffice, website, incidents, talent-pipeline-tracker (Next.js)
├── data/                   # process/ (indexing), pipelines/ (RAG, reporting, RFP), eval/
├── docs/                   # design docs, security reports, company knowledge base
├── mcps/                   # read-only MCP server (incidents and inventory tools)
├── scripts/                # Codespaces setup, model training, exports
└── tests/pipelines/        # agent, RAG, RFP and pipeline tests
```

## Stack

- **Backend:** Python, FastAPI, SQLModel. Supabase Postgres for inventory, telemetry and reporting; TinyDB (`db.json`) for users and roles.
- **Frontends:** Next.js (App Router), React, TypeScript, Tailwind CSS.
- **AI:** LangGraph (support agent, RFP intake, response and approval graphs), Qdrant vector store, embeddings and generation through the course LLM gateway, MCP with OAuth (read-only), Random Forest forecast model.
- **Background work:** Celery with Redis; Flower for monitoring. Agent memory and guardrail logs use Redis database 1.
- **Real time:** server-sent events (RFP notifications) and WebSocket (chat streaming).
- **Runtime:** Docker Compose (api, ui, redis, qdrant, worker, flower). Development in GitHub Codespaces, started with `scripts/codespace-up.sh`.

## Architectural decisions made

- **Import, don't copy.** Shared logic in `src/` is imported by the UIs. The dashboard reads the business-logic layer directly.
- **One interface per `uis/` subfolder,** each with its own layout.
- **Labels never leak raw API values.** UI code maps raw values to human-readable labels.
- **Currency in both COP and USD** wherever money is calculated or shown.
- **Knowledge base chunks:** one chunk per list item for dash lists of three or more; numbered procedures stay whole (`docs/rag/rag-design.md`).
- **Relevance cutoff:** `min_score` 0.27, measured on 10 test questions. When nothing passes it, the model is not called.
- **Input guard is code, not a model:** regex pattern matching, so it behaves the same every time. Backed by answer-only-from-context and an output guard (`docs/agent-guardrails/`).
- **Retrieved text is isolated:** document chunks, saved notes and ticket titles get the same injection check as user input. A suspicious piece is withheld whole.
- **Humans approve RFP work:** each team's approval is a paused LangGraph run; the CEO approves above $50,000 a year.

## Known technical constraints

- Environment variables exposed to the browser must be prefixed `NEXT_PUBLIC_`.
- `.env` is never committed; `.env.example` documents required variables.
- In Codespaces, port 8000 must be Public, or the browser reports a CORS error. Port 3001 must be forwarded to open the backoffice.
- The knowledge base must be reloaded into Qdrant after a rebuild that clears it.
- Next.js apps pin their workspace root (`turbopack.root`) so tooling resolves the right directory.
- Node 20+ is required.