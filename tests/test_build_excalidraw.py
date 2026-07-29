import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_excalidraw.py"
SPEC = importlib.util.spec_from_file_location("build_excalidraw", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class BuildSceneTests(unittest.TestCase):
    def test_builds_editable_shapes_labels_and_arrow(self):
        scene = MODULE.build_scene(
            {
                "title": "Test flow",
                "elements": [
                    {
                        "id": "a",
                        "kind": "rectangle",
                        "x": 0,
                        "y": 0,
                        "width": 160,
                        "height": 70,
                        "text": "Start",
                    },
                    {
                        "id": "b",
                        "kind": "ellipse",
                        "x": 260,
                        "y": 0,
                        "width": 160,
                        "height": 70,
                        "text": "Finish",
                    },
                    {"kind": "arrow", "from": "a", "to": "b", "text": "next"},
                ],
            }
        )

        types = [element["type"] for element in scene["elements"]]
        self.assertEqual(types.count("rectangle"), 1)
        self.assertEqual(types.count("ellipse"), 1)
        self.assertEqual(types.count("arrow"), 1)
        self.assertEqual(types.count("text"), 3)
        self.assertEqual(scene["appState"]["name"], "Test flow")
        self.assertEqual(
            scene["source"],
            "https://github.com/iruochen/excalidraw-diagram-skill",
        )

    def test_rejects_unknown_arrow_reference(self):
        with self.assertRaisesRegex(SystemExit, "unknown element"):
            MODULE.build_scene(
                {
                    "elements": [
                        {"id": "a", "kind": "rectangle"},
                        {"kind": "arrow", "from": "a", "to": "missing"},
                    ]
                }
            )

    def test_cli_writes_scene_and_fallback_svg(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            input_path = temporary / "input.scene.json"
            scene_path = temporary / "output.excalidraw"
            svg_path = temporary / "output.svg"
            input_path.write_text(
                json.dumps(
                    {
                        "elements": [
                            {
                                "id": "box",
                                "kind": "rectangle",
                                "x": 10,
                                "y": 10,
                                "width": 180,
                                "height": 80,
                                "text": "Hello",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(input_path),
                    str(scene_path),
                    "--svg",
                    str(svg_path),
                    "--simple-svg",
                    "--pretty",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            scene = json.loads(scene_path.read_text(encoding="utf-8"))
            self.assertEqual(scene["type"], "excalidraw")
            self.assertIn("<svg", svg_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
