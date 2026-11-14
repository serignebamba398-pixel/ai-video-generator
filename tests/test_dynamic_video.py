from __future__ import annotations

import sys
from pathlib import Path


# ==========================================================
# PROJECT PATH
# ==========================================================

PROJECT_DIR = (
    Path(__file__)
    .resolve()
    .parent
)

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_DIR),
    )


# ==========================================================
# IMPORTS
# ==========================================================

from src.agnes_client import (
    AgnesClient,
)

from src.config import (
    AUDIO_DIR,
    OUTPUT_DIR,
)

from src.job_manager import (
    JobManager,
)

from src.reference_image_manager import (
    ReferenceImageError,
    ReferenceImageManager,
)

from src.scene_planner import (
    ScenePlanner,
    ScenePlannerError,
    VideoPlan,
)

from src.video_assembler import (
    VideoAssembler,
    VideoAssemblyError,
)

from src.video_pipeline import (
    PreparedScene,
    VideoPipeline,
    VideoPipelineError,
)


# ==========================================================
# PRODUCTION CONFIGURATION
# ==========================================================

JOB_ID = "millionaire_secret_fr_v1"

TARGET_DURATION = 60

VIDEO_SIZE = "720P"

ASPECT_RATIO = "9:16"

COOLDOWN_SECONDS = 45

KEEP_AUDIO_FILES = False


# ==========================================================
# USER PROMPT
#
# This is the ONLY scenario-specific part of the file.
#
# The pipeline itself remains generic and can later receive
# any prompt from Streamlit.
# ==========================================================

USER_PROMPT = """
Créer une vidéo cinématographique verticale 9:16 d'environ une minute,
entièrement en français, avec une narration visuelle claire, émotionnelle
et légèrement humoristique.

STYLE VISUEL :

Animation 3D extrêmement détaillée et réaliste, de qualité cinéma,
avec des personnages anthropomorphes ressemblant à des fruits.

Textures très détaillées, expressions faciales crédibles, lumière
cinématographique chaleureuse, profondeur de champ et mouvements de caméra
fluides.

L'esthétique, le design des personnages et l'univers visuel doivent rester
cohérents du début à la fin.


PERSONNAGES PRINCIPAUX :

Marcel :

Un vieil ouvrier du bâtiment anthropomorphe jaune-orangé, petit et trapu,
avec un visage fatigué et ridé.

Il porte toujours un casque de chantier blanc usé, une veste de travail
orange sale, un t-shirt gris foncé, un pantalon de chantier sombre et des
chaussures de sécurité.

Il travaille depuis de nombreuses années et commence à avoir de grandes
difficultés physiques pour marcher et travailler.


Victor :

Un riche entrepreneur anthropomorphe bleu foncé, légèrement plus grand,
élégant et imposant.

Il porte toujours un costume bleu marine parfaitement taillé, une chemise
blanche, une cravate sombre et une montre luxueuse.

Il paraît sévère et froid, mais cache en réalité de bonnes intentions.


HISTOIRE :

Au début, Marcel travaille péniblement sur un chantier de construction
luxueux.

Il est épuisé, se tient le dos et marche difficilement.

Marcel s'approche de Victor et lui dit avec respect :

« Monsieur Victor, mon corps ne suit plus. Je voudrais prendre ma retraite. »

Victor le regarde sérieusement et répond :

« J'accepte… mais à une seule condition. »

Ils entrent ensuite dans un bureau où Victor présente à Marcel la maquette
d'une immense maison luxueuse en construction.

Victor explique :

« Je veux que tu termines cette maison avant de partir. »

Marcel accepte.

Victor commence ensuite à donner des exigences qui paraissent étranges.

Il montre l'entrée de la maison et dit :

« Je ne veux aucune marche à l'entrée. Fais une pente douce. »

Marcel paraît surpris mais exécute la demande.

On le voit construire soigneusement une entrée parfaitement accessible.

Plus tard, Victor inspecte une porte et dit :

« Les portes sont trop étroites. Fais-les beaucoup plus larges. »

Marcel trouve la demande étrange mais continue le travail.

On le voit mesurer puis modifier les ouvertures.

Dans une autre partie de la maison, près d'une grande piscine intérieure,
Victor demande :

« Installe le système d'hydromassage le plus puissant possible. »

Marcel demande :

« Pourquoi autant de puissance ? »

Victor répond calmement :

« Certaines personnes ont très mal aux jambes après des années de travail. »

Marcel reste silencieux, sans comprendre que Victor parle de lui.

Le chantier avance.

Marcel travaille malgré sa fatigue.

La maison devient progressivement magnifique :

grande entrée accessible, portes larges, pièces luxueuses,
piscine avec hydromassage et circulation facile dans toute la maison.

Quand tout est terminé, Marcel remet symboliquement les clés à Victor.

Marcel dit :

« Voilà. Tout est exactement comme vous l'avez demandé. »

Victor observe la maison puis répond :

« Parfait. Demain matin, le nouveau propriétaire viendra la découvrir. »

Marcel regarde cette immense demeure avec tristesse.

Il murmure :

« Certains riches ne savent vraiment pas quoi faire de leur argent… »

Marcel rentre lentement chez lui en pensant que son dernier travail
servira encore à un millionnaire.

La nuit, Victor est seul dans son bureau.

Il tient une vieille photo montrant Marcel après de nombreuses années
de travail à ses côtés.

Victor sourit légèrement et dit :

« Après toutes ces années, il mérite enfin de se reposer. »

Puis il regarde les clés de la maison sur son bureau.

Dernier plan :

Victor prend les clés et dit avec un sourire :

« Demain, je vais lui faire une surprise qu'il n'oubliera jamais. »

La révélation implicite doit être très claire pour le spectateur :

la maison a secrètement été construite pour Marcel.

Toutes les demandes étranges de Victor — absence de marches,
portes larges et hydromassage — étaient destinées à faciliter
la vie du vieil ouvrier après sa retraite.


CONTRAINTES IMPORTANTES :

- conserver exactement les mêmes personnages tout au long de la vidéo ;
- conserver leur visage, leur morphologie et leurs vêtements ;
- assurer une forte continuité visuelle entre les scènes ;
- faire progresser naturellement le chantier ;
- ne pas changer aléatoirement l'architecture de la maison ;
- maintenir la même identité visuelle de la maison ;
- dialogues courts, naturels et exclusivement en français ;
- les mouvements des lèvres doivent correspondre à la voix française ;
- aucun sous-titre ;
- aucun texte généré visible à l'écran ;
- aucun panneau avec du texte illisible ;
- privilégier les expressions faciales et la mise en scène ;
- rendre les émotions compréhensibles même sans dialogue ;
- utiliser des plans cinématographiques professionnels ;
- éviter les mouvements physiques incohérents ;
- éviter les changements inexpliqués de vêtements ou d'accessoires ;
- conserver les objets importants entre deux scènes directement liées ;
- la fin doit fonctionner comme une révélation émotionnelle ;
- ne pas révéler trop tôt que la maison est destinée à Marcel ;
- condenser intelligemment l'histoire afin qu'elle tienne en environ
  60 secondes ;
- chaque scène doit faire avancer l'histoire ;
- éviter les scènes de remplissage ;
- ne pas reproduire de logo, watermark ou texte provenant d'une autre vidéo.
""".strip()


# ==========================================================
# DISPLAY HELPERS
# ==========================================================


def print_separator(
    title: str,
) -> None:

    print()
    print("=" * 72)
    print(title)
    print("=" * 72)
    print()


# ==========================================================
# SOURCE PROMPT
# ==========================================================


def ensure_source_prompt(
    job: JobManager,
    source_prompt: str,
) -> Path:
    """
    Save the original user prompt as the authoritative
    source for the entire production job.

    A JOB_ID may never silently be reused with another
    prompt.
    """

    source_prompt = (
        source_prompt
        or ""
    ).strip()

    if not source_prompt:

        raise RuntimeError(
            "USER_PROMPT is empty."
        )

    job.job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_prompt_path = (
        job.job_dir
        / "source_prompt.txt"
    )

    if source_prompt_path.exists():

        existing_prompt = (
            source_prompt_path
            .read_text(
                encoding="utf-8"
            )
            .strip()
        )

        if (
            existing_prompt
            != source_prompt
        ):

            raise RuntimeError(
                "\nThis JOB_ID already belongs to another "
                "source prompt.\n\n"
                f"Current JOB_ID: {JOB_ID}\n\n"
                "Use a new JOB_ID for a new video instead "
                "of overwriting an existing production job."
            )

        print(
            "Original source prompt: "
            "existing verified version reused."
        )

        return source_prompt_path

    temporary_path = Path(
        str(source_prompt_path)
        + ".tmp"
    )

    temporary_path.write_text(
        source_prompt,
        encoding="utf-8",
    )

    temporary_path.replace(
        source_prompt_path
    )

    print(
        "Original source prompt saved:"
    )

    print(
        source_prompt_path.resolve()
    )

    return source_prompt_path


# ==========================================================
# PROGRESS CALLBACK
# ==========================================================


def progress_callback(
    current: int,
    total: int,
    status: str,
    progress: int,
) -> None:

    # ======================================================
    # QUEUE FULL
    # ======================================================

    if status.startswith(
        "queue_full_wait_"
    ):

        seconds = (
            status
            .replace(
                "queue_full_wait_",
                "",
            )
            .replace(
                "s",
                "",
            )
        )

        print(
            f"Scene {current}/{total} | "
            "Agnes queue full | "
            f"retry in {seconds}s"
        )

        return

    # ======================================================
    # RATE LIMIT
    # ======================================================

    if status.startswith(
        "rate_limit_wait_"
    ):

        seconds = (
            status
            .replace(
                "rate_limit_wait_",
                "",
            )
            .replace(
                "s",
                "",
            )
        )

        print(
            f"Scene {current}/{total} | "
            "rate limit | "
            f"retry in {seconds}s"
        )

        return

    # ======================================================
    # TEMPORARY ERROR
    # ======================================================

    if status.startswith(
        "temporary_error_wait_"
    ):

        seconds = (
            status
            .replace(
                "temporary_error_wait_",
                "",
            )
            .replace(
                "s",
                "",
            )
        )

        print(
            f"Scene {current}/{total} | "
            "temporary error | "
            f"retry in {seconds}s"
        )

        return

    # ======================================================
    # COOLDOWN
    # ======================================================

    if status.startswith(
        "cooldown_"
    ):

        seconds = (
            status
            .replace(
                "cooldown_",
                "",
            )
            .replace(
                "s",
                "",
            )
        )

        print(
            f"Scene {current}/{total} | "
            f"cooldown {seconds}s"
        )

        return

    # ======================================================
    # NORMAL STATUS
    # ======================================================

    readable_status = (
        status
        .replace(
            "_",
            " ",
        )
    )

    print(
        f"Scene {current}/{total} | "
        f"{readable_status} | "
        f"{progress}%"
    )


# ==========================================================
# STORYBOARD DISPLAY
# ==========================================================


def print_storyboard(
    plan: VideoPlan,
    prepared: list[PreparedScene],
    pipeline: VideoPipeline,
) -> None:

    print_separator(
        "FINAL STORYBOARD"
    )

    character_map = (
        plan.character_map
    )

    for item in prepared:

        scene = (
            item.scene
        )

        print(
            "-" * 72
        )

        print(
            f"SCENE {scene.number}"
        )

        print(
            "-" * 72
        )

        print()

        print(
            f"Duration: "
            f"{scene.duration}s"
        )

        print()

        # ==================================================
        # VISUAL PROMPT
        # ==================================================

        print(
            "Visual prompt:"
        )

        print(
            scene.visual_prompt
        )

        print()

        # ==================================================
        # START / END STATE
        # ==================================================

        print(
            "Start state:"
        )

        print(
            scene.start_state
        )

        print()

        print(
            "End state:"
        )

        print(
            scene.end_state
        )

        print()

        # ==================================================
        # CONTINUITY
        # ==================================================

        print(
            "Previous-frame continuity:"
        )

        print(
            "YES"
            if scene.use_previous_frame
            else "NO"
        )

        print()

        # ==================================================
        # CHARACTERS
        # ==================================================

        print(
            "Visible recurring characters:"
        )

        if scene.character_ids:

            for character_id in (
                scene.character_ids
            ):

                character = (
                    character_map.get(
                        character_id
                    )
                )

                if character:

                    print(
                        f"- {character.name} "
                        f"[{character.id}]"
                    )

                else:

                    print(
                        f"- {character_id}"
                    )

        else:

            print(
                "none"
            )

        print()

        # ==================================================
        # REFERENCE IMAGES
        # ==================================================

        print(
            "Character reference images:"
        )

        if (
            item.reference_image_paths
        ):

            for image_path in (
                item.reference_image_paths
            ):

                print(
                    f"- {image_path}"
                )

        else:

            print(
                "none"
            )

        print()

        # ==================================================
        # EXPECTED AGNES MODE
        # ==================================================

        expected_reference_mode = bool(
            item.uses_reference_mode
            or scene.use_previous_frame
        )

        print(
            "Expected Agnes mode:"
        )

        print(
            "REFERENCE"
            if expected_reference_mode
            else "TEXT"
        )

        print()

        # ==================================================
        # DIALOGUE
        # ==================================================

        if item.has_dialogue:

            speaker = (
                character_map.get(
                    scene.speaker_id
                    or ""
                )
            )

            print(
                "Speaker:"
            )

            if speaker:

                print(
                    f"{speaker.name} "
                    f"[{speaker.id}]"
                )

            else:

                print(
                    scene.speaker_id
                    or "unknown"
                )

            print()

            print(
                "Dialogue:"
            )

            print(
                scene.dialogue
            )

            print()

            print(
                "Generated speech duration:"
            )

            print(
                f"{item.speech_duration:.2f}s"
            )

            timing = (
                pipeline
                .calculate_speech_timing(
                    scene_duration=(
                        scene.duration
                    ),
                    speech_duration=(
                        item.speech_duration
                    ),
                )
            )

            print(
                "Speech timing:"
            )

            print(
                f"- start: "
                f"{timing.start:.2f}s"
            )

            print(
                f"- end: "
                f"{timing.end:.2f}s"
            )

            print(
                f"- remaining visual action: "
                f"{timing.post_action:.2f}s"
            )

        else:

            print(
                "Dialogue: none"
            )

        print()

    print_separator(
        "STORYBOARD SUMMARY"
    )

    print(
        f"Title: "
        f"{plan.title}"
    )

    print(
        f"Language: "
        f"{plan.language}"
    )

    print(
        f"Scenes: "
        f"{len(plan.scenes)}"
    )

    print(
        f"Total planned duration: "
        f"{plan.total_duration}s"
    )

    print()


# ==========================================================
# CHARACTER DISPLAY
# ==========================================================


def print_characters(
    plan: VideoPlan,
) -> None:

    print_separator(
        "CHARACTER BIBLE"
    )

    if not plan.characters:

        print(
            "No recurring character "
            "was created."
        )

        return

    for character in (
        plan.characters
    ):

        print(
            "-" * 72
        )

        print(
            f"{character.name} "
            f"[{character.id}]"
        )

        print()

        print(
            "Description:"
        )

        print(
            character.description
        )

        print()

        print(
            "Reference-image prompt:"
        )

        print(
            character.reference_prompt
        )

        print()


# ==========================================================
# RESUME STATUS
# ==========================================================


def scene_video_path(
    job: JobManager,
    scene_number: int,
) -> Path:

    return (
        job.job_dir
        / (
            f"scene_"
            f"{scene_number:02d}"
            ".mp4"
        )
    )


def scene_is_complete(
    job: JobManager,
    scene_number: int,
) -> bool:

    path = (
        scene_video_path(
            job=job,
            scene_number=(
                scene_number
            ),
        )
    )

    try:

        return (
            path.exists()
            and path.is_file()
            and path.stat().st_size > 0
        )

    except OSError:

        return False


def print_resume_status(
    job: JobManager,
    plan: VideoPlan,
) -> int:

    print_separator(
        "RESUME STATUS"
    )

    missing = 0

    for scene in (
        plan.scenes
    ):

        if scene_is_complete(
            job=job,
            scene_number=(
                scene.number
            ),
        ):

            print(
                f"Scene "
                f"{scene.number}: "
                "COMPLETED"
            )

        else:

            print(
                f"Scene "
                f"{scene.number}: "
                "MISSING"
            )

            missing += 1

    print()

    print(
        "Scenes requiring generation: "
        f"{missing}"
    )

    print()

    return missing


# ==========================================================
# VERIFY GENERATED SCENES
# ==========================================================


def collect_scene_paths(
    job: JobManager,
    plan: VideoPlan,
) -> dict[int, Path]:

    print_separator(
        "SCENE VALIDATION"
    )

    result: dict[
        int,
        Path,
    ] = {}

    for scene in (
        plan.scenes
    ):

        path = (
            scene_video_path(
                job=job,
                scene_number=(
                    scene.number
                ),
            )
        )

        if not (
            path.exists()
            and path.is_file()
            and path.stat().st_size > 0
        ):

            raise VideoPipelineError(
                "Scene generation finished, "
                "but a required scene file "
                "is missing:\n"
                f"{path}"
            )

        result[
            scene.number
        ] = path

        print(
            f"Scene "
            f"{scene.number}: OK"
        )

        print(
            path.resolve()
        )

    print()

    return result


# ==========================================================
# MAIN
# ==========================================================


def main() -> None:

    prepared: list[
        PreparedScene
    ] = []

    # ======================================================
    # INITIALIZE CLIENTS
    # ======================================================

    agnes = (
        AgnesClient()
    )

    planner = (
        ScenePlanner()
    )

    pipeline = (
        VideoPipeline(
            audio_dir=(
                AUDIO_DIR
            ),
            video_dir=(
                OUTPUT_DIR
            ),
            agnes_client=(
                agnes
            ),
        )
    )

    job = (
        JobManager(
            base_dir=(
                OUTPUT_DIR
            ),
            job_id=(
                JOB_ID
            ),
        )
    )

    reference_manager = (
        ReferenceImageManager(
            agnes_client=(
                agnes
            ),
            reference_dir=(
                job.reference_dir
            ),
        )
    )

    # ======================================================
    # HEADER
    # ======================================================

    print_separator(
        "PROFESSIONAL AI VIDEO GENERATOR"
    )

    print(
        f"Job ID: "
        f"{JOB_ID}"
    )

    print(
        f"Format: "
        f"{ASPECT_RATIO}"
    )

    print(
        f"Target duration: "
        f"{TARGET_DURATION}s"
    )

    print(
        f"Resolution preset: "
        f"{VIDEO_SIZE}"
    )

    print()

    print(
        "Job directory:"
    )

    print(
        job.job_dir.resolve()
    )

    print()

    # ======================================================
    # ORIGINAL PROMPT
    # ======================================================

    print_separator(
        "SOURCE PROMPT"
    )

    ensure_source_prompt(
        job=job,
        source_prompt=(
            USER_PROMPT
        ),
    )

    # ======================================================
    # STORYBOARD
    # ======================================================

    print_separator(
        "STORYBOARD"
    )

    if job.has_plan():

        print(
            "Existing compatible storyboard found."
        )

        print(
            "Loading storyboard..."
        )

        plan = (
            job.load_plan()
        )

    else:

        print(
            "Creating a new storyboard..."
        )

        plan = (
            planner.create_plan(
                user_prompt=(
                    USER_PROMPT
                ),
                target_duration=(
                    TARGET_DURATION
                ),
            )
        )

        job.save_plan(
            plan
        )

    print()

    print(
        f"Title: "
        f"{plan.title}"
    )

    print(
        f"Language: "
        f"{plan.language}"
    )

    print(
        f"Scene count: "
        f"{len(plan.scenes)}"
    )

    print(
        f"Storyboard duration: "
        f"{plan.total_duration}s"
    )

    print()

    print(
        "Setting:"
    )

    print(
        plan.setting_description
    )

    print()

    print(
        "Global continuity constraints:"
    )

    print(
        plan.continuity_constraints
    )

    # ======================================================
    # CHARACTERS
    # ======================================================

    print_characters(
        plan
    )

    # ======================================================
    # GENERATE / REUSE CHARACTER REFERENCES
    # ======================================================

    print_separator(
        "CHARACTER REFERENCES"
    )

    references = (
        reference_manager
        .ensure_references(
            plan
        )
    )

    if references:

        for (
            character_id,
            image_path,
        ) in references.items():

            character = (
                plan.character_map.get(
                    character_id
                )
            )

            character_name = (
                character.name
                if character
                else character_id
            )

            print(
                f"{character_name}:"
            )

            print(
                image_path.resolve()
            )

            print()

    else:

        print(
            "No character references required."
        )

    # ======================================================
    # AUDIO + FINAL PREPARATION
    # ======================================================

    print_separator(
        "PREPARING SCENES"
    )

    final_plan, prepared = (
        pipeline.prepare_plan(
            plan=(
                plan
            ),
            dialogue_rewriter=(
                planner
                .rewrite_dialogue_for_duration
            ),
            reference_images=(
                references
            ),
        )
    )

    # Dialogue shortening or duration redistribution may
    # have modified the original storyboard.
    job.save_plan(
        final_plan
    )

    # ======================================================
    # DISPLAY FINAL STORYBOARD
    # ======================================================

    print_storyboard(
        plan=(
            final_plan
        ),
        prepared=(
            prepared
        ),
        pipeline=(
            pipeline
        ),
    )

    # ======================================================
    # RESUME STATUS
    # ======================================================

    print_resume_status(
        job=job,
        plan=(
            final_plan
        ),
    )

    # ======================================================
    # GENERATE ALL SCENES
    # ======================================================

    print_separator(
        "VIDEO GENERATION"
    )

    pipeline.generate_scenes(
        plan=(
            final_plan
        ),
        prepared_scenes=(
            prepared
        ),
        aspect_ratio=(
            ASPECT_RATIO
        ),
        size=(
            VIDEO_SIZE
        ),
        progress_callback=(
            progress_callback
        ),
        job_id=(
            JOB_ID
        ),
        resume=True,
        cooldown_seconds=(
            COOLDOWN_SECONDS
        ),
    )

    # ======================================================
    # VERIFY
    # ======================================================

    scene_paths = (
        collect_scene_paths(
            job=job,
            plan=(
                final_plan
            ),
        )
    )

    # ======================================================
    # FINAL ASSEMBLY
    # ======================================================

    print_separator(
        "FINAL ASSEMBLY"
    )

    assembler = (
        VideoAssembler()
    )

    final_video_path = (
        job.job_dir
        / "final_video.mp4"
    )

    assembly_result = (
        assembler.assemble(
            plan=(
                final_plan
            ),
            scene_paths=(
                scene_paths
            ),
            output_path=(
                final_video_path
            ),
            working_directory=(
                job.job_dir
                / "_assembly"
            ),
            cleanup_intermediate=True,
        )
    )

    # ======================================================
    # SUCCESS
    # ======================================================

    print_separator(
        "VIDEO PRODUCTION COMPLETE"
    )

    print(
        "Final video:"
    )

    print(
        assembly_result
        .output_path
        .resolve()
    )

    print()

    print(
        f"Duration: "
        f"{assembly_result.duration:.3f}s"
    )

    print(
        "Resolution: "
        f"{assembly_result.width}"
        "x"
        f"{assembly_result.height}"
    )

    print(
        f"Scenes: "
        f"{assembly_result.scene_count}"
    )

    print()

    print(
        "Original prompt:"
    )

    print(
        (
            job.job_dir
            / "source_prompt.txt"
        ).resolve()
    )

    print()

    print(
        "Next production step:"
    )

    print(
        "python test_post_production.py"
    )

    print()

    # ======================================================
    # AUDIO CLEANUP
    # ======================================================

    if (
        prepared
        and not KEEP_AUDIO_FILES
    ):

        VideoPipeline.cleanup_audio(
            prepared
        )


# ==========================================================
# ENTRY POINT
# ==========================================================


if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print("=" * 72)
        print("PROCESS INTERRUPTED")
        print("=" * 72)
        print()

        print(
            "The process was stopped by the user."
        )

        print(
            "Completed scenes and accepted Agnes "
            "task IDs remain stored."
        )

        print()

        print(
            "Run the same command again to resume:"
        )

        print()

        print(
            "python test_dynamic_video.py"
        )

        print()

    except ScenePlannerError as exc:

        print()
        print("=" * 72)
        print("STORYBOARD ERROR")
        print("=" * 72)
        print()

        print(
            str(exc)
        )

    except ReferenceImageError as exc:

        print()
        print("=" * 72)
        print("REFERENCE IMAGE ERROR")
        print("=" * 72)
        print()

        print(
            str(exc)
        )

    except VideoPipelineError as exc:

        print()
        print("=" * 72)
        print("VIDEO PIPELINE ERROR")
        print("=" * 72)
        print()

        print(
            str(exc)
        )

    except VideoAssemblyError as exc:

        print()
        print("=" * 72)
        print("VIDEO ASSEMBLY ERROR")
        print("=" * 72)
        print()

        print(
            str(exc)
        )

    except Exception as exc:

        print()
        print("=" * 72)
        print("UNEXPECTED ERROR")
        print("=" * 72)
        print()

        print(
            f"{type(exc).__name__}: "
            f"{exc}"
        )