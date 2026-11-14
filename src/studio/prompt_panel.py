from __future__ import annotations
from dataclasses import replace
import streamlit as st
from src.studio.layout import SCENE_PANEL_HEIGHT
from src.scene_prompt_analysis import analyze_scene_prompt
from src.production_state import invalidate_scene_content
from src.studio.actions import (
    get_current_job_id,
    invalidate_scene_video_output,
    persist_production_state,
    replace_scene_in_plan,
    save_plan,
)


def render_prompt_panel(scene, plan, production_state, job):
    st.subheader("Prompt scène")
    with st.form(
        key=f"story_form_{get_current_job_id()}_{scene.number}",
        height=SCENE_PANEL_HEIGHT,
    ):
        visual_prompt = st.text_area(
            "Prompt scène — action, caméra, ambiance et dialogue",
            value=scene.visual_prompt,
            height=560,
            key=f"scene_prompt_text_{get_current_job_id()}_{scene.number}",
            label_visibility="collapsed",
            placeholder="Décris l’action, la caméra, l’ambiance et les paroles…",
        )
        duration_column, save_column = st.columns([1, 2], vertical_alignment="bottom")
        duration = duration_column.number_input(
            "Durée (secondes)",
            min_value=4,
            max_value=12,
            value=int(scene.duration),
            step=1,
        )
        speaker_id = scene.speaker_id or ""
        use_previous_frame = scene.use_previous_frame
        start_state = scene.start_state
        end_state = scene.end_state
        with save_column:
            save_story = st.form_submit_button(
                (
                    "Enregistrer le prompt"
                    if st.session_state.audio_mode == "Agnes natif"
                    else "Analyser et enregistrer le prompt"
                ),
                use_container_width=False,
            )
    if save_story:
        if visual_prompt == scene.visual_prompt and int(duration) == scene.duration:
            st.toast("Le prompt est déjà enregistré. La vidéo est conservée.")
            return production_state
        analysis = analyze_scene_prompt(visual_prompt)
        dialogue = "\n".join((turn.dialogue for turn in analysis.turns))
        speakers = list(dict.fromkeys((turn.speaker for turn in analysis.turns)))
        speaker_id = speakers[0] if len(speakers) == 1 else ""
        updated_scene = replace(
            scene,
            duration=int(duration),
            visual_prompt=visual_prompt,
            dialogue=dialogue.strip(),
            speaker_id=speaker_id.strip() or None,
            use_previous_frame=bool(use_previous_frame),
            start_state=start_state.strip(),
            end_state=end_state.strip(),
        )
        updated_plan = replace_scene_in_plan(plan, updated_scene)
        save_plan(updated_plan)
        production_state = invalidate_scene_content(production_state, scene.number)
        persist_production_state(production_state)
        invalidate_scene_video_output(job, scene.number)
        st.rerun()
    return production_state
