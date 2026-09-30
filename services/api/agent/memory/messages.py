"""
services/api/agent/memory/messages.py -- the fixed sentences the agent adds
to its answers when it talks about memory.

They are plain text templates in English and Spanish, not model output, so
what the agent says about saving something is always exactly what the code
did. The language comes from the model calls in llm_steps.py, which report
whether the manager wrote in English or Spanish (default: English).
"""

_TEXT = {
    "en": {
        "ask": "Do you want me to remember this for next time? {location}: {fact}",
        "ask_replaces": " (This would replace what I have now: {old})",
        "saved": "Saved. I'll remember for next time: {fact} ({location}).",
        "rejected": "Okay, I won't save that.",
        "edited": "Got it, I've changed it. Do you want me to remember this instead? {location}: {fact}",
        "discarded_unclear": "(I didn't save my earlier suggestion, since I couldn't tell whether you wanted it.)",
        "edit_refused": "I can't save that kind of information, so I've dropped the suggestion.",
        "not_saved": "I couldn't save that one, so nothing was stored.",
        "rate_limited": "You've reached today's limit for saved corrections, so nothing was stored.",
    },
    "es": {
        "ask": "¿Quieres que lo recuerde para la próxima vez? {location}: {fact}",
        "ask_replaces": " (Esto reemplazaría lo que tengo ahora: {old})",
        "saved": "Guardado. Lo recordaré para la próxima vez: {fact} ({location}).",
        "rejected": "Listo, no lo guardaré.",
        "edited": "Entendido, lo cambié. ¿Quieres que recuerde esto en su lugar? {location}: {fact}",
        "discarded_unclear": "(No guardé mi sugerencia anterior porque no me quedó claro si la querías.)",
        "edit_refused": "No puedo guardar ese tipo de información, así que descarté la sugerencia.",
        "not_saved": "No pude guardar eso, así que no se almacenó nada.",
        "rate_limited": "Llegaste al límite de correcciones guardadas por hoy, así que no se almacenó nada.",
    },
}


def pretty_location(slug: str) -> str:
    return slug.replace("_", " ").title()


def say(name: str, language: str = "en", **values) -> str:
    table = _TEXT.get(language, _TEXT["en"])
    if "location" in values:
        values["location"] = pretty_location(values["location"])
    return table[name].format(**values)
