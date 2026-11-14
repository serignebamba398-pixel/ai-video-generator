from __future__ import annotations

from pathlib import Path

from src.config import (
    OUTPUT_DIR,
)

from src.job_manager import (
    JobManager,
)

from src.post_production import (
    PostProductionEngine,
    PostProductionError,
)

from src.post_production_planner import (
    PostProductionPlanner,
    PostProductionPlannerError,
)


# ==========================================================
# SETTINGS
# ==========================================================


JOB_ID = "taxi_refs_v1"


# ==========================================================
# PROJECT
# ==========================================================


PROJECT_DIR = (
    Path(__file__)
    .resolve()
    .parent
)


BACKGROUND_MUSIC = (
    PROJECT_DIR
    / "assets"
    / "music"
    / "background.mp3"
)


# ==========================================================
# MAIN
# ==========================================================


def main() -> None:

    job = (
        JobManager(
            base_dir=(
                OUTPUT_DIR
            ),
            job_id=(
                JOB_ID
            ),
        )
    )

    # ======================================================
    # STORYBOARD
    # ======================================================

    if not job.has_plan():

        raise RuntimeError(
            "No compatible storyboard "
            "was found for this job."
        )

    video_plan = (
        job.load_plan()
    )

    # ======================================================
    # ORIGINAL USER PROMPT
    # ======================================================

    source_prompt_path = (
        job.job_dir
        / "source_prompt.txt"
    )

    if not (
        source_prompt_path.exists()
        and source_prompt_path.is_file()
    ):

        raise RuntimeError(
            "source_prompt.txt is missing.\n\n"
            "The original user prompt must be "
            "saved with every production job so "
            "post-production can verify exact "
            "text and numbers safely."
        )

    source_prompt = (
        source_prompt_path
        .read_text(
            encoding="utf-8"
        )
        .strip()
    )

    if not source_prompt:

        raise RuntimeError(
            "source_prompt.txt is empty."
        )

    # ======================================================
    # SOURCE VIDEO
    # ======================================================

    source_video = (
        job.job_dir
        / "final_video.mp4"
    )

    if not source_video.exists():

        raise RuntimeError(
            "final_video.mp4 does not exist."
        )

    # ======================================================
    # POST-PRODUCTION PLAN
    # ======================================================

    post_plan_path = (
        job.job_dir
        / "post_production_plan.json"
    )

    planner = (
        PostProductionPlanner()
    )

    post_plan = None

    if post_plan_path.exists():

        try:

            post_plan = (
                planner.load(
                    post_plan_path
                )
            )

            print()

            print(
                "Compatible post-production "
                "plan found."
            )

        except PostProductionPlannerError:

            print()

            print(
                "Old or incompatible "
                "post-production plan detected."
            )

            print(
                "A new verified plan "
                "will be generated."
            )

            post_plan = None

    if post_plan is None:

        print()

        print(
            "Creating verified "
            "post-production plan..."
        )

        post_plan = (
            planner.create_plan(
                video_plan=(
                    video_plan
                ),
                source_prompt=(
                    source_prompt
                ),
            )
        )

        planner.save(
            post_plan,
            post_plan_path,
        )

    # ======================================================
    # DISPLAY PLAN
    # ======================================================

    print()

    print(
        "=" * 72
    )

    print(
        "VERIFIED POST-PRODUCTION PLAN"
    )

    print(
        "=" * 72
    )

    print()

    if not post_plan.overlays:

        print(
            "No verified exact overlay "
            "will be rendered."
        )

        print()

    else:

        for overlay in (
            post_plan.overlays
        ):

            print(
                f"Scene "
                f"{overlay.scene_number}"
            )

            print(
                f'Mode: '
                f'{overlay.mode}'
            )

            print(
                f'Text: '
                f'"{overlay.text}"'
            )

            print(
                "Verified source:"
            )

            print(
                f'"{overlay.source_quote}"'
            )

            print(
                "Local timing: "
                f"{overlay.start:.2f}s "
                "→ "
                f"{overlay.end:.2f}s"
            )

            print(
                f"Position: "
                f"{overlay.position}"
            )

            print(
                f"Style: "
                f"{overlay.style}"
            )

            if overlay.purpose:

                print(
                    f"Purpose: "
                    f"{overlay.purpose}"
                )

            print()

    # ======================================================
    # UNRESOLVED
    # ======================================================

    if (
        post_plan
        .unresolved_exact_graphics
    ):

        print(
            "=" * 72
        )

        print(
            "UNRESOLVED EXACT GRAPHICS"
        )

        print(
            "=" * 72
        )

        print()

        for item in (
            post_plan
            .unresolved_exact_graphics
        ):

            if (
                item.scene_number
                is not None
            ):

                print(
                    f"Scene: "
                    f"{item.scene_number}"
                )

            else:

                print(
                    "Scene: unspecified"
                )

            print(
                f"Purpose: "
                f"{item.purpose}"
            )

            print(
                f"Reason: "
                f"{item.reason}"
            )

            print()

        print(
            "These elements are NOT "
            "automatically invented or rendered."
        )

        print()

    # ======================================================
    # NOTES
    # ======================================================

    if post_plan.notes:

        print(
            "Planner notes:"
        )

        print(
            post_plan.notes
        )

        print()

    # ======================================================
    # OPTIONAL MUSIC
    # ======================================================

    music_path = None

    if (
        BACKGROUND_MUSIC.exists()
        and BACKGROUND_MUSIC.is_file()
    ):

        music_path = (
            BACKGROUND_MUSIC
        )

    # ======================================================
    # MASTER
    # ======================================================

    engine = (
        PostProductionEngine()
    )

    output_path = (
        job.job_dir
        / "final_master.mp4"
    )

    engine.master(
        source_video=(
            source_video
        ),

        output_path=(
            output_path
        ),

        video_plan=(
            video_plan
        ),

        post_plan=(
            post_plan
        ),

        music_path=(
            music_path
        ),

        working_directory=(
            job.job_dir
            / "_post"
        ),

        cleanup=True,

        # Important:
        # until we implement object tracking,
        # diegetic text must NOT become a floating
        # editorial overlay.
        allow_diegetic_proxy=False,
    )


# ==========================================================
# ENTRY POINT
# ==========================================================


if __name__ == "__main__":

    try:

        main()

    except PostProductionPlannerError as exc:

        print()

        print(
            "POST-PRODUCTION "
            "PLANNING ERROR"
        )

        print(
            exc
        )

    except PostProductionError as exc:

        print()

        print(
            "POST-PRODUCTION ERROR"
        )

        print(
            exc
        )

    except Exception as exc:

        print()

        print(
            "UNEXPECTED ERROR"
        )

        print(
            f"{type(exc).__name__}: "
            f"{exc}"
        )