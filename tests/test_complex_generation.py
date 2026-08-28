import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_excalidraw.py"
FIXTURE = ROOT / "tests" / "fixtures" / "complex-routing.scene.json"
SPEC = importlib.util.spec_from_file_location("build_excalidraw_complex", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ComplexGenerationTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.scene = MODULE.build_scene(self.spec)
        self.by_id = {element["id"]: element for element in self.scene["elements"]}

    def absolute_points(self, edge):
        return [(edge["x"] + x, edge["y"] + y) for x, y in edge["points"]]

    def test_complex_routes_preserve_all_routing_invariants(self):
        direct = self.by_id["direct-edge"]
        reverse = self.by_id["reverse-edge"]
        audit = self.by_id["audit-path"]
        explicit = self.by_id["explicit-edge"]

        self.assertEqual(len(direct["points"]), 2)
        self.assertGreaterEqual(len(reverse["points"]), 4)
        self.assertEqual(explicit["points"], [[0, 0], [120, -35], [260, -35], [340, 0]])

        audit_points = self.absolute_points(audit)
        start, after_start = audit_points[0], audit_points[1]
        before_end, end = audit_points[-2], audit_points[-1]
        self.assertEqual(start, (625, 480))
        self.assertEqual(after_start[0], start[0])
        self.assertLess(after_start[1], start[1])
        self.assertEqual(end, (1095, 480))
        self.assertEqual(before_end[0], end[0])
        self.assertLess(before_end[1], end[1])

        shapes = MODULE.visible_shapes(self.by_id)
        for item in self.spec["elements"]:
            if item.get("kind") not in {"arrow", "line"} or "from" not in item:
                continue
            edge = self.by_id[item["id"]]
            if len(edge["points"]) == 2:
                continue
            obstacles = [
                MODULE.shape_bounds(shape, MODULE.ROUTING_MARGIN)
                for shape in shapes
                if shape["id"] not in {item["from"], item["to"]}
            ]
            points = self.absolute_points(edge)
            self.assertTrue(
                all(
                    MODULE.path_is_clear(segment_start, segment_end, obstacles)
                    for segment_start, segment_end in zip(points, points[1:])
                ),
                item["id"],
            )

    def test_complex_generation_is_deterministic_and_labels_avoid_titles(self):
        second = MODULE.build_scene(self.spec)
        second_by_id = {element["id"]: element for element in second["elements"]}
        arrow_ids = [item["id"] for item in self.spec["elements"] if item.get("kind") == "arrow"]
        self.assertEqual(
            {edge_id: self.by_id[edge_id]["points"] for edge_id in arrow_ids},
            {edge_id: second_by_id[edge_id]["points"] for edge_id in arrow_ids},
        )

        frame = self.by_id["system-frame"]
        frame_titles = [
            element
            for element in self.scene["elements"]
            if element.get("type") == "text" and element.get("text") == "端到端服务链路"
        ]
        self.assertEqual(frame["name"], "")
        self.assertEqual(len(frame_titles), 1)
        titles = [self.by_id["lane-title"], self.by_id["audit-title"], frame_titles[0]]
        arrow_texts = {
            item["text"]
            for item in self.spec["elements"]
            if item.get("kind") in {"arrow", "line"} and item.get("text")
        }
        labels = [
            element
            for element in self.scene["elements"]
            if element.get("type") == "text" and element.get("text") in arrow_texts
        ]
        for label in labels:
            center = (label["x"] + label["width"] / 2, label["y"] + label["height"] / 2)
            self.assertTrue(
                MODULE.label_box_is_clear(center, label["width"], label["height"], titles),
                label["text"],
            )

    def test_complex_scene_renders_with_official_exporter(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            scene_path = temporary / "complex-routing.excalidraw"
            svg_path = temporary / "complex-routing.svg"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(FIXTURE),
                    str(scene_path),
                    "--svg",
                    str(svg_path),
                    "--pretty",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=90,
            )
            rendered_scene = json.loads(scene_path.read_text(encoding="utf-8"))
            svg = svg_path.read_text(encoding="utf-8")
            self.assertGreaterEqual(len(rendered_scene["elements"]), 25)
            self.assertIn("<svg", svg)
            self.assertIn("列表结果", svg)
            self.assertGreater(len(svg), 10_000)


if __name__ == "__main__":
    unittest.main()
