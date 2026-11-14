"""Frame-aligned audiovisual transitions between normalized scenes."""
import math


def transition_timing(durations, seconds, fps):
    if not math.isfinite(seconds) or seconds < 0 or fps <= 0:
        raise ValueError("Durée de transition invalide.")
    overlap = round(seconds * fps) / fps if len(durations) > 1 else 0.0
    if overlap and any(duration <= 2 * overlap for duration in durations):
        raise ValueError("La transition est trop longue pour ces scènes.")
    return overlap, sum(durations) - overlap * max(0, len(durations) - 1)


def dissolve_filter(durations, overlap, fps):
    parts = []
    for index, duration in enumerate(durations):
        parts.extend([
            f"[{index}:v]trim=duration={duration},setpts=PTS-STARTPTS,"
            f"fps={fps},settb=AVTB[v{index}]",
            f"[{index}:a]atrim=duration={duration},asetpts=PTS-STARTPTS[a{index}]",
        ])
    video, audio = "v0", "a0"
    elapsed = durations[0]
    for index in range(1, len(durations)):
        last = index == len(durations) - 1
        next_video = "vout" if last else f"mixv{index}"
        next_audio = "aout" if last else f"mixa{index}"
        parts.extend([
            f"[{video}][v{index}]xfade=transition=fade:duration={overlap:.9f}:"
            f"offset={elapsed - overlap:.9f}[{next_video}]",
            f"[{audio}][a{index}]acrossfade=d={overlap:.9f}:c1=tri:c2=tri[{next_audio}]",
        ])
        elapsed += durations[index] - overlap
        video, audio = next_video, next_audio
    return ";".join(parts)
