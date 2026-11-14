from __future__ import annotations

import hashlib
import json

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Optional

from src.scene_planner import Scene, VideoPlan
from src.scene_prompt_analysis import analyze_scene_prompt


PRODUCTION_STATE_SCHEMA_VERSION = 1


class ProductionStateError(Exception):
    pass


@dataclass(frozen=True)
class CharacterProductionState:
    character_id: str
    reference_path: str = ""
    validated_sha256: str = ""


@dataclass(frozen=True)
class SceneProductionState:
    scene_number: int
    included: bool = False
    image_validated_sha256: str = ""
    scene_validated_signature: str = ""
    video_validated_sha256: str = ""
    use_reference_image: bool = True


@dataclass(frozen=True)
class ProductionState:
    characters: dict[str, CharacterProductionState] = field(
        default_factory=dict
    )
    scenes: dict[int, SceneProductionState] = field(
        default_factory=dict
    )


def file_sha256(path: Path) -> str:
    path = Path(path)

    if not (
        path.exists()
        and path.is_file()
        and path.stat().st_size > 0
    ):
        return ""

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()


def scene_signature(scene: Scene) -> str:
    payload = {
        "number": scene.number,
        "duration": scene.duration,
        "visual_prompt": scene.visual_prompt,
        "dialogue": scene.dialogue,
        "speaker_id": scene.speaker_id,
        "character_ids": list(scene.character_ids),
        "start_state": scene.start_state,
        "end_state": scene.end_state,
        "use_previous_frame": scene.use_previous_frame,
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def load_production_state(path: Path) -> ProductionState:
    path = Path(path)

    if not path.exists():
        return ProductionState()

    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise ProductionStateError(
            f"Unable to load production state: {exc}"
        ) from exc

    if data.get("schema_version") != PRODUCTION_STATE_SCHEMA_VERSION:
        return ProductionState()

    characters: dict[str, CharacterProductionState] = {}

    for character_id, raw in (
        data.get("characters", {}) or {}
    ).items():
        if not isinstance(raw, dict):
            continue

        characters[str(character_id)] = (
            CharacterProductionState(
                character_id=str(character_id),
                reference_path=str(
                    raw.get("reference_path", "") or ""
                ),
                validated_sha256=str(
                    raw.get("validated_sha256", "") or ""
                ),
            )
        )

    scenes: dict[int, SceneProductionState] = {}

    for scene_number, raw in (
        data.get("scenes", {}) or {}
    ).items():
        if not isinstance(raw, dict):
            continue

        try:
            number = int(scene_number)
        except (TypeError, ValueError):
            continue

        scenes[number] = SceneProductionState(
            scene_number=number,
            use_reference_image=bool(raw.get("use_reference_image", True)),
            included=bool(raw.get("included", False)),
            image_validated_sha256=str(
                raw.get("image_validated_sha256", "") or ""
            ),
            scene_validated_signature=str(
                raw.get("scene_validated_signature", "") or ""
            ),
            video_validated_sha256=str(raw.get("video_validated_sha256", "") or ""),
        )

    return ProductionState(
        characters=characters,
        scenes=scenes,
    )


def save_production_state(
    state: ProductionState,
    path: Path,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": PRODUCTION_STATE_SCHEMA_VERSION,
        "characters": {
            character_id: asdict(character_state)
            for character_id, character_state
            in state.characters.items()
        },
        "scenes": {
            str(scene_number): asdict(scene_state)
            for scene_number, scene_state
            in state.scenes.items()
        },
    }

    temporary = Path(str(path) + ".tmp")

    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)


def sync_production_state(
    state: ProductionState,
    plan: VideoPlan,
) -> ProductionState:
    characters: dict[str, CharacterProductionState] = {}

    for character in plan.characters:
        characters[character.id] = state.characters.get(
            character.id,
            CharacterProductionState(
                character_id=character.id,
            ),
        )

    scenes: dict[int, SceneProductionState] = {}

    for scene in plan.scenes:
        scenes[scene.number] = state.scenes.get(
            scene.number,
            SceneProductionState(
                scene_number=scene.number,
                included=False,
            ),
        )

    return ProductionState(
        characters=characters,
        scenes=scenes,
    )


def set_character_reference_path(
    state: ProductionState,
    character_id: str,
    path: Optional[Path],
    invalidate_validation: bool = True,
) -> ProductionState:
    characters = dict(state.characters)

    current = characters.get(
        character_id,
        CharacterProductionState(
            character_id=character_id,
        ),
    )

    characters[character_id] = CharacterProductionState(
        character_id=character_id,
        reference_path=(
            str(Path(path).resolve())
            if path is not None
            else ""
        ),
        validated_sha256=(
            ""
            if invalidate_validation
            else current.validated_sha256
        ),
    )

    return ProductionState(
        characters=characters,
        scenes=dict(state.scenes),
    )


def validate_character_reference(
    state: ProductionState,
    character_id: str,
    path: Path,
) -> ProductionState:
    digest = file_sha256(path)

    if not digest:
        raise ProductionStateError(
            "Character reference image is missing or invalid."
        )

    characters = dict(state.characters)

    characters[character_id] = CharacterProductionState(
        character_id=character_id,
        reference_path=str(Path(path).resolve()),
        validated_sha256=digest,
    )

    return ProductionState(
        characters=characters,
        scenes=dict(state.scenes),
    )


def unvalidate_character_reference(
    state: ProductionState,
    character_id: str,
) -> ProductionState:
    characters = dict(state.characters)

    current = characters.get(
        character_id,
        CharacterProductionState(
            character_id=character_id,
        ),
    )

    characters[character_id] = CharacterProductionState(
        character_id=character_id,
        reference_path=current.reference_path,
        validated_sha256="",
    )

    return ProductionState(
        characters=characters,
        scenes=dict(state.scenes),
    )


def is_character_reference_validated(
    state: ProductionState,
    character_id: str,
) -> bool:
    item = state.characters.get(character_id)

    if item is None or not item.reference_path:
        return False

    path = Path(item.reference_path)
    current_hash = file_sha256(path)

    return bool(
        current_hash
        and item.validated_sha256
        and current_hash == item.validated_sha256
    )


def set_scene_included(
    state: ProductionState,
    scene_number: int,
    included: bool,
) -> ProductionState:
    scenes = dict(state.scenes)

    current = scenes.get(
        scene_number,
        SceneProductionState(
            scene_number=scene_number,
        ),
    )

    scenes[scene_number] = SceneProductionState(
        scene_number=scene_number,
        included=bool(included),
        use_reference_image=current.use_reference_image,
        image_validated_sha256=current.image_validated_sha256,
        scene_validated_signature=current.scene_validated_signature,
        video_validated_sha256=current.video_validated_sha256,
    )

    return ProductionState(
        characters=dict(state.characters),
        scenes=scenes,
    )


def invalidate_scene_image(
    state: ProductionState,
    scene_number: int,
) -> ProductionState:
    scenes = dict(state.scenes)

    current = scenes.get(
        scene_number,
        SceneProductionState(
            scene_number=scene_number,
        ),
    )

    scenes[scene_number] = SceneProductionState(
        scene_number=scene_number,
        included=current.included,
        image_validated_sha256="",
        use_reference_image=current.use_reference_image,
        scene_validated_signature="",
    )

    return ProductionState(
        characters=dict(state.characters),
        scenes=scenes,
    )


def validate_scene_image(
    state: ProductionState,
    scene_number: int,
    path: Path,
) -> ProductionState:
    digest = file_sha256(path)

    if not digest:
        raise ProductionStateError(
            "Scene image is missing or invalid."
        )

    scenes = dict(state.scenes)

    current = scenes.get(
        scene_number,
        SceneProductionState(
            scene_number=scene_number,
        ),
    )

    scenes[scene_number] = SceneProductionState(
        scene_number=scene_number,
        included=current.included,
        image_validated_sha256=digest,
        use_reference_image=current.use_reference_image,
        scene_validated_signature=current.scene_validated_signature,
    )

    return ProductionState(
        characters=dict(state.characters),
        scenes=scenes,
    )


def is_scene_image_validated(
    state: ProductionState,
    scene_number: int,
    path: Optional[Path],
) -> bool:
    if path is None:
        return False

    item = state.scenes.get(scene_number)

    if item is None:
        return False

    current_hash = file_sha256(path)

    return bool(
        current_hash
        and item.image_validated_sha256
        and current_hash == item.image_validated_sha256
    )


def validate_scene_content(
    state: ProductionState,
    scene: Scene,
) -> ProductionState:
    scenes = dict(state.scenes)

    current = scenes.get(
        scene.number,
        SceneProductionState(
            scene_number=scene.number,
        ),
    )

    scenes[scene.number] = SceneProductionState(
        scene_number=scene.number,
        included=current.included,
        use_reference_image=current.use_reference_image,
        image_validated_sha256=current.image_validated_sha256,
        scene_validated_signature=scene_signature(scene),
    )

    return ProductionState(
        characters=dict(state.characters),
        scenes=scenes,
    )


def invalidate_scene_content(
    state: ProductionState,
    scene_number: int,
) -> ProductionState:
    scenes = dict(state.scenes)

    current = scenes.get(
        scene_number,
        SceneProductionState(
            scene_number=scene_number,
        ),
    )

    scenes[scene_number] = SceneProductionState(
        scene_number=scene_number,
        included=current.included,
        image_validated_sha256=current.image_validated_sha256,
        scene_validated_signature="",
        use_reference_image=current.use_reference_image,
    )

    return ProductionState(
        characters=dict(state.characters),
        scenes=scenes,
    )


def is_scene_content_validated(
    state: ProductionState,
    scene: Scene,
) -> bool:
    item = state.scenes.get(scene.number)

    if item is None:
        return False

    return bool(
        item.scene_validated_signature
        and item.scene_validated_signature
        == scene_signature(scene)
    )


def invalidate_scenes_for_character(
    state: ProductionState,
    plan: VideoPlan,
    character_id: str,
) -> ProductionState:
    result = state

    for scene in plan.scenes:
        if character_id in scene.character_ids:
            result = invalidate_scene_image(
                result,
                scene.number,
            )

    return result


def scene_required_characters_validated(
    state: ProductionState,
    scene: Scene,
) -> bool:
    return all(
        is_character_reference_validated(
            state,
            character_id,
        )
        for character_id in scene.character_ids
    )


def scene_is_ready(
    state: ProductionState,
    scene: Scene,
    scene_image_path: Optional[Path],
) -> bool:
    item = state.scenes.get(scene.number)

    if item is None or not item.included:
        return False

    if not (scene.visual_prompt or "").strip():
        return False

    if not (4 <= int(scene.duration) <= 12):
        return False

    if item.use_reference_image and not is_scene_image_validated(
        state,
        scene.number,
        scene_image_path,
    ):
        return False

    if not is_scene_content_validated(
        state,
        scene,
    ):
        return False

    return True


def invalidate_scene_video(state: ProductionState, scene_number: int) -> ProductionState:
    scenes = dict(state.scenes)
    scenes[scene_number] = replace(scenes[scene_number], video_validated_sha256="")
    return replace(state, scenes=scenes)


def set_scene_reference_mode(state: ProductionState, scene_number: int, use_image: bool) -> ProductionState:
    current = state.scenes[scene_number]
    if current.use_reference_image == use_image:
        return state
    scenes = dict(state.scenes)
    scenes[scene_number] = replace(
        current, use_reference_image=use_image,
        scene_validated_signature="", video_validated_sha256="",
    )
    return replace(state, scenes=scenes)


def validate_scene_video(
    state: ProductionState, scene: Scene, image_path: Optional[Path], video_path: Path,
) -> ProductionState:
    if not scene_is_ready(state, scene, image_path):
        raise ProductionStateError("La scène doit être prête avant de valider sa vidéo.")
    digest = file_sha256(video_path)
    if not digest:
        raise ProductionStateError("La vidéo est absente ou vide.")
    scenes = dict(state.scenes)
    scenes[scene.number] = replace(scenes[scene.number], video_validated_sha256=digest)
    return replace(state, scenes=scenes)


def is_scene_video_validated(
    state: ProductionState, scene: Scene, image_path: Optional[Path], video_path: Path,
) -> bool:
    return bool(
        scene_is_ready(state, scene, image_path)
        and state.scenes[scene.number].video_validated_sha256
        and state.scenes[scene.number].video_validated_sha256 == file_sha256(video_path)
    )
