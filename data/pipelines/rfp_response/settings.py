"""
settings.py -- the numbers and names the RFP response pipeline (Milestone 9,
Part 2) checks against. Everything that might change lives here, in one place.

Sources:
  - Guidelines: CONTEXT-brasaland.md section 5
  - Ticket statuses: CONTEXT-brasaland.md section 2.3
"""

import os

# --- The generator-evaluator loop -------------------------------------
# A section gets at most this many drafts. If the last one still fails,
# the section is marked needs_human_review (it is never dropped).
ITERATION_LIMIT = 3

# --- Readability (py-readability-metrics) ---------------------------------
# A Flesch-Kincaid grade level at or below this passes. Part 1 measured the
# RFPs themselves at about 12-14, so 12 asks the proposal to be no harder
# to read than the client's own document. Change it here if your tech
# lead prefers another target.
MAX_GRADE_LEVEL = 12.0
# The package cannot score text shorter than this (same limit as Part 1).
MIN_WORDS_TO_SCORE = 100

# --- CONTEXT section 5 guidelines -------------------------------------------
MIN_SETUP_BUSINESS_DAYS = 10
OFFER_VALIDITY_DAYS = 30
BRAND_PILLARS = ("consistent quality", "warm experience", "speed of service")

# Brasaland's CONTEXT gives no competitor list, so none is invented here.
# Set COMPETITOR_NAMES (comma separated) in .env to have code check for them.
COMPETITOR_NAMES = tuple(
    name.strip() for name in os.environ.get("COMPETITOR_NAMES", "").split(",") if name.strip()
)

# --- Currency ---------------------------------------------------------------
# REFERENCE RATE, NOT AN OFFICIAL ONE. Nothing in the repo defines an exchange
# rate, so this is a labeled setting. Confirm the real number with your tech
# lead. It is only used to show the second currency for a figure the RFP
# already gave, never to make up a price.
COP_PER_USD = float(os.environ.get("COP_PER_USD", "4000"))

# --- Ticket statuses for Part 2 (same strings as rfp_models.py) ----------------
STATUS_DRAFTING = "drafting"
STATUS_UNDER_EVALUATION = "under_evaluation"
STATUS_NEEDS_HUMAN_REVIEW = "needs_human_review"
