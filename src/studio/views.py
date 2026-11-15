from __future__ import annotations
from src.studio.theme import apply_theme
from typing import Optional
import streamlit as st
from src.production_state import (
    ProductionState,
    ProductionStateError,
    sync_production_state,
)
from src.scene_planner import VideoPlan
from src.studio.actions import (
    get_current_job_id,
    initialize_session,
    load_director_plan,
    load_plan,
    load_synced_production_state,
)
from src.studio.scenes import render_scenes
from src.studio.settings import render_sidebar
from src.studio.delivery import render_delivery
from src.studio.restyle import render_restyle


def main():
    st.set_page_config(page_title="Studio — Scènes", layout="wide")
    apply_theme()
    initialize_session()
    render_sidebar()

    tab_studio, tab_restyle = st.tabs(["Studio", "Restyle"])

    with tab_studio:
        st.title("Studio de scènes")
        st.caption(
            "Ajoute tes scènes, importe leurs images, décris l'animation puis valide les vidéos."
        )
        plan = load_plan()
        if plan is None:
            plan = VideoPlan(
                title=get_current_job_id(),
                language="fr",
                character_description="",
                style_description="",
                setting_description="",
                continuity_constraints="",
                characters=[],
                scenes=[],
            )
        production_state: Optional[ProductionState] = None
        if plan is not None:
            try:
                production_state = load_synced_production_state(plan)
            except ProductionStateError as exc:
                st.error(str(exc))
                production_state = sync_production_state(ProductionState(), plan)
        director_plan = load_director_plan()
        plan, production_state = render_scenes(plan, production_state, director_plan)
        render_delivery(plan, production_state, director_plan)

    with tab_restyle:
        render_restyle()
