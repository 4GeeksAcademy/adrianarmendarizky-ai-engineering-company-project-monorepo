"""
services/api/agent/memory/policy.py -- the rules for what can enter memory.

Everything here is plain code, not a prompt. The model is also told these
rules (see llm_steps.py), but a model can be wrong or be talked into things,
so the code checks again. validate_proposal() is called three times:
when a proposal is created, when the user edits it, and inside
MemoryStore.write_fact() right before anything is saved. A fact that fails
here can never reach Redis, no matter which code path tried to save it.

The rules come from CONTEXT-brasaland.md (Milestone 8, Part 1):
  worth remembering: per-location hours, supplier delivery days, local
      exceptions, known causes of recurring alerts, a manager's preferred
      report format
  never remembered: Brasa Points customer personal data, payroll or staff
      compensation, one-off things (the one-off rule is judged by the model
      and by the "repeatable" test in llm_steps.py -- code can't judge that
      one, so it is the only rule here that is not enforced in code)
"""

import re
import unicodedata

# --- What may be remembered ---------------------------------------------

ALLOWED_CATEGORIES = ("hours", "suppliers", "known_incidents", "communication_prefs")

# --- Timing and size limits (all in one place so they are easy to change) --

PENDING_TTL_MINUTES = 10       # an unanswered proposal is dropped after this long
INCIDENT_EXPIRY_DAYS = 90      # a known incident not seen again in this long is forgotten
RECONFIRM_AFTER_DAYS = 180     # hours/suppliers/prefs older than this are flagged "may be outdated"
MAX_FACTS_PER_LOCATION = 40    # hard cap so one location can't grow without limit
MAX_WRITES_PER_USER_PER_DAY = 10
MAX_FACT_CHARS = 300
MAX_KEY_CHARS = 60

# --- Locations ------------------------------------------------------------

# Same location ids and names the rest of the monorepo uses
# (scripts/seed_incidents.py BRANCH_MAP).
BRANCH_SLUGS = {
    "COL-01": "medellin_centro",
    "COL-02": "medellin_laureles",
    "COL-03": "medellin_envigado",
    "COL-04": "medellin_bello",
    "COL-05": "medellin_itagui",
    "COL-06": "bogota_chapinero",
    "COL-07": "bogota_usaquen",
    "COL-08": "cali_granada",
    "COL-09": "barranquilla_norte",
    "COL-10": "central",
    "FLA-01": "miami_doral",
    "FLA-02": "miami_hialeah",
    "FLA-03": "miami_kendall",
    "FLA-04": "orlando_international",
}

# A correction like "the Medellín meat supplier delivers on Tuesdays" is about a
# whole city, not one restaurant, so a fact can also be stored for a city.
CITY_SCOPES = ("medellin", "bogota", "cali", "barranquilla", "miami", "orlando")

_LOCATION_RE = re.compile(r"[a-z0-9][a-z0-9_]{1,39}")


def fold(text: str) -> str:
    """Lowercase and remove accents, so 'Medellín' and 'medellin' match."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", fold(text)).strip("_")


def normalize_location(raw: str | None) -> str | None:
    """A location id ("COL-07") becomes its name ("bogota_usaquen"); anything
    else becomes a lowercase_with_underscores label. Returns None if the
    result isn't a sane short label. Names that aren't in the table above
    (the CONTEXT file mentions "Miami Beach", for example) are still accepted
    as labels -- the location is only a label, and the fact itself still has
    to be approved by the user and pass every other check."""
    text = (raw or "").strip()
    if text.upper() in BRANCH_SLUGS:
        return BRANCH_SLUGS[text.upper()]
    slug = slugify(text)
    return slug if _LOCATION_RE.fullmatch(slug) else None


# --- Content checks -------------------------------------------------------

_PAYROLL_RE = re.compile(
    r"\b(payroll|salary|salaries|wages?|paychecks?|payslips?|pay ?rate|compensation|bonus(es)?|"
    r"nomina|salarios?|sueldos?|honorarios|bonificacion(es)?)\b"
)

_PERSONAL_DATA_RES = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email address
    re.compile(r"\bcli-\d+\b"),  # customer id format used in the incident data
    re.compile(r"\b(customer|client|cliente)[ _-]?id\b"),
    re.compile(r"\b(cedula|ssn|social security|passport|pasaporte|credit card|debit card|"
               r"tarjeta de (credito|debito)|driver'?s licen[cs]e|licencia de conduccion)\b"),
    # Brasa Points / loyalty tied to a specific customer or balance
    re.compile(r"\b(brasa points?|puntos brasa|loyalty|lealtad)\b.{0,60}\b(customer|client|cliente|member|"
               r"miembro|socio|balance|saldo|account|cuenta)\b"),
    re.compile(r"\b(customer|client|cliente|member|miembro|socio|balance|saldo|account|cuenta)\b.{0,60}"
               r"\b(brasa points?|puntos brasa|loyalty|lealtad)\b"),
]
_PHONE_CANDIDATE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")

_INJECTION_RES = [
    re.compile(r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|rules?|prompts?|guidelines?|"
               r"memory|memories)\b"),
    re.compile(r"\b(system prompt|developer message|jailbreak|from now on|you (must|should) (always|never)|"
               r"(always|never) (answer|respond|reply)|act as (a|an|if)|pretend (to|you))\b"),
    re.compile(r"\b(ignora|olvida|omite)\b.{0,40}\b(instrucciones|reglas|indicaciones)\b"),
    re.compile(r"\b(a partir de ahora|siempre responde|nunca respondas|actua como)\b"),
]
_FORBIDDEN_CHARS_RE = re.compile(r"[<>`{}]")


def find_violation(text: str) -> str | None:
    """Returns a short reason code if the text must never be stored, else None."""
    folded = fold(text)
    if _PAYROLL_RE.search(folded):
        return "payroll_or_compensation"
    for pattern in _PERSONAL_DATA_RES:
        if pattern.search(folded):
            return "customer_personal_data"
    for match in _PHONE_CANDIDATE_RE.finditer(folded):
        # 9+ digits looks like a phone number; a date like 2026-09-01 has only 8.
        if sum(ch.isdigit() for ch in match.group()) >= 9:
            return "customer_personal_data"
    if _FORBIDDEN_CHARS_RE.search(text):
        return "instruction_like_text"
    for pattern in _INJECTION_RES:
        if pattern.search(folded):
            return "instruction_like_text"
    return None


def validate_proposal(fields: dict) -> tuple[dict | None, str | None]:
    """Checks a proposed memory. Returns (clean_fields, None) if it is allowed,
    or (None, reason_code) if not. The clean fields are what should be stored:
    location and key normalized, whitespace collapsed."""
    location = normalize_location(fields.get("location"))
    if location is None:
        return None, "invalid_location"

    category = fields.get("category")
    if category not in ALLOWED_CATEGORIES:
        return None, "category_not_allowed"

    key = slugify(fields.get("key") or "")[:MAX_KEY_CHARS].strip("_")
    if not key:
        return None, "invalid_key"

    fact = " ".join(str(fields.get("fact") or "").split())
    if not fact or len(fact) > MAX_FACT_CHARS:
        return None, "invalid_fact"

    violation = find_violation(f"{location} {key} {fact}")
    if violation:
        return None, violation

    return {"location": location, "category": category, "key": key, "fact": fact}, None
