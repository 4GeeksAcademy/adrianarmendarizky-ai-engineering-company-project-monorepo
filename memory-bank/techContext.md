# Technical Context — Brasaland Monorepo

## Repository shape

A single monorepo (`ai-engineering-company-project-monorepo`) that is the technical core of Brasaland Digital. All deliverables live here rather than in separate repos, so shared code is imported, not duplicated.

Top-level structure (relevant parts):

```text
ai-engineering-company-project-monorepo/
├── CONTEXT.md              # Assigned company scenario (Brasaland)
├── AGENTS.md               # Agent operating protocol (this milestone)
├── memory-bank/            # Persistent project context for agents (this milestone)
├── .agents/                # Agent configuration: rules and skills (this milestone)
├── src/                    # Milestone 2 — TypeScript business-logic layer
│   ├── types/models.ts
│   └── utils/{collections,search,transformations,validations}.ts
├── uis/                    # All user interfaces
│   ├── website/            # Milestone 4 — public corporate site (Next.js)
│   ├── backoffice/         # Milestone 4 — internal app (Next.js)
│   └── talent-pipeline-tracker/  # Milestone 3 — candidate tool (Next.js)
├── services/               # Backend services / APIs
├── agents/ data/ infra/ mcps/ packages/ scripts/ shared/ skills/ workflows/
```

## Stack

- **Language:** TypeScript throughout (strict typing).
- **Business logic (Milestone 2):** pure, framework-free TypeScript functions in `src/`. No I/O, no globals — filter/sort/search, financial calculations (COP/USD), location performance scoring, and validations. Fully unit-verified.
- **Frontends (Milestones 3–4):** Next.js (App Router) + React + Tailwind CSS. Component-level state via React hooks; no external state libraries.
- **APIs:** consumed from the course mock API (Milestone 3) and any internal services under `services/`.
- **Runtime:** Node.js 20+ (required by current Next.js). Development in GitHub Codespaces.

## Architectural decisions made

- **Import, don't copy.** Shared logic (`src/`) is imported by the UIs so there is a single source of truth. The back-office surfaces the Milestone 2 logic's output on screen by importing it directly.
- **One interface per `uis/` subfolder,** each with its own layout and documentation, per the `uis/` README convention.
- **Labels never leak raw API values.** UI code maps raw values (e.g. `in_progress`) to human-readable labels through a single mapping module.
- **Currency handled in both COP and USD** everywhere money is calculated or displayed.

## Known technical constraints

- The monorepo has multiple `package-lock.json` files; Next.js apps must pin their workspace root (`turbopack.root`) so tooling resolves the correct directory and reads the right `.env.local`.
- Environment variables exposed to the browser must be prefixed `NEXT_PUBLIC_`.
- `.env.local` is never committed; a `.env.example` documents required variables.
- Node 20+ must be active (`nvm use 20`) — the default Codespaces Node may be older.
