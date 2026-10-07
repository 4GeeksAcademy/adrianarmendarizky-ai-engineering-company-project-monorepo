"""
settings.py -- the names, limits and rules of the approval workflow
(Milestone 9, Part 3). Everything that might change lives here, in one place.

Sources: CONTEXT-brasaland.md section 2.1 (who owns each department),
section 2.3 (statuses), section 5 (the $50,000 CEO rule) and section 7
(conflict triggers and their fixed arbiters).
"""

from rfp_intake.synthesizer import OWNERS  # department_id -> the owner named in CONTEXT section 2.1

# --- Who approves -----------------------------------------------------------
CEO_SUBJECT = "ceo"
CEO_NAME = "Mariana Restrepo"
APPROVERS = {**OWNERS, CEO_SUBJECT: CEO_NAME}

# --- What a human can answer ---------------------------------------------------
APPROVE = "approve"
REJECT = "reject"
REQUEST_CHANGES = "request_changes"
ACTIONS = (APPROVE, REJECT, REQUEST_CHANGES)
CEO_ACTIONS = (APPROVE, REJECT)  # there is no generator to send a CEO's "changes" to
MIN_COMMENT_LENGTH = 10          # a rejection or a change request has to say why
MAX_COMMENT_LENGTH = 2000

# --- Approval statuses (CONTEXT section 2.3) -----------------------------------
PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"

# --- Limits ------------------------------------------------------------------
# How many times one department's approver may send the section back for
# changes. After that the section is rejected and the ticket goes back to
# needs_human_review (nothing loops forever).
REVISION_LIMIT = 2

# --- CONTEXT section 5: contracts ABOVE this many USD a year need the CEO -------
CEO_APPROVAL_THRESHOLD_USD = 50_000

# --- CONTEXT section 7: conflict triggers and their fixed arbiters --------------
TRIGGER_COST = "cost-vs-feasibility"
TRIGGER_SETUP = "setup-sla-breach"
TRIGGER_CEO = "ceo-threshold"
TRIGGERS = (TRIGGER_COST, TRIGGER_SETUP, TRIGGER_CEO)

ARBITERS = {
    TRIGGER_COST: OWNERS["marketing"],     # Camila Ospina (the ticket owner)
    TRIGGER_SETUP: OWNERS["operaciones"],  # Felipe Guerrero rejects the breach...
    TRIGGER_CEO: CEO_NAME,                 # Mariana Restrepo
}
# ...and Camila escalates when other departments still embed it.
ESCALATION_ARBITER = {TRIGGER_SETUP: OWNERS["marketing"]}

# What Camila can decide for cost-vs-feasibility (CONTEXT: "raise price or reduce scope").
RAISE_PRICE = "raise_price"
REDUCE_SCOPE = "reduce_scope"
ARBITRATION_CHOICES = {TRIGGER_COST: (RAISE_PRICE, REDUCE_SCOPE)}

# --- cost-vs-feasibility: the two structured numbers the approvers enter -------
# CONTEXT does not say which numbers to compare, so this is an ASSUMPTION to
# confirm with the tech lead: Lucia (procurement) enters the ingredient cost
# per cover, Felipe (operaciones) enters the price per cover, both in USD.
ESTIMATE_FIELDS = {
    "procurement": "ingredient_cost_per_cover_usd",
    "operaciones": "price_per_cover_usd",
}
# The ingredient cost may be at most this share of the price. 1.0 means "the
# ingredients alone must not cost more than the price" -- the weakest possible
# reading of "cannot support the price". CONTEXT gives no margin target.
MAX_INGREDIENT_COST_SHARE = 1.0
