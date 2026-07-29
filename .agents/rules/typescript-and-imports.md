---
name: typescript-and-imports
scope: file-pattern
applies_to:
  - "src/**/*.ts"
  - "uis/**/*.ts"
  - "uis/**/*.tsx"
  - "services/**/*.ts"
activation: always
---

# Rule: TypeScript standards and shared-code imports

**Scope:** Active automatically for all TypeScript and TSX files matching the patterns above (business logic in `src/`, UI code in `uis/`, and services). This is a file-pattern rule.

## Requirements

1. **Explicit typing.** Every function has typed parameters and a typed return value. Do not use `any`; if a type is genuinely unknown, use `unknown` and narrow it.
2. **Import shared logic from its source.** Business logic lives in `src/` and is the single source of truth. UI and service code must **import** from it — never copy or reimplement it. Duplication of `src/` logic is not allowed.
3. **Naming.** `camelCase` for variables and functions, `PascalCase` for types, interfaces, and React components.
4. **Purity in the logic layer.** Functions under `src/` must remain pure — no global state, no side effects, working only from their parameters.
5. **Currency correctness.** Any code handling money must handle both COP and USD; never hard-code a single currency where the data model carries both.
6. **No raw enum-like values in the UI.** API/domain raw values (e.g. `in_progress`) must be mapped to human-readable labels through a single mapping module before display.

## When this rule and a task conflict

If a requested change would violate this rule (for example, copying `src/` logic into an app to "make it work"), stop and ask the developer instead of proceeding.
