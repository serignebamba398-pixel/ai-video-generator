import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.video_artifacts import (
    archive_final_outputs,
    archive_scene_outputs,
    latest_scene_video,
    scene_video_history,
)


class VideoArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name)

    def write(self, relative, content):
        path = self.job / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_archive_preserves_scene_files_and_other_scenes(self):
        clip = self.write("scene_04.mp4", b"old scene 4")
        task = self.write("scene_04.task.json", b'{"task_id": "abc"}')
        frame = self.write("continuity/scene_04_last.jpg", b"last frame")
        sibling = self.write("scene_01.mp4", b"scene 1")
        sibling_task = self.write("scene_01.task.json", b"task 1")
        archive_scene_outputs(self.job, 4)

        history = scene_video_history(self.job, 4)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].read_bytes(), b"old scene 4")
        self.assertEqual((history[0].parent / task.name).read_bytes(), b'{"task_id": "abc"}')
        self.assertEqual((history[0].parent / frame.name).read_bytes(), b"last frame")
        self.assertFalse(any(path.exists() for path in (clip, task, frame)))
        self.assertEqual(sibling.read_bytes(), b"scene 1")
        self.assertEqual(sibling_task.read_bytes(), b"task 1")

    def test_repeated_archive_without_active_outputs_is_noop(self):
        self.write("scene_01.mp4", b"video")
        archive_scene_outputs(self.job, 1)
        before = scene_video_history(self.job, 1)
        archive_scene_outputs(self.job, 1)
        self.assertEqual(scene_video_history(self.job, 1), before)
        archive_scene_outputs(self.job, 99)
        self.assertFalse((self.job / "history/scene_99").exists())

    def test_latest_prefers_current_then_newest_archive(self):
        self.write("scene_01.mp4", b"first")
        archive_scene_outputs(self.job, 1)
        self.write("scene_01.mp4", b"second")
        archive_scene_outputs(self.job, 1)
        self.assertEqual([path.read_bytes() for path in scene_video_history(self.job, 1)],
                         [b"second", b"first"])
        self.assertEqual(latest_scene_video(self.job, 1).read_bytes(), b"second")
        current = self.write("scene_01.mp4", b"current")
        self.assertEqual(latest_scene_video(self.job, 1), current)

    def test_empty_files_and_incomplete_archives_are_not_previews(self):
        self.write("scene_01.mp4", b"")
        self.write("history/scene_01/old/scene_01.mp4", b"")
        self.write("history/scene_01/.pending_new/scene_01.mp4", b"incomplete")
        self.assertIsNone(latest_scene_video(self.job, 1))
        self.assertEqual(scene_video_history(self.job, 1), [])
        good = self.write("history/scene_01/valid/scene_01.mp4", b"valid")
        self.assertEqual(latest_scene_video(self.job, 1), good)
        archive_scene_outputs(self.job, 1)
        self.assertFalse((self.job / "scene_01.mp4").exists())
        self.assertEqual(scene_video_history(self.job, 1), [good])

    def test_copy_failure_keeps_all_active_artifacts_and_hides_partial_copy(self):
        import shutil

        clip = self.write("scene_01.mp4", b"keep this video")
        task = self.write("scene_01.task.json", b"keep this task")
        copy2 = shutil.copy2

        def fail_on_task(source, target):
            if source == task:
                raise OSError("disk full")
            return copy2(source, target)

        with patch("src.video_artifacts.shutil.copy2", side_effect=fail_on_task):
            with self.assertRaisesRegex(OSError, "disk full"):
                archive_scene_outputs(self.job, 1)
        self.assertEqual(clip.read_bytes(), b"keep this video")
        self.assertEqual(task.read_bytes(), b"keep this task")
        self.assertEqual(scene_video_history(self.job, 1), [])
        self.assertEqual(latest_scene_video(self.job, 1), clip)

    def test_final_outputs_archived_together_without_touching_scene(self):
        expected = {
            "final_video_raw.mp4": b"raw master",
            "final_video.mp4": b"master",
            "assembly_manifest.json": b'{"scenes": [1, 4]}',
        }
        for filename, content in expected.items():
            self.write(filename, content)
        scene = self.write("scene_01.mp4", b"scene")
        archive_final_outputs(self.job)
        versions = list((self.job / "history/assembly").iterdir())
        self.assertEqual(len(versions), 1)
        for filename, content in expected.items():
            self.assertEqual((versions[0] / filename).read_bytes(), content)
            self.assertFalse((self.job / filename).exists())
        self.assertEqual(scene.read_bytes(), b"scene")
        archive_final_outputs(self.job)
        self.assertEqual(list((self.job / "history/assembly").iterdir()), versions)


if __name__ == "__main__":
    unittest.main()
