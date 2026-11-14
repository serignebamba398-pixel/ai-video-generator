import re
from dataclasses import dataclass


class PromptParseError(ValueError):
    """Raised when no dialogue can be extracted from a prompt."""


@dataclass(frozen=True)
class ParsedPrompt:
    original_prompt: str
    dialogue: str


QUOTE_PATTERNS = (
    re.compile(r"«\s*(.*?)\s*»", re.DOTALL),
    re.compile(r"“\s*(.*?)\s*”", re.DOTALL),
    re.compile(r'"([^"]+)"', re.DOTALL),
)


def extract_dialogue(prompt: str) -> ParsedPrompt:
    """
    Extract spoken dialogue from quoted text.

    Supported quotation styles:
    - « Bonjour »
    - “Bonjour”
    - "Bonjour"
    """

    clean_prompt = prompt.strip()

    if not clean_prompt:
        raise PromptParseError(
            "The prompt cannot be empty."
        )

    dialogue_segments = []

    for pattern in QUOTE_PATTERNS:
        matches = pattern.findall(clean_prompt)

        if matches:
            dialogue_segments = matches
            break

    if not dialogue_segments:
        raise PromptParseError(
            "No dialogue was detected. "
            "Place the spoken sentence between quotation marks, "
            'for example: « Bonjour, comment allez-vous ? »'
        )

    normalized_segments = []

    for segment in dialogue_segments:
        normalized = " ".join(
            segment.split()
        )

        if normalized:
            normalized_segments.append(
                normalized
            )

    if not normalized_segments:
        raise PromptParseError(
            "The detected dialogue is empty."
        )

    dialogue = " ".join(
        normalized_segments
    )

    return ParsedPrompt(
        original_prompt=clean_prompt,
        dialogue=dialogue,
    )


def build_reference_prompt(
    parsed: ParsedPrompt,
) -> str:
    """
    Add instructions telling Agnes how the supplied audio
    must be used.
    """

    return f"""
{parsed.original_prompt}

The supplied reference audio <Audio 1> contains the exact
spoken dialogue for the visible speaker in this scene.

Use <Audio 1> as the character's speech.

The visible speaker must pronounce exactly the dialogue
contained in <Audio 1>.

Synchronize the lips, mouth shapes, jaw movement and facial
motion as closely as possible with <Audio 1>.

The face must remain clearly visible while speaking.

Use natural blinking, natural head movement and realistic
facial expressions.

Single visible speaker during the spoken dialogue.

Do not generate additional speech.
Do not generate additional voices.
Do not change the supplied dialogue.
Do not add subtitles.
Do not add on-screen text.

Maintain realistic human facial anatomy and natural mouth
movement throughout the spoken dialogue.
""".strip()