from __future__ import annotations
import os
import streamlit as st
from src import config
from src.elevenlabs_voice import ElevenLabsVoiceGenerator
from src.voice_generator import VoiceGenerationError
from src.studio.actions import get_job, load_director_plan, synchronize_job


def render_sidebar():
    with st.sidebar:
        st.caption(f"Studio {config.STUDIO_INSTANCE} · Compte Agnes {config.STUDIO_INSTANCE}")
        st.caption("Projets partagés entre les deux studios. Modifie un même projet dans un seul studio à la fois.")
        st.header("Projet")
        st.text_input(
            "Nom du projet",
            key="job_id",
            help="Dossier du projet : toutes ses scènes y sont conservées séparément (scene_01.mp4, scene_02.mp4…). Changer ce nom ouvre un autre projet.",
        )
        synchronize_job()
        st.selectbox("Format", ("9:16", "16:9"), key="aspect_ratio")
        st.selectbox("Taille vidéo", ("720P",), key="video_size")
        st.divider()
        st.subheader("Audio")
        st.selectbox("Mode audio", ("Agnes natif", "Voix contrôlées"), key="audio_mode")
        if st.session_state.audio_mode == "Agnes natif":
            st.caption(
                "Pour régler précisément la vitesse de la voix (×0,25 à ×2), sélectionne le mode Voix contrôlées."
            )
            st.caption(
                "Prompt complet, avec ou sans image → vidéo avec audio généré par Agnes. Vérifie les paroles et les voix dans le résultat."
            )
        if st.session_state.audio_mode != "Agnes natif":
            st.selectbox(
                "Vitesse de la voix",
                (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0),
                key="audio_speed",
                format_func=lambda speed: f"×{speed:g}".replace(".", ","),
                help="×1 : normale ; ×0,25 : quatre fois plus lente ; ×1,25 : 25 % plus rapide.",
            )
            st.caption(
                "S'applique aux aperçus et aux prochaines générations de voix, en conservant la hauteur. "
                "Une voix ralentie demande plus de temps dans la scène. Régénère un clip existant pour modifier sa voix."
            )
            st.selectbox(
                "Service vocal", ("ElevenLabs", "Microsoft Edge"), key="voice_provider"
            )
            if st.session_state.voice_provider == "ElevenLabs":
                if not os.getenv("ELEVENLABS_API_KEY"):
                    st.info("Ajoute ELEVENLABS_API_KEY dans .env, puis relance l'app.")
                st.selectbox(
                    "Modèle vocal",
                    ("eleven_multilingual_v2", "eleven_v3"),
                    key="eleven_model",
                    format_func=lambda value: (
                        "Multilingual v2 — naturel"
                        if value == "eleven_multilingual_v2"
                        else "Eleven v3 — expressif"
                    ),
                )
                if st.button("Charger mes voix ElevenLabs"):
                    try:
                        st.session_state["eleven_voices"] = ElevenLabsVoiceGenerator(
                            "", get_job().job_dir / "voice_cache"
                        ).list_voices()
                    except VoiceGenerationError as exc:
                        st.error(str(exc))
                voices = st.session_state.get("eleven_voices", [])
                if voices:
                    names = {
                        v["voice_id"]: v.get("name", v["voice_id"]) for v in voices
                    }
                    chosen = st.selectbox(
                        "Voix du compte",
                        list(names),
                        format_func=lambda vid: names[vid],
                    )
                    if st.button("Utiliser cette voix"):
                        st.session_state["eleven_voice_id"] = chosen
                st.text_input("Identifiant de voix ElevenLabs", key="eleven_voice_id")
                st.caption(
                    "Choisis une voix française. Les aperçus utilisent tes crédits ElevenLabs et sont réutilisés pour la vidéo."
                )
            if st.session_state.voice_provider == "Microsoft Edge":
                st.selectbox(
                    "Voix",
                    ("fr-FR-HenriNeural", "fr-FR-DeniseNeural", "fr-FR-EloiseNeural"),
                    key="voice",
                )
                st.selectbox(
                    "Hauteur",
                    ("-15Hz", "-10Hz", "-5Hz", "+0Hz", "+5Hz", "+10Hz"),
                    key="speech_pitch",
                )
        st.divider()
        if st.button("Charger le projet", use_container_width=True):
            job = get_job()
            if not job.has_plan():
                st.info("Ce projet est vide. Ajoute ta première scène dans le studio.")
            else:
                try:
                    st.session_state["plan"] = job.load_plan()
                    st.session_state["director_plan"] = None
                    st.session_state["prepared"] = None
                    load_director_plan()
                    st.success("Projet chargé.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
