"""Compatibility checks for Streamlit sessions surviving a source update."""

import importlib
import inspect
import sys


def _accepts_native_audio(function):
    parameters = inspect.signature(function).parameters
    return "native_audio" in parameters or any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    )


def ensure_generation_compatibility():
    pipeline = importlib.import_module("src.video_pipeline")
    generation = importlib.import_module("src.scene_video_production")
    pipeline_stale = (
        "native_audio" not in pipeline.PreparedScene.__dataclass_fields__
        or not _accepts_native_audio(pipeline.VideoPipeline.build_scene_prompt)
    )
    generation_stale = not _accepts_native_audio(generation.generate_scene_video)
    if pipeline_stale:
        importlib.reload(pipeline)
    if pipeline_stale or generation_stale:
        importlib.reload(generation)
        for module in ("src.studio.actions", "src.studio.views"):
            if module in sys.modules:
                importlib.reload(sys.modules[module])
