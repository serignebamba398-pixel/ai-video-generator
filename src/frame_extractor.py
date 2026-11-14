from __future__ import annotations

import shutil
import subprocess

from pathlib import Path


# ==========================================================
# PROJECT PATHS
# ==========================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

LOCAL_FFMPEG_DIR = (
    BASE_DIR
    / "tools"
    / "ffmpeg"
    / "bin"
)

LOCAL_FFMPEG = (
    LOCAL_FFMPEG_DIR
    / "ffmpeg.exe"
)

LOCAL_FFPROBE = (
    LOCAL_FFMPEG_DIR
    / "ffprobe.exe"
)


# ==========================================================
# EXCEPTION
# ==========================================================


class FrameExtractionError(Exception):
    pass


# ==========================================================
# FRAME EXTRACTOR
# ==========================================================


class FrameExtractor:
    """
    Extract a useful continuity frame near the end of a
    generated video.

    Important:
    this intentionally does NOT use the absolute final frame.

    AI-generated video clips often contain, near the end:

    - fades
    - empty frames
    - characters leaving the composition
    - transition artefacts
    - unstable geometry

    Instead, this extractor selects a frame slightly before
    the end of the clip.

    The offset adapts to video duration.
    """

    # ======================================================
    # CONTINUITY FRAME TIMING
    # ======================================================

    # Percentage of the video duration to move backwards.
    CONTINUITY_OFFSET_RATIO = 0.12

    # Never take a frame closer than this to the end.
    MIN_CONTINUITY_OFFSET = 0.60

    # For ordinary short AI clips, moving more than ~1 s
    # backwards is usually unnecessary.
    MAX_CONTINUITY_OFFSET = 1.00

    def __init__(
        self,
        ffmpeg_path: str | Path | None = None,
        ffprobe_path: str | Path | None = None,
    ) -> None:

        self.ffmpeg = (
            self._resolve_ffmpeg(
                custom_path=ffmpeg_path
            )
        )

        self.ffprobe = (
            self._resolve_ffprobe(
                custom_path=ffprobe_path
            )
        )

        print()

        print(
            "FFmpeg configuration"
        )

        print(
            f"ffmpeg: {self.ffmpeg}"
        )

        print(
            f"ffprobe: {self.ffprobe}"
        )

        print()

    # ======================================================
    # RESOLVE FFMPEG
    # ======================================================

    @staticmethod
    def _resolve_ffmpeg(
        custom_path: (
            str
            | Path
            | None
        ),
    ) -> str:

        if custom_path is not None:

            path = (
                Path(custom_path)
                .expanduser()
            )

            if (
                path.exists()
                and path.is_file()
            ):

                return str(
                    path.resolve()
                )

            raise FrameExtractionError(
                "The custom ffmpeg path "
                "does not exist:\n"
                f"{path}"
            )

        # ----------------------------------------------
        # PROJECT-LOCAL VERSION
        # ----------------------------------------------

        if (
            LOCAL_FFMPEG.exists()
            and LOCAL_FFMPEG.is_file()
        ):

            return str(
                LOCAL_FFMPEG.resolve()
            )

        # ----------------------------------------------
        # SYSTEM PATH FALLBACK
        # ----------------------------------------------

        system_ffmpeg = (
            shutil.which(
                "ffmpeg"
            )
        )

        if system_ffmpeg:

            return system_ffmpeg

        raise FrameExtractionError(
            "FFmpeg was not found.\n\n"
            "Expected project path:\n"
            f"{LOCAL_FFMPEG}\n\n"
            "Expected structure:\n"
            "tools/ffmpeg/bin/ffmpeg.exe"
        )

    # ======================================================
    # RESOLVE FFPROBE
    # ======================================================

    @staticmethod
    def _resolve_ffprobe(
        custom_path: (
            str
            | Path
            | None
        ),
    ) -> str:

        if custom_path is not None:

            path = (
                Path(custom_path)
                .expanduser()
            )

            if (
                path.exists()
                and path.is_file()
            ):

                return str(
                    path.resolve()
                )

            raise FrameExtractionError(
                "The custom ffprobe path "
                "does not exist:\n"
                f"{path}"
            )

        # ----------------------------------------------
        # PROJECT-LOCAL VERSION
        # ----------------------------------------------

        if (
            LOCAL_FFPROBE.exists()
            and LOCAL_FFPROBE.is_file()
        ):

            return str(
                LOCAL_FFPROBE.resolve()
            )

        # ----------------------------------------------
        # SYSTEM PATH FALLBACK
        # ----------------------------------------------

        system_ffprobe = (
            shutil.which(
                "ffprobe"
            )
        )

        if system_ffprobe:

            return system_ffprobe

        raise FrameExtractionError(
            "ffprobe was not found.\n\n"
            "Expected project path:\n"
            f"{LOCAL_FFPROBE}\n\n"
            "Expected structure:\n"
            "tools/ffmpeg/bin/ffprobe.exe"
        )

    # ======================================================
    # CALCULATE CONTINUITY OFFSET
    # ======================================================

    @classmethod
    def _calculate_continuity_offset(
        cls,
        duration: float,
    ) -> float:
        """
        Examples:

        4 s  -> 0.60 s before end
        6 s  -> 0.72 s before end
        8 s  -> 0.96 s before end
        10 s -> 1.00 s before end
        12 s -> 1.00 s before end
        """

        dynamic_offset = (
            duration
            * cls.CONTINUITY_OFFSET_RATIO
        )

        return max(
            cls.MIN_CONTINUITY_OFFSET,
            min(
                cls.MAX_CONTINUITY_OFFSET,
                dynamic_offset,
            ),
        )

    # ======================================================
    # EXTRACT CONTINUITY FRAME
    # ======================================================

    def extract_last_frame(
        self,
        video_path: Path,
        output_path: Path,
    ) -> Path:
        """
        Compatibility name retained for VideoPipeline.

        Despite the method name, this extracts a CONTINUITY
        frame slightly before the actual final frame.
        """

        video_path = Path(
            video_path
        )

        output_path = Path(
            output_path
        )

        # ----------------------------------------------
        # VALIDATE VIDEO
        # ----------------------------------------------

        if not (
            video_path.exists()
            and video_path.is_file()
            and video_path.stat().st_size > 0
        ):

            raise FrameExtractionError(
                "Invalid input video:\n"
                f"{video_path}"
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ----------------------------------------------
        # READ ACTUAL VIDEO DURATION
        # ----------------------------------------------

        duration = (
            self._get_video_duration(
                video_path
            )
        )

        offset = (
            self._calculate_continuity_offset(
                duration
            )
        )

        target_time = max(
            0.0,
            duration - offset,
        )

        print()

        print(
            "Continuity frame extraction"
        )

        print(
            f"Video: {video_path.name}"
        )

        print(
            f"Actual duration: "
            f"{duration:.3f}s"
        )

        print(
            f"Safety offset: "
            f"{offset:.3f}s"
        )

        print(
            f"Selected timestamp: "
            f"{target_time:.3f}s"
        )

        print()

        temporary_path = (
            output_path.parent
            / (
                output_path.stem
                + ".tmp.jpg"
            )
        )

        self._safe_delete(
            temporary_path
        )

        # ==================================================
        # PRIMARY EXTRACTION
        #
        # -ss is placed AFTER -i.
        #
        # This is slower than keyframe seeking, but these
        # videos are short and this produces a more accurate
        # timestamp.
        # ==================================================

        command = [
            self.ffmpeg,

            "-hide_banner",

            "-loglevel",
            "error",

            "-y",

            "-i",
            str(
                video_path
            ),

            "-ss",
            f"{target_time:.3f}",

            "-frames:v",
            "1",

            "-q:v",
            "2",

            str(
                temporary_path
            ),
        ]

        result = (
            self._run_command(
                command=command,
                timeout=120,
            )
        )

        # ==================================================
        # FALLBACK
        #
        # If timestamp extraction fails, use -sseof with the
        # same adaptive offset.
        # ==================================================

        if not self._is_valid_image(
            temporary_path
        ):

            self._safe_delete(
                temporary_path
            )

            fallback_command = [
                self.ffmpeg,

                "-hide_banner",

                "-loglevel",
                "error",

                "-y",

                "-sseof",
                f"-{offset:.3f}",

                "-i",
                str(
                    video_path
                ),

                "-frames:v",
                "1",

                "-q:v",
                "2",

                str(
                    temporary_path
                ),
            ]

            result = (
                self._run_command(
                    command=(
                        fallback_command
                    ),
                    timeout=120,
                )
            )

        # ==================================================
        # VALIDATE EXTRACTED IMAGE
        # ==================================================

        if not self._is_valid_image(
            temporary_path
        ):

            raise FrameExtractionError(
                "Unable to extract continuity "
                "frame from:\n"
                f"{video_path}\n\n"
                "FFmpeg error:\n"
                f"{result.stderr}"
            )

        # ==================================================
        # ATOMIC FINALIZATION
        # ==================================================

        try:

            if output_path.exists():

                output_path.unlink()

            temporary_path.replace(
                output_path
            )

        except OSError as exc:

            raise FrameExtractionError(
                "Unable to finalize continuity "
                "frame:\n"
                f"{output_path}\n\n"
                f"{exc}"
            ) from exc

        if not self._is_valid_image(
            output_path
        ):

            raise FrameExtractionError(
                "Continuity frame was created "
                "but appears invalid:\n"
                f"{output_path}"
            )

        print(
            "Continuity frame ready:"
        )

        print(
            output_path
        )

        print()

        return output_path

    # ======================================================
    # VIDEO DURATION
    # ======================================================

    def _get_video_duration(
        self,
        video_path: Path,
    ) -> float:

        command = [
            self.ffprobe,

            "-v",
            "error",

            "-show_entries",
            "format=duration",

            "-of",
            (
                "default="
                "noprint_wrappers=1:"
                "nokey=1"
            ),

            str(
                video_path
            ),
        ]

        result = (
            self._run_command(
                command=command,
                timeout=60,
            )
        )

        if (
            result.returncode
            != 0
        ):

            raise FrameExtractionError(
                "Unable to determine "
                "video duration.\n\n"
                "ffprobe error:\n"
                f"{result.stderr}"
            )

        raw_duration = (
            result.stdout
            or ""
        ).strip()

        try:

            duration = float(
                raw_duration
            )

        except ValueError as exc:

            raise FrameExtractionError(
                "ffprobe returned an "
                "invalid duration:\n"
                f"{raw_duration}"
            ) from exc

        if duration <= 0:

            raise FrameExtractionError(
                "Video duration is invalid:\n"
                f"{duration}"
            )

        return duration

    # ======================================================
    # RUN COMMAND
    # ======================================================

    @staticmethod
    def _run_command(
        command: list[str],
        timeout: int,
    ) -> subprocess.CompletedProcess:

        try:

            return subprocess.run(
                command,
                stdout=(
                    subprocess.PIPE
                ),
                stderr=(
                    subprocess.PIPE
                ),
                text=True,
                timeout=timeout,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if hasattr(
                        subprocess,
                        "CREATE_NO_WINDOW",
                    )
                    else 0
                ),
            )

        except subprocess.TimeoutExpired as exc:

            raise FrameExtractionError(
                "FFmpeg command timed out."
            ) from exc

        except OSError as exc:

            raise FrameExtractionError(
                "Unable to execute FFmpeg:\n"
                f"{exc}"
            ) from exc

    # ======================================================
    # IMAGE VALIDATION
    # ======================================================

    @staticmethod
    def _is_valid_image(
        path: Path,
    ) -> bool:

        try:

            return (
                path.exists()
                and path.is_file()
                and path.stat().st_size
                > 1000
            )

        except OSError:

            return False

    # ======================================================
    # SAFE DELETE
    # ======================================================

    @staticmethod
    def _safe_delete(
        path: Path,
    ) -> None:

        try:

            if path.exists():

                path.unlink()

        except OSError:

            pass