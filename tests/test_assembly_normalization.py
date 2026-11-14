import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.scene_planner import Scene, VideoPlan
from src.video_assembler import VideoAssembler


class AssemblyNormalizationTests(unittest.TestCase):
    def test_mixed_clips_normalized_in_storyboard_order(self):
        assembler = VideoAssembler(video_preset="ultrafast")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {7: root / "scene_07.mp4", 2: root / "scene_02.mp4"}
            subprocess.run([
                assembler.ffmpeg, "-v", "error", "-y", "-f", "lavfi",
                "-i", "color=c=red:s=96x64:r=15:d=1", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(sources[7]),
            ], check=True, capture_output=True)
            subprocess.run([
                assembler.ffmpeg, "-v", "error", "-y", "-f", "lavfi",
                "-i", "color=c=blue:s=64x96:r=30:d=5", "-f", "lavfi",
                "-i", "sine=frequency=440:sample_rate=44100:duration=5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-shortest", str(sources[2]),
            ], check=True, capture_output=True)
            plan = VideoPlan("Order", "fr", "", "", "", "", [], [
                Scene(7, 4, "Red"), Scene(2, 4, "Blue"),
            ])
            output = root / "final_video_raw.mp4"
            result = assembler.assemble(
                plan=plan, scene_paths=sources, output_path=output,
                working_directory=root / "work", cleanup_intermediate=True,
            )
            self.assertAlmostEqual(result.duration, 8, delta=0.2)
            probe = subprocess.run([
                assembler.ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output),
            ], check=True, capture_output=True, text=True)
            streams = json.loads(probe.stdout)["streams"]
            video = next(s for s in streams if s["codec_type"] == "video")
            audio = next(s for s in streams if s["codec_type"] == "audio")
            self.assertEqual((video["codec_name"], video["pix_fmt"], video["r_frame_rate"]),
                             ("h264", "yuv420p", "24/1"))
            self.assertEqual((video["width"], video["height"]), (96, 64))
            self.assertEqual((audio["codec_name"], audio["sample_rate"], audio["channels"]),
                             ("aac", "48000", 2))
            # Confirm actual picture order, independently of scene numbers.
            for timestamp, expected_channel in ((1, 0), (5, 2)):
                frame = subprocess.run([
                    assembler.ffmpeg, "-v", "error", "-ss", str(timestamp), "-i", str(output),
                    "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
                ], check=True, capture_output=True).stdout
                self.assertEqual(frame.index(max(frame)), expected_channel)


if __name__ == "__main__":
    unittest.main()
