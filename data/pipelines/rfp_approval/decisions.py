"""
decisions.py -- checks a human's answer BEFORE it is fed back to the graph
(Milestone 9, Part 3: "validate the human response before feeding it back").

A decision is a small dict:
    {"action": "approve" | "reject" | "request_changes",
     "comments": "why (required to reject or to ask for changes)",
     "estimates": {"<field>": number}}        # optional, only when approving

validate_decision() returns a clean copy or raises InvalidDecision with a
message a person can act on. Nothing else in the workflow trusts raw input.
"""

import math

from rfp_intake.state import DEPARTMENT_IDS

from . import settings

ALLOWED_KEYS = {"action", "comments", "estimates"}


class InvalidDecision(ValueError):
    """The answer is not one the workflow can accept."""


def _check_subject(subject: str) -> None:
    if subject != settings.CEO_SUBJECT and subject not in DEPARTMENT_IDS:
        raise InvalidDecision(
            f"'{subject}' is not an approver. Use one of: {', '.join(DEPARTMENT_IDS)}, {settings.CEO_SUBJECT}."
        )


def _clean_estimates(subject: str, estimates) -> dict:
    field = settings.ESTIMATE_FIELDS.get(subject)
    if field is None:
        raise InvalidDecision(f"Estimates are not accepted from '{subject}'.")
    if not isinstance(estimates, dict):
        raise InvalidDecision("'estimates' must be an object like {\"%s\": 12.5}." % field)
    unknown = sorted(set(estimates) - {field})
    if unknown:
        raise InvalidDecision(f"'{subject}' can only give '{field}', not: {', '.join(unknown)}.")
    value = estimates.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidDecision(f"'{field}' must be a number.")
    if math.isnan(value) or math.isinf(value) or value <= 0:
        raise InvalidDecision(f"'{field}' must be a number above zero.")
    return {field: float(value)}


def validate_decision(subject: str, response) -> dict:
    """Return {"action", "comments", "estimates"} or raise InvalidDecision."""
    _check_subject(subject)
    if not isinstance(response, dict):
        raise InvalidDecision("The decision must be an object with an 'action'.")

    unknown = sorted(set(response) - ALLOWED_KEYS)
    if unknown:
        raise InvalidDecision(f"Unknown field(s): {', '.join(unknown)}. Allowed: action, comments, estimates.")

    allowed_actions = settings.CEO_ACTIONS if subject == settings.CEO_SUBJECT else settings.ACTIONS
    action = response.get("action")
    if action not in allowed_actions:
        raise InvalidDecision(f"'action' must be one of: {', '.join(allowed_actions)}.")

    comments = response.get("comments", "")
    if comments is None:
        comments = ""
    if not isinstance(comments, str):
        raise InvalidDecision("'comments' must be text.")
    comments = comments.strip()
    if len(comments) > settings.MAX_COMMENT_LENGTH:
        raise InvalidDecision(f"'comments' is too long (limit: {settings.MAX_COMMENT_LENGTH} characters).")
    if action != settings.APPROVE and len(comments) < settings.MIN_COMMENT_LENGTH:
        raise InvalidDecision(
            f"Say why in 'comments' (at least {settings.MIN_COMMENT_LENGTH} characters) "
            f"when you {'reject' if action == settings.REJECT else 'ask for changes'}."
        )

    estimates = {}
    # An empty {} means "no estimates" (it is what this function itself returns), so
    # validating an already-validated decision works. Anything else is checked.
    if response.get("estimates") is not None and response["estimates"] != {}:
        if action != settings.APPROVE:
            raise InvalidDecision("Estimates can only be given together with 'approve'.")
        estimates = _clean_estimates(subject, response["estimates"])

    return {"action": action, "comments": comments, "estimates": estimates}


def validate_arbitration(trigger: str, response) -> dict:
    """The arbiter's answer for a conflict that needs a human choice.
    Only cost-vs-feasibility does: Camila picks raise_price or reduce_scope."""
    choices = settings.ARBITRATION_CHOICES.get(trigger)
    if choices is None:
        raise InvalidDecision(f"'{trigger}' is settled by its rule, not by a choice.")
    if not isinstance(response, dict):
        raise InvalidDecision("The arbitration answer must be an object with a 'choice'.")
    unknown = sorted(set(response) - {"choice", "comments"})
    if unknown:
        raise InvalidDecision(f"Unknown field(s): {', '.join(unknown)}. Allowed: choice, comments.")
    if response.get("choice") not in choices:
        raise InvalidDecision(f"'choice' must be one of: {', '.join(choices)}.")
    comments = response.get("comments")
    if comments is None:
        comments = ""
    if not isinstance(comments, str):
        raise InvalidDecision("'comments' must be text.")
    comments = comments.strip()
    if len(comments) < settings.MIN_COMMENT_LENGTH:
        raise InvalidDecision(f"Say why in 'comments' (at least {settings.MIN_COMMENT_LENGTH} characters).")
    return {"choice": response["choice"], "comments": comments}
