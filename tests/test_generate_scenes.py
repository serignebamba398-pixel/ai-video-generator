from src.config import (
    AUDIO_DIR,
    OUTPUT_DIR,
)

from src.scene_planner import (
    ScenePlanner,
    ScenePlannerError,
)

from src.video_pipeline import (
    VideoPipeline,
    VideoPipelineError,
)


# ==========================================================
# CONFIGURATION
# ==========================================================

TARGET_DURATION = 60

# Pour le diagnostic :
# 1 = générer uniquement la première scène.
# None = générer toutes les scènes.
TEST_SCENE_COUNT = 2

# IMPORTANT :
# True = conserver les fichiers MP3 après le test.
# False = supprimer les fichiers MP3 à la fin.
KEEP_AUDIO_FILES = True


USER_PROMPT = """
Create a funny 60-second vertical video about a
French man doing his weekly grocery shopping.

At first he thinks he will spend very little money,
but each aisle surprises him with higher prices.

He reacts humorously and speaks French.

The video should look realistic and cinematic,
with one consistent main character throughout.
"""


# ==========================================================
# PROGRESS CALLBACK
# ==========================================================


def show_progress(
    scene_position: int,
    total_scenes: int,
    status: str,
    progress: int,
) -> None:
    """
    Display Agnes generation progress in the terminal.
    """

    print(
        f"Scene {scene_position}/{total_scenes} "
        f"| {status} "
        f"| {progress}%"
    )


# ==========================================================
# INITIALIZE COMPONENTS
# ==========================================================


planner = ScenePlanner()

pipeline = VideoPipeline(
    audio_dir=AUDIO_DIR,
    video_dir=OUTPUT_DIR,
    voice="fr-FR-HenriNeural",
    speech_rate="+0%",
)

prepared = []
generated = []


# ==========================================================
# MAIN
# ==========================================================


try:

    # ======================================================
    # STEP 1 - CREATE VIDEO PLAN
    # ======================================================

    print()
    print("=" * 70)
    print("CREATING VIDEO PLAN")
    print("=" * 70)
    print()

    plan = planner.create_plan(
        user_prompt=USER_PROMPT,
        target_duration=TARGET_DURATION,
    )

    print(f"Title: {plan.title}")
    print(f"Language: {plan.language}")
    print(f"Scenes: {len(plan.scenes)}")
    print(
        f"Duration: {plan.total_duration} seconds"
    )

    print()
    print("MAIN CHARACTER:")
    print(plan.character_description)

    print()
    print("GLOBAL STYLE:")
    print(plan.style_description)

    print()

    # ======================================================
    # STEP 2 - GENERATE TTS AND PREPARE PLAN
    # ======================================================

    print("=" * 70)
    print("PREPARING AUDIO")
    print("=" * 70)
    print()

    final_plan, prepared = (
        pipeline.prepare_plan(
            plan
        )
    )

    print(
        f"Final duration: "
        f"{final_plan.total_duration} seconds"
    )

    print()

    # ======================================================
    # STEP 3 - DISPLAY ALL PREPARED SCENES
    # ======================================================

    print("=" * 70)
    print("PREPARED SCENES")
    print("=" * 70)
    print()

    for item in prepared:

        scene = item.scene

        print("=" * 70)

        print(
            f"SCENE {scene.number}"
        )

        print(
            f"Video duration: "
            f"{scene.duration} seconds"
        )

        print()

        print("VISUAL PROMPT:")
        print(scene.visual_prompt)

        print()

        # --------------------------------------------------
        # Speaking scene
        # --------------------------------------------------

        if item.has_dialogue:

            print("DIALOGUE:")
            print(scene.dialogue)

            print()

            print(
                "Speech duration:",
                f"{item.speech_duration:.2f}",
                "seconds",
            )

            print()

            print("AUDIO FILE:")

            if item.audio_path:

                print(
                    item.audio_path.resolve()
                )

            else:

                print(
                    "[Missing audio file]"
                )

        # --------------------------------------------------
        # Silent scene
        # --------------------------------------------------

        else:

            print("DIALOGUE:")
            print("[No dialogue]")

            print()

            print(
                "Speech duration: 0 seconds"
            )

        print()

    # ======================================================
    # STEP 4 - SELECT SCENES FOR TEST
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
            "No scene selected for generation."
        )

    print()
    print("=" * 70)
    print("TEST CONFIGURATION")
    print("=" * 70)
    print()

    print(
        "Scenes selected:",
        len(scenes_to_generate),
    )

    print(
        "Keep audio files:",
        KEEP_AUDIO_FILES,
    )

    print()

    # ======================================================
    # STEP 5 - DISPLAY EXACT AGNES PROMPT
    # ======================================================

    print("=" * 70)
    print("AGNES PROMPT DIAGNOSTIC")
    print("=" * 70)
    print()

    for item in scenes_to_generate:

        scene = item.scene

        speaking = (
            item.has_dialogue
        )

        agnes_prompt = (
            pipeline.build_scene_prompt(
                plan=final_plan,
                scene=scene,
                speaking=speaking,
            )
        )

        print(
            f"SCENE {scene.number}"
        )

        print(
            f"Speaking: {speaking}"
        )

        print()

        if speaking:

            print(
                "EXACT FRENCH DIALOGUE:"
            )

            print(
                scene.dialogue
            )

            print()

            if item.audio_path:

                print(
                    "REFERENCE AUDIO:"
                )

                print(
                    item.audio_path.resolve()
                )

                print()

        print(
            "PROMPT SENT TO AGNES:"
        )

        print()
        print(agnes_prompt)

        print()
        print("-" * 70)
        print()

    # ======================================================
    # STEP 6 - GENERATE VIDEO
    # ======================================================

    print("=" * 70)
    print("GENERATING VIDEO SCENES")
    print("=" * 70)
    print()

    print(
        f"Scenes to generate: "
        f"{len(scenes_to_generate)}"
    )

    print()

    generated = (
        pipeline.generate_scenes(
            plan=final_plan,
            prepared_scenes=(
                scenes_to_generate
            ),
            aspect_ratio="9:16",
            progress_callback=(
                show_progress
            ),
        )
    )

    # ======================================================
    # STEP 7 - DISPLAY RESULTS
    # ======================================================

    print()
    print("=" * 70)
    print("GENERATION COMPLETED")
    print("=" * 70)
    print()

    for generated_scene in generated:

        scene = (
            generated_scene.scene
        )

        print(
            f"SCENE {scene.number}"
        )

        print()

        print("VIDEO FILE:")

        print(
            generated_scene
            .video_path
            .resolve()
        )

        print()

        print("AGNES TASK ID:")

        print(
            generated_scene.task_id
        )

        print()

    # ======================================================
    # STEP 8 - DIAGNOSTIC COMPARISON
    # ======================================================

    print("=" * 70)
    print("FILES TO COMPARE")
    print("=" * 70)
    print()

    for item in scenes_to_generate:

        if not item.has_dialogue:
            continue

        print(
            f"SCENE {item.scene.number}"
        )

        print()

        print(
            "Expected dialogue:"
        )

        print(
            item.scene.dialogue
        )

        print()

        print(
            "Original Edge TTS audio:"
        )

        if item.audio_path:

            print(
                item.audio_path.resolve()
            )

        else:

            print(
                "[Missing audio]"
            )

        print()

        matching_video = next(
            (
                generated_scene
                for generated_scene
                in generated
                if (
                    generated_scene
                    .scene
                    .number
                    ==
                    item.scene.number
                )
            ),
            None,
        )

        print(
            "Agnes generated video:"
        )

        if matching_video:

            print(
                matching_video
                .video_path
                .resolve()
            )

        else:

            print(
                "[Missing video]"
            )

        print()

        print("-" * 70)
        print()

    print("=" * 70)
    print("DIAGNOSTIC INSTRUCTIONS")
    print("=" * 70)
    print()

    print(
        "1. Open the original MP3 file."
    )

    print(
        "2. Check whether the French sentence "
        "is clear and correct."
    )

    print(
        "3. Open the generated MP4."
    )

    print(
        "4. Compare the speech in the MP4 "
        "with the original MP3."
    )

    print()

    if KEEP_AUDIO_FILES:

        print(
            "The MP3 files have been kept "
            "for comparison."
        )

    print()


# ==========================================================
# ERRORS
# ==========================================================


except ScenePlannerError as exc:

    print()
    print("=" * 70)
    print("SCENE PLANNER ERROR")
    print("=" * 70)
    print()

    print(exc)


except VideoPipelineError as exc:

    print()
    print("=" * 70)
    print("VIDEO PIPELINE ERROR")
    print("=" * 70)
    print()

    print(exc)


except KeyboardInterrupt:

    print()
    print("=" * 70)
    print("GENERATION INTERRUPTED")
    print("=" * 70)
    print()


except Exception as exc:

    print()
    print("=" * 70)
    print("UNEXPECTED ERROR")
    print("=" * 70)
    print()

    print(
        f"{type(exc).__name__}: {exc}"
    )


# ==========================================================
# CLEANUP
# ==========================================================


finally:

    if (
        prepared
        and not KEEP_AUDIO_FILES
    ):

        pipeline.cleanup_audio(
            prepared
        )

        print()
        print(
            "Temporary audio files deleted."
        )

    elif (
        prepared
        and KEEP_AUDIO_FILES
    ):

        print()
        print(
            "=" * 70
        )

        print(
            "AUDIO FILES KEPT FOR DIAGNOSTIC"
        )

        print(
            "=" * 70
        )

        print()

        for item in prepared:

            if (
                item.audio_path
                and item.audio_path.exists()
            ):

                print(
                    item.audio_path.resolve()
                )

        print()