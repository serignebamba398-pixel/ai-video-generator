from pathlib import Path

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

TEST_SCENE_COUNT = 2

KEEP_AUDIO_FILES = True

VOICE = "fr-FR-HenriNeural"


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

During the first part of the shot he performs the action.

Then he stops, looks toward the camera and speaks.

After speaking, he silently looks back at the price
and gives a restrained comedic reaction.

One continuous full-screen shot.

No scene transition inside the clip.
""".strip(),
        dialogue=(
            "À ce prix-là, je vais bientôt demander "
            "un crédit pour faire les courses."
        ),
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

He stops moving, looks toward the camera and speaks.

After the sentence, he looks back at the pump
with a silent expression of disbelief.

One continuous full-screen cinematic shot.
""".strip(),
        dialogue=(
            "Je voulais faire le plein, "
            "pas acheter la station-service."
        ),
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

He turns his face toward the camera and speaks.

After speaking, he looks at the baguette as if it were
an expensive luxury product.

One continuous full-screen realistic cinematic shot.
""".strip(),
        dialogue=(
            "À ce tarif, la baguette devrait être "
            "livrée avec une assurance."
        ),
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

He slowly looks toward the camera and speaks.

After the dialogue he takes a very small sip
and carefully puts the cup down as if it were precious.

One continuous full-screen cinematic shot.
""".strip(),
        dialogue=(
            "À ce prix-là, je vais boire "
            "chaque goutte avec respect."
        ),
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

He finally looks directly toward the camera and speaks.

After the sentence, he quietly puts the phone down
and stares into the distance in comedic defeat.

One continuous full-screen cinematic ending shot.
""".strip(),
        dialogue=(
            "Finalement, rester chez moi, "
            "c'est peut-être mon meilleur investissement."
        ),
    ),
]


# ==========================================================
# VIDEO PLAN
# ==========================================================

plan = VideoPlan(
    title="La vie chère",
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
    voice=VOICE,
    speech_rate="+0%",
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

    print(
        f"Scene {scene_position}/{total_scenes} "
        f"| {status} "
        f"| {progress}%"
    )


# ==========================================================
# PREPARE AUDIO WITHOUT CHANGING 12-SECOND DURATIONS
# ==========================================================

prepared = []
generated = []


try:

    print()
    print("=" * 70)
    print("FULL-SCREEN CINEMATIC TEST")
    print("=" * 70)

    print()
    print(
        f"Total planned duration: "
        f"{plan.total_duration} seconds"
    )

    print(
        f"Scenes: {len(plan.scenes)}"
    )

    print()

    # ------------------------------------------------------
    # Generate TTS manually.
    # We intentionally keep every scene at 12 seconds.
    # ------------------------------------------------------

    for scene in plan.scenes:

        dialogue = (
            scene.dialogue or ""
        ).strip()

        if not dialogue:

            prepared.append(
                PreparedScene(
                    scene=scene,
                    audio_path=None,
                    speech_duration=0.0,
                )
            )

            continue

        audio_path = (
            Path(AUDIO_DIR)
            / f"fullscreen_scene_{scene.number:02d}.mp3"
        )

        pipeline.voice_generator.generate(
            text=dialogue,
            output_path=audio_path,
        )

        speech_duration = (
            pipeline.get_audio_duration(
                audio_path
            )
        )

        print(
            f"Scene {scene.number}: "
            f"video = {scene.duration}s "
            f"| speech = {speech_duration:.2f}s"
        )

        print(
            f"Dialogue: {dialogue}"
        )

        print(
            f"Audio: {audio_path.resolve()}"
        )

        print()

        if speech_duration > 9.5:

            raise VideoPipelineError(
                f"Scene {scene.number}: "
                "dialogue is too long for this "
                "12-second cinematic scene."
            )

        prepared.append(
            PreparedScene(
                scene=scene,
                audio_path=audio_path,
                speech_duration=speech_duration,
            )
        )

    # ======================================================
    # SELECT ONLY FIRST SCENES FOR TEST
    # ======================================================

    if TEST_SCENE_COUNT is None:

        scenes_to_generate = prepared

    else:

        scenes_to_generate = (
            prepared[
                :TEST_SCENE_COUNT
            ]
        )

    print()
    print("=" * 70)
    print("GENERATING")
    print("=" * 70)

    print(
        f"Generating "
        f"{len(scenes_to_generate)} "
        f"of {len(prepared)} scenes."
    )

    print()

    # ======================================================
    # SHOW EXACT PROMPTS
    # ======================================================

    for item in scenes_to_generate:

        prompt = (
            pipeline.build_scene_prompt(
                plan=plan,
                scene=item.scene,
                speaking=item.has_dialogue,
            )
        )

        print("=" * 70)
        print(
            f"PROMPT FOR SCENE "
            f"{item.scene.number}"
        )
        print("=" * 70)
        print()
        print(prompt)
        print()

    # ======================================================
    # GENERATE AGNES VIDEOS
    # ======================================================

    generated = (
        pipeline.generate_scenes(
            plan=plan,
            prepared_scenes=(
                scenes_to_generate
            ),
            aspect_ratio="16:9",
            progress_callback=(
                show_progress
            ),
        )
    )

    # ======================================================
    # RESULTS
    # ======================================================

    print()
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()

    for result in generated:

        print(
            f"Scene "
            f"{result.scene.number}:"
        )

        print(
            result.video_path.resolve()
        )

        print()

    print(
        "Compare especially:"
    )

    print(
        "- same character"
    )

    print(
        "- same clothing"
    )

    print(
        "- natural action before speech"
    )

    print(
        "- French dialogue"
    )

    print(
        "- lip synchronization"
    )

    print(
        "- silent reaction after speech"
    )

    print(
        "- full-screen cinematic composition"
    )


except VideoPipelineError as exc:

    print()
    print(
        "Video pipeline error:"
    )
    print(exc)


except KeyboardInterrupt:

    print()
    print(
        "Generation interrupted."
    )


except Exception as exc:

    print()
    print(
        f"Unexpected error: "
        f"{type(exc).__name__}: {exc}"
    )


finally:

    if (
        prepared
        and not KEEP_AUDIO_FILES
    ):

        pipeline.cleanup_audio(
            prepared
        )

    elif prepared:

        print()
        print(
            "Audio files kept for testing."
        )