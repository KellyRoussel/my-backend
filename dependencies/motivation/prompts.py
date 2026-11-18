"""Prompt of the motivation phrase generator.

The examples are in assets/motivation/exemples.txt (read at each generation);
the style below is the other thing to edit to change the tone.
"""
import random
from pathlib import Path

from config import settings

EXAMPLES_FILE = Path(__file__).resolve().parents[2] / "assets" / "motivation" / "exemples.txt"

# TODO(Kelly): describe the style (tone, length, person, vocabulary, what to avoid...)
STYLE_DESCRIPTION = """\
Phrases courtes, percutantes, à la deuxième personne du singulier.
Une seule idée par phrase, faciles à dire à voix haute.
"""



def load_examples() -> list[str]:
    """Examples separated by blank lines, `#` lines being comments."""
    if not EXAMPLES_FILE.is_file():
        return []
    lines = [line.rstrip() for line in EXAMPLES_FILE.read_text(encoding="utf-8").splitlines()]
    examples, current = [], []
    for line in lines + [""]:
        if line.lstrip().startswith("#"):
            continue
        if line.strip():
            current.append(line.strip())
        elif current:
            examples.append(" ".join(current))
            current = []
    return examples


def build_system_prompt() -> str:
    examples = load_examples()
    if len(examples) > settings.motivation_max_examples:
        examples = random.sample(examples, settings.motivation_max_examples)
    examples_section = ""
    if examples:
        listed = "\n".join(f"- {example}" for example in examples)
        examples_section = f"Exemples du style attendu (ne les recopie pas, inspire-t'en) :\n{listed}\n\n"
    return (
        "Tu écris des phrases de motivation qui seront lues à voix haute sur un fond musical.\n\n"
        f"Style à respecter :\n{STYLE_DESCRIPTION}\n"
        f"{examples_section}"
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
