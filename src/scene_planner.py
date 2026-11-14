from __future__ import annotations

import json
import re

from dataclasses import dataclass
from typing import Optional

import requests

from src.config import (
    AGNES_API_KEY,
    AGNES_BASE_URL,
    AGNES_TEXT_MODEL,
)


class ScenePlannerError(Exception):
    pass


# ==========================================================
# DATA MODELS
# ==========================================================


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    description: str
    reference_prompt: str


@dataclass(frozen=True)
class Scene:
    number: int
    duration: int

    visual_prompt: str

    dialogue: str = ""

    speaker_id: Optional[str] = None

    character_ids: tuple[str, ...] = ()

    start_state: str = ""

    end_state: str = ""

    # Whether this scene should receive a visual continuity
    # reference extracted from the previous scene.
    use_previous_frame: bool = False


@dataclass(frozen=True)
class VideoPlan:
    title: str
    language: str

    character_description: str

    style_description: str

    setting_description: str

    continuity_constraints: str

    characters: list[Character]

    scenes: list[Scene]

    @property
    def total_duration(
        self,
    ) -> int:

        return sum(
            scene.duration
            for scene in self.scenes
        )

    @property
    def character_map(
        self,
    ) -> dict[str, Character]:

        return {
            character.id: character
            for character
            in self.characters
        }


# ==========================================================
# PLANNER
# ==========================================================


class ScenePlanner:

    def __init__(
        self,
        model: str = AGNES_TEXT_MODEL,
        timeout: int = 120,
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
    # GENERIC CHAT
    # ======================================================

    def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 7000,
    ) -> str:

        payload = {
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
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:

            response = requests.post(
                self.url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout,
            )

        except requests.RequestException as exc:

            raise ScenePlannerError(
                "Unable to contact Agnes text API: "
                f"{exc}"
            ) from exc

        if not response.ok:

            raise ScenePlannerError(
                "Agnes text request failed. "
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

            raise ScenePlannerError(
                "Unexpected Agnes text response."
            ) from exc

    # ======================================================
    # CREATE PLAN
    # ======================================================

    def create_plan(
        self,
        user_prompt: str,
        target_duration: int = 60,
        max_attempts: int = 3,
    ) -> VideoPlan:

        user_prompt = (
            user_prompt
            or ""
        ).strip()

        if not user_prompt:

            raise ScenePlannerError(
                "User prompt is empty."
            )

        last_error = None

        for attempt in range(
            1,
            max_attempts + 1,
        ):

            try:

                raw = self._request_plan(
                    user_prompt=(
                        user_prompt
                    ),
                    target_duration=(
                        target_duration
                    ),
                )

                draft_data = (
                    self._extract_json(
                        raw
                    )
                )

                repaired_data = (
                    self._repair_plan(
                        user_prompt=(
                            user_prompt
                        ),
                        target_duration=(
                            target_duration
                        ),
                        draft_data=(
                            draft_data
                        ),
                    )
                )

                plan = self._parse_plan(
                    repaired_data
                )

                plan = (
                    self._normalize_duration(
                        plan=plan,
                        target_duration=(
                            target_duration
                        ),
                    )
                )

                self._validate_plan(
                    plan=plan,
                    target_duration=(
                        target_duration
                    ),
                )

                return plan

            except Exception as exc:

                last_error = exc

                print()

                print(
                    f"Storyboard attempt "
                    f"{attempt} failed:"
                )

                print(
                    exc
                )

                print()

        raise ScenePlannerError(
            "Unable to create storyboard. "
            f"Last error: {last_error}"
        )

    # ======================================================
    # INITIAL STORYBOARD
    # ======================================================

    def _request_plan(
        self,
        user_prompt: str,
        target_duration: int,
    ) -> str:

        system_prompt = f"""
You are a professional film director, storyboard artist,
continuity supervisor and AI-video prompt engineer.

Transform ONE user idea into a coherent cinematic video.

TOTAL DURATION

Exactly {target_duration} seconds.

Return ONLY valid JSON.
No Markdown.
No explanation.


============================================================
SCENE STRUCTURE
============================================================

Create as many scenes as the story requires, with no fixed scene-count cap.
For a total of {target_duration} seconds, use between {(target_duration + 11) // 12} and {target_duration // 4} scenes so each scene can last 4 to 12 seconds.

Every scene lasts between 4 and 12 seconds.

Every scene must advance the story.

Avoid filler.

Avoid repetitive scenes.


============================================================
SETTING
============================================================

Derive the visual world from the user's prompt.

Create:

setting_description

It should define, when relevant:

- country
- city or region
- historical era
- architecture
- environment
- roads
- vehicle types
- technology
- clothing
- weather
- time of day
- interiors
- infrastructure
- cultural context

Never automatically replace local objects with famous
foreign stereotypes.

Do not depend on readable AI-generated text to establish
location.


============================================================
GLOBAL CONTINUITY
============================================================

Create:

continuity_constraints

Describe important things that should remain stable:

- time of day
- weather
- vehicle identity
- important rooms
- props
- clothing
- object ownership
- damage caused earlier
- direction of travel
- environment


============================================================
CHARACTERS
============================================================

Identify every recurring human character.

Use stable IDs:

character_1
character_2
character_3

Each character has:

- id
- name
- description
- reference_prompt

description contains persistent identity:

- approximate age
- face
- hair
- body build
- clothing
- accessories
- important physical features

reference_prompt must request a realistic single-person
reference image.

Clear face.
Neutral background.
No other people.
No text.


============================================================
CHARACTER PRESENCE
============================================================

For EVERY scene:

character_ids must contain EVERY recurring character who
is visibly present.

This includes someone:

- in the background
- through a window
- in a mirror
- partially visible
- entering
- exiting
- driving
- sitting
- reacting silently

If a character performs an action in visual_prompt, that
character MUST appear in character_ids.

If no recurring character is visible:

character_ids = []


============================================================
ACTION DIRECTION
============================================================

Every scene must define:

start_state
end_state

start_state describes what is true at the FIRST frame.

end_state describes what must be true at the LAST frame.

The action must progress clearly from start_state to
end_state.

Be particularly explicit for:

- entering / exiting
- arriving / leaving
- opening / closing
- sitting / standing
- picking up / putting down
- giving / receiving
- getting into / getting out of vehicles


============================================================
PREVIOUS-FRAME CONTINUITY
============================================================

Every scene also contains:

use_previous_frame

This is a boolean.

For scene 1 it MUST be false.

Set use_previous_frame=true when the scene is a direct
visual continuation of the previous scene and the previous
scene's final frame would help preserve:

- environment
- character position
- vehicle state
- object state
- lighting
- physical action
- spatial continuity

Examples where true is useful:

- person continues entering a vehicle
- conversation continues in same room
- reaction follows immediately
- camera changes angle but action is continuous
- same object/vehicle/environment continues immediately

Set use_previous_frame=false when there is an intentional:

- time jump
- new unrelated location
- montage jump
- dream/flashback change
- major scene transition
- deliberately different environment

Do NOT set it true automatically for every scene.

Character reference images will still preserve identity
when use_previous_frame is false.


============================================================
PHYSICAL PLAUSIBILITY
============================================================

Keep movements physically plausible unless the user's
story intentionally contains surrealism, fantasy or
impossible comedy.

Vehicles should use plausible surfaces and routes.

Objects should behave coherently.


============================================================
DIALOGUE
============================================================

Dialogue should normally be French unless another language
is requested.

dialogue contains ONLY words actually spoken.

Never include:

character names
quotation marks
stage directions
parentheses
speaker labels

If dialogue is empty:

speaker_id = null

If dialogue exists:

speaker_id must identify one visible recurring character.

The speaker must also appear in character_ids.

Prefer short natural spoken lines.


============================================================
OUTPUT
============================================================

Return exactly this JSON structure:

{{
  "title": "string",
  "language": "French",
  "style_description": "string",
  "setting_description": "string",
  "continuity_constraints": "string",

  "characters": [
    {{
      "id": "character_1",
      "name": "string",
      "description": "string",
      "reference_prompt": "string"
    }}
  ],

  "scenes": [
    {{
      "number": 1,
      "duration": 8,
      "visual_prompt": "English visual description",
      "start_state": "English first-frame state",
      "end_state": "English final-frame state",
      "use_previous_frame": false,
      "dialogue": "",
      "speaker_id": null,
      "character_ids": []
    }}
  ]
}}
""".strip()

        return self._chat(
            system_prompt=(
                system_prompt
            ),
            user_prompt=(
                user_prompt
            ),
            temperature=0.6,
            max_tokens=8000,
        )

    # ======================================================
    # STORYBOARD QA
    # ======================================================

    def _repair_plan(
        self,
        user_prompt: str,
        target_duration: int,
        draft_data: dict,
    ) -> dict:

        system_prompt = f"""
You are a final production continuity supervisor.

You receive:
- the original user request
- a draft storyboard

Return ONLY corrected JSON.

Do not explain corrections.

Preserve the user's story.


============================================================
CHECK CHARACTER PRESENCE
============================================================

Every recurring character visible in visual_prompt,
start_state or end_state must appear in character_ids.

Every speaker must be visible.


============================================================
CHECK WORLD AUTHENTICITY
============================================================

Correct accidental geographic, historical or cultural
mismatches.

Vehicles, buildings, roads, interiors, technology and
objects must fit the world described by the user's prompt.

Do not import visual stereotypes from unrelated places.


============================================================
CHECK ACTION DIRECTION
============================================================

start_state, visual_prompt and end_state must agree.

Do not reverse entering/exiting, arriving/leaving,
opening/closing, picking-up/putting-down or similar actions.


============================================================
CHECK SCENE-TO-SCENE CONTINUITY
============================================================

Compare the end_state of scene N with the start_state of
scene N+1.

They should be logically coherent unless there is an
intentional transition.


============================================================
CHECK use_previous_frame
============================================================

Scene 1 must have:
use_previous_frame = false

For later scenes:

Set it TRUE only when the new scene is a direct visual or
physical continuation and the final frame from the previous
scene would improve continuity.

Set it FALSE for intentional jumps in time, location,
montage, dream, flashback or major scene transitions.

Do not blindly set all scenes to true.


============================================================
CHECK DIALOGUE
============================================================

Dialogue contains spoken words only.

No speaker names.
No stage directions.
No quotation marks.


============================================================
CHECK TIMING
============================================================

No fixed scene-count cap. Use between {(target_duration + 11) // 12} and {target_duration // 4} scenes to fit the requested duration.

Every scene:
4 to 12 seconds.

Final total:
exactly {target_duration} seconds.


Return JSON only.
""".strip()

        draft_json = json.dumps(
            draft_data,
            ensure_ascii=False,
            indent=2,
        )

        user_message = f"""
ORIGINAL USER REQUEST

{user_prompt}


DRAFT STORYBOARD

{draft_json}


Return the corrected production-ready JSON.
""".strip()

        raw = self._chat(
            system_prompt=(
                system_prompt
            ),
            user_prompt=(
                user_message
            ),
            temperature=0.2,
            max_tokens=8500,
        )

        return self._extract_json(
            raw
        )

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

            if not isinstance(
                result,
                dict,
            ):
                raise ScenePlannerError(
                    "JSON root must be object."
                )

            return result

        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")

        if (
            start < 0
            or end <= start
        ):
            raise ScenePlannerError(
                "No valid JSON object found."
            )

        try:

            result = json.loads(
                text[
                    start:
                    end + 1
                ]
            )

        except json.JSONDecodeError as exc:

            raise ScenePlannerError(
                "Invalid storyboard JSON."
            ) from exc

        return result

    # ======================================================
    # BOOL PARSER
    # ======================================================

    @staticmethod
    def _parse_bool(
        value,
        default: bool = False,
    ) -> bool:

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            (int, float),
        ):
            return bool(value)

        if isinstance(
            value,
            str,
        ):

            normalized = (
                value.strip().lower()
            )

            if normalized in {
                "true",
                "yes",
                "1",
            }:
                return True

            if normalized in {
                "false",
                "no",
                "0",
            }:
                return False

        return default

    # ======================================================
    # DIALOGUE CLEANING
    # ======================================================

    @staticmethod
    def _clean_dialogue(
        dialogue: str,
        character_names: list[str],
    ) -> str:

        text = (
            dialogue
            or ""
        ).strip()

        if not text:
            return ""

        text = (
            text
            .strip()
            .strip('"')
            .strip("'")
            .strip()
        )

        for name in character_names:

            text = re.sub(
                (
                    r"^\s*"
                    + re.escape(name)
                    + r"\s*:\s*"
                ),
                "",
                text,
                flags=re.IGNORECASE,
            )

        text = re.sub(
            r"\s*\([^)]*\)\s*$",
            "",
            text,
        )

        text = re.sub(
            r"\s*\[[^\]]*\]\s*$",
            "",
            text,
        )

        return (
            text
            .strip()
            .strip('"')
            .strip("'")
            .strip()
        )

    # ======================================================
    # PARSE
    # ======================================================

    def _parse_plan(
        self,
        data: dict,
    ) -> VideoPlan:

        title = str(
            data.get(
                "title",
                "Untitled video",
            )
        ).strip()

        language = str(
            data.get(
                "language",
                "French",
            )
        ).strip()

        style_description = str(
            data.get(
                "style_description",
                "",
            )
        ).strip()

        setting_description = str(
            data.get(
                "setting_description",
                "",
            )
        ).strip()

        continuity_constraints = str(
            data.get(
                "continuity_constraints",
                "",
            )
        ).strip()

        # ==================================================
        # CHARACTERS
        # ==================================================

        characters = []

        for raw in data.get(
            "characters",
            [],
        ):

            if not isinstance(
                raw,
                dict,
            ):
                continue

            character_id = str(
                raw.get(
                    "id",
                    "",
                )
            ).strip()

            if not character_id:
                continue

            name = str(
                raw.get(
                    "name",
                    character_id,
                )
            ).strip()

            description = str(
                raw.get(
                    "description",
                    "",
                )
            ).strip()

            reference_prompt = str(
                raw.get(
                    "reference_prompt",
                    "",
                )
            ).strip()

            characters.append(
                Character(
                    id=character_id,
                    name=name,
                    description=(
                        description
                    ),
                    reference_prompt=(
                        reference_prompt
                    ),
                )
            )

        valid_character_ids = {
            character.id
            for character in characters
        }

        names = [
            character.name
            for character in characters
        ]

        scenes = []

        # ==================================================
        # SCENES
        # ==================================================

        for index, raw in enumerate(
            data.get(
                "scenes",
                [],
            ),
            start=1,
        ):

            if not isinstance(
                raw,
                dict,
            ):
                continue

            visual_prompt = str(
                raw.get(
                    "visual_prompt",
                    "",
                )
            ).strip()

            start_state = str(
                raw.get(
                    "start_state",
                    "",
                )
            ).strip()

            end_state = str(
                raw.get(
                    "end_state",
                    "",
                )
            ).strip()

            dialogue = (
                self._clean_dialogue(
                    dialogue=str(
                        raw.get(
                            "dialogue",
                            "",
                        )
                        or ""
                    ),
                    character_names=(
                        names
                    ),
                )
            )

            speaker = (
                raw.get(
                    "speaker_id"
                )
            )

            speaker_id = (
                str(speaker).strip()
                if speaker is not None
                else None
            )

            if not speaker_id:
                speaker_id = None

            raw_character_ids = (
                raw.get(
                    "character_ids",
                    [],
                )
            )

            if not isinstance(
                raw_character_ids,
                list,
            ):
                raw_character_ids = []

            scene_character_ids = []

            for value in (
                raw_character_ids
            ):

                character_id = str(
                    value
                ).strip()

                if (
                    character_id
                    in valid_character_ids
                    and character_id
                    not in scene_character_ids
                ):
                    scene_character_ids.append(
                        character_id
                    )

            combined_text = (
                visual_prompt
                + " "
                + start_state
                + " "
                + end_state
            )

            # Programmatic protection against a planner
            # forgetting character_ids.
            for character in characters:

                pattern = (
                    r"\b"
                    + re.escape(
                        character.name
                    )
                    + r"\b"
                )

                if re.search(
                    pattern,
                    combined_text,
                    flags=re.IGNORECASE,
                ):

                    if (
                        character.id
                        not in scene_character_ids
                    ):
                        scene_character_ids.append(
                            character.id
                        )

            if not dialogue:
                speaker_id = None

            elif (
                speaker_id
                and speaker_id
                in valid_character_ids
                and speaker_id
                not in scene_character_ids
            ):
                scene_character_ids.append(
                    speaker_id
                )

            use_previous_frame = (
                False
                if index == 1
                else self._parse_bool(
                    raw.get(
                        "use_previous_frame",
                        False,
                    )
                )
            )

            scenes.append(
                Scene(
                    number=int(
                        raw.get(
                            "number",
                            index,
                        )
                    ),
                    duration=int(
                        raw.get(
                            "duration",
                            8,
                        )
                    ),
                    visual_prompt=(
                        visual_prompt
                    ),
                    dialogue=dialogue,
                    speaker_id=(
                        speaker_id
                    ),
                    character_ids=tuple(
                        scene_character_ids
                    ),
                    start_state=(
                        start_state
                    ),
                    end_state=(
                        end_state
                    ),
                    use_previous_frame=(
                        use_previous_frame
                    ),
                )
            )

        character_description = (
            "\n\n".join(
                (
                    f"{character.name}: "
                    f"{character.description}"
                )
                for character
                in characters
            )
        )

        return VideoPlan(
            title=title,
            language=language,
            character_description=(
                character_description
            ),
            style_description=(
                style_description
            ),
            setting_description=(
                setting_description
            ),
            continuity_constraints=(
                continuity_constraints
            ),
            characters=characters,
            scenes=scenes,
        )

    # ======================================================
    # DURATION NORMALIZATION
    # ======================================================

    @staticmethod
    def _normalize_duration(
        plan: VideoPlan,
        target_duration: int,
    ) -> VideoPlan:

        durations = [
            max(
                4,
                min(
                    12,
                    scene.duration,
                ),
            )
            for scene in plan.scenes
        ]

        delta = (
            target_duration
            - sum(durations)
        )

        while delta > 0:

            changed = False

            for index in range(
                len(durations)
            ):

                if durations[index] < 12:

                    durations[index] += 1

                    delta -= 1
                    changed = True

                    if delta == 0:
                        break

            if not changed:
                break

        while delta < 0:

            changed = False

            for index in reversed(
                range(
                    len(durations)
                )
            ):

                if durations[index] > 4:

                    durations[index] -= 1

                    delta += 1
                    changed = True

                    if delta == 0:
                        break

            if not changed:
                break

        new_scenes = []

        for scene, duration in zip(
            plan.scenes,
            durations,
        ):

            new_scenes.append(
                Scene(
                    number=scene.number,
                    duration=duration,
                    visual_prompt=(
                        scene.visual_prompt
                    ),
                    dialogue=(
                        scene.dialogue
                    ),
                    speaker_id=(
                        scene.speaker_id
                    ),
                    character_ids=(
                        scene.character_ids
                    ),
                    start_state=(
                        scene.start_state
                    ),
                    end_state=(
                        scene.end_state
                    ),
                    use_previous_frame=(
                        scene.use_previous_frame
                    ),
                )
            )

        return VideoPlan(
            title=plan.title,
            language=plan.language,
            character_description=(
                plan.character_description
            ),
            style_description=(
                plan.style_description
            ),
            setting_description=(
                plan.setting_description
            ),
            continuity_constraints=(
                plan.continuity_constraints
            ),
            characters=(
                plan.characters
            ),
            scenes=new_scenes,
        )

    # ======================================================
    # VALIDATION
    # ======================================================

    @staticmethod
    def _validate_plan(
        plan: VideoPlan,
        target_duration: int,
    ) -> None:

        if not plan.scenes:
            raise ScenePlannerError(
                "Storyboard must contain at least one scene."
            )

        if (
            plan.total_duration
            != target_duration
        ):
            raise ScenePlannerError(
                f"Storyboard is "
                f"{plan.total_duration}s, "
                f"expected {target_duration}s."
            )

        valid_ids = {
            character.id
            for character in plan.characters
        }

        for index, scene in enumerate(
            plan.scenes
        ):

            if index == 0 and (
                scene.use_previous_frame
            ):
                raise ScenePlannerError(
                    "Scene 1 cannot use "
                    "a previous frame."
                )

            if not (
                4 <= scene.duration <= 12
            ):
                raise ScenePlannerError(
                    f"Invalid duration for "
                    f"scene {scene.number}."
                )

            if not scene.visual_prompt:
                raise ScenePlannerError(
                    f"Scene {scene.number} "
                    "has no visual prompt."
                )

            if not scene.start_state:
                raise ScenePlannerError(
                    f"Scene {scene.number} "
                    "has no start_state."
                )

            if not scene.end_state:
                raise ScenePlannerError(
                    f"Scene {scene.number} "
                    "has no end_state."
                )

            for character_id in (
                scene.character_ids
            ):

                if (
                    character_id
                    not in valid_ids
                ):
                    raise ScenePlannerError(
                        f"Unknown character ID "
                        f"{character_id}."
                    )

            if scene.dialogue:

                if not scene.speaker_id:
                    raise ScenePlannerError(
                        f"Scene {scene.number}: "
                        "dialogue has no speaker."
                    )

                if (
                    scene.speaker_id
                    not in scene.character_ids
                ):
                    raise ScenePlannerError(
                        f"Scene {scene.number}: "
                        "speaker is not visible."
                    )

    # ======================================================
    # REWRITE DIALOGUE
    # ======================================================

    def rewrite_dialogue_for_duration(
        self,
        dialogue: str,
        visual_prompt: str,
        language: str,
        current_duration: float,
        target_duration: float,
    ) -> str:

        system_prompt = """
Rewrite one spoken video line.

Return spoken words only.

No speaker name.
No quotation marks.
No stage direction.
No explanation.

Preserve meaning, tone and joke.
Make it shorter and natural.
""".strip()

        user_prompt = f"""
Language:
{language}

Scene:
{visual_prompt}

Dialogue:
{dialogue}

Current duration:
{current_duration:.2f}s

Desired duration:
approximately {target_duration:.2f}s
""".strip()

        result = self._chat(
            system_prompt=(
                system_prompt
            ),
            user_prompt=(
                user_prompt
            ),
            temperature=0.3,
            max_tokens=200,
        )

        return (
            result
            .strip()
            .strip('"')
            .strip("'")
        )
