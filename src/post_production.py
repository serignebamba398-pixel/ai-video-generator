from __future__ import annotations

import json
import math
import re
import shutil
import subprocess

from dataclasses import (
    asdict,
)

from pathlib import Path
from typing import Optional

from src.post_production_planner import (
    OverlayCue,
    PostProductionPlan,
)

from src.scene_planner import (
    VideoPlan,
)


# ==========================================================
# PATHS
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


class PostProductionError(Exception):
    pass


# ==========================================================
# ENGINE
# ==========================================================


class PostProductionEngine:
    """
    Professional generic finishing engine.

    Current responsibilities:

    - editorial text overlays
    - safe rejection of non-trackable diegetic overlays
    - optional background music
    - audio resampling
    - 2-pass loudness normalization
    - final duration validation
    - production manifest

    This engine contains NO scenario-specific logic.
    """

    TARGET_LUFS = -16.0

    TARGET_TRUE_PEAK = -1.5

    TARGET_LRA = 11.0

    AUDIO_SAMPLE_RATE = 48000

    AUDIO_BITRATE = "192k"

    VIDEO_CRF = 18

    VIDEO_PRESET = "medium"

    FADE_IN_DURATION = 0.15

    FADE_OUT_DURATION = 0.25

    def __init__(
        self,
        ffmpeg_path: (
            str
            | Path
            | None
        ) = None,
        ffprobe_path: (
            str
            | Path
            | None
        ) = None,
    ) -> None:

        self.ffmpeg = (
            self._resolve_binary(
                ffmpeg_path,
                LOCAL_FFMPEG,
                "ffmpeg",
            )
        )

        self.ffprobe = (
            self._resolve_binary(
                ffprobe_path,
                LOCAL_FFPROBE,
                "ffprobe",
            )
        )

        self.font_path = (
            self._find_font()
        )

    # ======================================================
    # BINARIES
    # ======================================================

    @staticmethod
    def _resolve_binary(
        custom_path,
        local_path: Path,
        name: str,
    ) -> str:

        if custom_path:

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

            raise PostProductionError(
                f"{name} not found: "
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
                name
            )
        )

        if system_path:

            return system_path

        raise PostProductionError(
            f"{name} was not found."
        )

    # ======================================================
    # FONT
    # ======================================================

    @staticmethod
    def _find_font() -> Optional[
        Path
    ]:

        candidates = [
            Path(
                r"C:\Windows\Fonts\segoeui.ttf"
            ),
            Path(
                r"C:\Windows\Fonts\arial.ttf"
            ),
            Path(
                "/usr/share/fonts/"
                "truetype/dejavu/"
                "DejaVuSans.ttf"
            ),
        ]

        for candidate in (
            candidates
        ):

            if (
                candidate.exists()
                and candidate.is_file()
            ):

                return candidate

        return None

    # ======================================================
    # COMMAND
    # ======================================================

    @staticmethod
    def _run(
        command: list[str],
        timeout: int = 1800,
        fail_on_error: bool = True,
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

            raise PostProductionError(
                "FFmpeg operation timed out."
            ) from exc

        except OSError as exc:

            raise PostProductionError(
                "Unable to execute FFmpeg: "
                f"{exc}"
            ) from exc

        if (
            fail_on_error
            and result.returncode != 0
        ):

            raise PostProductionError(
                "FFmpeg operation failed.\n\n"
                f"{result.stderr}"
            )

        return result

    # ======================================================
    # DURATION
    # ======================================================

    def _duration(
        self,
        path: Path,
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
                path
            ),
        ]

        result = self._run(
            command,
            timeout=60,
        )

        try:

            duration = float(
                result.stdout.strip()
            )

        except ValueError as exc:

            raise PostProductionError(
                "Unable to determine "
                "video duration."
            ) from exc

        if duration <= 0:

            raise PostProductionError(
                "Invalid source duration."
            )

        return duration

    # ======================================================
    # SCENE START TIMES
    # ======================================================

    @staticmethod
    def _scene_start_times(
        plan: VideoPlan,
    ) -> dict[
        int,
        float,
    ]:

        result = {}

        current = 0.0

        for scene in (
            plan.scenes
        ):

            result[
                scene.number
            ] = current

            current += float(
                scene.duration
            )

        return result

    # ======================================================
    # ABSOLUTE OVERLAYS
    # ======================================================

    def _absolute_overlays(
        self,
        video_plan: VideoPlan,
        post_plan: PostProductionPlan,
    ) -> list[dict]:

        starts = (
            self._scene_start_times(
                video_plan
            )
        )

        result = []

        for cue in (
            post_plan.overlays
        ):

            scene_start = (
                starts.get(
                    cue.scene_number
                )
            )

            if scene_start is None:

                continue

            result.append(
                {
                    "cue": cue,
                    "global_start": (
                        scene_start
                        + cue.start
                    ),
                    "global_end": (
                        scene_start
                        + cue.end
                    ),
                }
            )

        return result

    # ======================================================
    # PATH ESCAPING
    # ======================================================

    @staticmethod
    def _filter_path(
        path: Path,
    ) -> str:

        value = (
            path.resolve()
            .as_posix()
        )

        value = value.replace(
            ":",
            r"\:",
        )

        value = value.replace(
            "'",
            r"\'",
        )

        return value

    # ======================================================
    # POSITION
    # ======================================================

    @staticmethod
    def _position_expression(
        position: str,
    ) -> tuple[
        str,
        str,
    ]:

        margin_x = (
            "w*0.06"
        )

        margin_y = (
            "h*0.08"
        )

        positions = {
            "top": (
                "(w-text_w)/2",
                margin_y,
            ),

            "top_left": (
                margin_x,
                margin_y,
            ),

            "top_right": (
                "w-text_w-w*0.06",
                margin_y,
            ),

            "center": (
                "(w-text_w)/2",
                "(h-text_h)/2",
            ),

            "bottom": (
                "(w-text_w)/2",
                "h-text_h-h*0.10",
            ),

            "bottom_left": (
                margin_x,
                "h-text_h-h*0.10",
            ),

            "bottom_right": (
                "w-text_w-w*0.06",
                "h-text_h-h*0.10",
            ),
        }

        return positions.get(
            position,
            positions[
                "bottom"
            ],
        )

    # ======================================================
    # STYLE
    # ======================================================

    @staticmethod
    def _style_parameters(
        style: str,
    ) -> dict:

        if style == "impact":

            return {
                "fontsize": (
                    "h*0.085"
                ),
                "boxcolor": (
                    "black@0.56"
                ),
                "boxborderw": (
                    "22"
                ),
                "borderw": (
                    "3"
                ),
            }

        if style == "subtle":

            return {
                "fontsize": (
                    "h*0.042"
                ),
                "boxcolor": (
                    "black@0.28"
                ),
                "boxborderw": (
                    "10"
                ),
                "borderw": (
                    "1"
                ),
            }

        return {
            "fontsize": (
                "h*0.055"
            ),
            "boxcolor": (
                "black@0.42"
            ),
            "boxborderw": (
                "16"
            ),
            "borderw": (
                "2"
            ),
        }

    # ======================================================
    # OVERLAYS
    # ======================================================

    def _build_overlay_filters(
        self,
        video_plan: VideoPlan,
        post_plan: PostProductionPlan,
        working_directory: Path,
        allow_diegetic_proxy: bool,
    ) -> tuple[
        list[str],
        list[dict],
        list[dict],
    ]:

        absolute = (
            self._absolute_overlays(
                video_plan=(
                    video_plan
                ),
                post_plan=(
                    post_plan
                ),
            )
        )

        filters = []

        rendered = []

        skipped = []

        render_index = 0

        for item in absolute:

            cue: OverlayCue = (
                item[
                    "cue"
                ]
            )

            # ==============================================
            # DIEGETIC SAFETY
            # ==============================================

            if (
                cue.mode
                == "diegetic"
                and not allow_diegetic_proxy
            ):

                skipped.append(
                    {
                        **asdict(
                            cue
                        ),
                        "reason": (
                            "Diegetic text requires "
                            "spatial/object tracking. "
                            "Automatic floating overlay "
                            "was intentionally disabled."
                        ),
                    }
                )

                continue

            render_index += 1

            if self.font_path is None:

                raise PostProductionError(
                    "No suitable font was found "
                    "for editorial overlays."
                )

            start = float(
                item[
                    "global_start"
                ]
            )

            end = float(
                item[
                    "global_end"
                ]
            )

            text_path = (
                working_directory
                / (
                    f"overlay_"
                    f"{render_index:02d}"
                    ".txt"
                )
            )

            text_path.write_text(
                cue.text,
                encoding="utf-8",
            )

            x, y = (
                self._position_expression(
                    cue.position
                )
            )

            style = (
                self._style_parameters(
                    cue.style
                )
            )

            font_path = (
                self._filter_path(
                    self.font_path
                )
            )

            overlay_text_path = (
                self._filter_path(
                    text_path
                )
            )

            filter_string = (
                "drawtext="
                f"fontfile='{font_path}':"
                f"textfile='{overlay_text_path}':"
                "fontcolor=white:"
                f"fontsize={style['fontsize']}:"
                f"borderw={style['borderw']}:"
                "bordercolor=black@0.85:"
                "box=1:"
                f"boxcolor={style['boxcolor']}:"
                f"boxborderw={style['boxborderw']}:"
                f"x={x}:"
                f"y={y}:"
                "fix_bounds=true:"
                f"enable='between(t,"
                f"{start:.3f},"
                f"{end:.3f})'"
            )

            filters.append(
                filter_string
            )

            rendered.append(
                {
                    **asdict(
                        cue
                    ),
                    "global_start": (
                        round(
                            start,
                            3,
                        )
                    ),
                    "global_end": (
                        round(
                            end,
                            3,
                        )
                    ),
                }
            )

        return (
            filters,
            rendered,
            skipped,
        )

    # ======================================================
    # PREMASTER
    # ======================================================

    def _render_premaster(
        self,
        source_video: Path,
        output_path: Path,
        video_plan: VideoPlan,
        post_plan: PostProductionPlan,
        working_directory: Path,
        music_path: Optional[
            Path
        ],
        allow_diegetic_proxy: bool,
    ) -> tuple[
        list[dict],
        list[dict],
    ]:

        duration = (
            self._duration(
                source_video
            )
        )

        (
            overlay_filters,
            rendered_overlays,
            skipped_overlays,
        ) = self._build_overlay_filters(
            video_plan=(
                video_plan
            ),
            post_plan=(
                post_plan
            ),
            working_directory=(
                working_directory
            ),
            allow_diegetic_proxy=(
                allow_diegetic_proxy
            ),
        )

        # ==============================================
        # VISUAL FILTERS
        # ==============================================

        video_filters = []

        if (
            self.FADE_IN_DURATION
            > 0
        ):

            video_filters.append(
                (
                    "fade="
                    "t=in:"
                    "st=0:"
                    f"d="
                    f"{self.FADE_IN_DURATION}"
                )
            )

        if (
            self.FADE_OUT_DURATION
            > 0
        ):

            fade_out_start = max(
                0.0,
                duration
                - self.FADE_OUT_DURATION,
            )

            video_filters.append(
                (
                    "fade="
                    "t=out:"
                    f"st="
                    f"{fade_out_start:.3f}:"
                    f"d="
                    f"{self.FADE_OUT_DURATION}"
                )
            )

        video_filters.extend(
            overlay_filters
        )

        if video_filters:

            video_chain = ",".join(
                video_filters
            )

        else:

            video_chain = (
                "null"
            )

        # ==============================================
        # COMMAND
        # ==============================================

        command = [
            self.ffmpeg,

            "-hide_banner",

            "-loglevel",
            "error",

            "-y",

            "-i",
            str(
                source_video
            ),
        ]

        use_music = bool(
            music_path
            and Path(
                music_path
            ).exists()
        )

        if use_music:

            music_path = Path(
                music_path
            )

            command.extend(
                [
                    "-stream_loop",
                    "-1",

                    "-i",
                    str(
                        music_path
                    ),
                ]
            )

            music_fade_out = max(
                0.0,
                duration
                - 2.0,
            )

            filter_complex = (
                f"[0:v]"
                f"{video_chain}"
                f"[vout];"

                f"[0:a]"
                f"aresample="
                f"{self.AUDIO_SAMPLE_RATE},"
                "asetpts=PTS-STARTPTS"
                f"[original];"

                f"[1:a]"
                f"aresample="
                f"{self.AUDIO_SAMPLE_RATE},"
                f"atrim=duration="
                f"{duration:.3f},"
                "asetpts=PTS-STARTPTS,"
                "volume=0.10,"
                "afade="
                "t=in:"
                "st=0:"
                "d=1.5,"
                "afade="
                "t=out:"
                f"st="
                f"{music_fade_out:.3f}:"
                "d=2.0"
                f"[music];"

                "[original][music]"
                "amix="
                "inputs=2:"
                "duration=first:"
                "dropout_transition=2:"
                "normalize=0"
                "[aout]"
            )

        else:

            filter_complex = (
                f"[0:v]"
                f"{video_chain}"
                f"[vout];"

                f"[0:a]"
                f"aresample="
                f"{self.AUDIO_SAMPLE_RATE},"
                "asetpts=PTS-STARTPTS"
                "[aout]"
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
                self.VIDEO_PRESET,

                "-crf",
                str(
                    self.VIDEO_CRF
                ),

                "-pix_fmt",
                "yuv420p",

                "-c:a",
                "aac",

                "-b:a",
                self.AUDIO_BITRATE,

                "-ar",
                str(
                    self.AUDIO_SAMPLE_RATE
                ),

                "-ac",
                "2",

                "-t",
                f"{duration:.3f}",

                "-movflags",
                "+faststart",

                str(
                    output_path
                ),
            ]
        )

        self._run(
            command
        )

        if not (
            output_path.exists()
            and output_path.stat().st_size
            > 0
        ):

            raise PostProductionError(
                "Premaster was not generated."
            )

        return (
            rendered_overlays,
            skipped_overlays,
        )

    # ======================================================
    # LOUDNESS ANALYSIS
    # ======================================================

    def _analyse_loudness(
        self,
        path: Path,
    ) -> Optional[
        dict
    ]:

        loudnorm = (
            "loudnorm="
            f"I={self.TARGET_LUFS}:"
            f"LRA={self.TARGET_LRA}:"
            f"TP="
            f"{self.TARGET_TRUE_PEAK}:"
            "print_format=json"
        )

        command = [
            self.ffmpeg,

            "-hide_banner",

            "-nostats",

            "-i",
            str(
                path
            ),

            "-vn",

            "-af",
            loudnorm,

            "-f",
            "null",

            "-",
        ]

        result = self._run(
            command,
            timeout=600,
            fail_on_error=False,
        )

        matches = re.findall(
            (
                r"\{[\s\S]*?"
                r'"target_offset"\s*:\s*"[^"]+"'
                r"[\s\S]*?\}"
            ),
            result.stderr,
        )

        if not matches:

            return None

        try:

            data = json.loads(
                matches[
                    -1
                ]
            )

        except json.JSONDecodeError:

            return None

        required = [
            "input_i",
            "input_tp",
            "input_lra",
            "input_thresh",
            "target_offset",
        ]

        if not all(
            key in data
            for key in required
        ):

            return None

        for key in required:

            try:

                value = float(
                    data[
                        key
                    ]
                )

            except (
                ValueError,
                TypeError,
            ):

                return None

            if not math.isfinite(
                value
            ):

                return None

        return data

    # ======================================================
    # AUDIO MASTER
    # ======================================================

    def _master_audio(
        self,
        premaster_path: Path,
        output_path: Path,
    ) -> dict:

        analysis = (
            self._analyse_loudness(
                premaster_path
            )
        )

        if analysis:

            audio_filter = (
                "loudnorm="
                f"I={self.TARGET_LUFS}:"
                f"LRA={self.TARGET_LRA}:"
                f"TP="
                f"{self.TARGET_TRUE_PEAK}:"
                f"measured_I="
                f"{analysis['input_i']}:"
                f"measured_LRA="
                f"{analysis['input_lra']}:"
                f"measured_TP="
                f"{analysis['input_tp']}:"
                f"measured_thresh="
                f"{analysis['input_thresh']}:"
                f"offset="
                f"{analysis['target_offset']}:"
                "linear=true:"
                "print_format=summary"
            )

            mode = (
                "two_pass"
            )

        else:

            audio_filter = (
                "loudnorm="
                f"I={self.TARGET_LUFS}:"
                f"LRA={self.TARGET_LRA}:"
                f"TP="
                f"{self.TARGET_TRUE_PEAK}"
            )

            mode = (
                "single_pass_fallback"
            )

        temporary = Path(
            str(
                output_path
            )
            + ".part.mp4"
        )

        if temporary.exists():

            temporary.unlink()

        command = [
            self.ffmpeg,

            "-hide_banner",

            "-loglevel",
            "error",

            "-y",

            "-i",
            str(
                premaster_path
            ),

            "-map",
            "0:v:0",

            "-map",
            "0:a:0",

            "-c:v",
            "copy",

            "-af",
            audio_filter,

            "-c:a",
            "aac",

            "-b:a",
            self.AUDIO_BITRATE,

            "-ar",
            str(
                self.AUDIO_SAMPLE_RATE
            ),

            "-ac",
            "2",

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
            and temporary.stat().st_size
            > 0
        ):

            raise PostProductionError(
                "Final audio mastering failed."
            )

        if output_path.exists():

            output_path.unlink()

        temporary.replace(
            output_path
        )

        final_analysis = (
            self._analyse_loudness(
                output_path
            )
        )

        return {
            "mode": (
                mode
            ),
            "input_analysis": (
                analysis
            ),
            "final_analysis": (
                final_analysis
            ),
        }

    # ======================================================
    # MASTER
    # ======================================================

    def master(
        self,
        source_video: Path,
        output_path: Path,
        video_plan: VideoPlan,
        post_plan: PostProductionPlan,
        music_path: Optional[
            Path
        ] = None,
        working_directory: Optional[
            Path
        ] = None,
        cleanup: bool = True,
        allow_diegetic_proxy: bool = False,
    ) -> Path:

        source_video = Path(
            source_video
        )

        output_path = Path(
            output_path
        )

        if not (
            source_video.exists()
            and source_video.stat().st_size
            > 0
        ):

            raise PostProductionError(
                "Source final video "
                "does not exist."
            )

        if working_directory is None:

            working_directory = (
                output_path.parent
                / "_post"
            )

        working_directory = Path(
            working_directory
        )

        working_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        print()

        print(
            "=" * 72
        )

        print(
            "POST-PRODUCTION"
        )

        print(
            "=" * 72
        )

        print()

        source_duration = (
            self._duration(
                source_video
            )
        )

        print(
            f"Source: "
            f"{source_video.resolve()}"
        )

        print(
            f"Duration: "
            f"{source_duration:.3f}s"
        )

        print(
            f"Verified overlay cues: "
            f"{len(post_plan.overlays)}"
        )

        print()

        premaster = (
            working_directory
            / "premaster.mp4"
        )

        (
            rendered_overlays,
            skipped_overlays,
        ) = self._render_premaster(
            source_video=(
                source_video
            ),
            output_path=(
                premaster
            ),
            video_plan=(
                video_plan
            ),
            post_plan=(
                post_plan
            ),
            working_directory=(
                working_directory
            ),
            music_path=(
                music_path
            ),
            allow_diegetic_proxy=(
                allow_diegetic_proxy
            ),
        )

        print(
            "Rendered editorial overlays: "
            f"{len(rendered_overlays)}"
        )

        print(
            "Skipped diegetic overlays: "
            f"{len(skipped_overlays)}"
        )

        print()

        print(
            "Visual post-production ready."
        )

        print(
            "Running loudness mastering..."
        )

        loudness = (
            self._master_audio(
                premaster_path=(
                    premaster
                ),
                output_path=(
                    output_path
                ),
            )
        )

        final_duration = (
            self._duration(
                output_path
            )
        )

        if (
            abs(
                final_duration
                - source_duration
            )
            > 0.20
        ):

            raise PostProductionError(
                "Post-production changed "
                "video duration unexpectedly. "
                f"Before="
                f"{source_duration:.3f}s, "
                f"after="
                f"{final_duration:.3f}s."
            )

        manifest = {
            "source_video": (
                str(
                    source_video.resolve()
                )
            ),

            "master_video": (
                str(
                    output_path.resolve()
                )
            ),

            "source_duration": (
                round(
                    source_duration,
                    3,
                )
            ),

            "final_duration": (
                round(
                    final_duration,
                    3,
                )
            ),

            "target_lufs": (
                self.TARGET_LUFS
            ),

            "target_true_peak": (
                self.TARGET_TRUE_PEAK
            ),

            "audio_mastering": (
                loudness
            ),

            "music": (
                str(
                    Path(
                        music_path
                    ).resolve()
                )
                if (
                    music_path
                    and Path(
                        music_path
                    ).exists()
                )
                else None
            ),

            "rendered_overlays": (
                rendered_overlays
            ),

            "skipped_diegetic_overlays": (
                skipped_overlays
            ),

            "unresolved_exact_graphics": [
                asdict(
                    item
                )
                for item
                in post_plan
                .unresolved_exact_graphics
            ],
        }

        manifest_path = (
            output_path.parent
            / "post_production_manifest.json"
        )

        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        if cleanup:

            try:

                if premaster.exists():

                    premaster.unlink()

            except OSError:

                pass

        print()

        print(
            "=" * 72
        )

        print(
            "FINAL MASTER READY"
        )

        print(
            "=" * 72
        )

        print()

        print(
            output_path.resolve()
        )

        print()

        print(
            f"Duration: "
            f"{final_duration:.3f}s"
        )

        print(
            f"Audio target: "
            f"{self.TARGET_LUFS} LUFS"
        )

        print(
            f"True peak target: "
            f"{self.TARGET_TRUE_PEAK} dBTP"
        )

        print()

        return output_path