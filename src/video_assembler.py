from __future__ import annotations

import json
import shutil
import subprocess

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.scene_planner import VideoPlan
from src.video_transitions import dissolve_filter, transition_timing


# ==========================================================
# PROJECT PATHS
# ==========================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

LOCAL_FFMPEG = (
    BASE_DIR
    / "tools"
    / "ffmpeg"
    / "bin"
    / "ffmpeg.exe"
)

LOCAL_FFPROBE = (
    BASE_DIR
    / "tools"
    / "ffmpeg"
    / "bin"
    / "ffprobe.exe"
)


# ==========================================================
# EXCEPTION
# ==========================================================


class VideoAssemblyError(Exception):
    pass


# ==========================================================
# DATA MODELS
# ==========================================================


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float
    width: int
    height: int
    has_audio: bool


@dataclass(frozen=True)
class AssemblyResult:
    output_path: Path
    duration: float
    width: int
    height: int
    scene_count: int


# ==========================================================
# VIDEO ASSEMBLER
# ==========================================================


class VideoAssembler:
    """
    Professional scene assembler.

    Every scene is first normalized so that all clips have:

    - identical resolution
    - identical frame rate
    - H.264 video
    - AAC stereo audio
    - 48 kHz audio
    - yuv420p pixel format
    - exact planned scene duration

    Missing audio is replaced with silence.

    Clips shorter than the storyboard duration are extended
    by freezing the final video frame and padding audio.

    Clips longer than the storyboard duration are trimmed.

    After normalization, all scenes are concatenated and the
    final output is validated.
    """

    def __init__(
        self,
        ffmpeg_path: str | Path | None = None,
        ffprobe_path: str | Path | None = None,
        fps: int = 24,
        video_crf: int = 18,
        video_preset: str = "medium",
        audio_bitrate: str = "192k",
        audio_sample_rate: int = 48000,
    ) -> None:

        self.ffmpeg = self._resolve_binary(
            custom_path=ffmpeg_path,
            local_path=LOCAL_FFMPEG,
            system_name="ffmpeg",
        )

        self.ffprobe = self._resolve_binary(
            custom_path=ffprobe_path,
            local_path=LOCAL_FFPROBE,
            system_name="ffprobe",
        )

        self.fps = int(
            fps
        )

        self.video_crf = int(
            video_crf
        )

        self.video_preset = (
            video_preset
        )

        self.audio_bitrate = (
            audio_bitrate
        )

        self.audio_sample_rate = int(
            audio_sample_rate
        )

    # ======================================================
    # RESOLVE BINARIES
    # ======================================================

    @staticmethod
    def _resolve_binary(
        custom_path: str | Path | None,
        local_path: Path,
        system_name: str,
    ) -> str:

        if custom_path is not None:

            path = Path(
                custom_path
            )

            if (
                path.exists()
                and path.is_file()
            ):

                return str(
                    path.resolve()
                )

            raise VideoAssemblyError(
                f"{system_name} not found at: "
                f"{path}"
            )

        if (
            local_path.exists()
            and local_path.is_file()
        ):

            return str(
                local_path.resolve()
            )

        system_path = (
            shutil.which(
                system_name
            )
        )

        if system_path:

            return system_path

        raise VideoAssemblyError(
            f"{system_name} was not found."
        )

    # ======================================================
    # RUN COMMAND
    # ======================================================

    @staticmethod
    def _run(
        command: list[str],
        timeout: int = 1800,
    ) -> subprocess.CompletedProcess:

        try:

            result = subprocess.run(
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

            raise VideoAssemblyError(
                "FFmpeg operation timed out."
            ) from exc

        except OSError as exc:

            raise VideoAssemblyError(
                "Unable to execute FFmpeg: "
                f"{exc}"
            ) from exc

        if result.returncode != 0:

            raise VideoAssemblyError(
                "FFmpeg operation failed.\n\n"
                f"{result.stderr}"
            )

        return result

    # ======================================================
    # PROBE MEDIA
    # ======================================================

    def probe(
        self,
        path: Path,
    ) -> MediaInfo:

        path = Path(
            path
        )

        if not (
            path.exists()
            and path.is_file()
            and path.stat().st_size > 0
        ):

            raise VideoAssemblyError(
                f"Invalid video: {path}"
            )

        command = [
            self.ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]

        result = self._run(
            command,
            timeout=60,
        )

        try:

            data = json.loads(
                result.stdout
            )

        except json.JSONDecodeError as exc:

            raise VideoAssemblyError(
                "ffprobe returned invalid JSON."
            ) from exc

        streams = (
            data.get(
                "streams",
                []
            )
        )

        video_stream = None

        has_audio = False

        for stream in streams:

            codec_type = (
                stream.get(
                    "codec_type"
                )
            )

            if (
                codec_type == "video"
                and video_stream is None
            ):

                video_stream = (
                    stream
                )

            elif (
                codec_type == "audio"
            ):

                has_audio = True

        if video_stream is None:

            raise VideoAssemblyError(
                f"No video stream in {path}"
            )

        try:

            width = int(
                video_stream.get(
                    "width",
                    0,
                )
            )

            height = int(
                video_stream.get(
                    "height",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            width = 0
            height = 0

        try:

            duration = float(
                data.get(
                    "format",
                    {},
                ).get(
                    "duration",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            duration = 0.0

        if duration <= 0:

            try:

                duration = float(
                    video_stream.get(
                        "duration",
                        0,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                duration = 0.0

        if (
            width <= 0
            or height <= 0
            or duration <= 0
        ):

            raise VideoAssemblyError(
                "Invalid media information for "
                f"{path}"
            )

        return MediaInfo(
            path=path,
            duration=duration,
            width=width,
            height=height,
            has_audio=(
                has_audio
            ),
        )

    # ======================================================
    # VIDEO FILTER
    # ======================================================

    def _video_filter(
        self,
        width: int,
        height: int,
        target_duration: int,
    ) -> str:

        return (
            f"scale="
            f"{width}:"
            f"{height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad="
            f"{width}:"
            f"{height}:"
            "(ow-iw)/2:"
            "(oh-ih)/2,"
            "setsar=1,"
            f"fps={self.fps},"
            "tpad="
            "stop_mode=clone:"
            f"stop_duration={target_duration},"
            f"trim=duration={target_duration},"
            "setpts=PTS-STARTPTS"
        )

    # ======================================================
    # AUDIO FILTER
    # ======================================================

    def _audio_filter(
        self,
        target_duration: int,
    ) -> str:

        return (
            "aresample="
            f"{self.audio_sample_rate}:"
            "async=1:"
            "first_pts=0,"
            "apad="
            f"pad_dur={target_duration},"
            f"atrim=duration={target_duration},"
            "asetpts=PTS-STARTPTS"
        )

    # ======================================================
    # NORMALIZE ONE SCENE
    # ======================================================

    def _normalize_scene(
        self,
        input_path: Path,
        output_path: Path,
        target_duration: int,
        width: int,
        height: int,
    ) -> MediaInfo:

        info = self.probe(
            input_path
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = Path(
            str(output_path)
            + ".part.mp4"
        )

        self._safe_delete(
            temporary
        )

        video_filter = (
            self._video_filter(
                width=width,
                height=height,
                target_duration=(
                    target_duration
                ),
            )
        )

        audio_filter = (
            self._audio_filter(
                target_duration=(
                    target_duration
                )
            )
        )

        # ==================================================
        # SOURCE ALREADY HAS AUDIO
        # ==================================================

        if info.has_audio:

            command = [
                self.ffmpeg,

                "-hide_banner",
                "-loglevel",
                "error",
                "-y",

                "-i",
                str(input_path),

                "-map",
                "0:v:0",

                "-map",
                "0:a:0",

                "-vf",
                video_filter,

                "-af",
                audio_filter,

                "-c:v",
                "libx264",

                "-preset",
                self.video_preset,

                "-crf",
                str(
                    self.video_crf
                ),

                "-pix_fmt",
                "yuv420p",

                "-r",
                str(
                    self.fps
                ),

                "-c:a",
                "aac",

                "-b:a",
                self.audio_bitrate,

                "-ar",
                str(
                    self.audio_sample_rate
                ),

                "-ac",
                "2",

                "-t",
                str(
                    target_duration
                ),

                "-movflags",
                "+faststart",

                str(
                    temporary
                ),
            ]

        # ==================================================
        # SOURCE HAS NO AUDIO
        # ==================================================

        else:

            command = [
                self.ffmpeg,

                "-hide_banner",
                "-loglevel",
                "error",
                "-y",

                "-i",
                str(input_path),

                "-f",
                "lavfi",

                "-i",
                (
                    "anullsrc="
                    "channel_layout=stereo:"
                    f"sample_rate="
                    f"{self.audio_sample_rate}"
                ),

                "-map",
                "0:v:0",

                "-map",
                "1:a:0",

                "-vf",
                video_filter,

                "-c:v",
                "libx264",

                "-preset",
                self.video_preset,

                "-crf",
                str(
                    self.video_crf
                ),

                "-pix_fmt",
                "yuv420p",

                "-r",
                str(
                    self.fps
                ),

                "-c:a",
                "aac",

                "-b:a",
                self.audio_bitrate,

                "-ar",
                str(
                    self.audio_sample_rate
                ),

                "-ac",
                "2",

                "-t",
                str(
                    target_duration
                ),

                "-movflags",
                "+faststart",

                str(
                    temporary
                ),
            ]

        self._run(
            command
        )

        if not (
            temporary.exists()
            and temporary.is_file()
            and temporary.stat().st_size > 0
        ):

            raise VideoAssemblyError(
                "Normalized scene is empty: "
                f"{input_path}"
            )

        if output_path.exists():

            output_path.unlink()

        temporary.replace(
            output_path
        )

        normalized_info = (
            self.probe(
                output_path
            )
        )

        return normalized_info

    # ======================================================
    # CONCAT NORMALIZED SCENES
    # ======================================================

    def _concatenate(
        self,
        scene_paths: list[Path],
        output_path: Path,
        total_duration: int,
        scene_durations: list[float] | None = None,
        transition_seconds: float = 0.0,
    ) -> None:

        if not scene_paths:

            raise VideoAssemblyError(
                "No normalized scenes."
            )

        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]

        for scene_path in (
            scene_paths
        ):

            command.extend(
                [
                    "-i",
                    str(
                        scene_path
                    ),
                ]
            )

        filter_parts = []

        concat_inputs = []

        for index in range(
            len(
                scene_paths
            )
        ):

            filter_parts.append(
                (
                    f"[{index}:v]"
                    "setpts=PTS-STARTPTS"
                    f"[v{index}]"
                )
            )

            filter_parts.append(
                (
                    f"[{index}:a]"
                    "asetpts=PTS-STARTPTS"
                    f"[a{index}]"
                )
            )

            concat_inputs.append(
                f"[v{index}]"
                f"[a{index}]"
            )

        filter_parts.append(
            (
                "".join(
                    concat_inputs
                )
                + f"concat="
                f"n={len(scene_paths)}:"
                "v=1:"
                "a=1"
                "[vcat][acat]"
            )
        )

        filter_parts.append(
            (
                "[vcat]"
                f"trim=duration="
                f"{total_duration},"
                "setpts=PTS-STARTPTS"
                "[vout]"
            )
        )

        filter_parts.append(
            (
                "[acat]"
                f"atrim=duration="
                f"{total_duration},"
                "asetpts=PTS-STARTPTS"
                "[aout]"
            )
        )

        filter_complex = (
            ";".join(
                filter_parts
            )
        )

        if transition_seconds and scene_durations and len(scene_paths) > 1:
            filter_complex = dissolve_filter(scene_durations, transition_seconds, self.fps)

        temporary = Path(
            str(output_path)
            + ".part.mp4"
        )

        self._safe_delete(
            temporary
        )

        command.extend(
            [
                "-filter_complex",
                filter_complex,

                "-map",
                "[vout]",

                "-map",
                "[aout]",

                "-c:v",
                "libx264",

                "-preset",
                self.video_preset,

                "-crf",
                str(
                    self.video_crf
                ),

                "-pix_fmt",
                "yuv420p",

                "-r",
                str(
                    self.fps
                ),

                "-c:a",
                "aac",

                "-b:a",
                self.audio_bitrate,

                "-ar",
                str(
                    self.audio_sample_rate
                ),

                "-ac",
                "2",

                "-movflags",
                "+faststart",

                str(
                    temporary
                ),
            ]
        )

        self._run(
            command
        )

        if not (
            temporary.exists()
            and temporary.is_file()
            and temporary.stat().st_size > 0
        ):

            raise VideoAssemblyError(
                "Final assembly produced "
                "an empty file."
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if output_path.exists():

            output_path.unlink()

        temporary.replace(
            output_path
        )

    # ======================================================
    # PUBLIC ASSEMBLY
    # ======================================================

    def assemble(
        self,
        plan: VideoPlan,
        scene_paths: dict[int, Path],
        output_path: Path,
        working_directory: Optional[
            Path
        ] = None,
        cleanup_intermediate: bool = True,
        transition_seconds: float = 0.0,
    ) -> AssemblyResult:

        output_path = Path(
            output_path
        )

        if working_directory is None:

            working_directory = (
                output_path.parent
                / "_assembly"
            )

        working_directory = Path(
            working_directory
        )

        working_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not plan.scenes:

            raise VideoAssemblyError(
                "Storyboard contains no scenes."
            )

        durations = [scene.duration for scene in plan.scenes]
        try:
            overlap, expected_duration = transition_timing(durations, transition_seconds, self.fps)
        except ValueError as exc:
            raise VideoAssemblyError(str(exc)) from exc

        # ==================================================
        # VERIFY ALL SOURCE SCENES
        # ==================================================

        ordered_sources = []

        for scene in (
            plan.scenes
        ):

            source = (
                scene_paths.get(
                    scene.number
                )
            )

            if source is None:

                raise VideoAssemblyError(
                    f"Missing source for "
                    f"scene {scene.number}."
                )

            source = Path(
                source
            )

            if not (
                source.exists()
                and source.is_file()
                and source.stat().st_size > 0
            ):

                raise VideoAssemblyError(
                    f"Missing video file for "
                    f"scene {scene.number}: "
                    f"{source}"
                )

            ordered_sources.append(
                (
                    scene,
                    source,
                )
            )

        # ==================================================
        # USE FIRST SCENE AS OUTPUT GEOMETRY
        # ==================================================

        first_info = (
            self.probe(
                ordered_sources[
                    0
                ][1]
            )
        )

        target_width = (
            first_info.width
        )

        target_height = (
            first_info.height
        )

        print()

        print(
            "=" * 72
        )

        print(
            "FINAL VIDEO ASSEMBLY"
        )

        print(
            "=" * 72
        )

        print()

        print(
            "Target resolution: "
            f"{target_width}x"
            f"{target_height}"
        )

        print(
            f"Target FPS: "
            f"{self.fps}"
        )

        print(
            f"Target duration: "
            f"{plan.total_duration}s"
        )

        print()

        # ==================================================
        # NORMALIZE
        # ==================================================

        normalized_paths = []

        manifest_scenes = []

        for index, (
            scene,
            source,
        ) in enumerate(
            ordered_sources,
            start=1,
        ):

            print(
                f"Normalizing scene "
                f"{index}/"
                f"{len(ordered_sources)}..."
            )

            source_info = (
                self.probe(
                    source
                )
            )

            normalized_path = (
                working_directory
                / (
                    f"normalized_"
                    f"{scene.number:02d}"
                    ".mp4"
                )
            )

            normalized_info = (
                self._normalize_scene(
                    input_path=source,
                    output_path=(
                        normalized_path
                    ),
                    target_duration=(
                        scene.duration
                    ),
                    width=(
                        target_width
                    ),
                    height=(
                        target_height
                    ),
                )
            )

            normalized_paths.append(
                normalized_path
            )

            manifest_scenes.append(
                {
                    "scene_number": (
                        scene.number
                    ),
                    "planned_duration": (
                        scene.duration
                    ),
                    "source_path": (
                        str(
                            source.resolve()
                        )
                    ),
                    "source_duration": (
                        round(
                            source_info.duration,
                            3,
                        )
                    ),
                    "source_has_audio": (
                        source_info.has_audio
                    ),
                    "normalized_path": (
                        str(
                            normalized_path.resolve()
                        )
                    ),
                    "normalized_duration": (
                        round(
                            normalized_info.duration,
                            3,
                        )
                    ),
                }
            )

        print()

        print(
            "All scenes normalized."
        )

        print(
            "Concatenating final video..."
        )

        print()

        # ==================================================
        # CONCATENATE
        # ==================================================

        self._concatenate(
            scene_paths=(
                normalized_paths
            ),
            output_path=(
                output_path
            ),
            total_duration=(
                expected_duration
            ),
            scene_durations=durations,
            transition_seconds=overlap,
        )

        # ==================================================
        # FINAL VALIDATION
        # ==================================================

        final_info = (
            self.probe(
                output_path
            )
        )

        duration_difference = abs(
            final_info.duration
            - expected_duration
        )

        # MP4/AAC containers may differ by a few
        # hundredths of a second.
        if (
            duration_difference
            > 0.20
        ):

            raise VideoAssemblyError(
                "Final duration validation failed. "
                f"Expected "
                f"{expected_duration:.3f}s, "
                f"got "
                f"{final_info.duration:.3f}s."
            )

        if not final_info.has_audio:

            raise VideoAssemblyError(
                "Final video unexpectedly "
                "contains no audio stream."
            )

        if (
            final_info.width
            != target_width
            or final_info.height
            != target_height
        ):

            raise VideoAssemblyError(
                "Final video resolution "
                "validation failed."
            )

        # ==================================================
        # MANIFEST
        # ==================================================

        manifest = {
            "transition": "dissolve" if overlap else "cut",
            "transition_seconds": overlap,
            "expected_total_duration": expected_duration,
            "title": (
                plan.title
            ),
            "scene_count": (
                len(
                    plan.scenes
                )
            ),
            "planned_total_duration": (
                plan.total_duration
            ),
            "final_duration": (
                round(
                    final_info.duration,
                    3,
                )
            ),
            "width": (
                final_info.width
            ),
            "height": (
                final_info.height
            ),
            "fps": (
                self.fps
            ),
            "video_codec": (
                "H.264"
            ),
            "audio_codec": (
                "AAC"
            ),
            "audio_sample_rate": (
                self.audio_sample_rate
            ),
            "scenes": (
                manifest_scenes
            ),
        }

        manifest_path = (
            output_path.parent
            / "assembly_manifest.json"
        )

        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # ==================================================
        # CLEAN INTERMEDIATE FILES
        # ==================================================

        if cleanup_intermediate:

            for path in (
                normalized_paths
            ):

                self._safe_delete(
                    path
                )

            try:

                if (
                    working_directory.exists()
                    and not any(
                        working_directory.iterdir()
                    )
                ):

                    working_directory.rmdir()

            except OSError:

                pass

        print()

        print(
            "=" * 72
        )

        print(
            "FINAL VIDEO READY"
        )

        print(
            "=" * 72
        )

        print(
            f"Output: "
            f"{output_path.resolve()}"
        )

        print(
            f"Duration: "
            f"{final_info.duration:.3f}s"
        )

        print(
            "Resolution: "
            f"{final_info.width}x"
            f"{final_info.height}"
        )

        print(
            f"Scenes: "
            f"{len(plan.scenes)}"
        )

        print(
            f"Manifest: "
            f"{manifest_path.resolve()}"
        )

        print(
            "=" * 72
        )

        print()

        return AssemblyResult(
            output_path=(
                output_path
            ),
            duration=(
                final_info.duration
            ),
            width=(
                final_info.width
            ),
            height=(
                final_info.height
            ),
            scene_count=(
                len(
                    plan.scenes
                )
            ),
        )

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
