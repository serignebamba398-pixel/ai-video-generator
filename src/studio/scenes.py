from __future__ import annotations
from dataclasses import replace
import streamlit as st
from src.production_state import sync_production_state
from src.scene_planner import Scene
from src.studio.actions import get_current_job_id, persist_production_state, save_plan
from src.studio.scene_editor import render_scene


def render_scenes(plan, production_state, director_plan):
    if plan is not None and production_state is not None:
        st.header("Mes scènes")
        with st.form(f"add_scenes_{get_current_job_id()}"):
            additional_count = st.number_input(
                "Nombre de scènes à ajouter", min_value=1, value=1, step=1
            )
            st.caption(
                "Ajoute des scènes au projet, puis sélectionne celles à produire."
            )
            if st.form_submit_button("Ajouter des scènes"):
                next_number = max((s.number for s in plan.scenes), default=0) + 1
                plan = replace(
                    plan,
                    scenes=plan.scenes
                    + [
                        Scene(number=next_number + offset, duration=8, visual_prompt="")
                        for offset in range(int(additional_count))
                    ],
                )
                save_plan(plan)
                production_state = sync_production_state(production_state, plan)
                persist_production_state(production_state)
                st.rerun()
        if not plan.scenes:
            st.info(
                "Commence par ajouter une scène. Importe une image, écris ton prompt, puis génère et valide le clip."
            )
        else:
            st.caption(
                f"{len(plan.scenes)} scènes · Image, animation et validation réunies pour chaque plan."
            )
        for scene in plan.scenes:
            production_state = render_scene(
                scene, plan, production_state, director_plan
            )
    return (plan, production_state)
