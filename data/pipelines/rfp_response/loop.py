"""
loop.py -- the generator-evaluator loop for ONE department (Milestone 9, Part 2).

    draft -> evaluate -> passed?  yes: done
                                  no:  send the feedback back to the SAME
                                       department's generator and draft again

The loop stops after settings.ITERATION_LIMIT drafts. A section that still
fails keeps its LAST draft and its LAST EvaluationResult and is marked
needs_human_review. It is never dropped, and neither is the ticket.

If the model breaks down in the middle of a loop (for example it is
unreachable), the section keeps the last draft that WAS evaluated, records
the error, and is marked needs_human_review too. The draft and the
EvaluationResult it carries always belong together.

Progress: on_progress(department_id, stage, iteration) is called with stage
"drafting", "evaluating" and "finished", so the API can show the ticket's
status in real time. A progress callback that fails never stops the draft.
"""

from . import evaluators, generator, settings

SECTION_PASSED = "passed"
SECTION_NEEDS_REVIEW = settings.STATUS_NEEDS_HUMAN_REVIEW


def _notify(on_progress, department_id: str, stage: str, iteration: int) -> None:
    if on_progress is None:
        return
    try:
        on_progress(department_id, stage, iteration)
    except Exception as error:  # progress reporting must never stop the draft
        print(f"RFP response: progress update failed for {department_id}: {error}")


def run_section_loop(department_id: str, metadata: dict, key_aspects: list[str],
                     open_questions: list[str], *, on_progress=None, limit: int | None = None) -> dict:
    """Run one department's loop and return its finished section."""
    limit = limit or settings.ITERATION_LIMIT

    kept_draft = ""         # the last draft that has an EvaluationResult
    kept_result = None      # that draft's EvaluationResult
    candidate = None        # the draft being worked on right now
    feedback = None
    history = []
    attempts = 0
    error = None
    status = SECTION_NEEDS_REVIEW

    try:
        while attempts < limit:
            attempts += 1
            candidate = None

            _notify(on_progress, department_id, "drafting", attempts)
            candidate = generator.generate_draft(
                department_id, metadata, key_aspects, open_questions,
                previous_draft=kept_draft or None, feedback=feedback,
            )

            _notify(on_progress, department_id, "evaluating", attempts)
            result = evaluators.evaluate_section(
                department_id, candidate,
                metadata=metadata, key_aspects=key_aspects, open_questions=open_questions,
            )

            kept_draft, kept_result = candidate, result
            history.append({
                "iteration": attempts,
                "overall_pass": result["overall_pass"],
                "rule_ids": result["compliance"]["rule_ids"],
                "readability_score": result["readability"]["score"],
                "missing_aspects": len(result["relevance"]["missing_aspects"]),
            })
            if result["overall_pass"]:
                status = SECTION_PASSED
                break
            feedback = result["feedback_for_generator"]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if kept_result is None and candidate:
            kept_draft = candidate  # a first draft with no evaluation beats no draft

    _notify(on_progress, department_id, "finished", attempts)
    return {
        "department_id": department_id,
        "status": status,
        "draft_content": kept_draft,
        "evaluation_result": kept_result,
        "iterations": attempts,
        "history": history,
        "error": error,
    }
