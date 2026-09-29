"""
classifier.py -- stage 2 of the RFP intake pipeline (Milestone 9, Part 1).

Reads the Markdown from convert.py and decides: is this a real Brasaland
RFP, or not? If not, the ticket is marked "discarded" and the reason is
saved on the ticket.

The rules come from CONTEXT-brasaland.md:
  - formal RFPs AND informal emails/letters both count (section 2.2)
  - documents may be in English or Spanish
  - a franchise question with no scope, budget or deadline is rejected
    (section 4, sample 3)

If the model's answer can't be understood, this raises an error. It does
NOT quietly discard the document.
"""

from . import llm

# Very long documents cost tokens. RFPs are short, so this is a safety cap.
MAX_CHARS = 15000

SYSTEM_PROMPT = """You are the intake classifier for Brasaland, a grilled-food \
restaurant chain with locations in Colombia and Florida.

Your one job: decide whether a document is a business request asking Brasaland \
for a PROPOSAL, QUOTE or PRICING.

The document may be in English or Spanish. Always write your reason in English.

Answer is_rfp = true when ALL of these are true:
- Someone (a company, resort, school, or organization) is asking Brasaland to \
send a proposal, quote or pricing.
- It is for a business service: recurring catering, event catering, a food \
concession, or a co-branding partnership.
- It gives something concrete to plan or price, such as number of people, \
number of locations, how often, contract length, or a deadline.

Formal RFP documents count. Informal emails and letters of intent count too.

Answer is_rfp = false for anything else, for example:
- A general question or curiosity (for example, asking if Brasaland offers \
franchises) with no scope, budget or deadline.
- A customer complaint, a job application, spam, or a vendor trying to sell \
something to Brasaland.

Do NOT reject a document only because it is informal, is in Spanish, has no \
budget, or has a deadline date that has already passed.

Reply with JSON only, no other text:
{"is_rfp": true or false, "reason": "one or two plain English sentences"}"""


def classify_rfp(markdown: str) -> dict:
    """Return {"is_rfp": bool, "reason": str} for one converted document."""
    prompt = f"Document (Markdown):\n---\n{markdown[:MAX_CHARS]}\n---"
    answer = llm.ask_json(prompt, system=SYSTEM_PROMPT)

    is_rfp = answer.get("is_rfp")
    if not isinstance(is_rfp, bool):
        raise llm.LlmJsonError(f"is_rfp must be true or false, got: {is_rfp!r}")

    return {"is_rfp": is_rfp, "reason": str(answer.get("reason", "")).strip()}


def classify_node(state: dict) -> dict:
    """The graph step. Reads state["markdown"], fills is_rfp and discard_reason."""
    result = classify_rfp(state["markdown"])
    return {
        "is_rfp": result["is_rfp"],
        "discard_reason": None if result["is_rfp"] else result["reason"],
    }
