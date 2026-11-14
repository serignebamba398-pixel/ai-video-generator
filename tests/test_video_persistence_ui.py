import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from src.job_manager import JobManager
from src.scene_planner import Scene, VideoPlan
from src.production_state import (
    ProductionState, sync_production_state, set_scene_included,
    validate_scene_image, validate_scene_content, validate_scene_video,
    save_production_state, load_production_state,
)
from src.video_artifacts import latest_scene_video, scene_video_history


class VideoPersistenceTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.job = JobManager(self.root, "project_001")
        self.scenes = [Scene(n, 8, f"Animation {n}") for n in (1, 2)]
        plan = VideoPlan("Test", "fr", "", "", "", "", [], self.scenes)
        self.job.save_plan(plan)
        refs = self.job.job_dir / "scene_references"
        refs.mkdir()
        state = sync_production_state(ProductionState(), plan)
        for scene in self.scenes:
            image = refs / f"scene_{scene.number:02d}.png"
            Image.new("RGB", (8, 8)).save(image)
            self.clip(scene.number).write_bytes(f"video {scene.number}".encode())
            state = set_scene_included(state, scene.number, True)
            state = validate_scene_image(state, scene.number, image)
            state = validate_scene_content(state, scene)
            state = validate_scene_video(state, scene, image, self.clip(scene.number))
        self.state_path = self.job.job_dir / "production_state.json"
        save_production_state(state, self.state_path)
        output_patch = patch("src.config.OUTPUT_DIR", self.root)
        output_patch.start()
        self.addCleanup(output_patch.stop)
        self.app = self.open_app()

    def clip(self, number):
        return self.job.job_dir / f"scene_{number:02d}.mp4"

    def open_app(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        return app

    def assert_kept(self, number):
        self.assertEqual(self.clip(number).read_bytes(), f"video {number}".encode())

    def test_unchanged_save_other_scene_click_and_reload_keep_videos(self):
        saves = [b for b in self.app.button if b.label == "Enregistrer le prompt"]
        saves[1].click().run()
        self.assertFalse(self.app.exception)
        self.assert_kept(1)
        self.assert_kept(2)
        self.assertTrue(load_production_state(self.state_path).scenes[2].video_validated_sha256)
        self.app.checkbox(key="include_scene_project_001_2").uncheck().run()
        self.assertEqual(len(self.app.get("video")), 2)
        self.assert_kept(1)
        self.assertEqual(len(self.open_app().get("video")), 2)

    def test_withdraw_validation_keeps_player(self):
        self.app.button(key="unvalidate_scene_content_project_001_1").click().run()
        self.assertFalse(self.app.exception)
        self.assert_kept(1)
        self.assertEqual(len(self.app.get("video")), 2)

    def test_adding_scenes_keeps_existing_clips_and_pending_tasks(self):
        task = self.job.job_dir / "scene_02.task.json"
        task.write_text('{"task_id": "existing"}')
        next(b for b in self.app.button if b.label == "Ajouter des scènes").click().run()
        self.assertFalse(self.app.exception)
        self.assert_kept(1)
        self.assert_kept(2)
        self.assertEqual(task.read_text(), '{"task_id": "existing"}')
        self.assertEqual(len(self.app.session_state["plan"].scenes), 3)

    def test_changed_prompt_archives_and_never_validates_old_clip(self):
        self.app.text_area(key="scene_prompt_text_project_001_1").set_value("Nouvelle animation")
        next(b for b in self.app.button if b.label == "Enregistrer le prompt").click().run()
        self.assertFalse(self.app.exception)
        self.assertFalse(self.clip(1).exists())
        self.assertEqual(latest_scene_video(self.job.job_dir, 1).read_bytes(), b"video 1")
        self.assert_kept(2)
        self.app.button(key="validate_scene_content_project_001_1").click().run()
        self.assertNotIn("validate_video_project_001_1", [b.key for b in self.app.button])
        self.assertGreaterEqual(len(self.open_app().get("video")), 2)

    def test_failed_regeneration_keeps_old_version_and_other_scene(self):
        with patch("src.scene_video_production.generate_scene_video", side_effect=RuntimeError("test failure")):
            self.app.button(key="generate_video_project_001_2").click().run()
        self.assertFalse(self.app.exception)
        self.assertTrue(any("test failure" in e.value for e in self.app.error))
        self.assertEqual(latest_scene_video(self.job.job_dir, 2).read_bytes(), b"video 2")
        self.assertEqual(len(scene_video_history(self.job.job_dir, 2)), 1)
        self.assert_kept(1)
        self.assertGreaterEqual(len(self.app.get("video")), 2)

    def test_bulk_generation_passes_director_plan_and_keeps_sibling(self):
        from src.video_artifacts import archive_scene_outputs
        archive_scene_outputs(self.job.job_dir, 2)
        self.app.run()
        def generate(**kwargs):
            self.assertIsNone(kwargs["director_plan"])
            self.assertEqual(kwargs["scene"].number, 2)
            self.clip(2).write_bytes(b"new video")
        with patch("src.scene_video_production.generate_scene_video", side_effect=generate) as mocked:
            next(b for b in self.app.button if "manquante(s)" in b.label).click().run()
        self.assertFalse(self.app.exception)
        self.assertFalse(self.app.error)
        mocked.assert_called_once()
        self.assert_kept(1)


if __name__ == "__main__":
    unittest.main()
