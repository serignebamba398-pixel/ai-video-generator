import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from src.production_state import (
    ProductionState, ProductionStateError, sync_production_state,
    set_scene_included, validate_scene_image, validate_scene_content,
    validate_scene_video, is_scene_video_validated, invalidate_scene_image,
    invalidate_scene_content, invalidate_scene_video,
    save_production_state, load_production_state,
    scene_is_ready,
    set_scene_reference_mode,
)
from src.scene_planner import Scene, VideoPlan
from src.scene_video_production import generate_scene_video
from src.video_pipeline import VideoPipeline


class SceneVideoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scenes = [Scene(n, 6, f"Scene {n}") for n in (1, 2, 4, 7)]
        self.plan = VideoPlan("Test", "fr", "", "cinema", "park", "", [], self.scenes)
        self.image = self.root / "master.png"
        self.image.write_bytes(b"master")
        self.video = self.root / "scene.mp4"
        self.video.write_bytes(b"video")
        self.state = sync_production_state(ProductionState(), self.plan)
        for scene in self.scenes:
            self.state = set_scene_included(self.state, scene.number, True)
            self.state = validate_scene_image(self.state, scene.number, self.image)
            self.state = validate_scene_content(self.state, scene)

    def test_validation_roundtrip_and_changed_clip(self):
        scene = self.scenes[2]
        self.state = validate_scene_video(self.state, scene, self.image, self.video)
        path = self.root / "state.json"
        save_production_state(self.state, path)
        state = load_production_state(path)
        self.assertTrue(is_scene_video_validated(state, scene, self.image, self.video))
        self.video.write_bytes(b"replacement")
        self.assertFalse(is_scene_video_validated(state, scene, self.image, self.video))

    def test_scene_master_does_not_require_character_references(self):
        scene = replace(self.scenes[0], character_ids=("legacy_character",))
        state = validate_scene_content(self.state, scene)
        self.assertTrue(scene_is_ready(state, scene, self.image))
        self.assertFalse(scene_is_ready(invalidate_scene_image(state, 1), scene, self.image))

    def test_without_image_mode_persists_and_requires_confirmation(self):
        scene = self.scenes[0]
        state = validate_scene_video(self.state, scene, self.image, self.video)
        state = set_scene_reference_mode(state, 1, False)
        self.assertFalse(scene_is_ready(state, scene, None))
        self.assertFalse(state.scenes[1].video_validated_sha256)
        state = validate_scene_content(state, scene)
        self.assertTrue(scene_is_ready(state, scene, None))
        state = set_scene_included(state, 1, False)
        state = set_scene_included(state, 1, True)
        path = self.root / "state.json"
        save_production_state(state, path)
        state = load_production_state(path)
        self.assertTrue(scene_is_ready(state, scene, None))
        state = validate_scene_video(state, scene, None, self.video)
        self.assertTrue(is_scene_video_validated(state, scene, None, self.video))
        state = set_scene_reference_mode(state, 1, True)
        self.assertFalse(scene_is_ready(state, scene, None))

    def test_without_image_generation_ignores_stored_reference(self):
        scene = replace(self.scenes[0], use_previous_frame=True)
        state = validate_scene_content(set_scene_reference_mode(self.state, 1, False), scene)
        for native in (True, False):
            with self.subTest(native=native):
                pipeline = VideoPipeline(self.root / "audio", self.root / "video", agnes_client=Mock())
                pipeline.generate_scenes = Mock()
                generate_scene_video(
                    plan=self.plan, scene=scene, state=state, image_path=self.image,
                    pipeline=pipeline, dialogue_rewriter=None, job_id="text",
                    aspect_ratio="9:16", size="720P", native_audio=native,
                )
                item = pipeline.generate_scenes.call_args.kwargs["prepared_scenes"][0]
                self.assertIsNone(item.scene_reference_image_path)
                self.assertFalse(item.reference_image_paths)
                self.assertFalse(item.scene.use_previous_frame)
        prompt = pipeline.build_scene_prompt(self.plan, scene, False, native_audio=True)
        self.assertNotIn("supplied scene master image", prompt)
        self.assertIn(scene.visual_prompt, prompt)

    def test_ui_can_confirm_prompt_without_image(self):
        from streamlit.testing.v1 import AppTest
        from src.job_manager import JobManager
        job = JobManager(self.root, "project_001")
        job.save_plan(replace(self.plan, scenes=[self.scenes[0]]))
        save_production_state(self.state, job.job_dir / "production_state.json")
        with patch("src.config.OUTPUT_DIR", self.root):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
            app.checkbox(key="scene_reference_mode_project_001_1").uncheck().run()
            self.assertFalse(app.exception)
            confirm = app.button(key="validate_scene_content_project_001_1")
            self.assertFalse(confirm.disabled)
            confirm.click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.button(key="generate_video_project_001_1").disabled)
            saved = load_production_state(job.job_dir / "production_state.json")
            self.assertTrue(scene_is_ready(saved, self.scenes[0], None))

    def test_new_project_starts_with_scenes_without_global_prompt(self):
        from streamlit.testing.v1 import AppTest
        with patch("src.config.OUTPUT_DIR", self.root):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertIn("Mes scènes", [h.value for h in app.header])
            self.assertNotIn("1. Prompt global", [h.value for h in app.header])
            next(b for b in app.button if b.label == "Ajouter des scènes").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state["plan"].scenes), 1)
            self.assertEqual(app.session_state["plan"].scenes[0].visual_prompt, "")
            self.assertTrue(any("Prompt scène" in t.label for t in app.text_area))

    def test_invalidation_and_exclusion(self):
        scene = self.scenes[0]
        state = validate_scene_video(self.state, scene, self.image, self.video)
        for invalidate in (invalidate_scene_image, invalidate_scene_content, invalidate_scene_video):
            self.assertFalse(is_scene_video_validated(invalidate(state, 1), scene, self.image, self.video))
        excluded = set_scene_included(state, 1, False)
        self.assertFalse(is_scene_video_validated(excluded, scene, self.image, self.video))
        self.assertTrue(is_scene_video_validated(set_scene_included(excluded, 1, True), scene, self.image, self.video))
        with self.assertRaises(ProductionStateError):
            validate_scene_video(excluded, scene, self.image, self.video)

    def test_legacy_state_requires_video_validation(self):
        path = self.root / "state.json"
        save_production_state(self.state, path)
        data = json.loads(path.read_text())
        for item in data["scenes"].values():
            item.pop("video_validated_sha256")
        path.write_text(json.dumps(data))
        self.assertFalse(is_scene_video_validated(load_production_state(path), self.scenes[0], self.image, self.video))

    def test_single_scene_submission_and_readiness_gate(self):
        pipeline = Mock()
        scene = self.scenes[2]
        single = replace(self.plan, scenes=[scene])
        pipeline.prepare_plan.return_value = (single, ["prepared"])
        kwargs = dict(plan=self.plan, scene=scene, state=self.state,
                      image_path=self.image, pipeline=pipeline, dialogue_rewriter=Mock(),
                      job_id="test", aspect_ratio="9:16", size="720p")
        generate_scene_video(**kwargs)
        args = pipeline.prepare_plan.call_args.kwargs
        self.assertEqual([s.number for s in args["plan"].scenes], [4])
        self.assertEqual(args["scene_reference_images"], {4: self.image})
        self.assertEqual(args["reference_images"], {})
        self.assertIsNone(args["dialogue_rewriter"])
        self.assertEqual(pipeline.generate_scenes.call_args.kwargs["plan"].total_duration, 6)
        pipeline.reset_mock()
        kwargs["state"] = set_scene_included(self.state, 4, False)
        with self.assertRaises(ProductionStateError):
            generate_scene_video(**kwargs)
        pipeline.prepare_plan.assert_not_called()
        pipeline.generate_scenes.assert_not_called()

    def test_silent_scene_has_no_tts(self):
        pipeline = VideoPipeline(self.root / "audio", self.root / "video", agnes_client=Mock())
        pipeline.voice_generator = Mock()
        final, prepared = pipeline.prepare_plan(
            replace(self.plan, scenes=[self.scenes[2]]),
            scene_reference_images={4: self.image}, preserve_scene_durations=True,
        )
        pipeline.voice_generator.generate.assert_not_called()
        self.assertIsNone(prepared[0].audio_path)
        self.assertEqual(final.total_duration, 6)

    def test_native_audio_skips_tts_and_keeps_prompt(self):
        pipeline = Mock()
        scene = replace(self.scenes[0], visual_prompt='Marcel dit en français : « Bonjour Victor. »')
        state = validate_scene_content(self.state, scene)
        generate_scene_video(
            plan=replace(self.plan, scenes=[scene]), scene=scene, state=state,
            image_path=self.image, pipeline=pipeline, dialogue_rewriter=Mock(),
            job_id="native_test", aspect_ratio="9:16", size="720P", native_audio=True,
        )
        pipeline.prepare_plan.assert_not_called()
        item = pipeline.generate_scenes.call_args.kwargs["prepared_scenes"][0]
        self.assertTrue(item.native_audio)
        self.assertIsNone(item.audio_path)
        self.assertEqual(item.scene_reference_image_path, self.image)
        prompt = VideoPipeline.build_scene_prompt(
            Mock(), plan=self.plan, scene=scene, speaking=False, native_audio=True,
        )
        self.assertIn(scene.visual_prompt, prompt)
        self.assertNotIn("No generated speech", prompt)
        self.assertNotIn("remain silent", prompt)
        self.assertNotIn("<Audio 1>", prompt)

    def test_dialogue_shortened_only_when_it_exceeds_scene_budget(self):
        for durations, expected_rewrites in (([1.0], 0), ([5.0, 1.0], 1)):
            pipeline = VideoPipeline(self.root / "audio", self.root / "video", agnes_client=Mock())
            pipeline.voice_generator = Mock()
            pipeline.get_audio_duration = Mock(side_effect=durations)
            rewriter = Mock(return_value="Short dialogue")
            scene = replace(self.scenes[0], duration=4, dialogue="Original dialogue")
            final, _ = pipeline.prepare_plan(
                replace(self.plan, scenes=[scene]), dialogue_rewriter=rewriter,
                scene_reference_images={1: self.image}, preserve_scene_durations=True,
            )
            self.assertEqual(rewriter.call_count, expected_rewrites)
            self.assertEqual(final.total_duration, 4)

    def test_ui_validation_and_assembly_order(self):
        from PIL import Image
        from streamlit.testing.v1 import AppTest
        from src.job_manager import JobManager
        from types import SimpleNamespace

        job = JobManager(self.root, "project_001")
        job.save_plan(self.plan)
        image_dir = job.job_dir / "scene_references"
        image_dir.mkdir()
        state = self.state
        for scene in self.scenes:
            image = image_dir / f"scene_{scene.number:02d}.png"
            Image.new("RGB", (8, 8)).save(image)
            state = validate_scene_image(state, scene.number, image)
            video = job.job_dir / f"scene_{scene.number:02d}.mp4"
            video.write_bytes(b"test video")
            if scene.number in (1, 7):
                state = validate_scene_video(state, scene, image, video)
        state = set_scene_included(state, 2, False)
        save_production_state(state, job.job_dir / "production_state.json")
        with patch("src.config.OUTPUT_DIR", self.root), patch("src.video_assembler.VideoAssembler") as assembler:
            def assemble(**kwargs):
                kwargs["output_path"].write_bytes(b"assembled")
                return SimpleNamespace(duration=18)
            assembler.return_value.assemble.side_effect = assemble
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
            self.assertFalse(app.exception)
            app.button(key="validate_video_project_001_4").click().run()
            self.assertFalse(app.exception)
            button = next(b for b in app.button if b.label.startswith("Assembler les"))
            button.click().run()
            self.assertFalse(app.exception)
            args = assembler.return_value.assemble.call_args.kwargs
            self.assertEqual(args["output_path"].name, "final_video_raw.mp4")
            self.assertEqual(args["plan"].total_duration, 18)
            self.assertEqual([s.number for s in args["plan"].scenes], [1, 4, 7])
            self.assertEqual(list(args["scene_paths"]), [1, 4, 7])
            missing_button = next(b for b in app.button if "manquante(s)" in b.label)
            self.assertTrue(missing_button.disabled)
            with patch("src.scene_video_production.generate_scene_video") as generate:
                def regenerate(**kwargs):
                    number = kwargs["scene"].number
                    (job.job_dir / f"scene_{number:02d}.mp4").write_bytes(b"regenerated")
                generate.side_effect = regenerate
                app.button(key="generate_video_project_001_4").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(generate.call_count, 1)
                self.assertEqual(generate.call_args.kwargs["scene"].number, 4)
            saved = load_production_state(job.job_dir / "production_state.json")
            self.assertEqual(saved.scenes[4].video_validated_sha256, "")
            self.assertTrue(saved.scenes[1].video_validated_sha256)
            self.assertTrue(saved.scenes[7].video_validated_sha256)
            self.assertEqual((job.job_dir / "scene_01.mp4").read_bytes(), b"test video")
            self.assertFalse((job.job_dir / "final_video.mp4").exists())
            self.assertFalse((job.job_dir / "final_video_raw.mp4").exists())
            next(n for n in app.number_input if n.label == "Nombre de scènes à ajouter").set_value(10)
            next(b for b in app.button if b.label == "Ajouter des scènes").click().run()
            self.assertFalse(app.exception)
            updated = app.session_state["plan"]
            self.assertEqual(len(updated.scenes), 14)
            self.assertEqual([s.number for s in updated.scenes[:4]], [1, 2, 4, 7])
            self.assertEqual([s.number for s in updated.scenes[4:]], list(range(8, 18)))
            saved = load_production_state(job.job_dir / "production_state.json")
            self.assertTrue(saved.scenes[1].video_validated_sha256)
            self.assertTrue(all(not saved.scenes[n].included for n in range(8, 18)))


if __name__ == "__main__":
    unittest.main()
