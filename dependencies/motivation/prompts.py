"""Prompt of the motivation phrase generator.

The style and the examples are the only things to edit to change the tone.
"""

# TODO(Kelly): describe the style (tone, length, person, vocabulary, what to avoid...)
STYLE_DESCRIPTION = """\
Phrases courtes, percutantes, à la deuxième personne du singulier.
Une seule idée par phrase, faciles à dire à voix haute.
"""

# TODO(Kelly): replace with the real examples
EXAMPLES: list[str] = [
    "Exemple 1 — à remplacer.",
    "Exemple 2 — à remplacer.",
    "Exemple 3 — à remplacer.",
]


def build_system_prompt() -> str:
    examples = "\n".join(f"- {example}" for example in EXAMPLES)
    return (
        "Tu écris des phrases de motivation qui seront lues à voix haute sur un fond musical.\n\n"
        f"Style à respecter :\n{STYLE_DESCRIPTION}\n"
        f"Exemples du style attendu (ne les recopie pas, inspire-t'en) :\n{examples}\n\n"
        "Règles :\n"
        "- Écris en français, sans emoji, sans hashtag, sans guillemets.\n"
        "- Le texte est destiné à la synthèse vocale : pas d'abréviation, pas de liste, pas de symbole.\n"
        "- Chaque phrase doit être différente des autres et des exemples."
    )


def build_user_prompt(count: int, theme: str | None) -> str:
    prompt = f"Écris {count} phrase(s) de motivation."
    if theme:
        prompt += f"\nThème : {theme}"
    return prompt
