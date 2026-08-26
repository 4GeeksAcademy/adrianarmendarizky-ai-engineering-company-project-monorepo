# Monorepo Directory Summary

This document provides a quick structural overview of the `ai-engineering-company-project-monorepo` repository.

## Top-Level Layout

```text
.
|- .agents/                         # Agent rules and reusable skills for automation
|- agents/                          # Agent templates and test scaffolding
|- assets/                          # Shared static assets
|- data/                            # Data files used across scripts/apps
|- docs/                            # Architecture and project documentation
|- infra/                           # Infrastructure-related docs/materials
|- internal/                        # Internal process/reference docs
|- mcps/                            # MCP-related resources
|- memory-bank/                     # Project memory/context for agent workflows
|- packages/                        # Shared package workspace(s)
|- scripts/                         # Utility scripts for analysis/seeding
|- services/                        # Backend services (API)
|- shared/                          # Shared docs/resources across areas
|- skills/                          # Skill templates and skill examples/resources
|- src/                             # Core TypeScript business-logic layer
|- uis/                             # Frontend applications
|- workflows/                       # Workflow docs/resources
|- CONTEXT.md                       # Business scenario context
|- AGENTS.md                        # Root agent operating protocol
|- README.md                        # Main repository documentation
|- package.json                     # Root npm workspace configuration
```

## Key Areas

### 1) `.agents/`

```text
.agents/
|- rules/
|  |- typescript-and-imports.md
|- skills/
|  |- milestone-summary/
```

- Contains agent behavior rules and reusable skill material for guided development workflows.

### 2) `src/` (Shared Business Logic)

```text
src/
|- index.ts
|- package.json
|- types/
|  |- models.ts
|- utils/
|  |- collections.ts
|  |- search.ts
|  |- transformations.ts
|  |- validations.ts
```

- Central TypeScript logic layer intended to be imported by apps/services.

### 3) `services/` (Backend)

```text
services/
|- api/
|  |- app/
|  |- routes/
|  |- tests/
|  |- main.py
|  |- database.py
|  |- dependencies.py
|  |- models.py
|  |- incident_models.py
|  |- user_models.py
|  |- user_service.py
|  |- email_service.py
|  |- password_service.py
|  |- security.py
|  |- seed.py
|  |- requirements.txt
|  |- pyproject.toml
|  |- pytest.ini
|  |- README.md
|  |- TESTING.md
```

- Python API service with routing, data models, testing setup, and supporting services.

### 4) `uis/` (Frontend Apps)

```text
uis/
|- backoffice/                      # Internal operations app (Next.js)
|- incidents/                       # Incident-related app (Next.js)
|- talent-pipeline-tracker/         # Candidate pipeline app (Next.js)
|- website/                         # Public/corporate website app (Next.js)
|- README.md
```

Common structure inside UI apps:

```text
app/ components/ lib/ public/ (where applicable)
next.config.ts, tsconfig.json, eslint.config.mjs, postcss.config.mjs, package.json
```

### 5) `packages/`

```text
packages/
|- shared/
|  |- package.json
|  |- incident_validation/
|  |- types/
```

- Workspace for reusable package modules.

### 6) `skills/`

```text
skills/
|- _template/
|- code-review/
|- data-analysis/
|- research/
|- README.md
|- README.es.md
```

- Structured area for skill definitions, examples, scripts, and reusable resources.

## Legacy/Standalone Root Files

- `index.html`, `application.html`, `validation.js`, `tailwind.css`, `tailwind-input.css` remain at root as legacy/static artifacts.

## Notes

- The repository combines frontend apps, shared TypeScript logic, Python API services, and agent tooling in one monorepo.
- `node_modules/` is present at root (generated dependency directory, not source).
