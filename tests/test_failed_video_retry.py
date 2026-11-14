import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from src.agnes_client import AgnesAPIError, AgnesClient
from src.agnes_task_accounts import account_fingerprint
from src.video_pipeline import VideoPipeline


class FailedVideoRetryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'scene.task.json'
        self.pipeline = object.__new__(VideoPipeline)
        self.pipeline.agnes = AgnesClient(api_key='test-key')
        self.pipeline._save_task_state(self.path, 'old', account_fingerprint(self.pipeline.agnes))
        self.submit = Mock(return_value='replacement')
        self.progress = Mock()
        sleeper = patch('src.video_pipeline.time.sleep')
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def run_wait(self):
        return self.pipeline._wait_with_failed_task_retries(
            'old', self.path, self.submit, self.progress)

    def test_internal_failure_submits_and_saves_new_task_then_succeeds(self):
        responses = [
            {'status': 'failed', 'error': {'code': 'internal_error', 'message': 'generation failed'}},
            {'status': 'completed', 'url': 'https://example.com/video.mp4'},
        ]
        with patch.object(AgnesClient, 'get_video_status', side_effect=responses) as status:
            video_id, url = self.run_wait()
        self.assertEqual(video_id, 'replacement')
        self.assertEqual(url, 'https://example.com/video.mp4')
        self.assertEqual([call.args[0] for call in status.call_args_list], ['old', 'replacement'])
        self.submit.assert_called_once()
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['video_id'], 'replacement')
        self.assertEqual(saved['account_fingerprint'], account_fingerprint(self.pipeline.agnes))
        self.sleep.assert_called_once_with(self.pipeline.QUEUE_RETRY_DELAY)

    def test_repeated_failures_stop_after_three_replacements(self):
        with patch.object(AgnesClient, 'get_video_status', return_value={'status': 'failed'}):
            with self.assertRaises(AgnesAPIError):
                self.run_wait()
        self.assertEqual(self.submit.call_count, 3)

    def test_uncertain_or_cancelled_tasks_never_resubmit(self):
        for error in [
            AgnesAPIError('Timed out'),
            AgnesAPIError('HTTP error', status_code=503, retryable=True),
            AgnesAPIError('cancelled', response_body='{"status":"cancelled"}'),
            AgnesAPIError('rejected', response_body='{"status":"rejected"}'),
        ]:
            with self.subTest(error=str(error)):
                with patch('src.video_pipeline.wait_for_saved_task', side_effect=error):
                    with self.assertRaises(AgnesAPIError):
                        self.run_wait()
                self.submit.assert_not_called()
                self.assertEqual(json.loads(self.path.read_text())['video_id'], 'old')


if __name__ == '__main__':
    unittest.main()
