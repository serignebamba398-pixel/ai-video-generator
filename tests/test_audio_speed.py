import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from mutagen.mp3 import MP3

from src.audio_speed import TempoVoiceGenerator
from src.video_assembler import VideoAssembler
from src.voice_generator import VoiceGenerationError


class AudioSpeedTests(unittest.TestCase):
    def test_normal_speed_preserves_original(self):
        generator = Mock()
        destination = Path("voice.mp3")
        result = TempoVoiceGenerator(generator).generate("Bonjour", destination)
        generator.generate.assert_called_once_with(text="Bonjour", output_path=destination)
        self.assertIs(result, generator.generate.return_value)

    def test_invalid_speed_rejected(self):
        for speed in (0, -1, 2.1, float("nan"), float("inf")):
            with self.subTest(speed=speed), self.assertRaises(VoiceGenerationError):
                TempoVoiceGenerator(Mock(), speed)

    def test_real_audio_duration_and_source_preservation(self):
        ffmpeg = VideoAssembler().ffmpeg
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "cached.mp3"
            subprocess.run(
                [ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                 "sine=frequency=440:duration=2", str(source)],
                capture_output=True, check=True,
            )
            original = source.read_bytes()
            generator = Mock()
            generator.generate.side_effect = lambda text, output_path: output_path.write_bytes(original)
            for speed in (0.25, 0.5, 1.25, 2.0):
                with self.subTest(speed=speed):
                    output = directory / f"speed_{speed}.mp3"
                    TempoVoiceGenerator(generator, speed).generate("Bonjour", output)
                    self.assertAlmostEqual(MP3(output).info.length, 2 / speed, delta=0.15)
                    self.assertEqual(source.read_bytes(), original)

    def test_failed_synthesis_preserves_existing_output(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "voice.mp3"
            output.write_bytes(b"existing preview")
            generator = Mock()
            generator.generate.side_effect = VoiceGenerationError("Service unavailable")
            with self.assertRaises(VoiceGenerationError):
                TempoVoiceGenerator(generator, 0.25).generate("Bonjour", output)
            self.assertEqual(output.read_bytes(), b"existing preview")
            self.assertEqual(list(Path(directory).iterdir()), [output])
