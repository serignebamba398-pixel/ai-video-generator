import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.agnes_client import AgnesAPIError, AgnesClient
from src.agnes_task_accounts import account_fingerprint, wait_for_saved_task
from src.video_pipeline import VideoPipeline


class TaskAccountTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "scene_14.task.json"
        self.first = AgnesClient(api_key="first")
        self.second = AgnesClient(api_key="second")
        env = patch.dict(os.environ, {"AGNES_API_KEY": "first", "AGNES_API_KEY2": "second"})
        env.start()
        self.addCleanup(env.stop)

    def test_resume_from_other_port_uses_original_account(self):
        VideoPipeline._save_task_state(self.path, "task", account_fingerprint(self.first))
        with patch.object(AgnesClient, "wait_for_video", autospec=True, return_value="url") as wait:
            self.assertEqual(wait_for_saved_task(self.second, self.path, video_id="task"), "url")
            self.assertEqual(wait.call_args.args[0].api_key, "first")
            self.assertEqual(wait.call_args.args[0].headers["Authorization"], "Bearer first")
        self.assertEqual(self.second.api_key, "second")
        self.assertNotIn("first", self.path.read_text())

    def test_old_task_tries_other_account_after_404(self):
        VideoPipeline._save_task_state(self.path, "task")
        with patch.object(AgnesClient, "wait_for_video", autospec=True,
                          side_effect=[AgnesAPIError("task not found", status_code=404), "url"]) as wait:
            self.assertEqual(wait_for_saved_task(self.second, self.path, video_id="task"), "url")
            self.assertEqual([call.args[0].api_key for call in wait.call_args_list], ["second", "first"])

    def test_authentication_error_does_not_try_other_account(self):
        VideoPipeline._save_task_state(self.path, "task")
        with patch.object(AgnesClient, "wait_for_video", side_effect=AgnesAPIError("request failed", status_code=403)) as wait:
            with self.assertRaises(AgnesAPIError):
                wait_for_saved_task(self.second, self.path, video_id="task")
            self.assertEqual(wait.call_count, 1)

    def test_missing_owner_key_keeps_task(self):
        VideoPipeline._save_task_state(self.path, "task", "unconfigured-fingerprint")
        with patch.object(AgnesClient, "wait_for_video") as wait:
            with self.assertRaisesRegex(AgnesAPIError, "clé Agnes"):
                wait_for_saved_task(self.second, self.path, video_id="task")
            wait.assert_not_called()
        self.assertEqual(json.loads(self.path.read_text())["video_id"], "task")

    def test_known_owner_404_does_not_query_other_account(self):
        VideoPipeline._save_task_state(self.path, "task", account_fingerprint(self.first))
        with patch.object(AgnesClient, "wait_for_video", side_effect=AgnesAPIError("task not found", status_code=404)) as wait:
            with self.assertRaises(AgnesAPIError):
                wait_for_saved_task(self.second, self.path, video_id="task")
            self.assertEqual(wait.call_count, 1)

    def test_failed_http_request_is_not_a_failed_generation(self):
        self.assertFalse(VideoPipeline._is_terminal_task_error(
            AgnesAPIError("Agnes video status request failed.", status_code=403)))
        self.assertTrue(VideoPipeline._is_terminal_task_error(
            AgnesAPIError("Agnes video task failed. status=failed")))


if __name__ == "__main__":
    unittest.main()
