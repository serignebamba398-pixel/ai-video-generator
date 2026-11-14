from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from src.agnes_client import AgnesClient
from src.director import SceneDirection
from src.scene_planner import Scene, VideoPlan


def build_scene_image_prompt(
    plan: VideoPlan, scene: Scene, direction: SceneDirection | None = None,
) -> str:
    parts = [
        "Create one cinematic master frame for this scene. No collage, captions or watermarks.",
        f"Style: {plan.style_description}",
        f"Setting: {plan.setting_description}",
        f"Continuity: {plan.continuity_constraints}",
        f"Scene: {scene.visual_prompt}",
        f"Starting state: {scene.start_state}",
    ]
    for character_id in scene.character_ids:
        character = plan.character_map.get(character_id)
        if character:
            parts.append(f"Character {character.name}: {character.description}\n{character.reference_prompt}")
    if direction:
        parts.extend([
            f"Image direction: {direction.image_prompt}",
            f"Action: {direction.action}",
            f"Camera: {direction.camera}",
            f"Ambience: {direction.ambience}",
        ])
    return "\n\n".join(parts)


def generate_scene_image(client: AgnesClient, prompt: str, ratio: str) -> bytes:
    """Generate in isolation so failures cannot overwrite the current master frame."""
    from io import BytesIO

    if not prompt.strip():
        raise ValueError("Le prompt image ne peut pas être vide.")
    with TemporaryDirectory(prefix="scene_image_") as directory:
        path = Path(directory) / "generated.png"
        client.generate_image(prompt=prompt, output_path=path, ratio=ratio)
        with Image.open(path) as image:
            image.load()
            output = BytesIO()
            image.convert("RGB").save(output, format="PNG")
            return output.getvalue()
