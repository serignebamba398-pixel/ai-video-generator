from __future__ import annotations

import inspect
import json
import math
import time
from src.agnes_task_accounts import account_fingerprint, wait_for_saved_task
from src.config import STUDIO_INSTANCE

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from mutagen.mp3 import MP3

from src.agnes_client import (
    AgnesAPIError,
    AgnesClient,
)

from src.frame_extractor import (
    FrameExtractionError,
    FrameExtractor,
)

from src.scene_planner import (
    Scene,
    VideoPlan,
)

from src.voice_generator import (
    VoiceGenerationError,
    VoiceGenerator,
)


# ==========================================================
# EXCEPTION
# ==========================================================


class VideoPipelineError(Exception):
    """
    Raised when a video-generation pipeline operation fails.
    """


# ==========================================================
# DATA MODELS
# ==========================================================


@dataclass(frozen=True)
class PreparedScene:
    """
    Scene prepared for Agnes generation.

    reference_image_paths contains the stable character
    identity images attached to the scene.

    The previous-scene continuity frame is intentionally
    NOT stored here because it is produced dynamically
    during generation.
    """

    scene: Scene

    audio_path: Optional[Path]

    speech_duration: float
    native_audio: bool = False

    # Optional validated still image for this exact scene.
    # When present, this is the single visual reference sent
    # to Agnes for the video shot.
    scene_reference_image_path: Optional[Path] = None

    reference_image_paths: tuple[
        Path,
        ...
    ] = ()

    reference_character_ids: tuple[
        str,
        ...
    ] = ()

    # ------------------------------------------------------
    # Dialogue
    # ------------------------------------------------------

    @property
    def has_dialogue(
        self,
    ) -> bool:

        dialogue = (
            self.scene.dialogue
            or ""
        ).strip()

        return bool(
            dialogue
            and self.audio_path is not None
        )

    # ------------------------------------------------------
    # Scene image
    # ------------------------------------------------------

    @property
    def has_scene_reference(
        self,
    ) -> bool:

        return bool(
            self.scene_reference_image_path
        )

    # ------------------------------------------------------
    # Character images
    # ------------------------------------------------------

    @property
    def has_reference_images(
        self,
    ) -> bool:

        return bool(
            self.reference_image_paths
        )

    # ------------------------------------------------------
    # Compatibility / display helper
    # ------------------------------------------------------

    @property
    def uses_reference_mode(
        self,
    ) -> bool:
        """
        At preparation time, REFERENCE mode is necessary if
        character images or audio exist.

        During actual generation a previous-scene
        continuity frame may additionally force REFERENCE
        mode even when this property is False.

        This property is retained because test scripts use
        it to display the expected Agnes mode.
        """

        return bool(
            self.has_dialogue
            or self.has_scene_reference
            or self.has_reference_images
        )


@dataclass(frozen=True)
class GeneratedScene:
    scene: Scene
    video_path: Path
    task_id: str


@dataclass(frozen=True)
class SpeechTiming:
    start: float
    end: float
    post_action: float


# ==========================================================
# CALLBACK TYPES
# ==========================================================


PipelineProgressCallback = Callable[
    [
        int,
        int,
        str,
        int,
    ],
    None,
]


DialogueRewriteCallback = Callable[
    [
        str,
        str,
        str,
        float,
        float,
    ],
    str,
]


# ==========================================================
# VIDEO PIPELINE
# ==========================================================


class VideoPipeline:
    """
    Production-oriented AI video pipeline.

    Responsibilities:

    1. Generate TTS.
    2. Measure actual speech duration.
    3. Rewrite dialogue when it is too long.
    4. Preserve total storyboard duration.
    5. Attach recurring-character identity images.
    6. Extract a continuity frame after every generated clip.
    7. Optionally provide that frame to the next scene.
    8. Respect Agnes' maximum reference-image count.
    9. Submit TEXT or REFERENCE video requests.
    10. Retry indefinitely when Agnes reports queue_full.
    11. Respect rate limits separately.
    12. Persist Agnes video IDs for resume.
    13. Download videos atomically.
    14. Resume completed or pending scenes.
    """

    # ======================================================
    # SCENE LIMITS
    # ======================================================

    MIN_SCENE_DURATION = 4

    MAX_SCENE_DURATION = 12

    # ======================================================
    # SPEECH TIMING
    # ======================================================

    MIN_PRE_SPEECH_TIME = 0.5

    TARGET_PRE_SPEECH_TIME = 0.8

    MIN_POST_SPEECH_TIME = 0.6

    MAX_PREFERRED_SPEECH_DURATION = 6.5

    REWRITE_TARGET_SPEECH_DURATION = 5.5

    MAX_DIALOGUE_REWRITES = 3

    # ======================================================
    # AGNES VIDEO SETTINGS
    # ======================================================

    DEFAULT_SIZE = "720P"

    DEFAULT_ASPECT_RATIO = "16:9"

    # Agnes Video 2.5 Flash reference-image capacity.
    MAX_REFERENCE_IMAGES = 5

    # ======================================================
    # RETRY SETTINGS
    # ======================================================

    # Studio 1 (8501) uses Token Plan; leave a margin above 12 seconds.
    # Studio 2 keeps its existing retry interval. Retry-After takes precedence.
    QUEUE_RETRY_DELAY = 13 if STUDIO_INSTANCE == "1" else 31

    RATE_LIMIT_RETRY_DELAY = 60

    TEMPORARY_ERROR_RETRY_DELAY = 60
    MAX_FAILED_TASK_RETRIES = 3

    def _wait_with_failed_task_retries(self, video_id, task_path, submit, progress_callback):
        for attempt in range(self.MAX_FAILED_TASK_RETRIES + 1):
            try:
                url = wait_for_saved_task(
                    self.agnes, task_path, video_id=video_id,
                    polling_interval=5, timeout=30 * 60,
                    progress_callback=progress_callback,
                )
                return video_id, url
            except AgnesAPIError as exc:
                # Only a confirmed failed generation permits a new submission.
                # Network errors/timeouts must retain the existing task.
                try:
                    status = json.loads(exc.response_body or "{}").get("status")
                except (ValueError, AttributeError):
                    status = None
                if status != "failed" or attempt == self.MAX_FAILED_TASK_RETRIES:
                    raise
                self._delete_task_state(task_path)
                delay = max(self.QUEUE_RETRY_DELAY, self._get_retry_after(exc))
                progress_callback(
                    f"Generation echouee : relance automatique {attempt + 1}/"
                    f"{self.MAX_FAILED_TASK_RETRIES} dans {delay}s", 0,
                )
                time.sleep(delay)
                video_id = submit()
                try:
                    self._save_task_state(task_path, video_id, account_fingerprint(self.agnes))
                except OSError as save_error:
                    raise VideoPipelineError(
                        f"Agnes accepted replacement task {video_id}, but its ID could not "
                        f"be saved locally: {save_error}"
                    ) from save_error

    # ======================================================
    # INIT
    # ======================================================

    def __init__(
        self,
        audio_dir: Path,
        video_dir: Path,
        voice: str = "fr-FR-HenriNeural",
        speech_rate: str = "+0%",
        speech_volume: str = "+0%",
        speech_pitch: str = "+0Hz",
        agnes_client: Optional[
            AgnesClient
        ] = None,
    ) -> None:

        self.audio_dir = Path(
            audio_dir
        )

        self.video_dir = Path(
            video_dir
        )

        self.audio_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.video_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.voice_generator = (
            VoiceGenerator(
                voice=voice,
                rate=speech_rate,
                volume=speech_volume,
                pitch=speech_pitch,
            )
        )

        self.agnes = (
            agnes_client
            if agnes_client is not None
            else AgnesClient()
        )

        # Uses project-local FFmpeg when available.
        self.frame_extractor = (
            FrameExtractor()
        )

    # ======================================================
    # AUDIO DURATION
    # ======================================================

    @staticmethod
    def get_audio_duration(
        audio_path: Path,
    ) -> float:

        audio_path = Path(
            audio_path
        )

        if not (
            audio_path.exists()
            and audio_path.is_file()
        ):

            raise VideoPipelineError(
                "Audio file does not exist: "
                f"{audio_path}"
            )

        try:

            audio = MP3(
                str(
                    audio_path
                )
            )

            duration = float(
                audio.info.length
            )

        except Exception as exc:

            raise VideoPipelineError(
                "Unable to read audio duration "
                f"for {audio_path}: {exc}"
            ) from exc

        if duration <= 0:

            raise VideoPipelineError(
                "Audio duration is invalid: "
                f"{duration}"
            )

        return duration

    # ======================================================
    # SAFE DELETE
    # ======================================================

    @staticmethod
    def _safe_unlink(
        path: Optional[Path],
    ) -> None:

        if path is None:
            return

        try:

            if path.exists():

                path.unlink()

        except OSError:

            pass

    # ======================================================
    # SPEECH TIMING
    # ======================================================

    def calculate_speech_timing(
        self,
        scene_duration: int,
        speech_duration: float,
    ) -> SpeechTiming:

        if speech_duration <= 0:

            return SpeechTiming(
                start=0.0,
                end=0.0,
                post_action=float(
                    scene_duration
                ),
            )

        dynamic_start = (
            float(
                scene_duration
            )
            * 0.08
        )

        start = max(
            self.MIN_PRE_SPEECH_TIME,
            min(
                dynamic_start,
                self.TARGET_PRE_SPEECH_TIME,
            ),
        )

        end = (
            start
            + speech_duration
        )

        post_action = (
            float(
                scene_duration
            )
            - end
        )

        if (
            post_action
            < self.MIN_POST_SPEECH_TIME
        ):

            raise VideoPipelineError(
                f"Dialogue lasting "
                f"{speech_duration:.2f}s "
                f"does not fit inside a "
                f"{scene_duration}s scene."
            )

        return SpeechTiming(
            start=round(
                start,
                2,
            ),
            end=round(
                end,
                2,
            ),
            post_action=round(
                post_action,
                2,
            ),
        )

    # ======================================================
    # PREPARE PLAN
    # ======================================================

    def prepare_plan(
        self,
        plan: VideoPlan,
        dialogue_rewriter: Optional[
            DialogueRewriteCallback
        ] = None,
        reference_images: Optional[
            dict[str, Path]
        ] = None,
        scene_reference_images: Optional[
            dict[int, Path]
        ] = None,
        preserve_scene_durations: bool = False,
    ) -> tuple[
        VideoPlan,
        list[PreparedScene],
    ]:

        if not plan.scenes:

            raise VideoPipelineError(
                "Video plan contains no scenes."
            )

        reference_images = (
            reference_images
            or {}
        )

        scene_reference_images = (
            scene_reference_images
            or {}
        )

        target_total = (
            plan.total_duration
        )

        audio_job_id = (
            uuid4().hex[:10]
        )

        prepared: list[
            PreparedScene
        ] = []

        updated_scenes: list[
            Scene
        ] = []

        created_audio_paths: list[
            Path
        ] = []

        try:

            # ==================================================
            # PREPARE EACH SCENE
            # ==================================================

            for scene in (
                plan.scenes
            ):

                # ==============================================
                # VALIDATED SCENE REFERENCE IMAGE
                # ==============================================

                scene_reference_path: Optional[Path] = None

                candidate_scene_reference = (
                    scene_reference_images.get(
                        scene.number
                    )
                )

                if candidate_scene_reference is not None:

                    candidate_scene_reference = Path(
                        candidate_scene_reference
                    )

                    if (
                        candidate_scene_reference.exists()
                        and candidate_scene_reference.is_file()
                        and candidate_scene_reference.stat().st_size > 0
                    ):

                        scene_reference_path = (
                            candidate_scene_reference
                        )

                # ==============================================
                # CHARACTER REFERENCE IMAGES
                # ==============================================

                reference_ids: list[
                    str
                ] = []

                reference_paths: list[
                    Path
                ] = []

                for character_id in (
                    scene.character_ids
                ):

                    image_path = (
                        reference_images.get(
                            character_id
                        )
                    )

                    if image_path is None:
                        continue

                    image_path = Path(
                        image_path
                    )

                    if not (
                        image_path.exists()
                        and image_path.is_file()
                        and image_path.stat().st_size > 0
                    ):

                        continue

                    reference_ids.append(
                        character_id
                    )

                    reference_paths.append(
                        image_path
                    )

                dialogue = (
                    scene.dialogue
                    or ""
                ).strip()

                # ==============================================
                # SILENT SCENE
                # ==============================================

                if not dialogue:

                    updated_scene = replace(
                        scene,
                        dialogue="",
                        speaker_id=None,
                    )

                    updated_scenes.append(
                        updated_scene
                    )

                    prepared.append(
                        PreparedScene(
                            scene=(
                                updated_scene
                            ),
                            audio_path=None,
                            speech_duration=0.0,
                            scene_reference_image_path=(
                                scene_reference_path
                            ),
                            reference_image_paths=tuple(
                                reference_paths
                            ),
                            reference_character_ids=tuple(
                                reference_ids
                            ),
                        )
                    )

                    continue

                # ==============================================
                # SPEAKING SCENE
                # ==============================================

                audio_path = (
                    self.audio_dir
                    / (
                        f"speech_"
                        f"{audio_job_id}_"
                        f"{scene.number:02d}"
                        ".mp3"
                    )
                )

                created_audio_paths.append(
                    audio_path
                )

                current_dialogue = (
                    dialogue
                )

                speech_duration = 0.0
                speech_limit = (
                    scene.duration - self.TARGET_PRE_SPEECH_TIME - self.MIN_POST_SPEECH_TIME
                    if preserve_scene_durations else self.MAX_PREFERRED_SPEECH_DURATION
                )
                scene_duration_limit = scene.duration if preserve_scene_durations else self.MAX_SCENE_DURATION

                # ==============================================
                # TTS + OPTIONAL DIALOGUE REWRITE
                # ==============================================

                for rewrite_attempt in range(
                    self.MAX_DIALOGUE_REWRITES
                    + 1
                ):

                    self._safe_unlink(
                        audio_path
                    )

                    try:

                        self.voice_generator.generate(
                            text=current_dialogue,
                            output_path=(
                                audio_path
                            ),
                        )

                    except VoiceGenerationError as exc:

                        raise VideoPipelineError(
                            "Speech generation failed "
                            f"for scene "
                            f"{scene.number}: "
                            f"{exc}"
                        ) from exc

                    speech_duration = (
                        self.get_audio_duration(
                            audio_path
                        )
                    )

                    # Preferred length reached.
                    if (
                        speech_duration
                        <=
                        speech_limit
                    ):

                        break

                    minimum_required_duration = (
                        speech_duration
                        + self.TARGET_PRE_SPEECH_TIME
                        + self.MIN_POST_SPEECH_TIME
                    )

                    # No rewriter available.
                    if (
                        dialogue_rewriter
                        is None
                    ):

                        if (
                            minimum_required_duration
                            <= scene_duration_limit
                        ):

                            break

                        raise VideoPipelineError(
                            f"Scene {scene.number}: "
                            f"dialogue lasts "
                            f"{speech_duration:.2f}s "
                            "and cannot fit inside "
                            f"the {scene_duration_limit}s scene duration. "
                            "Raccourcis le dialogue ou augmente la durée, puis confirme à nouveau."
                        )

                    # Rewrite attempts exhausted.
                    if (
                        rewrite_attempt
                        >=
                        self.MAX_DIALOGUE_REWRITES
                    ):

                        if (
                            minimum_required_duration
                            <= scene_duration_limit
                        ):

                            break

                        raise VideoPipelineError(
                            f"Scene {scene.number}: "
                            "dialogue remains too long "
                            "after automatic rewriting."
                        )

                    old_dialogue = (
                        current_dialogue
                    )

                    try:

                        rewritten = (
                            dialogue_rewriter(
                                old_dialogue,
                                scene.visual_prompt,
                                plan.language,
                                speech_duration,
                                min(self.REWRITE_TARGET_SPEECH_DURATION, speech_limit),
                            )
                        )

                    except Exception as exc:

                        raise VideoPipelineError(
                            "Dialogue rewriting failed "
                            f"for scene "
                            f"{scene.number}: "
                            f"{exc}"
                        ) from exc

                    rewritten = (
                        rewritten
                        or ""
                    ).strip()

                    if not rewritten:

                        raise VideoPipelineError(
                            "Dialogue rewriter returned "
                            "empty text for scene "
                            f"{scene.number}."
                        )

                    if (
                        rewritten
                        == old_dialogue
                    ):

                        raise VideoPipelineError(
                            "Dialogue rewriter did not "
                            "shorten or modify scene "
                            f"{scene.number}."
                        )

                    print()

                    print(
                        f"Scene "
                        f"{scene.number}: "
                        "dialogue optimized"
                    )

                    print(
                        f'OLD: "{old_dialogue}"'
                    )

                    print(
                        f'NEW: "{rewritten}"'
                    )

                    print()

                    current_dialogue = (
                        rewritten
                    )

                updated_scene = replace(
                    scene,
                    dialogue=(
                        current_dialogue
                    ),
                )

                updated_scenes.append(
                    updated_scene
                )

                prepared.append(
                    PreparedScene(
                        scene=(
                            updated_scene
                        ),
                        audio_path=(
                            audio_path
                        ),
                        speech_duration=(
                            speech_duration
                        ),
                        scene_reference_image_path=(
                            scene_reference_path
                        ),
                        reference_image_paths=tuple(
                            reference_paths
                        ),
                        reference_character_ids=tuple(
                            reference_ids
                        ),
                    )
                )

            # ==================================================
            # ENSURE DIALOGUE FITS SCENE DURATIONS
            # ==================================================

            durations = [
                scene.duration
                for scene
                in updated_scenes
            ]

            for index, item in enumerate(
                prepared
            ):

                if not item.has_dialogue:
                    continue

                required_duration = math.ceil(
                    item.speech_duration
                    + self.TARGET_PRE_SPEECH_TIME
                    + self.MIN_POST_SPEECH_TIME
                )

                required_duration = max(
                    self.MIN_SCENE_DURATION,
                    required_duration,
                )

                if (
                    required_duration
                    > self.MAX_SCENE_DURATION
                ):

                    raise VideoPipelineError(
                        f"Scene "
                        f"{item.scene.number}: "
                        "speech requires "
                        f"{required_duration}s, "
                        "which exceeds Agnes' "
                        f"{self.MAX_SCENE_DURATION}s "
                        "scene limit."
                    )

                durations[index] = max(
                    durations[index],
                    required_duration,
                )

            # ==================================================
            # PRESERVE ORIGINAL TOTAL DURATION
            # ==================================================

            excess = (
                sum(
                    durations
                )
                - target_total
            )

            if excess > 0:

                durations = (
                    self._remove_excess_time(
                        durations=(
                            durations
                        ),
                        prepared=(
                            prepared
                        ),
                        seconds=(
                            excess
                        ),
                    )
                )

            if (
                sum(
                    durations
                )
                != target_total
            ):

                raise VideoPipelineError(
                    "Unable to preserve total "
                    f"video duration of "
                    f"{target_total}s."
                )

            # ==================================================
            # CREATE FINAL PLAN
            # ==================================================

            final_scenes: list[
                Scene
            ] = []

            final_prepared: list[
                PreparedScene
            ] = []

            for item, duration in zip(
                prepared,
                durations,
            ):

                final_scene = replace(
                    item.scene,
                    duration=duration,
                )

                final_scenes.append(
                    final_scene
                )

                final_prepared.append(
                    replace(
                        item,
                        scene=(
                            final_scene
                        ),
                    )
                )

            final_plan = VideoPlan(
                title=(
                    plan.title
                ),
                language=(
                    plan.language
                ),
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
                scenes=(
                    final_scenes
                ),
            )

            # Final timing validation.
            for item in (
                final_prepared
            ):

                if item.has_dialogue:

                    self.calculate_speech_timing(
                        scene_duration=(
                            item.scene.duration
                        ),
                        speech_duration=(
                            item.speech_duration
                        ),
                    )

            return (
                final_plan,
                final_prepared,
            )

        except Exception:

            for path in (
                created_audio_paths
            ):

                self._safe_unlink(
                    path
                )

            raise

    # ======================================================
    # REMOVE EXCESS TIME
    # ======================================================

    def _remove_excess_time(
        self,
        durations: list[int],
        prepared: list[
            PreparedScene
        ],
        seconds: int,
    ) -> list[int]:

        result = list(
            durations
        )

        remaining = int(
            seconds
        )

        # Silent scenes lose duration first.
        indexes = sorted(
            range(
                len(
                    prepared
                )
            ),
            key=lambda index: (
                prepared[
                    index
                ].has_dialogue,
                -result[index],
            ),
        )

        while remaining > 0:

            changed = False

            for index in indexes:

                item = (
                    prepared[
                        index
                    ]
                )

                if item.has_dialogue:

                    minimum_duration = max(
                        self.MIN_SCENE_DURATION,
                        math.ceil(
                            item.speech_duration
                            + self.TARGET_PRE_SPEECH_TIME
                            + self.MIN_POST_SPEECH_TIME
                        ),
                    )

                else:

                    minimum_duration = (
                        self.MIN_SCENE_DURATION
                    )

                if (
                    result[index]
                    > minimum_duration
                ):

                    result[index] -= 1

                    remaining -= 1

                    changed = True

                    if remaining == 0:
                        break

            if not changed:

                raise VideoPipelineError(
                    "Unable to redistribute "
                    "scene durations without "
                    "cutting required speech."
                )

        return result

    # ======================================================
    # CHARACTER REFERENCE SELECTION
    # ======================================================

    @staticmethod
    def _select_character_references(
        item: PreparedScene,
        max_count: int,
    ) -> list[
        tuple[
            str,
            Path,
        ]
    ]:
        """
        Select the character identity images that fit inside
        the remaining Agnes reference-image slots.

        The speaking character is prioritized.
        """

        if max_count <= 0:
            return []

        pairs = list(
            zip(
                item.reference_character_ids,
                item.reference_image_paths,
            )
        )

        speaker_id = (
            item.scene.speaker_id
        )

        if speaker_id:

            pairs.sort(
                key=lambda pair: (
                    0
                    if pair[0] == speaker_id
                    else 1
                )
            )

        return pairs[
            :max_count
        ]

    # ======================================================
    # CHARACTER BIBLE
    # ======================================================

    @staticmethod
    def _visible_character_bible(
        plan: VideoPlan,
        scene: Scene,
    ) -> str:

        if not scene.character_ids:

            return (
                "No recurring character should be "
                "visibly present in this scene."
            )

        lines: list[
            str
        ] = []

        for character_id in (
            scene.character_ids
        ):

            character = (
                plan.character_map.get(
                    character_id
                )
            )

            if character is None:
                continue

            lines.append(
                f"{character.name}: "
                f"{character.description}"
            )

        if not lines:

            return (
                "No recurring character should be "
                "visibly present in this scene."
            )

        return "\n\n".join(
            lines
        )

    # ======================================================
    # REFERENCE IMAGE ROLES
    # ======================================================

    @staticmethod
    def _build_reference_block(
        plan: VideoPlan,
        scene_reference_present: bool,
        continuity_frame_present: bool,
        reference_character_ids: list[str],
    ) -> str:

        lines = [
            "REFERENCE IMAGE ROLES",
            "",
        ]

        # --------------------------------------------------
        # PRODUCTION MODE: ONE VALIDATED SCENE MASTER IMAGE
        # --------------------------------------------------

        if scene_reference_present:

            lines.extend(
                [
                    (
                        "<Image 1> is the VALIDATED MASTER "
                        "IMAGE for the current scene."
                    ),
                    "",
                    (
                        "Treat <Image 1> as the authoritative "
                        "starting visual state for:"
                    ),
                    "- character appearance visible in this shot",
                    "- composition",
                    "- environment",
                    "- framing",
                    "- lighting",
                    "- props",
                    "- current spatial layout",
                    "",
                    (
                        "Animate this image naturally. Do not "
                        "freeze it as a static frame."
                    ),
                    (
                        "Do not redesign the visible characters, "
                        "their anatomy, species, colors or stable "
                        "clothing."
                    ),
                    (
                        "The storyboard text controls what happens "
                        "AFTER this starting state, including action, "
                        "camera movement and the final state."
                    ),
                    "",
                    "REFERENCE PRIORITY:",
                    (
                        "Because a validated scene master image is "
                        "provided, no separate identity portrait or "
                        "previous-scene frame is required for this "
                        "request."
                    ),
                ]
            )

            return "\n".join(
                lines
            )

        image_index = 1

        # --------------------------------------------------
        # LEGACY / FALLBACK MODE: PREVIOUS SCENE FRAME
        # --------------------------------------------------

        if continuity_frame_present:

            lines.extend(
                [
                    (
                        f"<Image {image_index}> is a continuity "
                        "frame taken near the end of the previous "
                        "scene."
                    ),
                    "",
                    "Use it primarily to preserve:",
                    "- persistent environment",
                    "- lighting",
                    "- important object state",
                    "- vehicle or room state",
                    "- spatial relationships",
                    "- clothing continuity",
                    "- character position when relevant",
                    "",
                    (
                        "It is NOT the authoritative identity "
                        "portrait."
                    ),
                    (
                        "Do not freeze or simply reproduce the "
                        "continuity frame."
                    ),
                    "Continue the story naturally.",
                    "",
                ]
            )

            image_index += 1

        # --------------------------------------------------
        # LEGACY / FALLBACK MODE: CHARACTER REFERENCES
        # --------------------------------------------------

        for character_id in (
            reference_character_ids
        ):

            character = (
                plan.character_map.get(
                    character_id
                )
            )

            if character is None:
                continue

            lines.extend(
                [
                    (
                        f"<Image {image_index}> is the "
                        f"authoritative IDENTITY reference "
                        f"for {character.name}."
                    ),
                    "Preserve this character's:",
                    "- face or defining head anatomy",
                    "- species / character type",
                    "- approximate age when applicable",
                    "- hairstyle or stable head features",
                    "- facial hair when applicable",
                    "- body build",
                    "- established clothing",
                    "- stable colors and visual features",
                    "",
                ]
            )

            image_index += 1

        if (
            not continuity_frame_present
            and not reference_character_ids
        ):

            lines.append(
                "No image reference is supplied."
            )

        lines.extend(
            [
                "",
                "IDENTITY PRIORITY:",
                (
                    "Character identity images are authoritative "
                    "for stable character identity."
                ),
                "",
                "CONTINUITY PRIORITY:",
                (
                    "A previous-scene frame is authoritative for "
                    "environment and scene state, but must not "
                    "redefine character identity."
                ),
            ]
        )

        return "\n".join(
            lines
        )

    # ======================================================
    # COMMON SCENE BLOCK
    # ======================================================

    def _build_common_scene_block(
        self,
        plan: VideoPlan,
        scene: Scene,
        scene_reference_present: bool,
        continuity_frame_present: bool,
        reference_character_ids: list[str],
    ) -> str:

        reference_block = (
            self._build_reference_block(
                plan=plan,
                scene_reference_present=(
                    scene_reference_present
                ),
                continuity_frame_present=(
                    continuity_frame_present
                ),
                reference_character_ids=(
                    reference_character_ids
                ),
            )
        )

        character_bible = (
            self._visible_character_bible(
                plan=plan,
                scene=scene,
            )
        )

        return f"""
GLOBAL VISUAL STYLE

{plan.style_description}


WORLD / SETTING

{plan.setting_description}


GLOBAL CONTINUITY CONSTRAINTS

{plan.continuity_constraints}


VISIBLE CHARACTER BIBLE

{character_bible}


{reference_block}


CURRENT SCENE

{scene.visual_prompt}


FIRST-FRAME STATE

{scene.start_state}


LAST-FRAME STATE

{scene.end_state}


ACTION DIRECTION

The scene must progress clearly from FIRST-FRAME STATE
toward LAST-FRAME STATE.

Do not reverse the intended action.

Examples of actions that must preserve direction include:

- entering / exiting
- arriving / leaving
- opening / closing
- picking up / putting down
- giving / receiving
- sitting / standing
- approaching / moving away
- getting into / getting out of a vehicle

Maintain coherent object ownership and physical state.

If a continuity frame is supplied, use it to maintain
persistent visual details while still following the
current scene's explicit start state, action, camera
direction and end state.


WORLD AUTHENTICITY

Everything visible must naturally belong to the world
defined for this story.

Preserve appropriate:

- geography
- architecture
- road design
- vehicle styling
- infrastructure
- interiors
- technology
- clothing
- props
- historical period
- cultural environment
- weather
- time of day

Do not replace contextual elements with unrelated
stereotypes from another country, region or era.

Avoid prominent AI-generated readable text unless the
story genuinely requires it.


SHOT DURATION

Approximately {scene.duration} seconds.


PHYSICAL REALISM

Use believable human and object motion unless fantasy,
surrealism or impossible comedy is explicitly part of
the story.

Maintain spatial logic.

Avoid unexplained teleportation.

Avoid unexplained changes in clothing, objects, vehicles
or environment.


COMPOSITION

Use one coherent full-screen cinematic composition.

No split screen unless explicitly requested.

No collage unless explicitly requested.
""".strip()

    # ======================================================
    # BUILD SCENE PROMPT
    # ======================================================

    def build_scene_prompt(
        self,
        plan: VideoPlan,
        scene: Scene,
        speaking: bool,
        speech_duration: float = 0.0,
        scene_reference_present: bool = False,
        continuity_frame_present: bool = False,
        reference_character_ids: Optional[
            list[str]
        ] = None,
        native_audio: bool = False,
    ) -> str:

        if native_audio:
            visual_instruction = (
                "Animate the supplied scene master image as one continuous shot. "
                "Preserve its characters, clothing, setting and lighting. "
                if scene_reference_present else
                "Create one continuous video shot from the scene prompt. "
                "Establish the characters, clothing, setting and lighting from the description. "
            )
            return (
                visual_instruction +
                "Generate synchronized native audio according to the scene prompt, "
                "including the requested dialogue and ambience. "
                "Use distinct appropriate voices for each named speaker and match "
                "each speaker's lip movements to their own lines. "
                "Do not invent extra dialogue. No subtitles or on-screen text.\n\n"
                f"Dialogue language: {plan.language}. Duration: {scene.duration} seconds.\n\n"
                "SCENE PROMPT (original instructions):\n" + scene.visual_prompt
            )

        reference_character_ids = (
            reference_character_ids
            or []
        )

        common = (
            self._build_common_scene_block(
                plan=plan,
                scene=scene,
                scene_reference_present=(
                    scene_reference_present
                ),
                continuity_frame_present=(
                    continuity_frame_present
                ),
                reference_character_ids=(
                    reference_character_ids
                ),
            )
        )

        # ==================================================
        # SILENT SCENE
        # ==================================================

        if not speaking:

            return f"""
ROLE

Create one polished, realistic and professionally directed
cinematic video shot.


{common}


VISUAL STORYTELLING

This scene contains NO spoken dialogue.

Start immediately from the defined FIRST-FRAME STATE.

Use meaningful action from the beginning.

Progress naturally toward the defined LAST-FRAME STATE.

Use connected visual beats rather than one static pose.

Visible characters may:

- move
- react
- gesture
- interact
- handle objects
- change position

but they must remain silent.


CAMERA

Use professional cinematic framing.

Use purposeful camera movement.

Maintain spatial continuity.

Maintain coherent screen direction.

Avoid random cuts.

Avoid unnecessary rapid editing.


RESTRICTIONS

No generated speech.

No unrelated voices.

No subtitles.

No captions.

No unnecessary readable text.

No reversed action.

No unexplained character redesign.

No unexplained location change.
""".strip()

        # ==================================================
        # SPEAKING SCENE
        # ==================================================

        dialogue = (
            scene.dialogue
            or ""
        ).strip()

        if not dialogue:

            raise VideoPipelineError(
                f"Scene {scene.number} is marked "
                "as speaking but contains no dialogue."
            )

        timing = (
            self.calculate_speech_timing(
                scene_duration=(
                    scene.duration
                ),
                speech_duration=(
                    speech_duration
                ),
            )
        )

        speaker = (
            plan.character_map.get(
                scene.speaker_id
                or ""
            )
        )

        speaker_name = (
            speaker.name
            if speaker
            else scene.speaker_id or "the speaking character"
        )

        from src.scene_prompt_analysis import analyze_scene_prompt
        turns = analyze_scene_prompt(scene.visual_prompt).turns
        if len({turn.speaker.casefold() for turn in turns}) > 1:
            speaker_name = "each character during their assigned turn"
            performance_rule = "Only the character assigned to the current audio turn speaks. All other characters remain silent during that turn."
            dialogue = "\n".join(f"{turn.speaker}: {turn.dialogue}" for turn in turns)
        else:
            performance_rule = f"Only {speaker_name} actively speaks. Other visible characters remain silent."

        return f"""
ROLE

Create one polished, realistic and professionally directed
cinematic video shot.


{common}


PACING

Start immediately inside the meaningful situation.

Avoid filler.

Avoid unnecessary establishing footage.

Avoid dead time.


BEAT 1 — VISUAL HOOK

Timing:

0.0 to approximately {timing.start:.2f} seconds.

Immediately establish the FIRST-FRAME STATE and begin the
required action.


BEAT 2 — SPOKEN PERFORMANCE

Speaker:

{speaker_name}


Language:

{plan.language}


Exact spoken words:

"{dialogue}"


AUDIO REFERENCE

<Audio 1> contains the authoritative recording.

Begin the first spoken word around:

{timing.start:.2f} seconds.

The reference speech lasts approximately:

{speech_duration:.2f} seconds.

Expected speech end:

{timing.end:.2f} seconds.


IMPORTANT

Use exactly the spoken performance contained in <Audio 1>.

Do not translate it.

Do not paraphrase it.

Do not rewrite it.

Do not invent words.

Do not add another sentence.

Do not continue speaking after <Audio 1> has finished.


LIP SYNCHRONIZATION

Synchronize {speaker_name}'s:

- lips
- mouth shapes
- jaw movement
- facial muscles

closely with <Audio 1>.

{performance_rule}

Keep the speaker's mouth sufficiently visible during the
important part of the line.

Avoid covering the mouth.

Avoid excessive head movement during speech.

Avoid unnecessary cuts during the spoken sentence.


BEAT 3 — VISUAL PAYOFF

The dialogue should finish around:

{timing.end:.2f} seconds.

Approximately:

{timing.post_action:.2f} seconds

remain after speech.

Use that remaining time for meaningful visual storytelling
and continue naturally toward LAST-FRAME STATE.

Use actions appropriate to the current story, such as:

- reaction
- consequence
- interaction
- movement
- reveal
- escalation
- visual comedy
- transition

Do not add new dialogue.


CAMERA

Use professional cinematic framing.

Use purposeful camera movement.

Maintain coherent spatial relationships.

Avoid random camera movement.

Avoid unexplained cuts.


RESTRICTIONS

No subtitles.

No captions.

No additional dialogue.

No unrelated voices.

No accidental text overlays.

No reversed action.

No unexplained identity changes.
""".strip()

    # ======================================================
    # AGNES ERROR CLASSIFICATION
    # ======================================================

    @staticmethod
    def _classify_agnes_error(
        exc: Exception,
    ) -> str:

        message = str(
            exc
        ).lower()

        status_code = getattr(
            exc,
            "status_code",
            None,
        )

        error_code = str(
            getattr(
                exc,
                "error_code",
                "",
            )
            or ""
        ).lower()

        # --------------------------------------------------
        # VIDEO QUEUE FULL
        # --------------------------------------------------

        if (
            error_code
            == "video_queue_full"
        ):

            return "queue_full"

        if (
            "video_queue_full"
            in message
            or "video queue is full"
            in message
            or "video queue full"
            in message
        ):

            return "queue_full"

        # --------------------------------------------------
        # RATE LIMIT
        # --------------------------------------------------

        if (
            status_code == 429
            or "rate limit"
            in message
            or "too many requests"
            in message
        ):

            return "rate_limit"

        # --------------------------------------------------
        # QUOTA / CREDIT
        # --------------------------------------------------

        quota_indicators = (
            "quota",
            "insufficient credit",
            "insufficient balance",
            "credit exhausted",
            "credits exhausted",
            "usage limit",
            "daily limit",
        )

        if any(
            indicator in message
            for indicator
            in quota_indicators
        ):

            return "quota"

        # --------------------------------------------------
        # AUTH
        # --------------------------------------------------

        if status_code == 401:

            return "authentication"

        if status_code == 403:

            return "authorization"

        # --------------------------------------------------
        # TEMPORARY SERVER ERROR
        # --------------------------------------------------

        if (
            status_code
            in {
                408,
                425,
                500,
                502,
                503,
                504,
            }
        ):

            return "temporary"

        if getattr(
            exc,
            "retryable",
            False,
        ):

            return "temporary"

        return "other"

    # ======================================================
    # TERMINAL TASK ERROR
    # ======================================================

    @staticmethod
    def _is_terminal_task_error(
        exc: Exception,
    ) -> bool:

        message = str(
            exc
        ).lower()

        indicators = (
            "agnes video task failed",
            "cancelled",
            "canceled",
            "rejected",
            "invalid task",
            "invalid video",
            "task not found",
            "video not found",
        )

        return any(
            indicator in message
            for indicator
            in indicators
        )

    # ======================================================
    # RETRY-AFTER
    # ======================================================

    @staticmethod
    def _get_retry_after(
        exc: Exception,
    ) -> int:

        retry_after = getattr(
            exc,
            "retry_after",
            None,
        )

        if retry_after is None:

            return 0

        try:

            return max(
                0,
                int(
                    math.ceil(
                        float(
                            retry_after
                        )
                    )
                ),
            )

        except (
            TypeError,
            ValueError,
        ):

            return 0

    # ======================================================
    # DISABLE NESTED AGNES RETRIES
    # ======================================================

    @staticmethod
    def _call_with_optional_retry_control(
        method,
        **kwargs,
    ):
        """
        VideoPipeline owns the retry strategy.

        If AgnesClient exposes max_retries/retry_delay, force
        it to submit only once per pipeline attempt.
        """

        try:

            parameters = (
                inspect.signature(
                    method
                ).parameters
            )

        except (
            TypeError,
            ValueError,
        ):

            parameters = {}

        if (
            "max_retries"
            in parameters
        ):

            kwargs[
                "max_retries"
            ] = 1

        if (
            "retry_delay"
            in parameters
        ):

            kwargs[
                "retry_delay"
            ] = 1

        return method(
            **kwargs
        )

    # ======================================================
    # SUBMIT SCENE WITH RETRY
    # ======================================================

    def _submit_scene_with_backoff(
        self,
        item: PreparedScene,
        prompt: str,
        image_paths: list[Path],
        size: str,
        aspect_ratio: str,
        scene_position: int,
        total_scenes: int,
        progress_callback: Optional[
            PipelineProgressCallback
        ],
    ) -> str:

        attempt = 0

        started = (
            time.monotonic()
        )

        while True:

            attempt += 1

            try:

                # ==========================================
                # REFERENCE MODE
                # ==========================================

                if (
                    image_paths
                    or item.audio_path
                    is not None
                ):

                    audio_paths: list[
                        Path
                    ] = []

                    if (
                        item.audio_path
                        is not None
                    ):

                        audio_paths.append(
                            item.audio_path
                        )

                    video_id = (
                        self
                        ._call_with_optional_retry_control(
                            self.agnes
                            .create_reference_video,
                            prompt=prompt,
                            image_paths=(
                                image_paths
                            ),
                            audio_paths=(
                                audio_paths
                            ),
                            seconds=(
                                item.scene.duration
                            ),
                            size=size,
                            aspect_ratio=(
                                aspect_ratio
                            ),
                        )
                    )

                # ==========================================
                # TEXT MODE
                # ==========================================

                else:

                    video_id = (
                        self
                        ._call_with_optional_retry_control(
                            self.agnes
                            .create_video,
                            prompt=prompt,
                            seconds=(
                                item.scene.duration
                            ),
                            size=size,
                            aspect_ratio=(
                                aspect_ratio
                            ),
                        )
                    )

                elapsed = int(
                    time.monotonic()
                    - started
                )

                print()

                print(
                    "=" * 72
                )

                print(
                    "AGNES REQUEST ACCEPTED"
                )

                print(
                    "=" * 72
                )

                print(
                    f"Scene: "
                    f"{item.scene.number}"
                )

                print(
                    f"Attempts: "
                    f"{attempt}"
                )

                print(
                    "Waiting time before acceptance: "
                    f"{elapsed}s"
                )

                print(
                    f"Video ID: "
                    f"{video_id}"
                )

                print(
                    "=" * 72
                )

                print()

                return video_id

            except AgnesAPIError as exc:

                error_type = (
                    self._classify_agnes_error(
                        exc
                    )
                )

                elapsed = int(
                    time.monotonic()
                    - started
                )

                print()

                print(
                    "=" * 72
                )

                print(
                    "AGNES SUBMISSION STATUS"
                )

                print(
                    "=" * 72
                )

                print(
                    f"Scene: "
                    f"{item.scene.number}"
                )

                print(
                    f"Attempt: "
                    f"{attempt}"
                )

                print(
                    f"Classification: "
                    f"{error_type}"
                )

                print(
                    f"Waiting time: "
                    f"{elapsed}s"
                )

                print(
                    "Original Agnes message:"
                )

                print(
                    str(exc)
                )

                print(
                    "=" * 72
                )

                print()

                server_delay = (
                    self._get_retry_after(
                        exc
                    )
                )

                # ==========================================
                # VIDEO QUEUE FULL
                # ==========================================

                if (
                    error_type
                    == "queue_full"
                ):

                    delay = max(
                        self.QUEUE_RETRY_DELAY,
                        server_delay,
                    )

                    self._notify_progress(
                        progress_callback,
                        scene_position,
                        total_scenes,
                        (
                            "queue_full_wait_"
                            f"{delay}s"
                        ),
                        0,
                    )

                    print(
                        "Agnes video queue is full."
                    )

                    print(
                        "The job will NOT stop."
                    )

                    print(
                        f"Retrying automatically "
                        f"in {delay} seconds."
                    )

                    print()

                    time.sleep(
                        delay
                    )

                    continue

                # ==========================================
                # RATE LIMIT
                # ==========================================

                if (
                    error_type
                    == "rate_limit"
                ):

                    delay = max(
                        self.RATE_LIMIT_RETRY_DELAY,
                        server_delay,
                    )

                    self._notify_progress(
                        progress_callback,
                        scene_position,
                        total_scenes,
                        (
                            "rate_limit_wait_"
                            f"{delay}s"
                        ),
                        0,
                    )

                    print(
                        "Agnes rate limit reached."
                    )

                    print(
                        "The job remains active."
                    )

                    print(
                        f"Retrying automatically "
                        f"in {delay} seconds."
                    )

                    print()

                    time.sleep(
                        delay
                    )

                    continue

                # ==========================================
                # TEMPORARY ERROR
                # ==========================================

                if (
                    error_type
                    == "temporary"
                ):

                    delay = max(
                        self.TEMPORARY_ERROR_RETRY_DELAY,
                        server_delay,
                    )

                    self._notify_progress(
                        progress_callback,
                        scene_position,
                        total_scenes,
                        (
                            "temporary_error_wait_"
                            f"{delay}s"
                        ),
                        0,
                    )

                    print(
                        "Temporary Agnes/server error."
                    )

                    print(
                        "The job remains active."
                    )

                    print(
                        f"Retrying automatically "
                        f"in {delay} seconds."
                    )

                    print()

                    time.sleep(
                        delay
                    )

                    continue

                # ==========================================
                # ACCOUNT / AUTH FATAL ERRORS
                # ==========================================

                if (
                    error_type
                    == "quota"
                ):

                    raise VideoPipelineError(
                        "Agnes quota, credit or usage "
                        "limit appears to have been "
                        f"reached. Original error: {exc}"
                    ) from exc

                if (
                    error_type
                    == "authentication"
                ):

                    raise VideoPipelineError(
                        "Agnes authentication failed. "
                        f"Original error: {exc}"
                    ) from exc

                if (
                    error_type
                    == "authorization"
                ):

                    raise VideoPipelineError(
                        "Agnes refused access to the "
                        "requested model or operation. "
                        f"Original error: {exc}"
                    ) from exc

                raise

    # ======================================================
    # TASK STATE PATH
    # ======================================================

    @staticmethod
    def _task_state_path(
        output_directory: Path,
        scene_number: int,
    ) -> Path:

        return (
            output_directory
            / (
                f"scene_"
                f"{scene_number:02d}"
                ".task.json"
            )
        )

    # ======================================================
    # SAVE TASK STATE
    # ======================================================

    @staticmethod
    def _save_task_state(
        path: Path,
        video_id: str,
        account_id: Optional[str] = None,
    ) -> None:

        data = {
            "video_id": (
                video_id
            ),
        }
        if account_id:
            data["account_fingerprint"] = account_id

        temporary = Path(
            str(path)
            + ".tmp"
        )

        temporary.write_text(
            json.dumps(
                data,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary.replace(
            path
        )

    # ======================================================
    # LOAD TASK STATE
    # ======================================================

    @staticmethod
    def _load_task_state(
        path: Path,
    ) -> Optional[str]:

        if not path.exists():

            return None

        try:

            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            video_id = str(
                data.get(
                    "video_id",
                    "",
                )
            ).strip()

            return (
                video_id
                or None
            )

        except (
            OSError,
            json.JSONDecodeError,
            TypeError,
        ):

            return None

    # ======================================================
    # DELETE TASK STATE
    # ======================================================

    @staticmethod
    def _delete_task_state(
        path: Path,
    ) -> None:

        try:

            if path.exists():

                path.unlink()

        except OSError:

            pass

    # ======================================================
    # CONTINUITY FRAME PATH
    # ======================================================

    @staticmethod
    def _continuity_frame_path(
        continuity_directory: Path,
        scene_number: int,
    ) -> Path:

        return (
            continuity_directory
            / (
                f"scene_"
                f"{scene_number:02d}"
                "_last.jpg"
            )
        )

    # ======================================================
    # ENSURE CONTINUITY FRAME
    # ======================================================

    def _ensure_continuity_frame(
        self,
        video_path: Path,
        output_path: Path,
    ) -> Path:

        if (
            output_path.exists()
            and output_path.is_file()
            and output_path.stat().st_size > 1000
        ):

            return output_path

        try:

            return (
                self.frame_extractor
                .extract_last_frame(
                    video_path=(
                        video_path
                    ),
                    output_path=(
                        output_path
                    ),
                )
            )

        except FrameExtractionError as exc:

            raise VideoPipelineError(
                "Unable to extract continuity "
                f"frame from {video_path}: "
                f"{exc}"
            ) from exc

    # ======================================================
    # GENERATE SCENES
    # ======================================================

    def generate_scenes(
        self,
        plan: VideoPlan,
        prepared_scenes: list[
            PreparedScene
        ],
        aspect_ratio: str = (
            DEFAULT_ASPECT_RATIO
        ),
        size: str = DEFAULT_SIZE,
        progress_callback: Optional[
            PipelineProgressCallback
        ] = None,
        job_id: Optional[str] = None,
        resume: bool = True,
        cooldown_seconds: int = 45,
    ) -> list[GeneratedScene]:

        if not prepared_scenes:

            raise VideoPipelineError(
                "No prepared scenes provided."
            )

        total = len(
            prepared_scenes
        )

        generated: list[
            GeneratedScene
        ] = []

        generation_id = (
            uuid4().hex[:10]
        )

        # ==================================================
        # OUTPUT DIRECTORIES
        # ==================================================

        if job_id:

            clean_job_id = (
                job_id.strip()
            )

            if not clean_job_id:

                raise VideoPipelineError(
                    "Invalid generation job ID."
                )

            output_directory = (
                self.video_dir
                / "jobs"
                / clean_job_id
            )

            continuity_directory = (
                output_directory
                / "continuity"
            )

        else:

            output_directory = (
                self.video_dir
            )

            continuity_directory = (
                self.video_dir
                / "continuity"
                / generation_id
            )

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        continuity_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ==================================================
        # MAP SCENE -> PREVIOUS STORYBOARD SCENE
        # ==================================================

        previous_scene_map: dict[
            int,
            int,
        ] = {}

        for index, scene in enumerate(
            plan.scenes
        ):

            if index == 0:
                continue

            previous_scene_map[
                scene.number
            ] = (
                plan.scenes[
                    index - 1
                ].number
            )

        cooldown_required = False

        # ==================================================
        # PROCESS SCENES
        # ==================================================

        for position, item in enumerate(
            prepared_scenes,
            start=1,
        ):

            scene = (
                item.scene
            )

            # ==============================================
            # VIDEO OUTPUT PATH
            # ==============================================

            if job_id:

                output_path = (
                    output_directory
                    / (
                        f"scene_"
                        f"{scene.number:02d}"
                        ".mp4"
                    )
                )

            else:

                output_path = (
                    output_directory
                    / (
                        f"scene_"
                        f"{scene.number:02d}_"
                        f"{generation_id}"
                        ".mp4"
                    )
                )

            continuity_output_path = (
                self._continuity_frame_path(
                    continuity_directory=(
                        continuity_directory
                    ),
                    scene_number=(
                        scene.number
                    ),
                )
            )

            # ==============================================
            # COMPLETED SCENE
            # ==============================================

            if (
                resume
                and output_path.exists()
                and output_path.is_file()
                and output_path.stat().st_size > 0
            ):

                # Important:
                # a completed scene must also have a usable
                # continuity frame for possible later scenes.
                self._ensure_continuity_frame(
                    video_path=(
                        output_path
                    ),
                    output_path=(
                        continuity_output_path
                    ),
                )

                self._notify_progress(
                    progress_callback,
                    position,
                    total,
                    "already_completed",
                    100,
                )

                generated.append(
                    GeneratedScene(
                        scene=scene,
                        video_path=(
                            output_path
                        ),
                        task_id="cached",
                    )
                )

                continue

            # ==============================================
            # PREVIOUS-SCENE CONTINUITY FRAME
            # ==============================================

            previous_frame: Optional[
                Path
            ] = None

            previous_scene_number = (
                previous_scene_map.get(
                    scene.number
                )
            )

            if (
                item.scene_reference_image_path is None
                and scene.use_previous_frame
                and previous_scene_number
                is not None
            ):

                candidate_frame = (
                    self._continuity_frame_path(
                        continuity_directory=(
                            continuity_directory
                        ),
                        scene_number=(
                            previous_scene_number
                        ),
                    )
                )

                # ------------------------------------------
                # REBUILD FRAME FROM PREVIOUS VIDEO
                # ------------------------------------------

                if not (
                    candidate_frame.exists()
                    and candidate_frame.is_file()
                    and candidate_frame.stat().st_size > 1000
                ):

                    previous_video = (
                        output_directory
                        / (
                            f"scene_"
                            f"{previous_scene_number:02d}"
                            ".mp4"
                        )
                    )

                    if (
                        previous_video.exists()
                        and previous_video.is_file()
                        and previous_video.stat().st_size > 0
                    ):

                        candidate_frame = (
                            self
                            ._ensure_continuity_frame(
                                video_path=(
                                    previous_video
                                ),
                                output_path=(
                                    candidate_frame
                                ),
                            )
                        )

                if (
                    candidate_frame.exists()
                    and candidate_frame.is_file()
                    and candidate_frame.stat().st_size > 1000
                ):

                    previous_frame = (
                        candidate_frame
                    )

                else:

                    print()

                    print(
                        f"Scene {scene.number}: "
                        "previous-frame continuity was "
                        "requested but no previous frame "
                        "is available."
                    )

                    print(
                        "Generation will continue using "
                        "character references and text "
                        "continuity only."
                    )

                    print()

            # ==============================================
            # REFERENCE IMAGE SELECTION
            # ==============================================

            image_paths: list[
                Path
            ] = []

            selected_character_ids: list[
                str
            ] = []

            scene_reference_present = bool(
                item.scene_reference_image_path
                is not None
            )

            # --------------------------------------------------
            # PRODUCTION MODE
            # --------------------------------------------------
            #
            # If a validated scene master image exists, send
            # exactly ONE image to Agnes. The master image has
            # already incorporated character identity, set,
            # composition and lighting during pre-production.
            #
            # This deliberately avoids conflicting simultaneous
            # visual references.

            if scene_reference_present:

                scene_reference_path = Path(
                    item.scene_reference_image_path
                )

                if not (
                    scene_reference_path.exists()
                    and scene_reference_path.is_file()
                    and scene_reference_path.stat().st_size > 0
                ):

                    raise VideoPipelineError(
                        f"Scene {scene.number}: validated "
                        "scene reference image is missing or "
                        "invalid."
                    )

                image_paths.append(
                    scene_reference_path
                )

            # --------------------------------------------------
            # LEGACY / FALLBACK MODE
            # --------------------------------------------------
            # Preserve the previous behavior for tests and old
            # projects that do not provide scene master images.

            else:

                continuity_slots = (
                    1
                    if previous_frame
                    is not None
                    else 0
                )

                character_slots = (
                    self.MAX_REFERENCE_IMAGES
                    - continuity_slots
                )

                selected_pairs = (
                    self._select_character_references(
                        item=item,
                        max_count=(
                            character_slots
                        ),
                    )
                )

                selected_character_ids = [
                    character_id
                    for (
                        character_id,
                        _
                    )
                    in selected_pairs
                ]

                if (
                    len(
                        item.reference_character_ids
                    )
                    >
                    len(
                        selected_pairs
                    )
                ):

                    omitted = (
                        len(
                            item.reference_character_ids
                        )
                        - len(
                            selected_pairs
                        )
                    )

                    print()

                    print(
                        f"Scene {scene.number}: "
                        f"{omitted} character reference "
                        "image(s) omitted because Agnes "
                        f"accepts a maximum of "
                        f"{self.MAX_REFERENCE_IMAGES} "
                        "reference images."
                    )

                    print()

                if (
                    previous_frame
                    is not None
                ):

                    image_paths.append(
                        previous_frame
                    )

                image_paths.extend(
                    image_path
                    for (
                        _,
                        image_path
                    )
                    in selected_pairs
                )

            if (
                len(
                    image_paths
                )
                >
                self.MAX_REFERENCE_IMAGES
            ):

                raise VideoPipelineError(
                    f"Scene {scene.number}: "
                    "too many reference images "
                    f"({len(image_paths)})."
                )

            # ==============================================
            # BUILD FINAL AGNES PROMPT
            # ==============================================

            prompt = (
                self.build_scene_prompt(
                    plan=plan,
                    scene=scene,
                    speaking=(
                        item.has_dialogue
                    ),
                    speech_duration=(
                        item.speech_duration
                    ),
                    scene_reference_present=(
                        scene_reference_present
                    ),
                    continuity_frame_present=(
                        previous_frame
                        is not None
                    ),
                    reference_character_ids=(
                        selected_character_ids
                    ),
                    native_audio=item.native_audio,
                )
            )

            # ==============================================
            # TASK STATE
            # ==============================================

            task_path = (
                self._task_state_path(
                    output_directory=(
                        output_directory
                    ),
                    scene_number=(
                        scene.number
                    ),
                )
            )

            video_id: Optional[
                str
            ] = None

            if resume:

                video_id = (
                    self._load_task_state(
                        task_path
                    )
                )

            # ==============================================
            # RESUME EXISTING AGNES TASK
            # ==============================================

            if video_id:

                self._notify_progress(
                    progress_callback,
                    position,
                    total,
                    "resuming_existing_task",
                    0,
                )

                print()

                print(
                    f"Scene {scene.number}: "
                    "resuming Agnes task"
                )

                print(
                    f"Video ID: "
                    f"{video_id}"
                )

                print()

            # ==============================================
            # SUBMIT NEW AGNES TASK
            # ==============================================

            else:

                if (
                    cooldown_required
                    and cooldown_seconds > 0
                ):

                    self._notify_progress(
                        progress_callback,
                        position,
                        total,
                        (
                            f"cooldown_"
                            f"{cooldown_seconds}s"
                        ),
                        0,
                    )

                    time.sleep(
                        cooldown_seconds
                    )

                self._notify_progress(
                    progress_callback,
                    position,
                    total,
                    "submitting",
                    0,
                )

                try:

                    video_id = (
                        self
                        ._submit_scene_with_backoff(
                            item=item,
                            prompt=prompt,
                            image_paths=(
                                image_paths
                            ),
                            size=size,
                            aspect_ratio=(
                                aspect_ratio
                            ),
                            scene_position=(
                                position
                            ),
                            total_scenes=(
                                total
                            ),
                            progress_callback=(
                                progress_callback
                            ),
                        )
                    )

                except VideoPipelineError:
                    raise

                except AgnesAPIError as exc:

                    raise VideoPipelineError(
                        "Unable to submit "
                        f"scene {scene.number}: "
                        f"{exc}"
                    ) from exc

                # Save immediately.
                try:

                    self._save_task_state(
                        task_path,
                        video_id,
                        account_fingerprint(self.agnes),
                    )

                except OSError as exc:

                    raise VideoPipelineError(
                        "Agnes accepted scene "
                        f"{scene.number}, but the task "
                        "ID could not be saved locally. "
                        f"Video ID: {video_id}. "
                        f"Error: {exc}"
                    ) from exc

            # ==============================================
            # POLL AGNES
            # ==============================================

            def scene_progress(
                status: str,
                progress: int,
            ) -> None:

                self._notify_progress(
                    progress_callback,
                    position,
                    total,
                    status,
                    progress,
                )

            try:

                video_id, video_url = self._wait_with_failed_task_retries(
                    video_id, task_path,
                    submit=lambda: self._submit_scene_with_backoff(
                        item=item, prompt=prompt, image_paths=image_paths,
                        size=size, aspect_ratio=aspect_ratio,
                        scene_position=position, total_scenes=total,
                        progress_callback=progress_callback,
                    ),
                    progress_callback=scene_progress,
                )

            except AgnesAPIError as exc:

                # Only destroy the saved task ID if Agnes
                # clearly says the task no longer exists or
                # has permanently failed.
                if (
                    self._is_terminal_task_error(
                        exc
                    )
                ):

                    self._delete_task_state(
                        task_path
                    )

                raise VideoPipelineError(
                    f"Scene "
                    f"{scene.number} "
                    "generation failed: "
                    f"{exc}"
                ) from exc

            # ==============================================
            # DOWNLOAD VIDEO
            # ==============================================

            self._notify_progress(
                progress_callback,
                position,
                total,
                "downloading",
                100,
            )

            temporary_video_path = Path(
                str(
                    output_path
                )
                + ".part"
            )

            self._safe_unlink(
                temporary_video_path
            )

            try:

                self.agnes.download_video(
                    video_url=(
                        video_url
                    ),
                    output_path=(
                        temporary_video_path
                    ),
                )

            except AgnesAPIError as exc:

                raise VideoPipelineError(
                    f"Scene "
                    f"{scene.number} "
                    "download failed: "
                    f"{exc}"
                ) from exc

            # ==============================================
            # VERIFY DOWNLOAD
            # ==============================================

            if not (
                temporary_video_path.exists()
                and temporary_video_path.is_file()
                and temporary_video_path.stat().st_size > 0
            ):

                raise VideoPipelineError(
                    f"Scene "
                    f"{scene.number}: "
                    "download produced an empty "
                    "or invalid video file."
                )

            # ==============================================
            # ATOMIC VIDEO FINALIZATION
            # ==============================================

            try:

                if output_path.exists():

                    output_path.unlink()

                temporary_video_path.replace(
                    output_path
                )

            except OSError as exc:

                raise VideoPipelineError(
                    f"Unable to finalize "
                    f"scene {scene.number}: "
                    f"{exc}"
                ) from exc

            # ==============================================
            # CONTINUITY FRAME EXTRACTION
            # ==============================================

            self._notify_progress(
                progress_callback,
                position,
                total,
                "extracting_continuity_frame",
                100,
            )

            try:

                self._ensure_continuity_frame(
                    video_path=(
                        output_path
                    ),
                    output_path=(
                        continuity_output_path
                    ),
                )

            except VideoPipelineError:
                # The video itself remains safely saved.
                # We keep the Agnes task state until all
                # post-processing is safely complete.
                raise

            # ==============================================
            # SCENE FULLY SAFE
            # ==============================================

            self._delete_task_state(
                task_path
            )

            generated.append(
                GeneratedScene(
                    scene=scene,
                    video_path=(
                        output_path
                    ),
                    task_id=(
                        video_id
                    ),
                )
            )

            self._notify_progress(
                progress_callback,
                position,
                total,
                "completed",
                100,
            )

            cooldown_required = True

        return generated

    # ======================================================
    # PROGRESS CALLBACK
    # ======================================================

    @staticmethod
    def _notify_progress(
        callback: Optional[
            PipelineProgressCallback
        ],
        current: int,
        total: int,
        status: str,
        progress: int,
    ) -> None:

        if callback is None:

            return

        try:

            progress = int(
                progress
            )

        except (
            TypeError,
            ValueError,
        ):

            progress = 0

        progress = max(
            0,
            min(
                progress,
                100,
            ),
        )

        callback(
            current,
            total,
            status,
            progress,
        )

    # ======================================================
    # CLEANUP AUDIO
    # ======================================================

    @staticmethod
    def cleanup_audio(
        prepared_scenes: list[
            PreparedScene
        ],
    ) -> None:

        for item in (
            prepared_scenes
        ):

            if (
                item.audio_path
                is None
            ):

                continue

            try:

                if (
                    item.audio_path.exists()
                ):

                    item.audio_path.unlink()

            except OSError:

                pass
