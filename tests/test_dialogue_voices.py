import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess

from mutagen.mp3 import MP3
from src.dialogue_voices import DialogueVoiceGenerator, save_voices, load_voices
from src.scene_planner import Scene
from src.video_assembler import VideoAssembler
from src.voice_generator import VoiceGenerationError


class DialogueVoiceTests(unittest.TestCase):
    def setUp(self):
        self.scene = Scene(1, 8, 'Marcel dit : « Bonjour. »\nJulie répond : « Salut. »', dialogue='Bonjour.\nSalut.')

    def test_missing_assignment_blocks_audio(self):
        with TemporaryDirectory() as root:
            generator = DialogueVoiceGenerator(self.scene, {"marcel": "one"}, root, "eleven_v3")
            with self.assertRaises(VoiceGenerationError):
                generator.generate(self.scene.dialogue, Path(root) / "out.mp3")

    def test_distinct_voices_combined_and_cached(self):
        with TemporaryDirectory() as root, patch('src.dialogue_voices.ElevenLabsVoiceGenerator') as service:
            root = Path(root)
            voices = {"marcel": "older-man", "julie": "woman"}
            save_voices(root, voices)
            self.assertEqual(load_voices(root), voices)
            ffmpeg = VideoAssembler().ffmpeg
            calls = []
            def make(voice, cache, model):
                class FakeVoice:
                    def generate(self, text, path):
                        calls.append((voice, text))
                        subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.3', str(path)], check=True, capture_output=True)
                return FakeVoice()
            service.side_effect = make
            generator = DialogueVoiceGenerator(self.scene, voices, root / 'cache', 'eleven_v3')
            generator.generate(self.scene.dialogue, root / 'preview.mp3')
            generator.generate(self.scene.dialogue, root / 'video.mp3')
            self.assertEqual(calls, [('older-man', 'Bonjour.'), ('woman', 'Salut.')])
            self.assertEqual((root / 'preview.mp3').read_bytes(), (root / 'video.mp3').read_bytes())
            self.assertAlmostEqual(MP3(root / 'video.mp3').info.length, 0.8, delta=0.1)
