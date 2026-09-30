"""
convert.py -- first stage of the RFP intake pipeline (Milestone 9, Part 1).

Turns an uploaded PDF into Markdown BEFORE any AI agent reads it (the ticket
requires this: PDFs are heavy on tokens), works out whether the text is
English or Spanish, and computes readability scores.

No AI model is used in this file, so it is fast and easy to test.

Readability caveats:
  - py-readability-metrics refuses text under 100 words. When that happens
    we store "not available" instead of crashing the pipeline.
  - The formulas are built for English. Scores on Spanish text still
    run, but should be treated as rough.
"""

import re
from pathlib import Path

# A few very common words in each language. Whichever list matches more
# words in the document wins. Good enough for English vs Spanish RFPs.
SPANISH_WORDS = {
    "el", "la", "los", "las", "de", "que", "y", "en", "un", "una", "para",
    "con", "por", "del", "nos", "somos", "hola", "gracias", "saludos",
    "asunto", "como", "más", "es", "si", "al", "se", "su", "muy",
}
ENGLISH_WORDS = {
    "the", "and", "of", "to", "in", "for", "is", "we", "with", "our",
    "this", "that", "will", "are", "be", "on", "as", "by", "or", "at",
}


def pdf_to_markdown(pdf_path) -> str:
    """Read a PDF file and return its text as Markdown."""
    # Imported here so other code can import this file without
    # needing markitdown installed (same idea as database.py's imports).
    from markitdown import MarkItDown

    result = MarkItDown().convert(str(Path(pdf_path)))
    return (result.text_content or "").strip()


def detect_language(text: str) -> str:
    """Return "es" or "en" (defaults to "en" on a tie or empty text)."""
    words = re.findall(r"[a-záéíóúñü]+", text.lower())
    spanish = sum(1 for w in words if w in SPANISH_WORDS)
    english = sum(1 for w in words if w in ENGLISH_WORDS)
    return "es" if spanish > english else "en"


def compute_readability(text: str) -> dict:
    """Return word count and readability scores.

    The keys match the columns in rfp_models.RfpMetadata:
    word_count, flesch_kincaid, gunning_fog, readability_note.
    A score that can't be computed is None, and the note says why.
    """
    result = {
        "word_count": len(text.split()),
        "flesch_kincaid": None,
        "gunning_fog": None,
        "readability_note": None,
    }

    # Imported here for the same reason as markitdown above.
    from readability import Readability

    try:
        reader = Readability(text)
        result["flesch_kincaid"] = reader.flesch_kincaid().score
        result["gunning_fog"] = reader.gunning_fog().score
    except Exception as error:  # short text, missing NLTK data, etc.
        result["readability_note"] = f"not available: {error}"

    return result
