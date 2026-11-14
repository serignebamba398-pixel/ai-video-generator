from dataclasses import replace
from pathlib import Path

from src.director import apply_director_plan
from src.production_state import ProductionStateError, scene_is_ready
from src.video_pipeline import PreparedScene


def generate_scene_video(
    *, plan, scene, state, image_path, pipeline, dialogue_rewriter,
    job_id, aspect_ratio, size, director_plan=None, progress_callback=None,
    prepared_callback=None, native_audio=False,
):
    """Prepare and submit only the requested, validated scene; resume pending tasks."""
    if not scene_is_ready(state, scene, image_path):
        raise ProductionStateError("Valide le prompt et, en mode avec image, l'image de cette scène.")
    if not state.scenes[scene.number].use_reference_image:
        image_path = None
        scene = replace(scene, use_previous_frame=False)
    production_plan = replace(plan, scenes=[scene])
    if director_plan is not None:
        production_plan = apply_director_plan(production_plan, director_plan)
    if native_audio:
        final_plan = production_plan
        prepared = [PreparedScene(
            scene=production_plan.scenes[0], audio_path=None, speech_duration=0,
            scene_reference_image_path=Path(image_path) if image_path is not None else None, native_audio=True,
        )]
    else:
        final_plan, prepared = pipeline.prepare_plan(
            plan=production_plan,
            dialogue_rewriter=None,
            reference_images={},
            scene_reference_images={scene.number: Path(image_path)} if image_path is not None else {},
            preserve_scene_durations=True,
        )
    if prepared_callback is not None:
        prepared_callback(prepared)
    return pipeline.generate_scenes(
        plan=final_plan, prepared_scenes=prepared,
        aspect_ratio=aspect_ratio, size=size, job_id=job_id,
        resume=True, cooldown_seconds=45, progress_callback=progress_callback,
    )
