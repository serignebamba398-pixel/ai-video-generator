import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

from PIL import Image

from src.agnes_client import AgnesAPIError
from src.scene_image_generator import generate_scene_image


class SceneImageGeneratorTests(unittest.TestCase):
    def test_normalizes_image_and_cleans_temporary_file(self):
        client = Mock()
        def generate(**kwargs):
            Image.new("RGB", (8, 8), "red").save(kwargs["output_path"], format="JPEG")
        client.generate_image.side_effect = generate
        result = generate_scene_image(client, "Scene prompt", "16:9")
        with Image.open(BytesIO(result)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (8, 8))
        arguments = client.generate_image.call_args.kwargs
        self.assertEqual(arguments["ratio"], "16:9")
        self.assertFalse(arguments["output_path"].exists())

    def test_rejects_invalid_response_and_cleans_up(self):
        client = Mock()
        client.generate_image.side_effect = lambda **kw: kw["output_path"].write_bytes(b"not an image")
        with self.assertRaises(OSError):
            generate_scene_image(client, "Scene", "9:16")
        self.assertFalse(client.generate_image.call_args.kwargs["output_path"].exists())

    def test_api_failure_propagates(self):
        client = Mock()
        client.generate_image.side_effect = AgnesAPIError("Unavailable")
        with self.assertRaises(AgnesAPIError):
            generate_scene_image(client, "Scene", "9:16")

    def test_empty_prompt_does_not_call_api(self):
        client = Mock()
        with self.assertRaises(ValueError):
            generate_scene_image(client, "  ", "9:16")
        client.generate_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
