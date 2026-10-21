# Brasaland Backoffice Suite

The Brasaland Backoffice Suite is an AI-powered operations suite for Brasaland, a 14-restaurant grilled-food chain in Colombia and Florida. It is built as a monorepo with a FastAPI backend and a Next.js backoffice. It adds a document-grounded knowledge assistant, an RFP workflow with human approvals, and a revenue forecasting model, each answering a real request from a Brasaland team.

**Demo video and project files:** [Google Drive folder](https://drive.google.com/drive/folders/1I4Jo_frKXxJplf48SlcvDQJIQeeGYynz?usp=sharing)

## What is inside

### Everyday tools (no AI needed)

| Tool | What it does | Where |
|---|---|---|
| Dashboard | Sales and average ticket in USD and COP, plus a ranking of locations (sample data) | `uis/backoffice/app/(protected)/page.tsx` |
| Suppliers | One shared supplier directory for both countries | `uis/backoffice/app/(protected)/suppliers/` |
| Inventory | Stock in and out per ingredient, low-stock alerts | `uis/backoffice/app/(protected)/inventory/` |
| Reporting | Weekly cost and waste report per location | `uis/backoffice/app/(protected)/reporting/` |

### AI features

| Feature | The problem it answers | How it works | Where |
|---|---|---|---|
| Knowledge Base and Support Chat | Company rules sit in documents nobody can search | RAG: four manuals are split into 30 chunks and stored in Qdrant. A LangGraph agent picks where to look, answers only from what it finds, and passes through input and output guards. Has consent-based memory and read-only tools (MCP with OAuth). | `docs/rag/rag-design.md`, `docs/agent-guardrails/`, `docs/agent-memory/` |
| RFP workflow | Big catering requests arrive as long PDFs and need four teams | Intake (scan, classify, orchestrator and one worker per department), drafting with three automatic checks, then approvals by team owners and the CEO above $50,000 a year | `data/pipelines/rfp_intake/`, `rfp_response/`, `rfp_approval/`, `docs/rfp-e2e-example.md` |
| Sales forecast | Ordering is guesswork without a revenue outlook | Random Forest model that predicts monthly revenue one month ahead (about 5% average error on two held-out years) | `scripts/sales_forecast_train.py`, `data/eval/` |

Also included: live RFP notifications (server-sent events), streaming chat (WebSocket), a weekly business-performance pipeline (`data/pipelines/PIPELINE_DESIGN.md`), event telemetry (`docs/telemetry/`), and a read-only MCP server (`mcps/incidents-inventory-tools/`).

## Security and quality

- Agent guardrails: input guard, output guard, and isolation of retrieved text (`docs/agent-guardrails/agent-guardrails-design.md`).
- Security reviews: `docs/nist-security/nist-security-report.md` and `docs/owasp-audit/owasp-top10-audit-report.md`.
- Automated tests: `services/api/tests/` (API) and `tests/pipelines/` (agent, RAG, RFP, pipeline).
- Model and retrieval evaluations: `data/eval/`.

## Run it

### With Docker Compose (local)

```bash
cp .env.example .env    # then fill in real values; also add the model and Qdrant
                        # settings listed in services/api/.env.example
docker compose up --build
```

| Service | Address |
|---|---|
| Website | http://localhost:3000 |
| Backoffice | http://localhost:3001 |
| API docs | http://localhost:8000/docs |
| Flower (task queue) | http://localhost:5555 |

After the first start, load the knowledge base into Qdrant (and again after any rebuild that clears Qdrant):

```bash
docker compose exec -w /workspace/services/api api uv run python ../../data/process/rag.py
```

It should report that it indexed 30 chunks.

### In GitHub Codespaces

```bash
./scripts/codespace-up.sh
```

The script sets the app addresses for the Codespace, makes port 8000 public, and starts the services in order. Then forward port 3001 in the Ports tab to open the backoffice, and load the knowledge base with the command above.

### Roles

Accounts have one of three roles: `admin`, `manager` or `user`. Only managers and admins can record RFP approvals. Roles are changed by an admin (`services/api/routes/users.py`).

## Run the tests

```bash
cd services/api
uv sync
uv run pytest                                       # API tests
uv run python -m pytest ../../tests/pipelines -v    # agent, RAG, RFP and pipeline tests
```

Some agent tests need Qdrant and a `.env`. The guardrail tests (`tests/pipelines/test_agent_guardrails.py`) do not.

## Structure

```
services/api/                    FastAPI backend: auth, suppliers, inventory, reporting,
                                 knowledge base, support agent, RFP, telemetry
  agent/                         LangGraph support agent, guardrails, memory, MCP client
uis/
  backoffice/                    Internal app (the one with login): all tools above
  website/                       Public site
  incidents/                     CSV analyzer and incident manager
  talent-pipeline-tracker/       Candidate tracking
data/
  process/                       Indexing for the knowledge base (chunks, embeddings, Qdrant)
  pipelines/                     RAG query, weekly reporting pipeline, RFP intake/response/approval
  eval/                          Evaluation results (retrieval, forecast model)
docs/                            Design docs, security reports, company knowledge base
mcps/                            MCP server with read-only incident and inventory tools
scripts/                         Setup script for Codespaces, model training, exports
src/                             Business-logic layer (types, collections, transformations)
tests/pipelines/                 Agent, RAG, RFP and pipeline tests
```

## More documentation

- `CONTEXT.md`: the Brasaland company scenario
- `services/api/README.md`: backend setup, endpoints, business rules
- `uis/README.md`: frontend apps, ports, Docker details
- `services/api/TESTING.md`: authentication test plan
- `memory-bank/`: project brief, tech context, current progress