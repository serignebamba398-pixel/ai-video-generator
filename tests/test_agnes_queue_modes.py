from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from src.agnes_client import (
    AgnesAPIError,
    AgnesClient,
)

from src.config import (
    AUDIO_DIR,
    OUTPUT_DIR,
)

from src.voice_generator import (
    VoiceGenerator,
    VoiceGenerationError,
)


# ==========================================================
# CONFIGURATION
# ==========================================================

# Number of complete A/B rounds.
#
# 3 rounds = 6 submissions:
#
# Round 1:
#   reference -> text
#
# Round 2:
#   text -> reference
#
# Round 3:
#   reference -> text
#
ROUNDS = 3


# Agnes clip configuration.
SECONDS = 4
SIZE = "720P"
ASPECT_RATIO = "16:9"


# Delay between the two tests of one round.
#
# We do not want to fire two requests immediately,
# otherwise a possible rate limit could distort the test.
BETWEEN_REQUESTS_SECONDS = 70


# Delay between complete rounds.
BETWEEN_ROUNDS_SECONDS = 120


# We only want the FIRST Agnes answer.
#
# No automatic retries inside AgnesClient.
MAX_RETRIES = 1


# ==========================================================
# TEST FILES
# ==========================================================

TEST_DIR = (
    OUTPUT_DIR
    / "agnes_mode_test"
)

TEST_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


RESULT_PATH = (
    TEST_DIR
    / "agnes_mode_test_results.json"
)


REFERENCE_AUDIO_PATH = (
    AUDIO_DIR
    / "agnes_mode_test_reference.mp3"
)


# ==========================================================
# TEST PROMPTS
# ==========================================================

# Keep the visual situation nearly identical.
#
# The only fundamental difference is:
#
# TEXT:
#   normal text-to-video request
#
# REFERENCE:
#   same type of shot + reference audio


TEXT_PROMPT = """
Create a realistic cinematic 4-second video.

Medium close-up of a French man sitting inside a parked
car at night.

He looks calmly toward the camera.

Natural facial movement.

Very subtle head movement.

Realistic lighting.

Stable camera.

Full-screen composition.

No subtitles.

No captions.

No spoken dialogue.

No visible text.
""".strip()


REFERENCE_PROMPT = """
Create a realistic cinematic 4-second video.

Medium close-up of a French man sitting inside a parked
car at night.

He looks calmly toward the camera.

Natural facial movement.

Very subtle head movement.

Realistic lighting.

Stable camera.

Full-screen composition.

The man speaks using <Audio 1>.

Use <Audio 1> as the exact spoken performance.

Synchronize his lips naturally with <Audio 1>.

No additional dialogue.

No subtitles.

No captions.

No visible text.
""".strip()


REFERENCE_TEXT = "Test."


# ==========================================================
# UTILITIES
# ==========================================================


def separator() -> None:
    print()
    print(
        "=" * 72
    )
    print()


def classify_error(
    exc: AgnesAPIError,
) -> str:

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

    message = str(
        exc
    ).lower()

    if (
        error_code
        == "video_queue_full"
        or "video_queue_full"
        in message
        or "video queue is full"
        in message
    ):

        return "QUEUE_FULL"

    if (
        status_code == 429
        or "rate limit"
        in message
        or "too many requests"
        in message
    ):

        return "RATE_LIMIT"

    if (
        status_code == 401
    ):

        return "AUTHENTICATION"

    if (
        status_code == 403
    ):

        return "AUTHORIZATION"

    if (
        "quota"
        in message
        or "credit"
        in message
        or "balance"
        in message
        or "usage limit"
        in message
    ):

        return "QUOTA"

    if (
        status_code
        in {
            500,
            502,
            503,
            504,
        }
    ):

        return "SERVER_ERROR"

    return "OTHER_ERROR"


def save_results(
    results: list[dict],
) -> None:

    RESULT_PATH.write_text(
        json.dumps(
            results,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ==========================================================
# REFERENCE AUDIO
# ==========================================================


def prepare_reference_audio() -> None:

    print(
        "Preparing reference audio..."
    )

    voice = VoiceGenerator(
        voice="fr-FR-HenriNeural",
        rate="+0%",
        volume="+0%",
        pitch="+0Hz",
    )

    try:

        voice.generate(
            text=REFERENCE_TEXT,
            output_path=(
                REFERENCE_AUDIO_PATH
            ),
        )

    except VoiceGenerationError as exc:

        raise RuntimeError(
            "Unable to create reference audio: "
            f"{exc}"
        ) from exc

    if (
        not REFERENCE_AUDIO_PATH.exists()
        or REFERENCE_AUDIO_PATH.stat().st_size
        <= 0
    ):

        raise RuntimeError(
            "Reference audio was not created."
        )

    print(
        "Reference audio:"
    )

    print(
        REFERENCE_AUDIO_PATH.resolve()
    )


# ==========================================================
# SINGLE TEXT TEST
# ==========================================================


def test_text_mode(
    client: AgnesClient,
) -> dict:

    print(
        "MODE: TEXT"
    )

    print(
        "Submitting one request..."
    )

    started_at = (
        time.monotonic()
    )

    timestamp = (
        datetime.now()
        .isoformat(
            timespec="seconds"
        )
    )

    try:

        video_id = (
            client.create_video(
                prompt=TEXT_PROMPT,
                seconds=SECONDS,
                size=SIZE,
                aspect_ratio=(
                    ASPECT_RATIO
                ),
                max_retries=(
                    MAX_RETRIES
                ),
                retry_delay=1,
            )
        )

        elapsed = (
            time.monotonic()
            - started_at
        )

        print(
            "RESULT: ACCEPTED"
        )

        print(
            f"Video ID: {video_id}"
        )

        print(
            f"Response time: "
            f"{elapsed:.2f}s"
        )

        return {
            "timestamp": timestamp,
            "mode": "text",
            "result": "accepted",
            "video_id": video_id,
            "elapsed_seconds": round(
                elapsed,
                2,
            ),
            "http_status": None,
            "error_code": None,
            "error": None,
        }

    except AgnesAPIError as exc:

        elapsed = (
            time.monotonic()
            - started_at
        )

        classification = (
            classify_error(
                exc
            )
        )

        status_code = getattr(
            exc,
            "status_code",
            None,
        )

        error_code = getattr(
            exc,
            "error_code",
            None,
        )

        print(
            f"RESULT: {classification}"
        )

        print(
            f"HTTP status: "
            f"{status_code}"
        )

        print(
            f"Agnes error code: "
            f"{error_code}"
        )

        print(
            "Original error:"
        )

        print(
            str(exc)
        )

        return {
            "timestamp": timestamp,
            "mode": "text",
            "result": (
                classification
            ),
            "video_id": None,
            "elapsed_seconds": round(
                elapsed,
                2,
            ),
            "http_status": (
                status_code
            ),
            "error_code": (
                error_code
            ),
            "error": str(
                exc
            ),
        }


# ==========================================================
# SINGLE REFERENCE TEST
# ==========================================================


def test_reference_mode(
    client: AgnesClient,
) -> dict:

    print(
        "MODE: REFERENCE"
    )

    print(
        "Submitting one request..."
    )

    started_at = (
        time.monotonic()
    )

    timestamp = (
        datetime.now()
        .isoformat(
            timespec="seconds"
        )
    )

    try:

        video_id = (
            client
            .create_reference_video(
                prompt=(
                    REFERENCE_PROMPT
                ),
                audio_path=(
                    REFERENCE_AUDIO_PATH
                ),
                seconds=SECONDS,
                size=SIZE,
                aspect_ratio=(
                    ASPECT_RATIO
                ),
                max_retries=(
                    MAX_RETRIES
                ),
                retry_delay=1,
            )
        )

        elapsed = (
            time.monotonic()
            - started_at
        )

        print(
            "RESULT: ACCEPTED"
        )

        print(
            f"Video ID: {video_id}"
        )

        print(
            f"Response time: "
            f"{elapsed:.2f}s"
        )

        return {
            "timestamp": timestamp,
            "mode": "reference",
            "result": "accepted",
            "video_id": video_id,
            "elapsed_seconds": round(
                elapsed,
                2,
            ),
            "http_status": None,
            "error_code": None,
            "error": None,
        }

    except AgnesAPIError as exc:

        elapsed = (
            time.monotonic()
            - started_at
        )

        classification = (
            classify_error(
                exc
            )
        )

        status_code = getattr(
            exc,
            "status_code",
            None,
        )

        error_code = getattr(
            exc,
            "error_code",
            None,
        )

        print(
            f"RESULT: {classification}"
        )

        print(
            f"HTTP status: "
            f"{status_code}"
        )

        print(
            f"Agnes error code: "
            f"{error_code}"
        )

        print(
            "Original error:"
        )

        print(
            str(exc)
        )

        return {
            "timestamp": timestamp,
            "mode": "reference",
            "result": (
                classification
            ),
            "video_id": None,
            "elapsed_seconds": round(
                elapsed,
                2,
            ),
            "http_status": (
                status_code
            ),
            "error_code": (
                error_code
            ),
            "error": str(
                exc
            ),
        }


# ==========================================================
# SUMMARY
# ==========================================================


def display_summary(
    results: list[dict],
) -> None:

    separator()

    print(
        "FINAL RESULTS"
    )

    separator()

    text_results = [
        result
        for result
        in results
        if result[
            "mode"
        ]
        == "text"
    ]

    reference_results = [
        result
        for result
        in results
        if result[
            "mode"
        ]
        == "reference"
    ]

    text_accepted = sum(
        1
        for result
        in text_results
        if result[
            "result"
        ]
        == "accepted"
    )

    reference_accepted = sum(
        1
        for result
        in reference_results
        if result[
            "result"
        ]
        == "accepted"
    )

    text_queue_full = sum(
        1
        for result
        in text_results
        if result[
            "result"
        ]
        == "QUEUE_FULL"
    )

    reference_queue_full = sum(
        1
        for result
        in reference_results
        if result[
            "result"
        ]
        == "QUEUE_FULL"
    )

    print(
        "TEXT MODE"
    )

    print(
        f"Accepted: "
        f"{text_accepted}/"
        f"{len(text_results)}"
    )

    print(
        f"Queue full: "
        f"{text_queue_full}/"
        f"{len(text_results)}"
    )

    print()

    print(
        "REFERENCE MODE"
    )

    print(
        f"Accepted: "
        f"{reference_accepted}/"
        f"{len(reference_results)}"
    )

    print(
        f"Queue full: "
        f"{reference_queue_full}/"
        f"{len(reference_results)}"
    )

    separator()

    # ======================================================
    # BASIC INTERPRETATION
    # ======================================================

    print(
        "INTERPRETATION"
    )

    print()

    if (
        text_accepted == 0
        and reference_accepted == 0
    ):

        print(
            "Both modes were rejected."
        )

        print(
            "This strongly supports a globally "
            "saturated Agnes video service."
        )

    elif (
        reference_accepted > 0
        and text_accepted == 0
    ):

        print(
            "REFERENCE succeeded at least once, "
            "while TEXT never succeeded."
        )

        print(
            "This is evidence that the two modes "
            "may not have identical capacity or "
            "queue behavior."
        )

        print(
            "More rounds would strengthen the conclusion."
        )

    elif (
        text_accepted > 0
        and reference_accepted == 0
    ):

        print(
            "TEXT succeeded at least once, "
            "while REFERENCE never succeeded."
        )

        print(
            "This suggests a possible mode-specific "
            "difference in the opposite direction."
        )

    else:

        print(
            "Both TEXT and REFERENCE were accepted "
            "at least once."
        )

        print(
            "Therefore TEXT mode itself is not broken."
        )

        print(
            "Queue saturation / timing is the more "
            "likely explanation."
        )

    print()

    print(
        "Detailed JSON:"
    )

    print(
        RESULT_PATH.resolve()
    )


# ==========================================================
# MAIN
# ==========================================================


def main() -> None:

    separator()

    print(
        "AGNES TEXT vs REFERENCE QUEUE TEST"
    )

    separator()

    print(
        f"Rounds: {ROUNDS}"
    )

    print(
        f"Duration: {SECONDS}s"
    )

    print(
        f"Size: {SIZE}"
    )

    print(
        f"Aspect ratio: "
        f"{ASPECT_RATIO}"
    )

    print(
        "Retries per request: 1"
    )

    print()

    print(
        "IMPORTANT:"
    )

    print(
        "This test intentionally disables "
        "automatic submission retries."
    )

    print(
        "We want the first raw Agnes response "
        "for every request."
    )

    separator()

    prepare_reference_audio()

    client = (
        AgnesClient()
    )

    results: list[
        dict
    ] = []

    # ======================================================
    # RUN ROUNDS
    # ======================================================

    for round_number in range(
        1,
        ROUNDS + 1,
    ):

        separator()

        print(
            f"ROUND "
            f"{round_number}/"
            f"{ROUNDS}"
        )

        # Alternate the first mode to prevent a systematic
        # "first request gets the free slot" bias.

        if (
            round_number
            % 2
            == 1
        ):

            order = [
                "reference",
                "text",
            ]

        else:

            order = [
                "text",
                "reference",
            ]

        print(
            "Order:",
            " -> ".join(
                order
            ),
        )

        separator()

        for test_index, mode in enumerate(
            order
        ):

            if (
                mode
                == "text"
            ):

                result = (
                    test_text_mode(
                        client
                    )
                )

            else:

                result = (
                    test_reference_mode(
                        client
                    )
                )

            result[
                "round"
            ] = round_number

            result[
                "position_in_round"
            ] = (
                test_index
                + 1
            )

            results.append(
                result
            )

            save_results(
                results
            )

            # ----------------------------------------------
            # WAIT BEFORE SECOND MODE
            # ----------------------------------------------

            if (
                test_index
                < len(order) - 1
            ):

                print()

                print(
                    "Waiting "
                    f"{BETWEEN_REQUESTS_SECONDS}s "
                    "before testing the other mode..."
                )

                time.sleep(
                    BETWEEN_REQUESTS_SECONDS
                )

        # ----------------------------------------------
        # WAIT BEFORE NEXT ROUND
        # ----------------------------------------------

        if (
            round_number
            < ROUNDS
        ):

            print()

            print(
                "Round complete."
            )

            print(
                "Waiting "
                f"{BETWEEN_ROUNDS_SECONDS}s "
                "before the next round..."
            )

            time.sleep(
                BETWEEN_ROUNDS_SECONDS
            )

    # ======================================================
    # SUMMARY
    # ======================================================

    display_summary(
        results
    )


# ==========================================================
# ENTRY POINT
# ==========================================================


if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()

        print(
            "Test interrupted by user."
        )

        print(
            "Partial results are preserved in:"
        )

        print(
            RESULT_PATH.resolve()
        )

    except Exception as exc:

        print()

        print(
            "=" * 72
        )

        print(
            "TEST ERROR"
        )

        print(
            "=" * 72
        )

        print()

        print(
            f"{type(exc).__name__}: "
            f"{exc}"
        )