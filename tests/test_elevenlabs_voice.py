import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from src.elevenlabs_voice import ElevenLabsVoiceGenerator
from src.voice_generator import VoiceGenerationError


class ElevenLabsTests(unittest.TestCase):
    def test_preview_audio_is_reused_for_generation(self):
        with TemporaryDirectory() as directory, patch("src.elevenlabs_voice.requests.post") as post, patch("src.elevenlabs_voice.MP3") as mp3:
            root = Path(directory)
            post.return_value = Mock(ok=True, content=b"audio")
            mp3.return_value.info.length = 1.5
            voice = ElevenLabsVoiceGenerator("voice123", root / "cache", api_key="test-key")
            voice.generate("Bonjour", root / "preview.mp3")
            voice.generate("Bonjour", root / "video.mp3")
            self.assertEqual(post.call_count, 1)
            self.assertEqual((root / "preview.mp3").read_bytes(), (root / "video.mp3").read_bytes())
            self.assertEqual(post.call_args.kwargs["json"]["text"], "Bonjour")
            voice.generate("Bonsoir", root / "other.mp3")
            self.assertEqual(post.call_count, 2)
            voice.model = "eleven_v3"
            voice.generate("Bonsoir", root / "v3.mp3")
            self.assertEqual(post.call_count, 3)

    def test_missing_key_and_http_error(self):
        with TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True), patch("src.elevenlabs_voice.requests.post") as post:
            voice = ElevenLabsVoiceGenerator("voice", directory)
            with self.assertRaises(VoiceGenerationError):
                voice.generate("Bonjour", Path(directory) / "out.mp3")
            post.assert_not_called()
            voice.api_key = "secret"
            post.return_value = Mock(ok=False, status_code=401)
            with self.assertRaises(VoiceGenerationError) as error:
                voice.generate("Bonjour", Path(directory) / "out.mp3")
            self.assertNotIn("secret", str(error.exception))
            self.assertFalse((Path(directory) / "out.mp3").exists())

    def test_lists_voices(self):
        with patch("src.elevenlabs_voice.requests.get") as get:
            get.return_value = Mock(ok=True)
            get.return_value.json.return_value = {"voices": [{"voice_id": "abc", "name": "French voice"}]}
            self.assertEqual(ElevenLabsVoiceGenerator("", ".", api_key="test").list_voices()[0]["voice_id"], "abc")
