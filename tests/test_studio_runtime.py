import inspect
import unittest
from unittest.mock import patch

from src import scene_video_production
from src.studio.runtime import ensure_generation_compatibility


class StudioRuntimeTests(unittest.TestCase):
    def test_reload_stale_generation_module(self):
        def old_generation(*, plan):
            raise AssertionError("Stale function must never generate a video")

        with patch.object(
            scene_video_production, "generate_scene_video", old_generation
        ):
            ensure_generation_compatibility()
            parameters = inspect.signature(
                scene_video_production.generate_scene_video
            ).parameters
            self.assertIn("native_audio", parameters)

    def test_current_runtime_is_not_reloaded(self):
        with patch("src.studio.runtime.importlib.reload") as reload:
            ensure_generation_compatibility()
            reload.assert_not_called()
