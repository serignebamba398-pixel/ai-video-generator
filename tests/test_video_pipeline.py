from src.config import (
    AUDIO_DIR,
    OUTPUT_DIR,
)

from src.scene_planner import (
    ScenePlanner,
)

from src.video_pipeline import (
    VideoPipeline,
    VideoPipelineError,
)


prompt = """
Create a funny 60-second vertical video about a
French man doing his weekly grocery shopping.

At first he thinks he will spend very little money,
but each aisle surprises him with higher prices.

He reacts humorously and speaks French.

The video should look realistic and cinematic,
with one consistent main character throughout.
"""


planner = ScenePlanner()

pipeline = VideoPipeline(
    audio_dir=AUDIO_DIR,
    video_dir=OUTPUT_DIR,
    voice="fr-FR-HenriNeural",
    speech_rate="+0%",
)


try:

    print()
    print("Creating scene plan...")

    plan = planner.create_plan(
        user_prompt=prompt,
        target_duration=60,
    )

    print(
        "Initial duration:",
        plan.total_duration,
    )

    print()
    print(
        "Generating and analyzing dialogue audio..."
    )

    final_plan, prepared = (
        pipeline.prepare_plan(
            plan
        )
    )

    print()
    print(
        "FINAL DURATION:",
        final_plan.total_duration,
        "seconds",
    )

    print()

    for item in prepared:

        scene = item.scene

        print(
            "=" * 60
        )

        print(
            f"SCENE {scene.number}"
        )

        print(
            "Final video duration:",
            scene.duration,
            "seconds",
        )

        if item.audio_path:

            print(
                "Speech duration:",
                f"{item.speech_duration:.2f}",
                "seconds",
            )

            print(
                "Dialogue:",
                scene.dialogue,
            )

        else:

            print(
                "Speech: none"
            )

        print()

finally:

    if "prepared" in locals():

        pipeline.cleanup_audio(
            prepared
        )