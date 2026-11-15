import os
from pathlib import Path

from dotenv import load_dotenv


# ==========================================================
# PATHS
# ==========================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

load_dotenv(
    BASE_DIR / ".env"
)


# ==========================================================
# AGNES API
# ==========================================================

STUDIO_INSTANCE = os.getenv("STUDIO_INSTANCE", "1")
if STUDIO_INSTANCE not in {"1", "2"}:
    raise RuntimeError("STUDIO_INSTANCE must be 1 or 2.")

AGNES_API_KEY_NAME = "AGNES_API_KEY2" if STUDIO_INSTANCE == "2" else "AGNES_API_KEY"
AGNES_API_KEY = os.getenv(AGNES_API_KEY_NAME)

if not AGNES_API_KEY:
    raise RuntimeError(
        f"{AGNES_API_KEY_NAME} is missing from the .env file."
    )


AGNES_BASE_URL = (
    "https://apihub.agnes-ai.com"
)

AGNES_MODEL = (
    "agnes-video-2.5-flash"
)

# Agnes Video 2.5 (non-Flash) : supporte les vidéos de référence (video-to-video)
AGNES_VIDEO2VIDEO_MODEL = (
    "agnes-video-2.5"
)

AGNES_TEXT_MODEL = (
    "agnes-3.0-flash"
)

AGNES_IMAGE_MODEL = (
    "agnes-image-2.5-flash"
)


# ==========================================================
# OUTPUT DIRECTORIES
# ==========================================================

# Both studios share projects and media; only the Agnes account is per instance.
DATA_DIR = BASE_DIR
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "videos"

AUDIO_DIR = (
    DATA_DIR / "audio"
)

REFERENCE_DIR = (
    DATA_DIR
    / "reference_images"
)


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

AUDIO_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

REFERENCE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)
