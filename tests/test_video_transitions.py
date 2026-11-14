import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.scene_planner import Scene, VideoPlan
from src.video_assembler import VideoAssembler
from src.video_transitions import transition_timing


class TransitionTests(unittest.TestCase):
    def test_timing_and_limits(self):
        self.assertEqual(transition_timing([12, 12, 12], .25, 24), (.25, 35.5))
        self.assertEqual(transition_timing([12], .25, 24), (0, 12))
        self.assertEqual(transition_timing([12, 12], 0, 24), (0, 24))
        with self.assertRaises(ValueError):
            transition_timing([1, 1], 1, 24)

    def test_real_three_clip_dissolve_and_single_clip(self):
        assembler = VideoAssembler(video_preset="ultrafast")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            for number, color in ((1, "red"), (4, "blue"), (7, "green")):
                path = root / f"scene_{number:02d}.mp4"
                command = [assembler.ffmpeg, "-v", "error", "-y", "-f", "lavfi",
                           "-i", f"color=c={color}:s=96x64:r=24:d=4"]
                if number != 1:
                    command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-c:a", "aac"]
                command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
                subprocess.run(command, check=True, capture_output=True)
                paths[number] = path
            plan = VideoPlan("Transitions", "fr", "", "", "", "", [],
                             [Scene(n, 4, "Test") for n in paths])
            output = root / "final.mp4"
            result = assembler.assemble(plan, paths, output, transition_seconds=.25)
            self.assertAlmostEqual(result.duration, 11.5, delta=.1)
            self.assertTrue(assembler.probe(output).has_audio)
            manifest = json.loads((root / "assembly_manifest.json").read_text())
            self.assertEqual(manifest["transition_seconds"], .25)
            self.assertEqual([s["scene_number"] for s in manifest["scenes"]], [1, 4, 7])
            # Mid-transition pixels must contain BOTH adjacent colors, not a cut or black frame.
            for timestamp, channels in ((3.875, (0, 2)), (7.625, (1, 2))):
                frame = subprocess.run([
                    assembler.ffmpeg, "-v", "error", "-ss", str(timestamp), "-i", str(output),
                    "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
                ], check=True, capture_output=True).stdout
                for channel in channels:
                    self.assertGreater(frame[channel], 35)
            plan.scenes[:] = plan.scenes[:1]
            single = assembler.assemble(plan, paths, root / "single.mp4", transition_seconds=.25)
            self.assertAlmostEqual(single.duration, 4, delta=.1)


if __name__ == "__main__":
    unittest.main()
