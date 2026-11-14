"""Conservative local extraction of explicitly quoted speech; never rewrite the prompt."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DialogueTurn:
    speaker: str
    dialogue: str


@dataclass(frozen=True)
class ScenePromptAnalysis:
    raw_prompt: str
    turns: tuple[DialogueTurn, ...]
    uncertain: bool = False


def analyze_scene_prompt(raw_prompt: str) -> ScenePromptAnalysis:
    turns = []
    uncertain = False
    quoted = re.compile(r'«\s*(.*?)\s*»|"([^"\n]*(?:\n[^"\n]*)*)"|“(.*?)”', re.S)
    for match in quoted.finditer(raw_prompt):
        prefix = raw_prompt[:match.start()].rstrip()
        label = re.search(
            r"(?:^|[.!?\n])\s*([\wÀ-ÿ][\wÀ-ÿ '’-]*?)\s+"
            r"(?:dit|répond|demande|ajoute|murmure|crie|says|asks|replies)\s*:?$",
            prefix, re.I,
        )
        if label is None:
            label = re.search(r"(?:^|\n)\s*([\wÀ-ÿ][\wÀ-ÿ '’-]*):$", prefix)
        if label is None:
            uncertain = True
            continue
        turns.append(DialogueTurn(label.group(1).strip(), next(g for g in match.groups() if g is not None).strip()))
    if not turns and re.search(r"\b(dit|répond|demande|murmure|crie)\s*:", raw_prompt, re.I):
        uncertain = True
    return ScenePromptAnalysis(raw_prompt, tuple(turns), uncertain)
