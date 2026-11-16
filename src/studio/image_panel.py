from __future__ import annotations
from io import BytesIO
import streamlit as st
from src.studio.layout import SCENE_PANEL_HEIGHT
from src.agnes_client import AgnesAPIError
from src.scene_image_generator import build_scene_image_prompt, generate_scene_image
from src.production_state import (
    ProductionStateError,
    invalidate_scene_image,
    is_scene_image_validated,
    validate_scene_image,
)
from src.studio.actions import (
    delete_final_video,
    delete_scene_reference,
    get_agnes,
    get_current_job_id,
    get_scene_reference,
    persist_production_state,
    save_scene_reference,
)


def render_image_panel(
    scene, production_state, image_path, direction, include_scene, job, plan
):
    st.subheader("Image de scène")
    image_validated = is_scene_image_validated(
        production_state, scene.number, image_path
    )
    with st.container(
        height=SCENE_PANEL_HEIGHT, border=True, key=f"scene_image_frame_{scene.number}"
    ):
        if image_path is not None:
            st.image(str(image_path), use_container_width=True)
        else:
            st.info("Importe une image pour définir le premier plan de la scène.")
    if image_path is not None:
        if image_validated:
            st.caption("Image validée")
        else:
            st.caption("Image à valider")
    with st.expander("Importer ou modifier l’image", expanded=image_path is None):
        if direction is not None:
            with st.expander("Prompt image"):
                st.write(direction.image_prompt)
        with st.expander("Générer une image (facultatif)"):
            generation_prompt = st.text_area(
                "Prompt pour générer l'image",
                value=build_scene_image_prompt(plan, scene, direction),
                key=f"scene_image_prompt_{get_current_job_id()}_{scene.number}",
                height=150,
            )
            st.caption(
                "Les personnages sont décrits par texte. Vérifie leur apparence avant de valider l'image générée."
            )
            if st.button(
                "Régénérer l'image" if image_path else "Générer l'image",
                key=f"generate_scene_image_{get_current_job_id()}_{scene.number}",
                disabled=not include_scene or not generation_prompt.strip(),
                use_container_width=False,
            ):
                try:
                    with st.spinner("Génération de l'image de scène..."):
                        generated = BytesIO(
                            generate_scene_image(
                                get_agnes(),
                                generation_prompt,
                                st.session_state.aspect_ratio,
                            )
                        )
                        generated.name = "generated.png"
                        save_scene_reference(generated, scene.number)
                        production_state = invalidate_scene_image(
                            production_state, scene.number
                        )
                        persist_production_state(production_state)
                    st.rerun()
                except (AgnesAPIError, OSError, ValueError) as exc:
                    st.error(f"Impossible de générer l'image : {exc}")
        uploaded = st.file_uploader(
            "Importer / remplacer l'image",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"scene_upload_{get_current_job_id()}_{scene.number}",
        )
        if uploaded is not None:
            st.image(
                uploaded.getvalue(),
                caption="Aperçu du fichier sélectionné",
                use_container_width=True,
            )
            st.caption(
                "Clique sur « Enregistrer cette image » pour l'appliquer à la scène."
            )
            if st.button(
                "Enregistrer cette image",
                key=f"save_scene_image_{get_current_job_id()}_{scene.number}",
                type="primary",
                use_container_width=False,
            ):
                if image_path is not None and image_path.read_bytes() == uploaded.getvalue():
                    st.toast("Cette image est déjà enregistrée. La vidéo est conservée.")
                    return production_state
                save_scene_reference(uploaded, scene.number)
                # Auto-valide l'image dès l'enregistrement
                new_image_path = get_scene_reference(job, scene.number)
                try:
                    production_state = validate_scene_image(
                        production_state, scene.number, new_image_path
                    )
                except Exception:
                    production_state = invalidate_scene_image(
                        production_state, scene.number
                    )
                persist_production_state(production_state)
                st.rerun()
    image_button1 = image_button2 = st.container(horizontal=True)
    with image_button1:
        if image_path is not None:
            if image_validated:
                if st.button(
                    "Retirer validation",
                    key=f"unvalidate_scene_image_{get_current_job_id()}_{scene.number}",
                    use_container_width=False,
                ):
                    production_state = invalidate_scene_image(
                        production_state, scene.number
                    )
                    persist_production_state(production_state)
                    delete_final_video(job)
                    st.rerun()
            elif st.button(
                "Valider l'image",
                key=f"validate_scene_image_{get_current_job_id()}_{scene.number}",
                type="primary",
                use_container_width=False,
            ):
                try:
                    production_state = validate_scene_image(
                        production_state, scene.number, image_path
                    )
                    persist_production_state(production_state)
                    st.rerun()
                except ProductionStateError as exc:
                    st.error(str(exc))
    with image_button2:
        if image_path is not None:
            if st.button(
                "Supprimer",
                key=f"delete_scene_image_{get_current_job_id()}_{scene.number}",
                use_container_width=False,
            ):
                delete_scene_reference(scene.number)
                production_state = invalidate_scene_image(
                    production_state, scene.number
                )
                persist_production_state(production_state)
                st.rerun()
    st.caption(
        "Après génération ou remplacement, valide l'image puis le prompt d'animation pour rendre la scène prête."
    )
    return production_state
