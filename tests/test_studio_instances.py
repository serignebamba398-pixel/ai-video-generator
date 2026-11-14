import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch


CONFIG = Path(__file__).resolve().parents[1] / "src" / "config.py"


class StudioInstanceTests(unittest.TestCase):
    def config(self, **env):
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"), patch.object(Path, "mkdir"):
            return runpy.run_path(str(CONFIG))

    def test_default_keeps_existing_projects_and_first_key(self):
        config = self.config(AGNES_API_KEY="first", AGNES_API_KEY2="second")
        self.assertEqual(config["AGNES_API_KEY"], "first")
        self.assertEqual(config["OUTPUT_DIR"], CONFIG.parents[1] / "videos")

    def test_second_account_shares_projects_media_and_uploads(self):
        first = self.config(AGNES_API_KEY="first")
        second = self.config(STUDIO_INSTANCE="2", AGNES_API_KEY="first", AGNES_API_KEY2="second")
        self.assertEqual(second["AGNES_API_KEY"], "second")
        self.assertEqual(first["AGNES_API_KEY"], "first")
        for name in ("OUTPUT_DIR", "AUDIO_DIR", "REFERENCE_DIR", "UPLOADS_DIR"):
            self.assertEqual(first[name], second[name])
            self.assertEqual(second[name].parent, CONFIG.parents[1])

    def test_second_account_never_falls_back_to_first_key(self):
        with self.assertRaisesRegex(RuntimeError, "AGNES_API_KEY2"):
            self.config(STUDIO_INSTANCE="2", AGNES_API_KEY="first")

    def test_invalid_instance_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "STUDIO_INSTANCE"):
            self.config(STUDIO_INSTANCE="3", AGNES_API_KEY="first")


if __name__ == "__main__":
    unittest.main()
