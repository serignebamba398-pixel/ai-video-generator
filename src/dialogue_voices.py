import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from src.elevenlabs_voice import ElevenLabsVoiceGenerator
from src.scene_prompt_analysis import analyze_scene_prompt, DialogueTurn
from src.video_assembler import VideoAssembler
from src.voice_generator import VoiceGenerationError


def scene_turns(scene):
    if not scene.dialogue.strip():
        return ()
    turns = analyze_scene_prompt(scene.visual_prompt).turns
    if len({t.speaker.casefold() for t in turns}) > 1:
        if "\n".join(t.dialogue for t in turns) != scene.dialogue:
            raise VoiceGenerationError("Le dialogue a changé : analyse et confirme à nouveau le prompt.")
        return turns
    return (DialogueTurn(scene.speaker_id or (turns[0].speaker if turns else "Narrateur"), scene.dialogue),)


def load_voices(job_dir):
    path = Path(job_dir) / "character_voices.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_voices(job_dir, voices):
    path = Path(job_dir) / "character_voices.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(voices, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class DialogueVoiceGenerator:
    def __init__(self, scene, voices, cache_dir, model):
        self.turns = scene_turns(scene)
        self.voices = voices
        self.cache_dir = Path(cache_dir)
        self.model = model

    def generate(self, text, output_path):
        if text.strip() != "\n".join(t.dialogue for t in self.turns).strip():
            raise VoiceGenerationError("Le texte audio ne correspond pas au dialogue confirmé.")
        assigned = [self.voices.get(t.speaker.casefold(), "").strip() for t in self.turns]
        if not assigned or not all(assigned):
            raise VoiceGenerationError("Choisis une voix ElevenLabs pour chaque personnage avant de générer le dialogue.")
        key = hashlib.sha256(json.dumps([[(t.speaker, t.dialogue, v) for t, v in zip(self.turns, assigned)], self.model]).encode()).hexdigest()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached = self.cache_dir / f"dialogue_{key}.mp3"
        if not cached.exists():
            ffmpeg = VideoAssembler().ffmpeg
            try:
                with TemporaryDirectory(dir=self.cache_dir) as directory:
                    directory = Path(directory)
                    pcm = directory / "dialogue.pcm"
                    with pcm.open("wb") as out:
                        for index, (turn, voice) in enumerate(zip(self.turns, assigned)):
                            clip = directory / f"{index}.mp3"
                            ElevenLabsVoiceGenerator(voice, self.cache_dir, model=self.model).generate(turn.dialogue, clip)
                            result = subprocess.run([ffmpeg, "-v", "error", "-i", str(clip), "-f", "s16le", "-ac", "1", "-ar", "44100", "-"], capture_output=True, check=True)
                            if index:
                                out.write(b"\0" * (int(44100 * 0.2) * 2))
                            out.write(result.stdout)
                    combined = directory / "combined.mp3"
                    subprocess.run([ffmpeg, "-v", "error", "-f", "s16le", "-ar", "44100", "-ac", "1", "-i", str(pcm), "-c:a", "libmp3lame", "-b:a", "128k", str(combined)], capture_output=True, check=True)
                    combined.replace(cached)
            except subprocess.CalledProcessError as exc:
                raise VoiceGenerationError("Impossible d'assembler les répliques audio.") from exc
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, output_path)
        return output_path
