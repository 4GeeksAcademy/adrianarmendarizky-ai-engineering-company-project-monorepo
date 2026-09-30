"""
evaluators.py -- the evaluator agents (Milestone 9, Part 2).

Three evaluators look at ONE section's draft:
  readability  plain code, py-readability-metrics (Flesch-Kincaid grade level)
  relevance    the model checks the draft against the department's key aspects
  compliance   CONTEXT section 5 rules in code (rules.py), a check that no
               number is invented, and a model check for competitor names

Each evaluator sees only what it needs: the draft and that department's own
facts. Never the whole document and never another department's section.

The three run in parallel (threads). Each returns its OWN dict and writes
nothing shared. Only evaluation.combine() puts the three together, so they
can't overwrite each other's results.
"""

import re
from concurrent.futures import ThreadPoolExecutor

from rfp_intake import llm

from . import evaluation, facts, rules, settings

# --- readability ------------------------------------------------------------


def _scoring_text(draft: str) -> str:
    """Turn Markdown into plain sentences so headings and bullets don't run
    together and inflate the grade level."""
    sentences = []
    for line in draft.splitlines():
        line = line.strip()
        if not line or re.fullmatch(r"[|:\-\s]+", line):
            continue
        line = re.sub(r"^(?:#+|[-*\u2022]|\d+[.)])\s*", "", line)
        line = line.replace("**", "").replace("__", "").replace("|", " ")
        line = re.sub(r"\s+", " ", line).strip().rstrip(":")
        if not line:
            continue
        if line[-1] not in ".!?":
            line += "."
        sentences.append(line)
    return " ".join(sentences)


def evaluate_readability(draft: str) -> dict:
    text = _scoring_text(draft)
    words = len(text.split())
    if words < settings.MIN_WORDS_TO_SCORE:
        return {
            "pass": True, "score": None,
            "details": (f"Only {words} words, so it could not be scored "
                        f"(the tool needs {settings.MIN_WORDS_TO_SCORE}). Readability was not applied."),
        }
    try:
        from readability import Readability
        score = Readability(text).flesch_kincaid().score
    except Exception as error:  # missing NLTK data, odd text, ...
        return {"pass": True, "score": None,
                "details": f"Could not be scored ({error}). Readability was not applied."}

    return {
        "pass": score <= settings.MAX_GRADE_LEVEL,
        "score": round(score, 1),
        "details": f"Flesch-Kincaid grade level {score:.1f} (the limit is {settings.MAX_GRADE_LEVEL:g}).",
    }


# --- relevance --------------------------------------------------------------

RELEVANCE_SYSTEM = """You are the relevance checker for Brasaland proposal drafts. \
You get one department's draft and the numbered key aspects of the client's RFP \
that this department must respond to.

List the numbers of the aspects that the draft clearly does NOT respond to. Count an \
aspect as covered if the draft addresses it in any way, even briefly. Do not list an \
aspect that is only background and needs no response from Brasaland (for example a \
date in the client's own timeline, the client's contact person or the proposal deadline). Facts that only identify the client or schedule the RFP are background: never list them.

Reply with JSON only, no other text:
{"missing": [2, 5]}
Use an empty list if nothing is missing."""


def evaluate_relevance(draft: str, key_aspects: list[str]) -> dict:
    if not key_aspects:
        return {"pass": True, "missing_aspects": []}

    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(key_aspects, start=1))
    prompt = f"Key aspects:\n{numbered}\n\nDraft:\n---\n{draft}\n---"
    answer = llm.ask_json(prompt, system=RELEVANCE_SYSTEM)

    raw = answer.get("missing")
    if not isinstance(raw, list):
        raise llm.LlmJsonError(f"'missing' must be a list, got: {raw!r}")

    # The model answers with numbers; we map them back to the real aspect
    # text, so it can't make up an aspect that isn't in the RFP.
    missing = []
    for item in raw:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= len(key_aspects) and key_aspects[number - 1] not in missing:
            missing.append(key_aspects[number - 1])
    return {"pass": not missing, "missing_aspects": missing}


# --- compliance -------------------------------------------------------------

COMPETITOR_SYSTEM = """You are the competitor checker for Brasaland proposal drafts. \
Brasaland is a grilled-food restaurant chain.

List every OTHER restaurant, catering company or food-service brand named in the \
draft. These are NOT competitors: Brasaland itself, the client named in the RFP \
details, and ingredient suppliers.

Reply with JSON only, no other text:
{"competitors": [{"name": "..."}]}
Use an empty list if there are none."""


def find_competitors(draft: str, metadata: dict) -> list[dict]:
    prompt = (
        f"Client named in the RFP: {metadata.get('client_name') or 'unknown'}\n\n"
        f"Draft:\n---\n{draft}\n---"
    )
    answer = llm.ask_json(prompt, system=COMPETITOR_SYSTEM)
    items = answer.get("competitors")
    if not isinstance(items, list):
        raise llm.LlmJsonError(f"'competitors' must be a list, got: {items!r}")

    client = (metadata.get("client_name") or "").lower()
    found = []
    for item in items:
        name = str(item.get("name") if isinstance(item, dict) else item).strip()
        lowered = name.lower()
        if not name or "brasaland" in lowered:
            continue
        if client and (lowered in client or client in lowered):
            continue  # the model named the client by mistake
        # The evidence comes from OUR text, not the model's: if the name is
        # not really in the draft, the model made it up and we ignore it.
        for sentence in rules._sentences(draft):
            if lowered in sentence.lower():
                found.append(rules._violation(
                    rules.RULE_COMPETITORS,
                    f'This names a possible competitor ("{name}"). Remove it.',
                    sentence,
                ))
                break
    return found


# "1 USD = 4,000 COP": the reference-rate sentence the generator is asked to
# write. Its "1" is part of the phrase, not a figure. It is only skipped when
# the rate matches the configured COP_PER_USD, so a different rate is still flagged.
RATE_PHRASE = re.compile(r"\b1\s*USD\s*(?:=|equals|is)\s*([\d.,]+)\s*COP", re.IGNORECASE)


def _strip_reference_rate(line: str) -> str:
    real = re.sub(r"\D", "", f"{settings.COP_PER_USD:,.0f}")

    def _drop_if_real(match):
        return "" if re.sub(r"\D", "", match.group(1)) == real else match.group(0)

    return RATE_PHRASE.sub(_drop_if_real, line)


def check_no_invented_numbers(draft: str, allowed: set[str]) -> list[dict]:
    """Flag any line with a number that is not in the RFP facts (CONTEXT 2.3)."""
    found = []
    for line in rules._sentences(draft):
        if re.fullmatch(r"\d+[.)]?", line.strip()):
            continue  # a bare list marker ("1."): sentence splitting can leave one alone
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)  # a marker in front of text is not a figure either
        bad = []
        for token in re.findall(r"\d[\d.,]*", _strip_reference_rate(line)):
            digits = re.sub(r"\D", "", token)
            if digits not in allowed:
                bad.append(token.rstrip(".,"))
        if bad:
            found.append(rules._violation(
                rules.RULE_NUMBERS,
                "This has figures that are not in the RFP details or key aspects: "
                + ", ".join(bad) + '. Remove them, or write "to be confirmed".',
                line,
            ))
    return found


def evaluate_compliance(department_id: str, draft: str, *, metadata: dict,
                        key_aspects: list[str], open_questions: list[str]) -> dict:
    violations = list(rules.check_compliance(department_id, draft)["violations"])
    allowed = facts.allowed_numbers(metadata, key_aspects, open_questions)
    violations += check_no_invented_numbers(draft, allowed)
    violations += find_competitors(draft, metadata)

    unique, seen = [], set()
    for violation in violations:
        key = (violation["rule_id"], violation["evidence"], violation["message"])
        if key not in seen:
            seen.add(key)
            unique.append(violation)
    return {
        "pass": not unique,
        "rule_ids": sorted({v["rule_id"] for v in unique}),
        "violations": unique,
    }


# --- all three, in parallel --------------------------------------------------

def evaluate_section(department_id: str, draft: str, *, metadata: dict,
                     key_aspects: list[str], open_questions: list[str]) -> dict:
    """Run the three evaluators in parallel and return one EvaluationResult."""
    with ThreadPoolExecutor(max_workers=3) as pool:
        readability = pool.submit(evaluate_readability, draft)
        relevance = pool.submit(evaluate_relevance, draft, key_aspects)
        compliance = pool.submit(
            evaluate_compliance, department_id, draft,
            metadata=metadata, key_aspects=key_aspects, open_questions=open_questions,
        )
        return evaluation.combine(
            department_id, readability.result(), relevance.result(), compliance.result()
        )
