from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import streamlit as st
from src.production_state import (
    invalidate_scene_video,
    is_scene_video_validated,
    is_scene_image_validated,
)
from src import video_assembler
from src.video_assembler import VideoAssemblyError
from src.video_transitions import transition_timing
from src.studio.actions import (
    director_plan_path,
    get_job,
    get_scene_reference,
    persist_production_state,
    production_state_path,
    ready_scenes,
    run_scene_video,
    scene_video_path,
    source_prompt_path,
)


def render_delivery(plan, production_state, director_plan=None):
    if plan is not None and production_state is not None:
        st.header("Production")
        transition = st.selectbox(
            "Transition entre les scènes",
            ("Fondu court · 0,25 s", "Cut direct"),
            key=f"assembly_transition_{get_job().job_id}",
        )
        transition_seconds = 0.25 if transition.startswith("Fondu") else 0.0
        if transition_seconds:
            st.caption("Fondu image et audio sur 0,25 s. Les extrémités des clips se chevauchent : évite les paroles au tout début ou à la toute fin d’un plan. Réassemble pour appliquer ce réglage.")
        selected_scenes = [
            scene
            for scene in plan.scenes
            if production_state.scenes[scene.number].included
        ]
        production_ready_scenes = ready_scenes(plan, production_state)
        not_ready_selected = [
            scene for scene in selected_scenes if scene not in production_ready_scenes
        ]
        job = get_job()
        selected_count = len(selected_scenes)
        image_scenes = [s for s in selected_scenes if production_state.scenes[s.number].use_reference_image]
        image_count = sum(
            (
                is_scene_image_validated(
                    production_state,
                    scene.number,
                    get_scene_reference(job, scene.number),
                )
                for scene in image_scenes
            )
        )
        generated_count = sum(
            (
                scene_video_path(job, scene.number).is_file()
                and scene_video_path(job, scene.number).stat().st_size > 0
                for scene in selected_scenes
            )
        )
        montage_scenes = [
            scene
            for scene in selected_scenes
            if is_scene_video_validated(
                production_state,
                scene,
                get_scene_reference(job, scene.number),
                scene_video_path(job, scene.number),
            )
        ]
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Scènes incluses", selected_count)
        col2.metric("Images validées", f"{image_count}/{len(image_scenes)}")
        col3.metric("Vidéos générées", f"{generated_count}/{selected_count}")
        col4.metric("Vidéos validées", f"{len(montage_scenes)}/{selected_count}")
        col5.metric(
            "Durée du montage estimée", f"{transition_timing([s.duration for s in montage_scenes], transition_seconds, 24)[1]:g} s"
        )
        st.caption(
            f"Durée des scènes incluses : {sum((s.duration for s in selected_scenes))} s. Seules les vidéos validées entrent dans le montage."
        )
        if not selected_scenes:
            st.info(
                "Aucune scène n'est activée. Active uniquement les scènes que tu veux produire."
            )
        elif not_ready_selected:
            st.warning(
                f"{len(not_ready_selected)} scène(s) active(s) ne sont pas encore prêtes. Elles seront ignorées si tu lances maintenant la génération."
            )
        if production_ready_scenes:
            st.success(
                "Scènes prêtes : "
                + ", ".join((str(scene.number) for scene in production_ready_scenes))
            )
    if plan is not None and production_state is not None:
        st.header("Génération et assemblage")
        production_ready_scenes = ready_scenes(plan, production_state)
        generation_col, assembly_col = st.columns(2)
        with generation_col:
            missing_scenes = [
                scene
                for scene in production_ready_scenes
                if not (
                    scene_video_path(get_job(), scene.number).is_file()
                    and scene_video_path(get_job(), scene.number).stat().st_size > 0
                )
            ]
            if st.button(
                f"Générer / reprendre les {len(missing_scenes)} vidéo(s) manquante(s)",
                type="primary",
                use_container_width=True,
                disabled=not missing_scenes,
            ):
                try:
                    for scene in missing_scenes:
                        production_state = invalidate_scene_video(
                            production_state, scene.number
                        )
                        persist_production_state(production_state)
                        run_scene_video(plan, scene, production_state, director_plan)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Génération interrompue : {exc}")
        with assembly_col:
            usable_scenes = []
            scene_paths: dict[int, Path] = {}
            job = get_job()
            for scene in production_ready_scenes:
                path = scene_video_path(job, scene.number)
                if is_scene_video_validated(
                    production_state,
                    scene,
                    get_scene_reference(job, scene.number),
                    path,
                ):
                    usable_scenes.append(scene)
                    scene_paths[scene.number] = path
            selected_count = sum(
                (item.included for item in production_state.scenes.values())
            )
            st.write(
                f"{selected_count} scènes retenues · {len(usable_scenes)} vidéos validées · {selected_count - len(usable_scenes)} vidéos à terminer"
            )
            st.caption(
                "Le montage utilise uniquement les vidéos validées, dans l'ordre du storyboard."
            )
            st.caption(
                "Ordre du montage : "
                + " → ".join((str(s.number) for s in usable_scenes))
                + f" — durée estimée : {transition_timing([s.duration for s in usable_scenes], transition_seconds, 24)[1]:g} s"
            )
            assemble_label = (
                "Assembler à nouveau"
                if (job.job_dir / "final_video_raw.mp4").exists()
                else f"Assembler les {len(usable_scenes)} vidéo(s) validée(s)"
            )
            if st.button(
                assemble_label,
                use_container_width=True,
                disabled=len(usable_scenes) == 0,
            ):
                try:
                    assembly_plan = replace(plan, scenes=usable_scenes)
                    assembler = video_assembler.VideoAssembler()
                    output_path = job.job_dir / "final_video_raw.mp4"
                    with st.spinner("Assemblage FFmpeg..."):
                        result = assembler.assemble(
                            plan=assembly_plan,
                            scene_paths=scene_paths,
                            output_path=output_path,
                            working_directory=job.job_dir / "_assembly",
                            cleanup_intermediate=True,
                            transition_seconds=transition_seconds,
                        )
                    st.success(f"Montage brut créé — {result.duration:.2f}s")
                except (VideoAssemblyError, ValueError) as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(str(exc))
    current_job = get_job()
    raw_video = current_job.job_dir / "final_video_raw.mp4"
    if raw_video.exists():
        st.header("Montage brut")
        st.video(str(raw_video), width=800)
        st.caption(
            "final_video_raw.mp4 — scènes normalisées et assemblées. La musique, les ambiances et le traitement audio final seront ajoutés en post-production."
        )
    final_video = current_job.job_dir / "final_video.mp4"
    if final_video.exists():
        st.header("Master final")
        st.video(str(final_video), width=800)
        st.caption(str(final_video.resolve()))
    assembly_history = sorted(
        (path for path in (current_job.job_dir / "history" / "assembly").glob("*/*.mp4")
         if not path.parent.name.startswith(".") and path.stat().st_size > 0),
        reverse=True,
    )
    if assembly_history:
        with st.expander("Montages précédents"):
            previous = st.selectbox(
                "Montage conservé", assembly_history,
                format_func=lambda path: f"{path.parent.name.split('_')[0]} · {path.name}",
                key=f"assembly_history_{current_job.job_id}",
            )
            st.video(str(previous), width=800)
            st.caption("Version conservée avant les dernières modifications du projet.")
    if plan is not None:
        with st.expander("Fichiers du projet"):
            st.write("Dossier du projet :")
            st.code(str(current_job.job_dir.resolve()))
            st.write("État de production :")
            st.code(str(production_state_path(current_job).resolve()))
            prompt_file = source_prompt_path(current_job)
            if prompt_file.exists():
                st.write("Prompt original :")
                st.code(prompt_file.read_text(encoding="utf-8"))
            direction_file = director_plan_path(current_job)
            if direction_file.exists():
                st.write("Plan de réalisation :")
                st.code(str(direction_file.resolve()))
