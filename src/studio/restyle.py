from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from src.agnes_client import AgnesClient, AgnesAPIError
from src.config import UPLOADS_DIR


def render_restyle() -> None:
    st.title("Restyle — Changer les personnages")
    st.caption(
        "Upload une vidéo existante, décris les nouveaux personnages, "
        "et Agnes génère une nouvelle version en conservant les mouvements et actions."
    )

    st.info(
        "Utilise le modèle **Agnes Video 2.5** (non-Flash) qui supporte "
        "les vidéos de référence. La vidéo source garde ses mouvements, "
        "actions et cadrage. Seuls les personnages changent."
    )

    # ----------------------------------------------------------------
    # Vidéo de référence
    # ----------------------------------------------------------------
    st.subheader("1. Vidéo de référence")
    video_file = st.file_uploader(
        "Upload la vidéo source (MP4, MOV, WebM)",
        type=["mp4", "mov", "webm"],
        key="restyle_video",
    )

    # ----------------------------------------------------------------
    # Images de référence des personnages (optionnel)
    # ----------------------------------------------------------------
    st.subheader("2. Images de référence des nouveaux personnages (optionnel)")
    st.caption("Max 5 images — Soren, Mira, Elya, etc.")
    character_images = st.file_uploader(
        "Upload les images de référence",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="restyle_characters",
    )
    if len(character_images) > 5:
        st.error("Maximum 5 images de référence.")
        character_images = character_images[:5]

    # ----------------------------------------------------------------
    # Prompt
    # ----------------------------------------------------------------
    st.subheader("3. Décris les nouveaux personnages")
    prompt = st.text_area(
        "Prompt",
        placeholder=(
            "Remplace les personnages par Soren (guerrier viking aux cheveux blonds, "
            "armure nordique) et Mira (femme viking aux cheveux roux). "
            "Conserve exactement les mouvements, actions, cadrage et mise en scène de la vidéo originale."
        ),
        height=120,
        key="restyle_prompt",
    )

    # ----------------------------------------------------------------
    # Paramètres
    # ----------------------------------------------------------------
    st.subheader("4. Paramètres")
    col1, col2, col3 = st.columns(3)
    with col1:
        seconds = st.number_input("Durée (secondes)", min_value=2, max_value=30, value=8, key="restyle_seconds")
    with col2:
        size = st.selectbox("Résolution", ["720P", "1080P", "480P"], key="restyle_size")
    with col3:
        aspect_ratio = st.selectbox("Format", ["16:9", "9:16", "1:1", "4:3"], key="restyle_ratio")

    # ----------------------------------------------------------------
    # Génération
    # ----------------------------------------------------------------
    st.divider()
    can_generate = video_file is not None and prompt.strip()
    if not can_generate:
        st.warning("Upload une vidéo et écris un prompt pour continuer.")

    if st.button(
        "Générer la nouvelle version",
        type="primary",
        disabled=not can_generate,
        use_container_width=True,
    ):
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

        # Sauvegarde la vidéo uploadée
        video_path = UPLOADS_DIR / video_file.name
        video_path.write_bytes(video_file.read())

        # Sauvegarde les images de personnages
        char_paths: list[Path] = []
        for img in character_images:
            img_path = UPLOADS_DIR / img.name
            img_path.write_bytes(img.read())
            char_paths.append(img_path)

        client = AgnesClient()

        with st.spinner("Envoi à Agnes Video 2.5... (peut prendre 2-5 minutes)"):
            try:
                video_id = client.create_video_to_video(
                    prompt=prompt.strip(),
                    reference_video_path=video_path,
                    seconds=int(seconds),
                    size=size,
                    aspect_ratio=aspect_ratio,
                    character_image_paths=char_paths or None,
                )
            except AgnesAPIError as exc:
                st.error(f"Erreur Agnes : {exc}")
                return

        with st.spinner("Génération en cours..."):
            try:
                video_url = client.wait_for_video(
                    video_id=video_id,
                    polling_interval=5,
                    timeout=600,
                    progress_callback=lambda status, progress: st.caption(
                        f"Statut : {status} — {progress}%"
                    ),
                )
            except AgnesAPIError as exc:
                st.error(f"Erreur génération : {exc}")
                return

        output_path = UPLOADS_DIR / f"restyle_{video_id[:8]}.mp4"

        with st.spinner("Téléchargement de la vidéo..."):
            try:
                client.download_video(video_url, output_path)
            except AgnesAPIError as exc:
                st.error(f"Erreur téléchargement : {exc}")
                return

        st.success("Vidéo générée !")
        st.video(str(output_path))
        st.download_button(
            label="Télécharger la vidéo restylisée",
            data=output_path.read_bytes(),
            file_name=f"restyle_{video_id[:8]}.mp4",
            mime="video/mp4",
            use_container_width=True,
        )
