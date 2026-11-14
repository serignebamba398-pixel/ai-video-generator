import asyncio
from pathlib import Path

import edge_tts


class VoiceGenerationError(Exception):
    """Raised when speech synthesis fails."""


class VoiceGenerator:
    """
    Generate speech audio using Microsoft Edge TTS.
    """

    VOICES = {
        "French Male": "fr-FR-HenriNeural",
        "French Female": "fr-FR-DeniseNeural",
    }

    def __init__(
        self,
        voice: str = "fr-FR-HenriNeural",
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
    ):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.pitch = pitch

    async def _generate_async(
        self,
        text: str,
        output_path: Path,
    ) -> Path:

        text = text.strip()

        if not text:
            raise VoiceGenerationError(
                "The speech text cannot be empty."
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                volume=self.volume,
                pitch=self.pitch,
            )

            await communicate.save(
                str(output_path)
            )

        except Exception as exc:
            raise VoiceGenerationError(
                f"Speech generation failed: {exc}"
            ) from exc

        if not output_path.exists():
            raise VoiceGenerationError(
                "The audio file was not created."
            )

        if output_path.stat().st_size == 0:
            raise VoiceGenerationError(
                "The generated audio file is empty."
            )

        return output_path

    def generate(
        self,
        text: str,
        output_path: Path,
    ) -> Path:

        return asyncio.run(
            self._generate_async(
                text=text,
                output_path=output_path,
            )
        )