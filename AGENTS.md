# AGENTS.md — Agent Operating Protocol

This file defines how any coding agent must operate in this repository. Agents read this file first, before taking any action. It is the team agreement that keeps automated changes safe and consistent with existing work.

---

## 1. Read at the start of every session

Before making any change, the agent must read, in order:

1. `CONTEXT.md` — the Brasaland company scenario. All work must align with it.
2. `memory-bank/projectbrief.md` — business context and what is being built.
3. `memory-bank/techContext.md` — stack, structure, and technical decisions.
4. `memory-bank/progress.md` — current state, in-progress work, and next steps.
5. `.agents/rules/` — active development rules.

The agent must not assume prior context from earlier sessions; the memory bank is the source of truth.

---

## 2. Mandatory workflow before every commit

The agent must complete these ordered steps before any commit. If a step cannot be completed, the agent stops and asks the developer.

1. **Confirm scope.** Restate what is being changed and why, and verify it matches a task in `memory-bank/progress.md` or an explicit developer request. Do not expand scope beyond that.
2. **Verify locally.** Run the relevant checks — type-check (`npx tsc --noEmit`) for TypeScript, and start the affected app (`npm run dev`) to confirm it builds without errors. Do not commit code that fails to compile or run.
3. **Update the memory bank.** Reflect the change in `memory-bank/progress.md` (and `techContext.md` if a technical decision changed). An out-of-date memory bank is treated as a defect.
4. **Review the diff.** Inspect `git status` and `git diff` to confirm only intended files are staged — no `node_modules`, no `.env.local`, no unrelated files.
5. **Commit with a descriptive message** stating what changed and which milestone/area it belongs to.

---

## 3. Files the agent must NOT modify without explicit developer confirmation

The agent may read these freely but must ask before changing them:

- `CONTEXT.md` — the assigned company scenario (fixed input).
- `src/**` — the Milestone 2 business-logic layer. It is imported by other code; changes risk breaking consumers. Modify only on explicit request.
- `.env.local` in any app — secrets/config; never commit and never edit blindly.
- Any `package.json` / lockfile at the repo root — dependency and workspace changes can affect the whole monorepo.
- Existing delivered apps under `uis/` (e.g. `talent-pipeline-tracker`) — do not alter previously graded work without confirmation.

---

## 4. General rules

- **Import, never copy** shared logic. If two places need the same code, import it from its original location in `src/` or `packages/`.
- **Match existing conventions.** Follow the structure documented in each folder's `README.md` before creating new folders or files.
- **Stop and ask** when a decision is ambiguous, when a change would touch a protected file, or when acceptance criteria for a task are unclear. The agent does not make product decisions on its own.
- **TypeScript only** for logic and app code, with explicit types.

---

_Keep this protocol current. If the workflow changes, update this file in the same commit._
