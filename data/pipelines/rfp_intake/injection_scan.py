"""injection_scan.py -- a cheap safety check on an uploaded RFP, run BEFORE
any model sees the text.

An RFP comes from outside the company, so its text could hide instructions
meant for the AI ("ignore your previous instructions ..."). This looks for
those classic phrases only. If it finds one, the intake stops and a person
has to look at the document.

It does NOT rewrite the document, and it does NOT use the wider list in
services/api/agent/guardrails/patterns.py, because real RFPs use ordinary
phrases like "when responding to this request ...".
"""
import re
import unicodedata

# (label shown on the ticket, pattern). Patterns run on lowercase text
# with accents removed.
PATTERNS = [
    ("ignore previous instructions",
     re.compile(r"\bignore\s+(all\s+|any\s+)?(the\s+|your\s+)?(previous|prior|above|earlier)\s+instructions?\b")),
    ("disregard instructions or rules",
     re.compile(r"\bdisregard\s+(the\s+|your\s+)?(previous|prior|above)?\s*(instructions?|rules?|guidelines?)\b")),
    ("forget your instructions",
     re.compile(r"\bforget\s+(what\s+you\s+)?(your\s+instructions?|the\s+company|you\s+work\s+for)\b")),
    ("reveal the system prompt",
     re.compile(r"\b(reveal|show|print|repeat)\s+(me\s+)?your\s+(system\s+)?(prompt|instructions?|rules?)\b")),
    ("new instructions",
     re.compile(r"\bnew\s+instructions?\s*:")),
    ("from now on you will",
     re.compile(r"\bfrom\s+now\s+on\s+you\s+will\b")),
    ("ignorar instrucciones (Spanish)",
     re.compile(r"\bignora\s+(todas\s+)?(las\s+)?instrucciones\s+(anteriores|previas)\b")),
    ("revelar instrucciones (Spanish)",
     re.compile(r"\brevela\s+tu\s+(system\s+prompt|instrucciones|configuracion)\b")),
]


def _fold(text: str) -> str:
    """Lowercase and strip accents, so 'ignorá' and 'IGNORA' both match."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def find_injection(text: str) -> str | None:
    """Return the label of the first suspicious phrase found, or None."""
    folded = _fold(text)
    for label, pattern in PATTERNS:
        if pattern.search(folded):
            return label
    return None
