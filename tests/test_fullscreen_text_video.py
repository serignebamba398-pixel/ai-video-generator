from __future__ import annotations

from src.config import (
    AUDIO_DIR,
    OUTPUT_DIR,
)

from src.scene_planner import (
    Scene,
    VideoPlan,
)

from src.video_pipeline import (
    PreparedScene,
    VideoPipeline,
    VideoPipelineError,
)


# ==========================================================
# CONFIGURATION
# ==========================================================

# Generate only the first 2 scenes for comparison.
#
# Set to None if you later want all 5 scenes.
TEST_SCENE_COUNT = 2


# ==========================================================
# FIXED CHARACTER
# ==========================================================

CHARACTER = """
A French man in his late 30s.

Short dark brown hair.

Clean-shaven face.

Expressive eyebrows.

Slightly serious but naturally funny facial expression.

He wears exactly the same clothes in every scene:
a beige casual jacket over a plain white t-shirt,
dark blue jeans and white sneakers.

His face, hairstyle, body proportions and clothing
must remain visually consistent throughout the video.
""".strip()


# ==========================================================
# GLOBAL STYLE
# ==========================================================

STYLE = """
Realistic cinematic live-action video.

Natural French everyday-life atmosphere.

Full-screen composition.

16:9 horizontal format.

Natural lighting.

Realistic skin texture.

Natural body motion.

Professional commercial-style cinematography.

No split screen.

No collage.

No subtitles.

No captions.

No on-screen text.
""".strip()


# ==========================================================
# FIVE 12-SECOND SCENES
# ==========================================================
#
# IMPORTANT:
#
# These are deliberately based on the same visual situations
# as test_fullscreen_video.py.
#
# But ALL dialogue has been removed.
#
# Therefore:
#
# item.has_dialogue == False
#
# and VideoPipeline will use:
#
# AgnesClient.create_video(...)
#
# instead of:
#
# AgnesClient.create_reference_video(...)
#
# ==========================================================

scenes = [

    Scene(
        number=1,
        duration=12,
        visual_prompt="""
The same French man enters a modern supermarket
holding a small shopping basket.

He walks confidently through the aisle and picks up
a simple everyday grocery item.

He looks at its price.

His confident expression immediately changes to disbelief.

He looks back at the product, then at the price again.

He gives a restrained comedic reaction.

He remains completely silent.

Use natural facial expressions and body language
to communicate the joke visually.

One continuous full-screen shot.

No scene transition inside the clip.

No spoken dialogue.
""".strip(),
        dialogue="",
    ),

    Scene(
        number=2,
        duration=12,
        visual_prompt="""
The same French man arrives at a fuel station.

The exact same face, hairstyle and clothing are preserved.

He stands beside a car and begins filling the fuel tank.

He watches the numbers on the fuel pump rise quickly.

His expression becomes increasingly worried.

He freezes briefly and looks at the fuel pump
with disbelief.

He then looks toward the camera with a silent,
restrained comedic reaction.

He remains completely silent.

One continuous full-screen cinematic shot.

No spoken dialogue.
""".strip(),
        dialogue="",
    ),

    Scene(
        number=3,
        duration=12,
        visual_prompt="""
The same French man enters a traditional French bakery.

The same face and exact same clothing are preserved.

Fresh bread and pastries are visible behind the counter.

He receives one baguette and looks at the displayed price.

He freezes for a moment.

He looks at the baguette as if it were
an expensive luxury product.

He gives a subtle silent reaction toward the camera.

He remains completely silent.

One continuous full-screen realistic cinematic shot.

No spoken dialogue.
""".strip(),
        dialogue="",
    ),

    Scene(
        number=4,
        duration=12,
        visual_prompt="""
The same French man sits at a small French café.

Maintain exactly the same face, hairstyle and clothing.

A waiter places one small coffee on the table.

The man looks at the bill.

He checks the coffee, then checks the bill again.

He gives a restrained expression of disbelief.

He takes a very small sip
and carefully puts the cup down as if it were precious.

He remains completely silent.

One continuous full-screen cinematic shot.

No spoken dialogue.
""".strip(),
        dialogue="",
    ),

    Scene(
        number=5,
        duration=12,
        visual_prompt="""
The same French man is back home sitting at a table.

Maintain the exact same face, hairstyle and clothing.

Several receipts from the supermarket, fuel station,
bakery and café are spread across the table.

He calculates the expenses on his phone.

He becomes increasingly shocked.

He slowly puts the phone down.

He stares into the distance in comedic defeat.

He remains completely silent.

One continuous full-screen cinematic ending shot.

No spoken dialogue.
""".strip(),
        dialogue="",
    ),
]


# ==========================================================
# VIDEO PLAN
# ==========================================================

plan = VideoPlan(
    title="La vie chère - TEXT MODE TEST",
    language="French",
    character_description=CHARACTER,
    style_description=STYLE,
    scenes=scenes,
)


# ==========================================================
# PIPELINE
# ==========================================================

pipeline = VideoPipeline(
    audio_dir=AUDIO_DIR,
    video_dir=OUTPUT_DIR,
)


# ==========================================================
# PROGRESS
# ==========================================================

def show_progress(
    scene_position: int,
    total_scenes: int,
    status: str,
    progress: int,
) -> None:

    # ------------------------------------------------------
    # QUEUE FULL
    # ------------------------------------------------------

    if status.startswith(
        "queue_full_wait_"
    ):

        wait_time = status.replace(
            "queue_full_wait_",
            "",
        )

        print(
            f"Scene {scene_position}/{total_scenes} "
            f"| TEXT MODE "
            f"| queue full "
            f"| waiting {wait_time}"
        )

        return

    # ------------------------------------------------------
    # RATE LIMIT
    # ------------------------------------------------------

    if status.startswith(
        "rate_limit_wait_"
    ):

        wait_time = status.replace(
            "rate_limit_wait_",
            "",
        )

        print(
            f"Scene {scene_position}/{total_scenes} "
            f"| TEXT MODE "
            f"| rate limit "
            f"| waiting {wait_time}"
        )

        return

    # ------------------------------------------------------
    # TEMPORARY ERROR
    # ------------------------------------------------------

    if status.startswith(
        "temporary_error_wait_"
    ):

        wait_time = status.replace(
            "temporary_error_wait_",
            "",
        )

        print(
            f"Scene {scene_position}/{total_scenes} "
            f"| TEXT MODE "
            f"| temporary error "
            f"| waiting {wait_time}"
        )

        return

    # ------------------------------------------------------
    # NORMAL STATUS
    # ------------------------------------------------------

    print(
        f"Scene {scene_position}/{total_scenes} "
        f"| TEXT MODE "
        f"| {status} "
        f"| {progress}%"
    )


# ==========================================================
# PREPARE SCENES
# ==========================================================

prepared: list[PreparedScene] = []

generated = []


try:

    print()

    print(
        "=" * 70
    )

    print(
        "FULL-SCREEN TEXT-ONLY TEST"
    )

    print(
        "=" * 70
    )

    print()

    print(
        "IMPORTANT:"
    )

    print(
        "This test uses NO reference audio."
    )

    print(
        "All scenes use Agnes TEXT mode."
    )

    print()

    print(
        f"Total planned duration: "
        f"{plan.total_duration} seconds"
    )

    print(
        f"Scenes: "
        f"{len(plan.scenes)}"
    )

    print(
        f"Aspect ratio: 16:9"
    )

    print()

    # ======================================================
    # PREPARE WITHOUT AUDIO
    # ======================================================

    for scene in plan.scenes:

        prepared_scene = PreparedScene(
            scene=scene,
            audio_path=None,
            speech_duration=0.0,
        )

        prepared.append(
            prepared_scene
        )

        print(
            f"Scene {scene.number}: "
            f"video = {scene.duration}s "
            f"| dialogue = NO "
            f"| audio = NONE "
            f"| mode = TEXT"
        )

    # ======================================================
    # SELECT FIRST SCENES
    # ======================================================

    if TEST_SCENE_COUNT is None:

        scenes_to_generate = (
            prepared
        )

    else:

        scenes_to_generate = (
            prepared[
                :TEST_SCENE_COUNT
            ]
        )

    if not scenes_to_generate:

        raise VideoPipelineError(
            "No scenes selected."
        )

    print()

    print(
        "=" * 70
    )

    print(
        "TEST CONFIGURATION"
    )

    print(
        "=" * 70
    )

    print()

    print(
        f"Generating "
        f"{len(scenes_to_generate)} "
        f"of {len(prepared)} scenes."
    )

    print(
        "Agnes mode: TEXT"
    )

    print(
        "Reference audio: NONE"
    )

    print(
        "Dialogue: NONE"
    )

    print(
        "Aspect ratio: 16:9"
    )

    print()

    # ======================================================
    # SHOW EXACT PROMPTS
    # ======================================================

    print(
        "=" * 70
    )

    print(
        "PROMPTS"
    )

    print(
        "=" * 70
    )

    print()

    for item in scenes_to_generate:

        prompt = (
            pipeline.build_scene_prompt(
                plan=plan,
                scene=item.scene,
                speaking=False,
                speech_duration=0.0,
            )
        )

        print(
            "=" * 70
        )

        print(
            f"PROMPT FOR SCENE "
            f"{item.scene.number}"
        )

        print(
            "=" * 70
        )

        print()

        print(
            "AGNES MODE: TEXT"
        )

        print(
            "REFERENCE AUDIO: NONE"
        )

        print()

        print(
            prompt
        )

        print()

    # ======================================================
    # GENERATE
    # ======================================================

    print(
        "=" * 70
    )

    print(
        "GENERATING TEXT-ONLY VIDEOS"
    )

    print(
        "=" * 70
    )

    print()

    generated = (
        pipeline.generate_scenes(
            plan=plan,
            prepared_scenes=(
                scenes_to_generate
            ),
            aspect_ratio="16:9",
            size="720P",
            progress_callback=(
                show_progress
            ),

            # IMPORTANT:
            #
            # No job_id here.
            #
            # Every launch is a completely fresh test.
            #
            # We do not want an old completed scene
            # to be skipped.
            job_id=None,

            resume=False,

            # Same general behavior as our other test.
            cooldown_seconds=45,
        )
    )

    # ======================================================
    # RESULTS
    # ======================================================

    print()

    print(
        "=" * 70
    )

    print(
        "TEXT MODE TEST COMPLETED"
    )

    print(
        "=" * 70
    )

    print()

    for result in generated:

        print(
            f"Scene "
            f"{result.scene.number}"
        )

        print(
            "Mode: TEXT"
        )

        print(
            "Reference audio: NONE"
        )

        print(
            f"Task ID: "
            f"{result.task_id}"
        )

        print(
            f"Video:"
        )

        print(
            result.video_path.resolve()
        )

        print()

    print(
        "=" * 70
    )

    print(
        "INTERPRETATION"
    )

    print(
        "=" * 70
    )

    print()

    print(
        "Compare the submission behavior with "
        "test_fullscreen_video.py."
    )

    print()

    print(
        "Reference version:"
    )

    print(
        "dialogue + MP3 -> REFERENCE mode"
    )

    print()

    print(
        "This version:"
    )

    print(
        "no dialogue + no MP3 -> TEXT mode"
    )

    print()

    print(
        "If this TEXT test repeatedly receives "
        "video_queue_full while the REFERENCE test "
        "is immediately accepted during the same period, "
        "that would be useful evidence of different "
        "queue/capacity behavior."
    )


# ==========================================================
# ERRORS
# ==========================================================

except VideoPipelineError as exc:

    print()

    print(
        "=" * 70
    )

    print(
        "VIDEO PIPELINE ERROR"
    )

    print(
        "=" * 70
    )

    print()

    print(
        exc
    )


except KeyboardInterrupt:

    print()

    print(
        "=" * 70
    )

    print(
        "TEST INTERRUPTED"
    )

    print(
        "=" * 70
    )

    print()

    print(
        "Generation interrupted manually."
    )


except Exception as exc:

    print()

    print(
        "=" * 70
    )

    print(
        "UNEXPECTED ERROR"
    )

    print(
        "=" * 70
    )

    print()

    print(
        f"{type(exc).__name__}: "
        f"{exc}"
    )