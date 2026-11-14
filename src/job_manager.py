from __future__ import annotations

import hashlib
import json

from dataclasses import asdict
from pathlib import Path

from src.scene_planner import (
    Character,
    Scene,
    VideoPlan,
)


class JobManager:

    PLAN_SCHEMA_VERSION = 3

    def __init__(
        self,
        base_dir: Path,
        job_id: str,
    ) -> None:

        job_id = (
            job_id
            or ""
        ).strip()

        if not job_id:
            raise ValueError(
                "job_id cannot be empty."
            )

        self.base_dir = Path(
            base_dir
        )

        self.job_id = job_id

        self.job_dir = (
            self.base_dir
            / "jobs"
            / job_id
        )

        self.reference_dir = (
            self.job_dir
            / "references"
        )

        self.continuity_dir = (
            self.job_dir
            / "continuity"
        )

        self.plan_path = (
            self.job_dir
            / "plan.json"
        )

        self.job_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.reference_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.continuity_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ======================================================
    # RAW PLAN
    # ======================================================

    def _read_raw_plan(
        self,
    ) -> dict | None:

        if not (
            self.plan_path.exists()
            and self.plan_path.is_file()
            and self.plan_path.stat().st_size > 0
        ):
            return None

        try:

            data = json.loads(
                self.plan_path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ):
            return None

        return (
            data
            if isinstance(
                data,
                dict,
            )
            else None
        )

    # ======================================================
    # HAS PLAN
    # ======================================================

    def has_plan(
        self,
    ) -> bool:

        data = (
            self._read_raw_plan()
        )

        if data is None:
            return False

        try:

            version = int(
                data.get(
                    "schema_version",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            return False

        return (
            version
            == self.PLAN_SCHEMA_VERSION
        )

    # ======================================================
    # FINGERPRINT
    # ======================================================

    @staticmethod
    def _fingerprint(
        data: dict,
    ) -> str:

        clean = dict(
            data
        )

        clean.pop(
            "plan_fingerprint",
            None,
        )

        serialized = json.dumps(
            clean,
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )

        return hashlib.sha256(
            serialized.encode(
                "utf-8"
            )
        ).hexdigest()

    # ======================================================
    # INVALIDATE OLD OUTPUTS
    # ======================================================

    def _invalidate_scene_outputs(self, scene_numbers: set[int]) -> None:
        """Archive only affected scenes; unrelated clips and tasks stay intact."""
        from src.video_artifacts import archive_scene_outputs, archive_final_outputs

        for number in sorted(scene_numbers):
            archive_scene_outputs(self.job_dir, number)
        if scene_numbers:
            archive_final_outputs(self.job_dir)

    @staticmethod
    def _changed_scene_numbers(old_data: dict, new_data: dict) -> set[int]:
        # Compare JSON-normalized values so tuples in memory equal saved lists.
        new_data = json.loads(json.dumps(new_data))
        old_scenes = {int(s["number"]): s for s in old_data.get("scenes", [])}
        new_scenes = {int(s["number"]): s for s in new_data.get("scenes", [])}
        context_keys = (
            "language", "character_description", "style_description",
            "setting_description", "continuity_constraints", "characters",
        )
        if any(old_data.get(k) != new_data.get(k) for k in context_keys):
            return set(old_scenes)
        return {number for number, scene in old_scenes.items()
                if scene != new_scenes.get(number)}

    # ======================================================
    # SAVE PLAN
    # ======================================================

    def save_plan(
        self,
        plan: VideoPlan,
    ) -> None:

        new_data = asdict(
            plan
        )

        new_data[
            "schema_version"
        ] = self.PLAN_SCHEMA_VERSION

        fingerprint = (
            self._fingerprint(
                new_data
            )
        )

        old_data = (
            self._read_raw_plan()
        )

        if old_data is not None:

            old_version = (
                old_data.get(
                    "schema_version",
                    0,
                )
            )

            old_fingerprint = (
                old_data.get(
                    "plan_fingerprint"
                )
            )

            if (
                old_version
                != self.PLAN_SCHEMA_VERSION
                or old_fingerprint
                != fingerprint
            ):
                self._invalidate_scene_outputs(
                    self._changed_scene_numbers(old_data, new_data)
                )

        new_data[
            "plan_fingerprint"
        ] = fingerprint

        temporary = Path(
            str(self.plan_path)
            + ".tmp"
        )

        temporary.write_text(
            json.dumps(
                new_data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary.replace(
            self.plan_path
        )

    # ======================================================
    # LOAD PLAN
    # ======================================================

    def load_plan(
        self,
    ) -> VideoPlan:

        data = (
            self._read_raw_plan()
        )

        if data is None:
            raise FileNotFoundError(
                "No saved storyboard."
            )

        if int(
            data.get(
                "schema_version",
                0,
            )
        ) != self.PLAN_SCHEMA_VERSION:

            raise ValueError(
                "Storyboard schema is obsolete."
            )

        characters = []

        for raw in data.get(
            "characters",
            [],
        ):

            characters.append(
                Character(
                    id=str(
                        raw.get(
                            "id",
                            "",
                        )
                    ),
                    name=str(
                        raw.get(
                            "name",
                            "",
                        )
                    ),
                    description=str(
                        raw.get(
                            "description",
                            "",
                        )
                    ),
                    reference_prompt=str(
                        raw.get(
                            "reference_prompt",
                            "",
                        )
                    ),
                )
            )

        scenes = []

        for raw in data.get(
            "scenes",
            [],
        ):

            speaker = (
                raw.get(
                    "speaker_id"
                )
            )

            scenes.append(
                Scene(
                    number=int(
                        raw.get(
                            "number",
                            0,
                        )
                    ),
                    duration=int(
                        raw.get(
                            "duration",
                            8,
                        )
                    ),
                    visual_prompt=str(
                        raw.get(
                            "visual_prompt",
                            "",
                        )
                    ),
                    dialogue=str(
                        raw.get(
                            "dialogue",
                            "",
                        )
                        or ""
                    ),
                    speaker_id=(
                        str(speaker)
                        if speaker is not None
                        else None
                    ),
                    character_ids=tuple(
                        str(value)
                        for value in raw.get(
                            "character_ids",
                            [],
                        )
                    ),
                    start_state=str(
                        raw.get(
                            "start_state",
                            "",
                        )
                    ),
                    end_state=str(
                        raw.get(
                            "end_state",
                            "",
                        )
                    ),
                    use_previous_frame=bool(
                        raw.get(
                            "use_previous_frame",
                            False,
                        )
                    ),
                )
            )

        character_description = str(
            data.get(
                "character_description",
                "",
            )
        )

        return VideoPlan(
            title=str(
                data.get(
                    "title",
                    "Untitled video",
                )
            ),
            language=str(
                data.get(
                    "language",
                    "French",
                )
            ),
            character_description=(
                character_description
            ),
            style_description=str(
                data.get(
                    "style_description",
                    "",
                )
            ),
            setting_description=str(
                data.get(
                    "setting_description",
                    "",
                )
            ),
            continuity_constraints=str(
                data.get(
                    "continuity_constraints",
                    "",
                )
            ),
            characters=characters,
            scenes=scenes,
        )

    # ======================================================
    # PATHS
    # ======================================================

    def scene_video_path(
        self,
        scene_number: int,
    ) -> Path:

        return (
            self.job_dir
            / (
                f"scene_"
                f"{scene_number:02d}"
                ".mp4"
            )
        )

    def scene_is_complete(
        self,
        scene_number: int,
    ) -> bool:

        path = (
            self.scene_video_path(
                scene_number
            )
        )

        return (
            path.exists()
            and path.is_file()
            and path.stat().st_size > 0
        )

    def continuity_frame_path(
        self,
        scene_number: int,
    ) -> Path:

        return (
            self.continuity_dir
            / (
                f"scene_"
                f"{scene_number:02d}"
                "_last.jpg"
            )
        )