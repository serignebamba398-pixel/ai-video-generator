"""Apply a playback tempo to synthesized speech before measuring its duration."""

import math
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from src.video_assembler import VideoAssembler, VideoAssemblyError
from src.voice_generator import VoiceGenerationError


class TempoVoiceGenerator:
    def __init__(self, generator, speed=1.0):
        self.generator = generator
        self.speed = float(speed)
        if not math.isfinite(self.speed) or not 0.25 <= self.speed <= 2.0:
            raise VoiceGenerationError("La vitesse audio doit être comprise entre ×0,25 et ×2.")

    def generate(self, text, output_path):
        if self.speed == 1.0:
            return self.generator.generate(text=text, output_path=output_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Keep each atempo stage in its conservative 0.5–2 range.
        remaining = self.speed
        filters = []
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining:g}")
        try:
            with TemporaryDirectory(dir=output_path.parent) as directory:
                original = Path(directory) / "original.mp3"
                adjusted = Path(directory) / "adjusted.mp3"
                self.generator.generate(text=text, output_path=original)
                subprocess.run(
                    [VideoAssembler().ffmpeg, "-v", "error", "-i", str(original),
                     "-vn", "-af", ",".join(filters), "-c:a", "libmp3lame",
                     "-b:a", "128k", str(adjusted)],
                    capture_output=True, check=True,
                )
                adjusted.replace(output_path)
        except (OSError, subprocess.CalledProcessError, VideoAssemblyError) as exc:
            raise VoiceGenerationError("Impossible d'appliquer la vitesse audio choisie.") from exc
        return output_path
