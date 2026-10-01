"""
evaluation.py -- builds the EvaluationResult the ticket asks for, and writes
the feedback the generator receives when a draft fails.

EvaluationResult (the shape from the ticket):
    department_id
    readability: {pass, score, details}
    relevance:   {pass, missing_aspects[]}
    compliance:  {pass, rule_ids[], violations[]}
    overall_pass: bool
    feedback_for_generator: str     (empty when the draft passes)

The feedback is built from the evaluators' concrete findings: the exact
rule that broke, the sentence that broke it, and the exact aspects that are
missing. It never says just "improve the tone".
"""

from . import rules


def build_feedback(readability: dict, relevance: dict, compliance: dict) -> str:
    lines = []

    if not readability["pass"]:
        lines.append(
            "READABILITY: " + readability["details"]
            + " Use shorter sentences and plainer words."
        )

    if not relevance["pass"]:
        lines.append(
            "RELEVANCE: the draft does not cover these points from the RFP. "
            "Add each one, using only facts from the key aspects:"
        )
        for item in relevance["missing_aspects"]:
            lines.append(f"  - {item}")

    if not compliance["pass"]:
        lines.append("COMPLIANCE: fix each problem below.")
        for violation in compliance["violations"]:
            rule_text = rules.rule_text(violation["rule_id"])
            lines.append(f"  - [{violation['rule_id']}] {rule_text}")
            lines.append(f"    Problem: {violation['message']}")
            if violation.get("evidence"):
                lines.append(f'    Text: "{violation["evidence"]}"')

    return "\n".join(lines)


def combine(department_id: str, readability: dict, relevance: dict, compliance: dict) -> dict:
    """Merge the three evaluators' results into one EvaluationResult.

    Each evaluator writes only its own part. Only this function puts them
    together, so two evaluators running in parallel can never overwrite each
    other's results.
    """
    overall = readability["pass"] and relevance["pass"] and compliance["pass"]
    return {
        "department_id": department_id,
        "readability": readability,
        "relevance": relevance,
        "compliance": compliance,
        "overall_pass": overall,
        "feedback_for_generator": "" if overall else build_feedback(readability, relevance, compliance),
    }
