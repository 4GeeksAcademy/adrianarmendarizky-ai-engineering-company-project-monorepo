# Progress — Brasaland Monorepo

_Update this file every time the project evolves: new decisions, completed features, problems encountered. A memory bank that is not kept current stops being useful within days._

## Current state (Milestone 4)

### Completed

- **Milestone 1 — Public website.** Static corporate site (`index.html`, `application.html`, `validation.js`, Tailwind) presenting Brasaland and capturing applications. Being migrated into `uis/website` as a Next.js app this milestone.
- **Milestone 2 — Business logic.** TypeScript logic layer in `src/` (types + collections, search, transformations, validations). Handles sales filtering/search, financial calculations in COP/USD, location performance scoring, waste cost, aggregations, and business-rule validations. Verified against sample data via a runnable demo.
- **Milestone 3 — Talent Pipeline Tracker.** Next.js app in `uis/talent-pipeline-tracker` consuming the recruitment mock API: candidate list with filter/search via query params, detail view, status/stage updates (PATCH), notes (POST/DELETE), candidate create (POST) and edit (PUT), with loading/success/error states and human-readable labels. Fix applied: list fetch limit raised so newly created candidates appear.

### In progress (Milestone 4)

- **Agent infrastructure:** memory bank (`memory-bank/`), root `AGENTS.md`, `.agents/` rules, and at least one reusable skill.
- **`uis/website`:** migrate the Milestone 1 corporate site into Next.js with reusable React components as the `/` route.
- **`uis/backoffice`:** internal app with its own layout, importing the Milestone 2 logic from `src/` and surfacing its output on screen.

## Next steps

- Complete the two Next.js apps under `uis/` and confirm both run with `npm run dev` without errors.
- Wire the back-office to import (not copy) from `src/` and render logic output on screen.
- Run the delivery workflow in `AGENTS.md` before the final commit; open a PR to `main` on branch `milestone-4`.

## Open questions / watch-items

- Cross-package imports from `uis/*` into root `src/` need a working path/module resolution setup; confirm before relying on it.
- Keep currency handling (COP/USD) consistent wherever Milestone 2 output is displayed.
