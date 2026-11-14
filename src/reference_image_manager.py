from __future__ import annotations

import hashlib
import json
import time

from pathlib import Path

from src.agnes_client import (
    AgnesAPIError,
    AgnesClient,
)

from src.scene_planner import (
    Character,
    VideoPlan,
)


class ReferenceImageError(Exception):
    pass


class ReferenceImageManager:

    def __init__(
        self,
        agnes_client: AgnesClient,
        reference_dir: Path,
        retry_delay: int = 60,
    ) -> None:

        self.agnes = (
            agnes_client
        )

        self.reference_dir = Path(
            reference_dir
        )

        self.reference_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.retry_delay = max(
            1,
            int(
                retry_delay
            ),
        )

    # ======================================================
    # BUILD FINAL CHARACTER PROMPT
    # ======================================================

    @staticmethod
    def _build_reference_prompt(
        character: Character,
    ) -> str:

        return f"""
Create a high-quality realistic cinematic character
reference photograph.

This image defines a recurring character's identity for
multiple AI-generated video scenes.

CHARACTER NAME

{character.name}


STABLE IDENTITY

{character.description}


CHARACTER-SPECIFIC VISUAL DIRECTION

{character.reference_prompt}


IDENTITY REQUIREMENTS

Show exactly one person.

The complete face must be clearly visible and unobstructed.

Use natural realistic facial anatomy.

Use a neutral natural facial expression.

Use a frontal or gentle three-quarter view.

Show enough of the body to establish:

- body proportions
- clothing
- accessories
- hairstyle
- persistent visual features

Use a simple neutral background.

Use realistic skin texture.

Use soft natural cinematic lighting.

Use realistic photography.


DO NOT INCLUDE

- other people
- duplicate people
- text
- captions
- logos added by the model
- collage
- split screen
- dramatic face obstruction
- sunglasses unless part of permanent character identity
- extreme camera distortion

The purpose of this image is stable identity, not action.
""".strip()

    # ======================================================
    # FINGERPRINT
    # ======================================================

    @staticmethod
    def _fingerprint(
        prompt: str,
    ) -> str:

        return hashlib.sha256(
            prompt.encode(
                "utf-8"
            )
        ).hexdigest()

    # ======================================================
    # PATHS
    # ======================================================

    def reference_path(
        self,
        character_id: str,
    ) -> Path:

        safe_id = (
            character_id
            .replace(
                "/",
                "_",
            )
            .replace(
                "\\",
                "_",
            )
        )

        return (
            self.reference_dir
            / f"{safe_id}.png"
        )

    def metadata_path(
        self,
        character_id: str,
    ) -> Path:

        safe_id = (
            character_id
            .replace(
                "/",
                "_",
            )
            .replace(
                "\\",
                "_",
            )
        )

        return (
            self.reference_dir
            / f"{safe_id}.reference.json"
        )

    # ======================================================
    # CHECK EXISTING REFERENCE
    # ======================================================

    def _reference_is_current(
        self,
        character: Character,
        prompt: str,
    ) -> bool:

        image_path = (
            self.reference_path(
                character.id
            )
        )

        metadata_path = (
            self.metadata_path(
                character.id
            )
        )

        if not (
            image_path.exists()
            and image_path.is_file()
            and image_path.stat().st_size > 0
        ):

            return False

        if not (
            metadata_path.exists()
            and metadata_path.is_file()
        ):

            return False

        try:

            metadata = json.loads(
                metadata_path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ):

            return False

        expected = (
            self._fingerprint(
                prompt
            )
        )

        actual = str(
            metadata.get(
                "prompt_fingerprint",
                "",
            )
        )

        return (
            actual
            == expected
        )

    # ======================================================
    # SAVE METADATA
    # ======================================================

    def _save_metadata(
        self,
        character: Character,
        prompt: str,
    ) -> None:

        path = (
            self.metadata_path(
                character.id
            )
        )

        data = {
            "character_id": (
                character.id
            ),
            "character_name": (
                character.name
            ),
            "prompt_fingerprint": (
                self._fingerprint(
                    prompt
                )
            ),
        }

        temporary = Path(
            str(path)
            + ".tmp"
        )

        temporary.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary.replace(
            path
        )

    # ======================================================
    # ENSURE ALL REFERENCES
    # ======================================================

    def ensure_references(
        self,
        plan: VideoPlan,
    ) -> dict[str, Path]:

        result = {}

        if not plan.characters:

            return result

        print()

        print(
            "=" * 72
        )

        print(
            "CHARACTER REFERENCE IMAGES"
        )

        print(
            "=" * 72
        )

        print()

        for character in (
            plan.characters
        ):

            prompt = (
                self._build_reference_prompt(
                    character
                )
            )

            image_path = (
                self.reference_path(
                    character.id
                )
            )

            if (
                self._reference_is_current(
                    character=character,
                    prompt=prompt,
                )
            ):

                print(
                    f"{character.name}: "
                    "current reference image found"
                )

                print(
                    image_path.resolve()
                )

                print()

                result[
                    character.id
                ] = image_path

                continue

            # Existing image belongs to an obsolete
            # character description.
            try:

                if image_path.exists():

                    image_path.unlink()

            except OSError:
                pass

            print(
                f"{character.name}: "
                "generating new reference image..."
            )

            self._generate_with_retry(
                character=character,
                prompt=prompt,
                output_path=(
                    image_path
                ),
            )

            self._save_metadata(
                character=character,
                prompt=prompt,
            )

            print(
                f"{character.name}: "
                "reference image ready"
            )

            print(
                image_path.resolve()
            )

            print()

            result[
                character.id
            ] = image_path

        return result

    # ======================================================
    # GENERATION WITH RETRIES
    # ======================================================

    def _generate_with_retry(
        self,
        character: Character,
        prompt: str,
        output_path: Path,
    ) -> None:

        attempt = 0

        while True:

            attempt += 1

            try:

                self.agnes.generate_image(
                    prompt=prompt,
                    output_path=(
                        output_path
                    ),
                    size="1K",
                    ratio="3:4",
                )

                if not (
                    output_path.exists()
                    and output_path.is_file()
                    and output_path.stat().st_size > 0
                ):

                    raise ReferenceImageError(
                        "Generated reference "
                        "image is invalid."
                    )

                return

            except AgnesAPIError as exc:

                status_code = getattr(
                    exc,
                    "status_code",
                    None,
                )

                retryable = bool(
                    getattr(
                        exc,
                        "retryable",
                        False,
                    )
                )

                if (
                    retryable
                    or status_code
                    in {
                        429,
                        500,
                        502,
                        503,
                        504,
                    }
                ):

                    print(
                        "Reference image generation "
                        f"temporarily failed "
                        f"(attempt {attempt})."
                    )

                    print(
                        exc
                    )

                    print(
                        f"Retrying in "
                        f"{self.retry_delay}s..."
                    )

                    time.sleep(
                        self.retry_delay
                    )

                    continue

                raise ReferenceImageError(
                    "Unable to generate reference "
                    f"image for {character.name}: "
                    f"{exc}"
                ) from exc