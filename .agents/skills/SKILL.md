---
name: milestone-summary
objective: Produce a standardized end-of-milestone summary document for a completed deliverable.
inputs:
  - milestone_name: string — the milestone or deliverable being summarized (e.g. "Milestone 4 — Monorepo AI Setup").
  - work_location: path(s) — the folders/files produced or changed (e.g. "uis/website", "uis/backoffice", "memory-bank/").
  - context: the assigned company scenario in CONTEXT.md.
activation: agent-requested
---

# Skill: Milestone Summary

## Objective

Given a completed milestone, generate one Markdown summary document that captures — consistently, every time — (1) a concise summary of the work done, (2) the troubleshooting and hurdles faced and how they were resolved, and (3) a short list of the skills and work a hiring employer would value from it. This is a recurring deliverable at the end of every milestone; this skill makes its structure and quality repeatable.

## Inputs

- **milestone_name** — the milestone/deliverable title.
- **work_location** — the path(s) to the code or documents produced, used to ground the summary in what actually changed.
- **context** — `CONTEXT.md`, so the summary uses the correct company framing (Brasaland).

## Procedure

1. Read `CONTEXT.md` and the relevant `memory-bank/` files for accurate framing and scope.
2. Inspect `work_location` to confirm what was actually built or changed (do not summarize from memory alone).
3. Write a Markdown document with exactly these sections, in order:
   - **Summary of work** — what was built and how it fits the company scenario (concise, prose).
   - **Architecture / key decisions** — the notable choices and their rationale.
   - **Troubleshooting and hurdles** — real problems encountered and how each was solved.
   - **Skills an employer would value** — a short bulleted list tying the work to marketable competencies.
   - **How to run / verify** — the exact command(s) to run or check the deliverable.
4. Keep it accurate to what was done; do not claim work that was not completed.

## Acceptance criteria (verifiable)

The output is accepted only if ALL are true:

- The document contains all five required sections named above, in order.
- Every hurdle listed includes both the problem and its resolution (not just a problem).
- The "how to run / verify" section contains at least one concrete, runnable command.
- The company framing matches `CONTEXT.md` (correct company name and scenario — Brasaland).
- No claimed feature is absent from `work_location`; every summarized item maps to something that actually exists.
- The document is valid Markdown and contains no placeholder text (no "TODO", no "[fill in]").

## Example invocation

> Run the `milestone-summary` skill for milestone_name="Milestone 4 — Monorepo AI Setup", work_location=["memory-bank/", "AGENTS.md", ".agents/", "uis/website", "uis/backoffice"].
