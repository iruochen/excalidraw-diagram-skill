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
    @staticmethod
    def arrow(scene):
        return next(element for element in scene["elements"] if element["type"] == "arrow")

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

    def test_reverse_connector_routes_around_horizontal_obstacle(self):
        scene = MODULE.build_scene(
            {
                "elements": [
                    {"id": "left", "kind": "rectangle", "x": 0, "y": 0, "width": 100, "height": 60},
                    {"id": "middle", "kind": "diamond", "x": 180, "y": -20, "width": 100, "height": 100},
                    {"id": "right", "kind": "rectangle", "x": 360, "y": 0, "width": 100, "height": 60},
                    {"kind": "arrow", "from": "right", "to": "left", "text": "back"},
                ]
            }
        )

        arrow = self.arrow(scene)
        absolute = [(arrow["x"] + x, arrow["y"] + y) for x, y in arrow["points"]]
        self.assertGreaterEqual(len(absolute), 4)
        self.assertTrue(all(
            MODULE.path_is_clear(start, end, [(160, -40, 300, 100)])
            for start, end in zip(absolute, absolute[1:])
        ))
        label = next(element for element in scene["elements"] if element["type"] == "text")
        shapes = [element for element in scene["elements"] if element["type"] in MODULE.SHAPE_TYPES]
        center = (label["x"] + label["width"] / 2, label["y"] + label["height"] / 2)
        self.assertTrue(MODULE.label_box_is_clear(center, label["width"], label["height"], shapes))

    def test_vertical_connector_routes_around_obstacle(self):
        scene = MODULE.build_scene(
            {
                "elements": [
                    {"id": "top", "kind": "rectangle", "x": 0, "y": 0, "width": 100, "height": 60},
                    {"id": "middle", "kind": "rectangle", "x": -20, "y": 150, "width": 140, "height": 80},
                    {"id": "bottom", "kind": "rectangle", "x": 0, "y": 320, "width": 100, "height": 60},
                    {"kind": "arrow", "from": "bottom", "to": "top"},
                ]
            }
        )

        arrow = self.arrow(scene)
        absolute = [(arrow["x"] + x, arrow["y"] + y) for x, y in arrow["points"]]
        self.assertGreaterEqual(len(absolute), 4)
        self.assertTrue(all(
            MODULE.path_is_clear(start, end, [(-40, 130, 140, 250)])
            for start, end in zip(absolute, absolute[1:])
        ))

    def test_obstacle_route_enters_target_from_top_and_leaves_source_normally(self):
        scene = MODULE.build_scene(
            {
                "elements": [
                    {"id": "source", "kind": "rectangle", "x": 0, "y": 200, "width": 100, "height": 60},
                    {"id": "block", "kind": "rectangle", "x": 120, "y": 160, "width": 260, "height": 140},
                    {"id": "target", "kind": "rectangle", "x": 400, "y": 200, "width": 100, "height": 60},
                    {"kind": "arrow", "from": "source", "to": "target"},
                ]
            }
        )

        arrow = self.arrow(scene)
        absolute = [(arrow["x"] + x, arrow["y"] + y) for x, y in arrow["points"]]
        start, after_start = absolute[0], absolute[1]
        before_end, end = absolute[-2], absolute[-1]
        self.assertEqual(start, (50, 200))
        self.assertEqual(after_start[0], start[0])
        self.assertLess(after_start[1], start[1])
        self.assertEqual(end, (450, 200))
        self.assertEqual(before_end[0], end[0])
        self.assertLess(before_end[1], end[1])
        self.assertGreater(end[0], 400)
        self.assertLess(end[0], 500)

    def test_obstacle_route_enters_target_from_side_horizontally(self):
        scene = MODULE.build_scene(
            {
                "elements": [
                    {"id": "source", "kind": "rectangle", "x": 0, "y": 0, "width": 100, "height": 60},
                    {"id": "block", "kind": "rectangle", "x": 150, "y": 20, "width": 100, "height": 140},
                    {"id": "target", "kind": "rectangle", "x": 400, "y": 180, "width": 100, "height": 60},
                    {"kind": "arrow", "from": "source", "to": "target"},
                ]
            }
        )

        arrow = self.arrow(scene)
        absolute = [(arrow["x"] + x, arrow["y"] + y) for x, y in arrow["points"]]
        before_end, end = absolute[-2], absolute[-1]
        self.assertEqual(end, (400, 210))
        self.assertEqual(before_end[1], end[1])
        self.assertLess(before_end[0], end[0])
        self.assertGreater(end[1], 180)
        self.assertLess(end[1], 240)

    def test_adjacent_nodes_keep_simple_direct_connector(self):
        scene = MODULE.build_scene(
            {
                "elements": [
                    {"id": "a", "kind": "rectangle", "x": 0, "y": 0, "width": 100, "height": 60},
                    {"id": "b", "kind": "rectangle", "x": 200, "y": 0, "width": 100, "height": 60},
                    {"kind": "arrow", "from": "a", "to": "b"},
                ]
            }
        )

        self.assertEqual(self.arrow(scene)["points"], [[0, 0], [100, 0]])

    def test_explicit_points_are_not_rewritten(self):
        points = [[0, 0], [40, -30], [120, -30], [120, 50]]
        scene = MODULE.build_scene(
            {
                "elements": [
                    {"id": "block", "kind": "rectangle", "x": 40, "y": -40, "width": 60, "height": 100},
                    {"kind": "arrow", "x": 10, "y": 20, "points": points},
                ]
            }
        )

        arrow = self.arrow(scene)
        self.assertEqual(arrow["points"], points)
        self.assertEqual((arrow["x"], arrow["y"]), (10, 20))

    def test_automatic_route_is_deterministic(self):
        spec = {
            "elements": [
                {"id": "a", "kind": "rectangle", "x": 0, "y": 0, "width": 100, "height": 60},
                {"id": "one", "kind": "rectangle", "x": 150, "y": -30, "width": 80, "height": 120},
                {"id": "two", "kind": "diamond", "x": 270, "y": -20, "width": 80, "height": 100},
                {"id": "b", "kind": "rectangle", "x": 420, "y": 0, "width": 100, "height": 60},
                {"kind": "arrow", "from": "a", "to": "b", "text": "stable"},
            ]
        }

        first = MODULE.build_scene(spec)
        second = MODULE.build_scene(spec)
        self.assertEqual(self.arrow(first)["points"], self.arrow(second)["points"])
        first_label = next(element for element in first["elements"] if element["type"] == "text")
        second_label = next(element for element in second["elements"] if element["type"] == "text")
        self.assertEqual((first_label["x"], first_label["y"]), (second_label["x"], second_label["y"]))

    def test_automatic_label_avoids_independent_title_text(self):
        scene = MODULE.build_scene(
            {
                "elements": [
                    {"id": "left", "kind": "rectangle", "x": 0, "y": 70, "width": 100, "height": 60},
                    {
                        "id": "lane-title",
                        "kind": "text",
                        "x": 190,
                        "y": 55,
                        "text": "③ 财税圈 API 服务",
                        "fontSize": 20,
                    },
                    {"id": "right", "kind": "rectangle", "x": 400, "y": 70, "width": 100, "height": 60},
                    {"kind": "arrow", "from": "right", "to": "left", "text": "列表结果"},
                ]
            }
        )

        arrow = self.arrow(scene)
        self.assertEqual(len(arrow["points"]), 2)
        title = next(element for element in scene["elements"] if element.get("text") == "③ 财税圈 API 服务")
        label = next(element for element in scene["elements"] if element.get("text") == "列表结果")
        label_center = (label["x"] + label["width"] / 2, label["y"] + label["height"] / 2)
        self.assertTrue(
            MODULE.label_box_is_clear(label_center, label["width"], label["height"], [title])
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
