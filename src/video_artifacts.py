"""Keep generated media available when an edit invalidates current outputs."""

from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Optional
from uuid import uuid4


def _nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _archive_outputs(paths: list[Path], history_dir: Path) -> None:
    """Copy every artifact before removing any current output.

    Incomplete copies stay in a hidden pending directory, which readers ignore.
    Filesystem errors propagate so callers cannot proceed after a failed archive.
    """
    existing = [path for path in paths if path.is_file()]
    populated = [path for path in existing if _nonempty_file(path)]
    if populated:
        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        version += "_" + uuid4().hex
        pending = history_dir / (".pending_" + version)
        pending.mkdir(parents=True, exist_ok=False)
        for path in populated:
            target = pending / path.name
            shutil.copy2(path, target)
            if target.stat().st_size != path.stat().st_size:
                raise OSError(f"Incomplete archive of {path}")
        pending.rename(history_dir / version)

    # Remove videos last: a metadata cleanup error leaves the active clip in place.
    for path in sorted(existing, key=lambda item: item.suffix == ".mp4"):
        path.unlink()


def archive_scene_outputs(job_dir: Path, scene_number: int) -> None:
    """Preserve a scene's clip, task and continuity frame before invalidation."""
    job_dir = Path(job_dir)
    name = f"scene_{scene_number:02d}"
    _archive_outputs(
        [
            job_dir / f"{name}.mp4",
            job_dir / f"{name}.task.json",
            job_dir / "continuity" / f"{name}_last.jpg",
        ],
        job_dir / "history" / name,
    )


def scene_video_history(job_dir: Path, scene_number: int) -> list[Path]:
    """Return archived, nonempty clips newest first, excluding pending copies."""
    name = f"scene_{scene_number:02d}"
    history_dir = Path(job_dir) / "history" / name
    return sorted(
        (
            path for path in history_dir.glob(f"*/{name}.mp4")
            if not path.parent.name.startswith(".") and _nonempty_file(path)
        ),
        key=lambda path: path.parent.name,
        reverse=True,
    )


def latest_scene_video(job_dir: Path, scene_number: int) -> Optional[Path]:
    """Find a preview clip, preferring the active version over any history."""
    current = Path(job_dir) / f"scene_{scene_number:02d}.mp4"
    if _nonempty_file(current):
        return current
    history = scene_video_history(job_dir, scene_number)
    return history[0] if history else None


def archive_final_outputs(job_dir: Path) -> None:
    """Preserve assembled masters and their manifest before invalidation."""
    job_dir = Path(job_dir)
    _archive_outputs(
        [job_dir / name for name in (
            "final_video_raw.mp4", "final_video.mp4", "assembly_manifest.json",
        )],
        job_dir / "history" / "assembly",
    )
