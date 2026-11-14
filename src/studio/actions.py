from __future__ import annotations
from src import config
from dataclasses import replace
from pathlib import Path
from typing import Optional
import streamlit as st
from src.agnes_client import AgnesClient
from src.audio_speed import TempoVoiceGenerator
from src import scene_video_production
from src.elevenlabs_voice import ElevenLabsVoiceGenerator
from src.dialogue_voices import DialogueVoiceGenerator, load_voices, scene_turns
from src.director import DirectorError, DirectorPlan, DirectorPlanner, SceneDirection
from src.job_manager import JobManager
from src.production_state import (
    ProductionState,
    is_scene_video_validated,
    load_production_state,
    save_production_state,
    scene_is_ready,
    sync_production_state,
)
from src.scene_planner import Scene, ScenePlanner, VideoPlan
from src.video_pipeline import VideoPipeline
from src.video_artifacts import archive_final_outputs, archive_scene_outputs

PROJECT_DIR = Path(__file__).resolve().parents[2]
UPLOADS_DIR = config.UPLOADS_DIR
DEFAULT_STATE = {
    "job_id": "project_001",
    "loaded_job_id": None,
    "source_prompt": "",
    "target_duration": 60,
    "aspect_ratio": "9:16",
    "video_size": "720P",
    "voice": "fr-FR-HenriNeural",
    "speech_rate": "+0%",
    "audio_speed": 1.0,
    "speech_pitch": "+0Hz",
    "plan": None,
    "director_plan": None,
    "prepared": None,
    "character_references": {},
}


def initialize_session():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_current_job_id() -> str:
    value = str(st.session_state.get("job_id", "project_001") or "").strip()
    return value or "project_001"


def get_job() -> JobManager:
    return JobManager(base_dir=config.OUTPUT_DIR, job_id=get_current_job_id())


def get_agnes() -> AgnesClient:
    return AgnesClient()


def get_planner() -> ScenePlanner:
    return ScenePlanner()


def get_pipeline(scene=None) -> VideoPipeline:
    pipeline = VideoPipeline(
        audio_dir=config.AUDIO_DIR,
        video_dir=config.OUTPUT_DIR,
        voice=st.session_state.voice,
        speech_rate="+0%",
        speech_pitch=st.session_state.speech_pitch,
        agnes_client=get_agnes(),
    )
    if st.session_state.get("voice_provider") == "ElevenLabs":
        pipeline.voice_generator = ElevenLabsVoiceGenerator(
            st.session_state.get("eleven_voice_id", ""),
            get_job().job_dir / "voice_cache",
            model=st.session_state.get("eleven_model", "eleven_multilingual_v2"),
        )
    if (
        scene is not None
        and scene.dialogue.strip()
        and (st.session_state.get("audio_mode") != "Agnes natif")
    ):
        voices = load_voices(get_job().job_dir)
        turns = scene_turns(scene)
        if len({t.speaker.casefold() for t in turns}) > 1 or any(
            (t.speaker.casefold() in voices for t in turns)
        ):
            pipeline.voice_generator = DialogueVoiceGenerator(
                scene,
                voices,
                get_job().job_dir / "voice_cache",
                st.session_state.get("eleven_model", "eleven_multilingual_v2"),
            )
    pipeline.voice_generator = TempoVoiceGenerator(
        pipeline.voice_generator, st.session_state.get("audio_speed", 1.0)
    )
    return pipeline


def source_prompt_path(job: JobManager) -> Path:
    return job.job_dir / "source_prompt.txt"


def director_plan_path(job: JobManager) -> Path:
    return job.job_dir / "director_plan.json"


def production_state_path(job: JobManager) -> Path:
    return job.job_dir / "production_state.json"


def scene_video_path(job: JobManager, scene_number: int) -> Path:
    return job.job_dir / f"scene_{scene_number:02d}.mp4"


def scene_reference_dir(job: JobManager) -> Path:
    path = job.job_dir / "scene_references"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_scene_reference(job: JobManager, scene_number: int) -> Optional[Path]:
    directory = scene_reference_dir(job)
    for extension in (".png", ".jpg", ".jpeg", ".webp"):
        path = directory / f"scene_{scene_number:02d}{extension}"
        if path.exists() and path.is_file() and (path.stat().st_size > 0):
            return path
    return None


def delete_final_video(job: JobManager) -> None:
    """Invalidate the current montage while preserving it in project history."""
    archive_final_outputs(job.job_dir)


def invalidate_scene_video_output(job: JobManager, scene_number: int) -> None:
    """
    A changed scene image or changed scene instructions make
    the previously generated clip stale.
    """
    archive_scene_outputs(job.job_dir, scene_number)
    delete_final_video(job)


def synchronize_job() -> None:
    """
    Synchronizes project-specific state after the Job ID
    changes.

    Never writes to session_state["job_id"] because the
    Streamlit Job ID widget has already been instantiated.
    """
    current_job_id = get_current_job_id()
    if st.session_state.get("loaded_job_id") == current_job_id:
        return
    st.session_state["loaded_job_id"] = current_job_id
    st.session_state["plan"] = None
    st.session_state["director_plan"] = None
    st.session_state["prepared"] = None
    st.session_state["character_references"] = {}
    job = JobManager(base_dir=config.OUTPUT_DIR, job_id=current_job_id)
    prompt_file = source_prompt_path(job)
    if prompt_file.exists():
        try:
            prompt = prompt_file.read_text(encoding="utf-8").strip()
        except OSError:
            prompt = ""
    else:
        prompt = ""
    st.session_state["source_prompt"] = prompt


def load_plan() -> Optional[VideoPlan]:
    current = st.session_state.get("plan")
    if current is not None:
        return current
    job = get_job()
    if not job.has_plan():
        return None
    try:
        plan = job.load_plan()
    except Exception:
        return None
    st.session_state["plan"] = plan
    return plan


def save_plan(plan: VideoPlan) -> None:
    job = get_job()
    job.save_plan(plan)
    st.session_state["plan"] = plan
    st.session_state["prepared"] = None


def replace_scene_in_plan(plan: VideoPlan, updated_scene: Scene) -> VideoPlan:
    scenes = []
    found = False
    for scene in plan.scenes:
        if scene.number == updated_scene.number:
            scenes.append(updated_scene)
            found = True
        else:
            scenes.append(scene)
    if not found:
        raise ValueError(f"Scène introuvable : {updated_scene.number}")
    return replace(plan, scenes=scenes)


def load_synced_production_state(plan: VideoPlan) -> ProductionState:
    job = get_job()
    path = production_state_path(job)
    state = load_production_state(path)
    synced = sync_production_state(state, plan)
    if synced != state:
        save_production_state(synced, path)
    return synced


def persist_production_state(state: ProductionState) -> None:
    save_production_state(state, production_state_path(get_job()))


def ready_scenes(plan: VideoPlan, state: ProductionState) -> list[Scene]:
    job = get_job()
    result = []
    for scene in plan.scenes:
        image_path = get_scene_reference(job, scene.number)
        if scene_is_ready(state, scene, image_path):
            result.append(scene)
    return result


def save_scene_reference(uploaded_file, scene_number: int) -> Path:
    job = get_job()
    current = get_scene_reference(job, scene_number)
    if current is not None and current.read_bytes() == uploaded_file.getvalue():
        return current
    directory = scene_reference_dir(job)
    for extension in (".png", ".jpg", ".jpeg", ".webp"):
        old_path = directory / f"scene_{scene_number:02d}{extension}"
        try:
            if old_path.exists():
                old_path.unlink()
        except OSError:
            pass
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".png"
    destination = directory / f"scene_{scene_number:02d}{suffix}"
    destination.write_bytes(uploaded_file.getvalue())
    invalidate_scene_video_output(job, scene_number)
    return destination


def delete_scene_reference(scene_number: int) -> None:
    job = get_job()
    path = get_scene_reference(job, scene_number)
    if path is not None:
        try:
            path.unlink()
        except OSError:
            pass
    invalidate_scene_video_output(job, scene_number)


def load_director_plan() -> Optional[DirectorPlan]:
    current = st.session_state.get("director_plan")
    if current is not None:
        return current
    path = director_plan_path(get_job())
    if not path.exists():
        return None
    try:
        director = DirectorPlanner.load(path)
    except DirectorError:
        return None
    st.session_state["director_plan"] = director
    return director


def save_director_plan(director_plan: DirectorPlan) -> None:
    DirectorPlanner.save(director_plan, director_plan_path(get_job()))
    st.session_state["director_plan"] = director_plan


def replace_scene_direction(
    director_plan: DirectorPlan, updated: SceneDirection
) -> DirectorPlan:
    scenes = []
    found = False
    for direction in director_plan.scenes:
        if direction.scene_number == updated.scene_number:
            scenes.append(updated)
            found = True
        else:
            scenes.append(direction)
    if not found:
        raise DirectorError(
            f"Mise en scène introuvable pour la scène {updated.scene_number}."
        )
    return replace(director_plan, scenes=scenes)


def run_scene_video(plan, scene, state, director_plan):
    job = get_job()
    status_box = st.empty()
    progress_bar = st.progress(0.0)

    def show_prepared(items):
        for item in items:
            if item.native_audio:
                st.caption(
                    "Agnes générera l'audio directement à partir du prompt, sans MP3 externe."
                )
                continue
            if item.audio_path is not None:
                st.caption(f"Voix prête — {item.speech_duration:.1f}s")
                st.write(item.scene.dialogue)
                st.audio(str(item.audio_path))
            else:
                st.caption("Scène silencieuse — aucun audio nécessaire")

    with st.spinner(f"Préparation et génération de la scène {scene.number}..."):
        scene_video_production.generate_scene_video(
            plan=plan,
            scene=scene,
            state=state,
            image_path=get_scene_reference(job, scene.number),
            pipeline=get_pipeline(scene),
            dialogue_rewriter=get_planner().rewrite_dialogue_for_duration,
            job_id=get_current_job_id(),
            aspect_ratio=st.session_state.aspect_ratio,
            size=st.session_state.video_size,
            director_plan=director_plan,
            progress_callback=create_progress_callback(status_box, progress_bar),
            prepared_callback=show_prepared,
            native_audio=st.session_state.get("audio_mode") == "Agnes natif",
        )
    delete_final_video(job)


def safe_density_index(density: str) -> int:
    values = ["none", "low", "medium", "high"]
    try:
        return values.index(density)
    except ValueError:
        return 0


def create_progress_callback(status_box, progress_bar):

    def callback(current: int, total: int, status: str, progress: int) -> None:
        readable = str(status).replace("_", " ")
        status_box.write(f"Scène {current}/{total} — {readable}")
        try:
            value = max(0.0, min(float(progress) / 100.0, 1.0))
            progress_bar.progress(value)
        except Exception:
            pass

    return callback


def scene_status_text(
    state: ProductionState, scene: Scene, image_path: Optional[Path], video_path: Path
) -> str:
    scene_state = state.scenes.get(scene.number)
    if scene_state is None or not scene_state.included:
        return "IGNORÉE"
    if scene_is_ready(state, scene, image_path):
        if video_path.exists() and video_path.stat().st_size > 0:
            if is_scene_video_validated(state, scene, image_path, video_path):
                return "VIDÉO VALIDÉE"
            return "VIDÉO À VALIDER"
        return "PRÊTE"
    return "À PRÉPARER"
