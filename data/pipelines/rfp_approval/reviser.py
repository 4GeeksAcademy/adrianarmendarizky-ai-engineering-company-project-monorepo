"""
reviser.py -- how a draft is rewritten after someone asks for changes
(Milestone 9, Part 3).

It reuses Part 2's generate / evaluate loop (rfp_response.loop) unchanged,
starting from the draft the approver saw and the approver's comments as the
feedback, so the new draft is evaluated by the same three evaluators as before.
"""

from rfp_response.loop import run_section_loop


def summarize_evaluation(evaluation_result) -> dict:
    """The short version of an EvaluationResult that an approver is shown."""
    if not evaluation_result:
        return {}
    readability = evaluation_result.get("readability") or {}
    relevance = evaluation_result.get("relevance") or {}
    compliance = evaluation_result.get("compliance") or {}
    return {
        "overall_pass": evaluation_result.get("overall_pass"),
        "readability": {"pass": readability.get("pass"), "score": readability.get("score")},
        "relevance": {"pass": relevance.get("pass"), "missing_aspects": relevance.get("missing_aspects", [])},
        "compliance": {"pass": compliance.get("pass"), "rule_ids": compliance.get("rule_ids", []),
                       "violations": compliance.get("violations", [])},
    }


def make_loop_reviser(context_for):
    """context_for(ticket_id, subject) -> {"metadata", "key_aspects", "open_questions"}:
    the same Part 1 facts the first draft was written from."""

    def reviser(subject: str, state: dict) -> dict:
        context = context_for(state["ticket_id"], subject)
        result = run_section_loop(
            subject, context["metadata"], context["key_aspects"], context["open_questions"],
            previous_draft=state.get("draft_content"), feedback=state["feedback"],
        )
        if not result["draft_content"]:
            # Nothing was written (for example the model was unreachable). Raising keeps the
            # approval exactly where it was, so it can be continued later.
            raise RuntimeError(f"Could not rewrite the {subject} section: {result['error']}")
        return {
            "draft_content": result["draft_content"],
            "evaluation": summarize_evaluation(result["evaluation_result"]),
            "error": result["error"],
        }

    return reviser
