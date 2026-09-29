"""
services/api/agent/guardrails/messages.py -- Milestone 8 Part 2 (SEC-114):
the fixed English/Spanish replies for each blocked scope.

Plain text templates, not model output -- like agent/memory/messages.py,
what the agent says when it refuses or redirects is always exactly what
the code decided, never something an LLM call could be talked out of.
The language is guessed from the user's own message (patterns.guess_language),
matching CONTEXT-brasaland's bilingual requirement from Part 1.
"""

_TEXT = {
    "en": {
        "instruction_change": (
            "I can't change how I operate based on a message, no matter how it's phrased. "
            "I'm the Brasaland support agent -- happy to help with locations, tickets, "
            "inventory, suppliers, or the loyalty program."
        ),
        "personal_task": (
            "That's outside what I can help with -- I'm the Brasaland support agent, not a "
            "general-purpose assistant. I can help with Brasaland topics: locations, tickets, "
            "inventory, suppliers, or the loyalty program."
        ),
        "casual": (
            "I don't have real-time information like that. I'm the Brasaland support agent -- "
            "happy to help with locations, tickets, inventory, suppliers, or the loyalty program."
        ),
        "output_blocked": (
            "I can't share that. Let me know if there's something else about Brasaland I can help with."
        ),
    },
    "es": {
        "instruction_change": (
            "No puedo cambiar cómo funciono por un mensaje, sin importar cómo esté formulado. "
            "Soy el agente de soporte de Brasaland -- con gusto te ayudo con ubicaciones, "
            "tickets, inventario, proveedores o el programa de lealtad."
        ),
        "personal_task": (
            "Eso está fuera de lo que puedo ayudar -- soy el agente de soporte de Brasaland, no "
            "un asistente de propósito general. Puedo ayudarte con temas de Brasaland: "
            "ubicaciones, tickets, inventario, proveedores o el programa de lealtad."
        ),
        "casual": (
            "No tengo información en tiempo real como esa. Soy el agente de soporte de "
            "Brasaland -- con gusto te ayudo con ubicaciones, tickets, inventario, proveedores "
            "o el programa de lealtad."
        ),
        "output_blocked": (
            "No puedo compartir eso. Avísame si hay algo más sobre Brasaland en lo que pueda ayudarte."
        ),
    },
}


def say(name: str, language: str = "en") -> str:
    table = _TEXT.get(language, _TEXT["en"])
    return table[name]
