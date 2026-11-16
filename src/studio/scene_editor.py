from __future__ import annotations
from src.studio.image_panel import render_image_panel
from src.studio.prompt_panel import render_prompt_panel
import hashlib
from dataclasses import replace
import streamlit as st
from src.video_artifacts import latest_scene_video, scene_video_history
from src.scene_prompt_analysis import analyze_scene_prompt
from src.voice_generator import VoiceGenerationError
from src.dialogue_voices import load_voices, save_voices
from src.director import BackgroundPopulation
from src.production_state import (
    ProductionStateError,
    invalidate_scene_content,
    invalidate_scene_video,
    is_scene_video_validated,
    validate_scene_video,
    is_scene_content_validated,
    is_scene_image_validated,
    scene_is_ready,
    set_scene_included,
    set_scene_reference_mode,
    validate_scene_content,
)
from src.studio.actions import (
    delete_final_video,
    get_current_job_id,
    get_job,
    get_pipeline,
    get_scene_reference,
    invalidate_scene_video_output,
    persist_production_state,
    replace_scene_direction,
    replace_scene_in_plan,
    run_scene_video,
    safe_density_index,
    save_director_plan,
    save_plan,
    scene_status_text,
    scene_video_path,
)


def render_scene(scene, plan, production_state, director_plan):
    job = get_job()
    image_path = get_scene_reference(job, scene.number)
    video_path = scene_video_path(job, scene.number)
    direction = None
    if director_plan is not None:
        direction = director_plan.scene_map.get(scene.number)
    scene_state = production_state.scenes[scene.number]
    status = scene_status_text(production_state, scene, image_path, video_path)
    with st.expander(
        f"Scène {scene.number} — {scene.duration}s — {status}",
        expanded=scene.number == 1,
        key=f"scene_expander_{get_current_job_id()}_{scene.number}",
        on_change="rerun",
    ):
        include_key = f"include_scene_{get_current_job_id()}_{scene.number}"
        if include_key not in st.session_state:
            st.session_state[include_key] = scene_state.included
        include_scene = st.checkbox(
            "Inclure cette scène dans la vidéo", key=include_key
        )
        if include_scene != scene_state.included:
            production_state = set_scene_included(
                production_state, scene.number, include_scene
            )
            persist_production_state(production_state)
            delete_final_video(job)
            scene_state = production_state.scenes[scene.number]
        if not include_scene:
            st.caption("Hors montage · Coche cette scène pour la produire.")
        mode_key = f"scene_reference_mode_{get_current_job_id()}_{scene.number}"
        if mode_key not in st.session_state:
            st.session_state[mode_key] = scene_state.use_reference_image
        use_image = st.checkbox(
            "Utiliser une image de référence", key=mode_key,
            help="Décoche pour créer la vidéo à partir du prompt seul. L'image enregistrée est conservée.",
        )
        if use_image != scene_state.use_reference_image:
            production_state = set_scene_reference_mode(production_state, scene.number, use_image)
            persist_production_state(production_state)
            invalidate_scene_video_output(job, scene.number)
            st.rerun()
        image_column, story_column = st.columns([0.35, 0.65])
        with image_column:
            if use_image:
                production_state = render_image_panel(
                    scene, production_state, image_path, direction, include_scene, job, plan
                )
            else:
                st.info("Sans image : décris les personnages, le décor, l'action et la caméra dans le prompt.")
        with story_column:
            production_state = render_prompt_panel(scene, plan, production_state, job)
        if direction is not None:
            with st.expander("Mise en scène existante (facultatif)"):
                st.divider()
                st.subheader("Mise en scène")
                if direction is None:
                    st.info(
                        "La mise en scène automatique n'a pas encore été préparée. Elle reste facultative."
                    )
                else:
                    with st.form(
                        key=f"director_form_{get_current_job_id()}_{scene.number}"
                    ):
                        narrative_focus = st.text_area(
                            "Intention narrative",
                            value=direction.narrative_focus,
                            height=70,
                        )
                        image_prompt = st.text_area(
                            "Prompt de l'image",
                            value=direction.image_prompt,
                            height=180,
                        )
                        action = st.text_area(
                            "Action / beats visuels", value=direction.action, height=120
                        )
                        camera = st.text_area(
                            "Caméra", value=direction.camera, height=110
                        )
                        st.markdown("#### Figurants / arrière-plan")
                        background_enabled = st.checkbox(
                            "Population secondaire",
                            value=direction.background_population.enabled,
                        )
                        density_values = ["none", "low", "medium", "high"]
                        density = st.selectbox(
                            "Densité",
                            density_values,
                            index=safe_density_index(
                                direction.background_population.density
                            ),
                        )
                        background_description = st.text_area(
                            "Description des figurants",
                            value=direction.background_population.description,
                            height=90,
                        )
                        background_activity = st.text_area(
                            "Activité des figurants",
                            value=direction.background_population.activity,
                            height=90,
                        )
                        background_continuity = st.checkbox(
                            "Conserver les mêmes figurants",
                            value=direction.background_population.continuity_required,
                        )
                        ambience = st.text_area(
                            "Ambiance visuelle", value=direction.ambience, height=90
                        )
                        sound_design = st.text_area(
                            "Sound design prévu",
                            value=direction.sound_design,
                            height=90,
                        )
                        save_direction = st.form_submit_button(
                            "Sauvegarder la mise en scène", use_container_width=True
                        )
                    if save_direction:
                        updated_direction = replace(
                            direction,
                            narrative_focus=narrative_focus.strip(),
                            image_prompt=image_prompt.strip(),
                            action=action.strip(),
                            camera=camera.strip(),
                            background_population=BackgroundPopulation(
                                enabled=bool(background_enabled),
                                description=background_description.strip(),
                                density=density,
                                activity=background_activity.strip(),
                                continuity_required=bool(background_continuity),
                            ),
                            ambience=ambience.strip(),
                            sound_design=sound_design.strip(),
                        )
                        if updated_direction == direction:
                            st.toast("La mise en scène est déjà enregistrée.")
                            st.rerun()
                        director_plan = replace_scene_direction(
                            director_plan, updated_direction
                        )
                        save_director_plan(director_plan)
                        production_state = invalidate_scene_content(
                            production_state, scene.number
                        )
                        persist_production_state(production_state)
                        invalidate_scene_video_output(job, scene.number)
                        st.rerun()
        st.divider()
        validation_column, preview_column = st.columns([1, 1], gap="large")
        with validation_column:
            st.subheader("Validation de la scène")
            if st.session_state.audio_mode != "Agnes natif":
                analysis = analyze_scene_prompt(scene.visual_prompt)
                detected_speakers = list(
                    dict.fromkeys((t.speaker for t in analysis.turns))
                )
                multiple_speakers = len(detected_speakers) > 1
                voice_speakers = (
                    detected_speakers
                    if multiple_speakers
                    else (
                        [
                            scene.speaker_id
                            or (
                                detected_speakers[0]
                                if detected_speakers
                                else "Narrateur"
                            )
                        ]
                        if scene.dialogue.strip()
                        else []
                    )
                )
                if voice_speakers and st.session_state.audio_mode != "Agnes natif":
                    with st.expander(
                        "Voix des personnages — conservées dans ce projet",
                        expanded=multiple_speakers,
                    ):
                        voice_map = load_voices(job.job_dir)
                        with st.form(
                            f"character_voices_{get_current_job_id()}_{scene.number}"
                        ):
                            changes = {}
                            available = {
                                v["voice_id"]: v.get("name", v["voice_id"])
                                for v in st.session_state.get("eleven_voices", [])
                            }
                            for name in voice_speakers:
                                current_voice = voice_map.get(name.casefold(), "")
                                if available:
                                    options = list(
                                        dict.fromkeys(
                                            ["", current_voice] + list(available)
                                        )
                                    )
                                    choice = st.selectbox(
                                        f"Voix de {name}",
                                        options,
                                        index=options.index(current_voice),
                                        format_func=lambda value: available.get(
                                            value, value or "Choisir une voix"
                                        ),
                                    )
                                else:
                                    choice = st.text_input(
                                        f"Identifiant de voix ElevenLabs pour {name}",
                                        value=current_voice,
                                    )
                                changes[name.casefold()] = choice.strip()
                            st.caption(
                                "Charge tes voix ElevenLabs dans la barre latérale. Choisis une voix adaptée à chaque personnage : âge, timbre et accent."
                            )
                            if st.form_submit_button(
                                "Enregistrer les voix des personnages"
                            ):
                                changed_names = {
                                    name
                                    for name, value in changes.items()
                                    if value != voice_map.get(name, "")
                                }
                                voice_map.update(changes)
                                save_voices(job.job_dir, voice_map)
                                for affected in plan.scenes:
                                    names = {
                                        t.speaker.casefold()
                                        for t in analyze_scene_prompt(
                                            affected.visual_prompt
                                        ).turns
                                    }
                                    names.add(
                                        (affected.speaker_id or "Narrateur").casefold()
                                    )
                                    if names & changed_names:
                                        production_state = invalidate_scene_video(
                                            production_state, affected.number
                                        )
                                        invalidate_scene_video_output(
                                            job, affected.number
                                        )
                                persist_production_state(production_state)
                                st.rerun()
                        if multiple_speakers:
                            assigned = [
                                voice_map.get(name.casefold(), "")
                                for name in voice_speakers
                            ]
                            if not all(assigned):
                                st.warning(
                                    "Choisis une voix pour chaque personnage avant la génération audio ou vidéo."
                                )
                            elif len(set(assigned)) < len(assigned):
                                st.warning(
                                    "Certains personnages partagent la même voix. Choisis des voix différentes si tu veux les distinguer."
                                )
                st.markdown("**Dialogue détecté — à vérifier avant confirmation**")
                if multiple_speakers:
                    for turn in analysis.turns:
                        st.write(f"{turn.speaker} : {turn.dialogue}")
                    st.info(
                        "Chaque réplique utilisera la voix du personnage. Pour modifier les répliques, modifie puis analyse le prompt."
                    )
                elif scene.dialogue:
                    st.write(f"Locuteur : {scene.speaker_id or 'Non précisé'}")
                    st.write(scene.dialogue)
                else:
                    st.write("Dialogue détecté : aucun — scène silencieuse")
                if analysis.uncertain:
                    st.warning(
                        "Certains passages sont ambigus. Vérifie les paroles ci-dessous. Pour faciliter la détection, écris : Marcel dit : « Bonjour. »"
                    )
                with st.expander("Modifier le dialogue détecté"):
                    with st.form(
                        f"dialogue_review_{get_current_job_id()}_{scene.number}"
                    ):
                        reviewed_speaker = st.text_input(
                            "Locuteur", value=scene.speaker_id or ""
                        )
                        reviewed_dialogue = st.text_area(
                            "Texte à prononcer", value=scene.dialogue or ""
                        )
                        st.caption(
                            "Laisse le texte vide pour une scène silencieuse. Le prompt original reste intact."
                        )
                        if st.form_submit_button(
                            "Enregistrer la correction", disabled=multiple_speakers
                        ):
                            updated_scene = replace(
                                scene,
                                speaker_id=reviewed_speaker.strip() or None,
                                dialogue=reviewed_dialogue.strip(),
                            )
                            if updated_scene == scene:
                                st.toast("Le dialogue est déjà enregistré.")
                                st.rerun()
                            save_plan(replace_scene_in_plan(plan, updated_scene))
                            production_state = invalidate_scene_content(
                                production_state, scene.number
                            )
                            persist_production_state(production_state)
                            invalidate_scene_video_output(job, scene.number)
                            st.rerun()
            image_path = get_scene_reference(job, scene.number)
            image_ok = not use_image or is_scene_image_validated(
                production_state, scene.number, image_path
            )
            content_ok = is_scene_content_validated(production_state, scene)
            # Auto-confirme le prompt si les conditions sont remplies
            if include_scene and not content_ok and bool(
                (scene.visual_prompt or "").strip() and image_ok
            ):
                production_state = validate_scene_content(production_state, scene)
                persist_production_state(production_state)
                content_ok = True
            action_bar = st.container(horizontal=True, gap="small")
            check1, check3, check4 = st.columns(3)
            check1.caption("Montage : incluse" if include_scene else "Montage : exclue")
            check3.caption("Image : sans image" if not use_image else ("Image : validée" if image_ok else "Image : à valider"))
            check4.caption(
                "Prompt : confirmé" if content_ok else "Prompt : à confirmer"
            )
            if include_scene:
                if action_bar.button(
                    "Retirer validation de la scène",
                    key=f"unvalidate_scene_content_{get_current_job_id()}_{scene.number}",
                    use_container_width=False,
                ):
                    production_state = invalidate_scene_content(
                        production_state, scene.number
                    )
                    persist_production_state(production_state)
                    delete_final_video(job)
                    st.rerun()
            video_ready = scene_is_ready(production_state, scene, image_path)
            if (
                scene.dialogue.strip()
                and include_scene
                and (st.session_state.audio_mode != "Agnes natif")
            ):
                audio_settings = (
                    scene.dialogue,
                    st.session_state.get("voice_provider"),
                    st.session_state.get("eleven_voice_id"),
                    st.session_state.get("eleven_model"),
                    st.session_state.voice,
                    st.session_state.get("audio_speed", 1.0),
                    st.session_state.speech_pitch,
                    scene.visual_prompt,
                    scene.speaker_id,
                    sorted(load_voices(job.job_dir).items()),
                )
                preview_id = hashlib.sha256(repr(audio_settings).encode()).hexdigest()
                preview_path = job.job_dir / "voice_previews" / f"{preview_id}.mp3"
                if st.button(
                    "Écouter la voix",
                    key=f"voice_preview_{get_current_job_id()}_{scene.number}",
                ):
                    try:
                        with st.spinner("Préparation de l'aperçu vocal..."):
                            if not preview_path.exists():
                                get_pipeline(scene).voice_generator.generate(
                                    scene.dialogue, preview_path
                                )
                    except (VoiceGenerationError, OSError) as exc:
                        st.error(str(exc))
                if preview_path.exists():
                    st.audio(str(preview_path))
                    st.caption(
                        "Écoute les paroles avant de lancer la vidéo. Pour changer la voix d'un clip existant, régénère uniquement ce clip."
                    )
            video_exists = video_path.is_file() and video_path.stat().st_size > 0
            if st.session_state.audio_mode == "Agnes natif":
                st.caption(
                    "Les dialogues et les voix seront générés par Agnes selon ton prompt."
                )
            elif scene.dialogue.strip():
                st.caption(
                    "La voix sera préparée et sa durée vérifiée avant l'envoi à Agnes."
                )
            else:
                st.caption("Scène silencieuse — aucun audio nécessaire")
            pending_task = (
                job.job_dir / f"scene_{scene.number:02d}.task.json"
            ).exists()
            video_label = (
                "Régénérer la vidéo"
                if video_exists
                else (
                    "Reprendre la génération vidéo"
                    if pending_task
                    else "Générer la vidéo"
                )
            )
            if action_bar.button(
                video_label,
                key=f"generate_video_{get_current_job_id()}_{scene.number}",
                disabled=not video_ready,
                use_container_width=False,
            ):
                try:
                    production_state = invalidate_scene_video(
                        production_state, scene.number
                    )
                    persist_production_state(production_state)
                    if video_exists:
                        invalidate_scene_video_output(job, scene.number)
                    run_scene_video(plan, scene, production_state, director_plan)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Génération interrompue : {exc}")
                    video_exists = (
                        video_path.is_file() and video_path.stat().st_size > 0
                    )
        with preview_column:
            st.subheader("Vidéo générée")
            preview_path = latest_scene_video(job.job_dir, scene.number)
            if preview_path is not None:
                st.video(str(preview_path), width=800)
                st.download_button(
                    label=f"Télécharger la scène {scene.number}",
                    data=preview_path.read_bytes(),
                    file_name=f"scene_{scene.number:02d}.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                )
                st.caption(f"Scène {scene.number} · {preview_path.name}")
                if preview_path != video_path:
                    st.info("Version précédente conservée. Génère puis valide une nouvelle vidéo pour utiliser les modifications dans le montage.")
                elif scene_is_ready(production_state, scene, image_path):
                    video_validated = is_scene_video_validated(
                        production_state, scene, image_path, video_path
                    )
                    if video_validated:
                        st.success("Vidéo validée pour le montage")
                    else:
                        st.warning("Vidéo générée — à visionner et valider")
                    if action_bar.button(
                        (
                            "Retirer la validation vidéo"
                            if video_validated
                            else "Valider la vidéo"
                        ),
                        key=f"validate_video_{get_current_job_id()}_{scene.number}",
                    ):
                        try:
                            production_state = (
                                invalidate_scene_video(production_state, scene.number)
                                if video_validated
                                else validate_scene_video(
                                    production_state, scene, image_path, video_path
                                )
                            )
                            persist_production_state(production_state)
                            delete_final_video(job)
                            st.rerun()
                        except ProductionStateError as exc:
                            st.error(str(exc))
                else:
                    st.warning(
                        "Une ancienne vidéo existe, mais la scène n'est plus validée. Elle ne sera pas utilisée dans l'assemblage."
                    )
            else:
                st.info("La vidéo apparaîtra ici après la génération.")
            history = scene_video_history(job.job_dir, scene.number)
            if history:
                with st.expander("Versions précédentes"):
                    previous = st.selectbox(
                        "Version conservée", history,
                        format_func=lambda path: path.parent.name.split("_")[0],
                        key=f"video_history_{get_current_job_id()}_{scene.number}",
                    )
                    st.video(str(previous), width=800)
    return production_state
