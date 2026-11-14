from __future__ import annotations

import json
import re

from dataclasses import (
    asdict,
    dataclass,
    replace,
)

from pathlib import Path

import requests

from src.config import (
    AGNES_API_KEY,
    AGNES_BASE_URL,
    AGNES_TEXT_MODEL,
)

from src.scene_planner import (
    VideoPlan,
)


# ==========================================================
# VERSION
# ==========================================================

DIRECTOR_SCHEMA_VERSION = 1


# ==========================================================
# EXCEPTION
# ==========================================================


class DirectorError(Exception):
    pass


# ==========================================================
# BACKGROUND POPULATION
# ==========================================================


@dataclass(frozen=True)
class BackgroundPopulation:

    enabled: bool = False

    description: str = ""

    density: str = "none"

    activity: str = ""

    continuity_required: bool = False


# ==========================================================
# SCENE DIRECTION
# ==========================================================


@dataclass(frozen=True)
class SceneDirection:

    scene_number: int

    narrative_focus: str

    image_prompt: str

    action: str

    camera: str

    background_population: BackgroundPopulation

    ambience: str

    sound_design: str


# ==========================================================
# DIRECTOR PLAN
# ==========================================================


@dataclass(frozen=True)
class DirectorPlan:

    scenes: list[SceneDirection]

    notes: str = ""

    @property
    def scene_map(
        self,
    ) -> dict[int, SceneDirection]:

        return {
            scene.scene_number: scene
            for scene in self.scenes
        }


# ==========================================================
# DIRECTOR
# ==========================================================


class DirectorPlanner:
    """
    Adds professional cinematographic direction on top of
    an existing storyboard.

    It does NOT rewrite the story.

    It decides:

    - image composition
    - visual action beats
    - camera direction
    - background population
    - ambience
    - future sound-design intention

    The logic is completely generic.
    """

    VALID_DENSITIES = {
        "none",
        "low",
        "medium",
        "high",
    }

    def __init__(
        self,
        model: str = AGNES_TEXT_MODEL,
        timeout: int = 180,
    ) -> None:

        self.model = model

        self.timeout = timeout

        self.url = (
            f"{AGNES_BASE_URL}"
            "/v1/chat/completions"
        )

        self.headers = {
            "Authorization": (
                f"Bearer {AGNES_API_KEY}"
            ),
            "Content-Type": (
                "application/json"
            ),
        }

    # ======================================================
    # CREATE
    # ======================================================

    def create_plan(
        self,
        video_plan: VideoPlan,
        source_prompt: str,
    ) -> DirectorPlan:

        source_prompt = (
            source_prompt
            or ""
        ).strip()

        if not source_prompt:

            raise DirectorError(
                "The original source prompt "
                "is required."
            )

        payload = {
            "original_prompt": (
                source_prompt
            ),
            "title": (
                video_plan.title
            ),
            "language": (
                video_plan.language
            ),
            "style": (
                video_plan.style_description
            ),
            "setting": (
                video_plan.setting_description
            ),
            "continuity": (
                video_plan.continuity_constraints
            ),
            "characters": [
                {
                    "id": character.id,
                    "name": character.name,
                    "description": (
                        character.description
                    ),
                    "reference_prompt": (
                        character.reference_prompt
                    ),
                }
                for character
                in video_plan.characters
            ],
            "scenes": [
                {
                    "number": scene.number,
                    "duration": scene.duration,
                    "visual_prompt": (
                        scene.visual_prompt
                    ),
                    "dialogue": (
                        scene.dialogue
                    ),
                    "speaker_id": (
                        scene.speaker_id
                    ),
                    "character_ids": list(
                        scene.character_ids
                    ),
                    "start_state": (
                        scene.start_state
                    ),
                    "end_state": (
                        scene.end_state
                    ),
                    "use_previous_frame": (
                        scene.use_previous_frame
                    ),
                }
                for scene
                in video_plan.scenes
            ],
        }

        system_prompt = """
You are the cinematography and mise-en-scène director for a
professional AI-video production system.

You receive an already approved STORYBOARD.

Do NOT rewrite the story.
Do NOT change the dialogue.
Do NOT change the characters.
Do NOT change scene duration.

Your task is to enrich every scene with professional
direction.


============================================================
GOAL
============================================================

A scene must feel alive, intentional and cinematic.

Avoid:

- static characters simply standing and talking
- empty locations that should naturally be populated
- random camera movement
- purposeless extras
- excessive internal cuts
- unexplained action
- visual clutter


============================================================
ACTION
============================================================

Create 2 to 4 connected visual ACTION BEATS whenever the
scene duration allows it.

Example structure:

character performs activity
→ notices something
→ reacts
→ approaches another character

The beats must form ONE coherent scene.

Do not create a montage inside a short scene unless the
storyboard explicitly requires a montage.


============================================================
CAMERA
============================================================

Describe:

1. initial framing
2. motivated camera movement
3. final framing when useful

Examples:

- wide establishing shot
- medium two-shot
- close-up
- over-the-shoulder
- slow dolly
- gentle tracking shot
- push-in
- controlled handheld
- static reaction shot
- object insert

Camera movement must have a narrative reason.

Never use random cinematic terminology just for style.

Dialogue scenes should keep the speaking mouth visible.


============================================================
BACKGROUND POPULATION
============================================================

Determine whether the location naturally needs secondary
people or activity.

Examples:

construction site:
workers, tools, active work

restaurant:
customers and staff

hospital:
medical staff and patients

market:
vendors and customers

school:
students and staff

street:
pedestrians when appropriate

office:
employees when appropriate


IMPORTANT:

Background people are NOT automatically recurring
characters.

They usually do NOT require identity continuity.

They must belong naturally to the same visual universe as
the main characters.

They must not steal attention from the protagonists.

Use:

density = none | low | medium | high


============================================================
IMAGE PROMPT
============================================================

Create one excellent still-image prompt representing the
strongest useful reference frame for the scene.

The image prompt should describe:

- visual style
- location
- main characters
- their positions
- important action state
- background population
- lighting
- composition
- camera angle
- relevant props

It must preserve all established character anatomy.

When characters are unusual, non-human, anthropomorphic,
robotic, stylized or otherwise anatomically distinctive,
repeat the critical anatomical traits clearly.

Never reduce an unusual character to a generic human.

The image should function as a composition reference for
future video generation.

Avoid readable generated text unless the original story
absolutely requires it.


============================================================
AMBIENCE
============================================================

Describe the visual atmosphere:

- lighting
- weather
- time of day
- environmental motion
- depth
- mood

Keep it concise.


============================================================
SOUND DESIGN
============================================================

Describe future post-production sound only.

Examples:

- construction tools
- room tone
- footsteps
- crowd murmur
- traffic
- rain
- machinery
- doors
- cloth movement

Do NOT invent new spoken dialogue.

Do NOT add dialogue to sound_design.


============================================================
NARRATIVE FOCUS
============================================================

State in one concise sentence what the viewer must
understand or feel in this scene.


============================================================
OUTPUT
============================================================

Return ONLY valid JSON.

No markdown.

Use exactly:

{
  "scenes": [
    {
      "scene_number": 1,
      "narrative_focus": "...",
      "image_prompt": "...",
      "action": "...",
      "camera": "...",
      "background_population": {
        "enabled": true,
        "description": "...",
        "density": "medium",
        "activity": "...",
        "continuity_required": false
      },
      "ambience": "...",
      "sound_design": "..."
    }
  ],
  "notes": ""
}

Return one entry for EVERY storyboard scene.
""".strip()

        raw = self._chat(
            system_prompt=(
                system_prompt
            ),
            user_prompt=json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
        )

        data = (
            self._extract_json(
                raw
            )
        )

        return self._parse(
            data=data,
            video_plan=(
                video_plan
            ),
        )

    # ======================================================
    # REQUEST
    # ======================================================

    def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:

        request_payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        system_prompt
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        user_prompt
                    ),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 6000,
        }

        try:

            response = requests.post(
                self.url,
                headers=(
                    self.headers
                ),
                json=(
                    request_payload
                ),
                timeout=(
                    self.timeout
                ),
            )

        except requests.RequestException as exc:

            raise DirectorError(
                "Unable to contact Agnes "
                f"text model: {exc}"
            ) from exc

        if not response.ok:

            raise DirectorError(
                "Director request failed. "
                f"HTTP {response.status_code}: "
                f"{response.text}"
            )

        try:

            return str(
                response.json()[
                    "choices"
                ][0][
                    "message"
                ][
                    "content"
                ]
            )

        except (
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:

            raise DirectorError(
                "Unexpected response from "
                "the director model."
            ) from exc

    # ======================================================
    # JSON
    # ======================================================

    @staticmethod
    def _extract_json(
        text: str,
    ) -> dict:

        text = (
            text
            or ""
        ).strip()

        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

        try:

            result = json.loads(
                text
            )

        except json.JSONDecodeError:

            start = text.find(
                "{"
            )

            end = text.rfind(
                "}"
            )

            if (
                start < 0
                or end <= start
            ):

                raise DirectorError(
                    "No valid JSON found "
                    "in director response."
                )

            try:

                result = json.loads(
                    text[
                        start:
                        end + 1
                    ]
                )

            except json.JSONDecodeError as exc:

                raise DirectorError(
                    "Invalid director JSON."
                ) from exc

        if not isinstance(
            result,
            dict,
        ):

            raise DirectorError(
                "Director JSON root must "
                "be an object."
            )

        return result

    # ======================================================
    # PARSE
    # ======================================================

    def _parse(
        self,
        data: dict,
        video_plan: VideoPlan,
    ) -> DirectorPlan:

        valid_scene_numbers = {
            scene.number
            for scene
            in video_plan.scenes
        }

        parsed = {}

        raw_scenes = (
            data.get(
                "scenes",
                [],
            )
        )

        if not isinstance(
            raw_scenes,
            list,
        ):

            raw_scenes = []

        for raw in raw_scenes:

            if not isinstance(
                raw,
                dict,
            ):

                continue

            try:

                scene_number = int(
                    raw.get(
                        "scene_number"
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                continue

            if (
                scene_number
                not in valid_scene_numbers
            ):

                continue

            background_raw = (
                raw.get(
                    "background_population",
                    {},
                )
            )

            if not isinstance(
                background_raw,
                dict,
            ):

                background_raw = {}

            density = str(
                background_raw.get(
                    "density",
                    "none",
                )
            ).strip().lower()

            if (
                density
                not in self.VALID_DENSITIES
            ):

                density = "none"

            enabled = bool(
                background_raw.get(
                    "enabled",
                    False,
                )
            )

            if not enabled:

                density = "none"

            background = (
                BackgroundPopulation(
                    enabled=enabled,
                    description=str(
                        background_raw.get(
                            "description",
                            "",
                        )
                    ).strip(),
                    density=density,
                    activity=str(
                        background_raw.get(
                            "activity",
                            "",
                        )
                    ).strip(),
                    continuity_required=bool(
                        background_raw.get(
                            "continuity_required",
                            False,
                        )
                    ),
                )
            )

            parsed[
                scene_number
            ] = SceneDirection(
                scene_number=(
                    scene_number
                ),
                narrative_focus=str(
                    raw.get(
                        "narrative_focus",
                        "",
                    )
                ).strip(),
                image_prompt=str(
                    raw.get(
                        "image_prompt",
                        "",
                    )
                ).strip(),
                action=str(
                    raw.get(
                        "action",
                        "",
                    )
                ).strip(),
                camera=str(
                    raw.get(
                        "camera",
                        "",
                    )
                ).strip(),
                background_population=(
                    background
                ),
                ambience=str(
                    raw.get(
                        "ambience",
                        "",
                    )
                ).strip(),
                sound_design=str(
                    raw.get(
                        "sound_design",
                        "",
                    )
                ).strip(),
            )

        # Every storyboard scene must have a direction.
        missing = (
            valid_scene_numbers
            - set(
                parsed
            )
        )

        if missing:

            raise DirectorError(
                "Director model omitted scenes: "
                + ", ".join(
                    str(number)
                    for number
                    in sorted(
                        missing
                    )
                )
            )

        ordered = [
            parsed[
                scene.number
            ]
            for scene
            in video_plan.scenes
        ]

        return DirectorPlan(
            scenes=ordered,
            notes=str(
                data.get(
                    "notes",
                    "",
                )
            ).strip(),
        )

    # ======================================================
    # SAVE
    # ======================================================

    @staticmethod
    def save(
        plan: DirectorPlan,
        path: Path,
    ) -> None:

        path = Path(
            path
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "schema_version": (
                DIRECTOR_SCHEMA_VERSION
            ),
            **asdict(
                plan
            ),
        }

        temporary = Path(
            str(path)
            + ".tmp"
        )

        temporary.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary.replace(
            path
        )

    # ======================================================
    # LOAD
    # ======================================================

    @staticmethod
    def load(
        path: Path,
    ) -> DirectorPlan:

        try:

            data = json.loads(
                Path(path).read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:

            raise DirectorError(
                "Unable to load "
                "director plan."
            ) from exc

        if (
            data.get(
                "schema_version"
            )
            !=
            DIRECTOR_SCHEMA_VERSION
        ):

            raise DirectorError(
                "Obsolete director-plan schema."
            )

        scenes = []

        for raw in (
            data.get(
                "scenes",
                []
            )
        ):

            background_raw = (
                raw.get(
                    "background_population",
                    {},
                )
            )

            scenes.append(
                SceneDirection(
                    scene_number=int(
                        raw[
                            "scene_number"
                        ]
                    ),
                    narrative_focus=str(
                        raw.get(
                            "narrative_focus",
                            "",
                        )
                    ),
                    image_prompt=str(
                        raw.get(
                            "image_prompt",
                            "",
                        )
                    ),
                    action=str(
                        raw.get(
                            "action",
                            "",
                        )
                    ),
                    camera=str(
                        raw.get(
                            "camera",
                            "",
                        )
                    ),
                    background_population=(
                        BackgroundPopulation(
                            enabled=bool(
                                background_raw.get(
                                    "enabled",
                                    False,
                                )
                            ),
                            description=str(
                                background_raw.get(
                                    "description",
                                    "",
                                )
                            ),
                            density=str(
                                background_raw.get(
                                    "density",
                                    "none",
                                )
                            ),
                            activity=str(
                                background_raw.get(
                                    "activity",
                                    "",
                                )
                            ),
                            continuity_required=bool(
                                background_raw.get(
                                    "continuity_required",
                                    False,
                                )
                            ),
                        )
                    ),
                    ambience=str(
                        raw.get(
                            "ambience",
                            "",
                        )
                    ),
                    sound_design=str(
                        raw.get(
                            "sound_design",
                            "",
                        )
                    ),
                )
            )

        return DirectorPlan(
            scenes=scenes,
            notes=str(
                data.get(
                    "notes",
                    "",
                )
            ),
        )


# ==========================================================
# APPLY DIRECTION TO VIDEO PROMPTS
# ==========================================================


DIRECTOR_START = (
    "\n\n--- DIRECTOR BLOCK START ---\n"
)

DIRECTOR_END = (
    "\n--- DIRECTOR BLOCK END ---"
)


def _remove_existing_director_block(
    text: str,
) -> str:

    text = (
        text
        or ""
    )

    start = text.find(
        DIRECTOR_START
    )

    if start < 0:

        return text.strip()

    return (
        text[
            :start
        ]
        .strip()
    )


def apply_director_plan(
    video_plan: VideoPlan,
    director_plan: DirectorPlan,
) -> VideoPlan:
    """
    Returns a copy of VideoPlan whose visual prompts include
    professional director instructions.

    It is idempotent: calling this function twice will not
    duplicate the director block.
    """

    direction_map = (
        director_plan.scene_map
    )

    updated_scenes = []

    for scene in (
        video_plan.scenes
    ):

        direction = (
            direction_map.get(
                scene.number
            )
        )

        if direction is None:

            updated_scenes.append(
                scene
            )

            continue

        base_prompt = (
            _remove_existing_director_block(
                scene.visual_prompt
            )
        )

        background = (
            direction
            .background_population
        )

        if background.enabled:

            background_text = (
                f"""
BACKGROUND POPULATION

Density: {background.density}

Description:
{background.description}

Activity:
{background.activity}

Background people are secondary to the main narrative.
Do not let them dominate the composition.
""".strip()
            )

        else:

            background_text = (
                """
BACKGROUND POPULATION

No significant background population is required.
Do not add distracting crowds.
""".strip()
            )

        director_block = f"""
{DIRECTOR_START}

NARRATIVE FOCUS

{direction.narrative_focus}


ACTION BEATS

{direction.action}


CAMERA DIRECTION

{direction.camera}


{background_text}


VISUAL AMBIENCE

{direction.ambience}

{DIRECTOR_END}
""".strip()

        updated_prompt = (
            base_prompt
            + "\n\n"
            + director_block
        )

        updated_scenes.append(
            replace(
                scene,
                visual_prompt=(
                    updated_prompt
                ),
            )
        )

    return replace(
        video_plan,
        scenes=(
            updated_scenes
        ),
    )