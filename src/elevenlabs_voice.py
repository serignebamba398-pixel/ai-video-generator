import hashlib
import json
import os
import shutil
from pathlib import Path
from urllib.parse import quote

import requests
from mutagen.mp3 import MP3

from src.voice_generator import VoiceGenerationError


class ElevenLabsVoiceGenerator:
    def __init__(self, voice_id, cache_dir, model="eleven_multilingual_v2", api_key=None):
        self.voice_id = voice_id.strip()
        self.model = model
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY", "")
        self.cache_dir = Path(cache_dir)

    def _headers(self):
        if not self.api_key:
            raise VoiceGenerationError("Ajoute ELEVENLABS_API_KEY dans le fichier .env puis relance l'app.")
        return {"xi-api-key": self.api_key}

    def list_voices(self):
        voices = []
        params = {"page_size": 100}
        try:
            while True:
                response = requests.get("https://api.elevenlabs.io/v2/voices", headers=self._headers(), params=params, timeout=30)
                if not response.ok:
                    raise VoiceGenerationError(f"ElevenLabs : accès aux voix refusé (HTTP {response.status_code}).")
                data = response.json()
                voices.extend(data.get("voices", []))
                if not data.get("has_more") or not data.get("next_page_token"):
                    return voices
                params["next_page_token"] = data["next_page_token"]
        except (requests.RequestException, ValueError) as exc:
            raise VoiceGenerationError("Impossible de charger les voix ElevenLabs.") from exc

    def generate(self, text, output_path):
        text = text.strip()
        if not text or not self.voice_id:
            raise VoiceGenerationError("Choisis une voix ElevenLabs et un dialogue non vide.")
        payload = {"text": text, "model_id": self.model, "language_code": "fr"}
        digest = hashlib.sha256(json.dumps([self.voice_id, payload], sort_keys=True).encode()).hexdigest()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached = self.cache_dir / f"{digest}.mp3"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cached.exists():
            try:
                response = requests.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{quote(self.voice_id, safe='')}",
                    headers=self._headers(), params={"output_format": "mp3_44100_128"},
                    json=payload, timeout=120,
                )
                if not response.ok:
                    raise VoiceGenerationError(
                        f"ElevenLabs : génération refusée (HTTP {response.status_code}). "
                        "Vérifie la clé API, l'accès à la voix et les crédits."
                    )
                from io import BytesIO
                if not response.content or MP3(BytesIO(response.content)).info.length <= 0:
                    raise ValueError("Invalid audio")
                temporary = cached.with_suffix(".tmp")
                temporary.write_bytes(response.content)
                temporary.replace(cached)
            except VoiceGenerationError:
                raise
            except Exception as exc:
                raise VoiceGenerationError("Impossible de générer un MP3 valide avec ElevenLabs.") from exc
        shutil.copyfile(cached, output_path)
        return output_path
