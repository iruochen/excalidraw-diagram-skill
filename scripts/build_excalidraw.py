#!/usr/bin/env python3
"""Build an editable .excalidraw file and optional SVG preview from a compact scene spec."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import subprocess
import sys
import time
import html
import unicodedata
from pathlib import Path
from typing import Any


DEFAULTS = {
    "strokeColor": "#1e1e1e",
    "backgroundColor": "transparent",
    "fillStyle": "hachure",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 1.4,
    "opacity": 100,
    "fontSize": 20,
    "fontFamily": 5,
    "textAlign": "center",
    "verticalAlign": "middle",
}


def stable_id(prefix: str, payload: Any) -> str:
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:12]}"


def nonce(seed_text: str) -> int:
    digest = hashlib.sha1(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def element_base(kind: str, item: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    eid = item.get("id") or stable_id(kind, item)
    seed = item.get("seed", random.Random(eid).randint(1, 2_000_000_000))
    return {
        "id": eid,
        "type": kind,
        "x": float(item.get("x", 0)),
        "y": float(item.get("y", 0)),
        "width": float(item.get("width", 100)),
        "height": float(item.get("height", 60)),
        "angle": float(item.get("angle", 0)),
        "strokeColor": item.get("strokeColor", defaults["strokeColor"]),
        "backgroundColor": item.get("backgroundColor", defaults["backgroundColor"]),
        "fillStyle": item.get("fillStyle", defaults["fillStyle"]),
        "strokeWidth": int(item.get("strokeWidth", defaults["strokeWidth"])),
        "strokeStyle": item.get("strokeStyle", defaults["strokeStyle"]),
        "roughness": float(item.get("roughness", defaults["roughness"])),
        "opacity": int(item.get("opacity", defaults["opacity"])),
        "groupIds": item.get("groupIds", []),
        "frameId": item.get("frameId"),
        "roundness": None,
        "seed": seed,
        "version": 1,
        "versionNonce": nonce(eid),
        "isDeleted": False,
        "boundElements": None,
        "updated": item.get("updated", int(time.time() * 1000)),
        "link": item.get("link"),
        "locked": bool(item.get("locked", False)),
    }


def estimate_text_size(text: str, font_size: int, line_height: float = 1.25) -> tuple[float, float]:
    lines = text.splitlines() or [""]
    def line_units(line: str) -> float:
        return sum(
            1.0 if unicodedata.east_asian_width(char) in {"W", "F", "A"} else 0.58
            for char in line
        )

    width = max(line_units(line) for line in lines) * font_size
    height = len(lines) * font_size * line_height
    return max(width, font_size), max(height, font_size * line_height)


def text_element(item: dict[str, Any], defaults: dict[str, Any], *, prefix: str = "text") -> dict[str, Any]:
    text = str(item.get("text", ""))
    font_size = int(item.get("fontSize", defaults["fontSize"]))
    line_height = float(item.get("lineHeight", 1.25))
    width, height = estimate_text_size(text, font_size, line_height)
    width = float(item.get("width", width))
    height = float(item.get("height", height))
    eid = item.get("id") or stable_id(prefix, item)
    font_family = int(item.get("fontFamily", defaults["fontFamily"]))
    font_weight = item.get("fontWeight")
    font_string = f"{font_size}px Excalifont"
    if font_family == 3:
        font_string = f"{font_size}px Cascadia"
    elif font_family == 2:
        font_string = f"{font_size}px Helvetica"
    elif font_family == 1:
        font_string = f"{font_size}px Virgil"
    if font_weight == "bold":
        font_string = f"bold {font_string}"
    return {
        **element_base("text", {**item, "id": eid, "width": width, "height": height}, defaults),
        "text": text,
        "fontSize": font_size,
        "fontFamily": font_family,
        "fontString": font_string,
        "textAlign": item.get("textAlign", defaults["textAlign"]),
        "verticalAlign": item.get("verticalAlign", defaults["verticalAlign"]),
        "containerId": item.get("containerId"),
        "originalText": text,
        "autoResize": bool(item.get("autoResize", True)),
        "lineHeight": line_height,
        "baseline": int(height * 0.78),
    }


def center_of(element: dict[str, Any]) -> tuple[float, float]:
    return element["x"] + element["width"] / 2, element["y"] + element["height"] / 2


def edge_point(source: dict[str, Any], target: dict[str, Any]) -> tuple[float, float]:
    sx, sy = center_of(source)
    tx, ty = center_of(target)
    dx, dy = tx - sx, ty - sy
    if dx == 0 and dy == 0:
        return sx, sy
    half_w = max(source["width"] / 2, 1)
    half_h = max(source["height"] / 2, 1)
    scale = min(abs(half_w / dx) if dx else math.inf, abs(half_h / dy) if dy else math.inf)
    return sx + dx * scale, sy + dy * scale


def point_at_path_position(points: list[list[float]], position: Any) -> tuple[float, float]:
    if not points:
        return 0, 0
    if len(points) == 1:
        return float(points[0][0]), float(points[0][1])
    if isinstance(position, str):
        position = {"start": 0.18, "middle": 0.5, "center": 0.5, "end": 0.82}.get(position, 0.5)
    try:
        ratio = float(position)
    except (TypeError, ValueError):
        ratio = 0.5
    ratio = min(max(ratio, 0), 1)
    segment_lengths: list[float] = []
    total = 0.0
    for start, end in zip(points, points[1:]):
        length = math.hypot(float(end[0]) - float(start[0]), float(end[1]) - float(start[1]))
        segment_lengths.append(length)
        total += length
    if total <= 0:
        return float(points[0][0]), float(points[0][1])
    target = total * ratio
    walked = 0.0
    for index, length in enumerate(segment_lengths):
        if walked + length >= target:
            start = points[index]
            end = points[index + 1]
            segment_ratio = 0 if length == 0 else (target - walked) / length
            return (
                float(start[0]) + (float(end[0]) - float(start[0])) * segment_ratio,
                float(start[1]) + (float(end[1]) - float(start[1])) * segment_ratio,
            )
        walked += length
    return float(points[-1][0]), float(points[-1][1])


def label_position(item: dict[str, Any], x: float, y: float, points: list[list[float]], defaults: dict[str, Any]) -> tuple[float, float]:
    if "labelX" in item or "labelY" in item:
        fallback_x, fallback_y = point_at_path_position(points, item.get("labelPosition", 0.5))
        return (
            float(item.get("labelX", x + fallback_x)),
            float(item.get("labelY", y + fallback_y)),
        )
    px, py = point_at_path_position(points, item.get("labelPosition", 0.5))
    return (
        x + px + float(item.get("labelOffsetX", 0)),
        y + py + float(item.get("labelOffsetY", -28)),
    )


def arrow_or_line(item: dict[str, Any], defaults: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    kind = "line" if item.get("kind") == "line" else "arrow"
    if "from" in item and "to" in item:
        start_ref = by_id[item["from"]]
        end_ref = by_id[item["to"]]
        sx, sy = edge_point(start_ref, end_ref)
        ex, ey = edge_point(end_ref, start_ref)
        points = [[0, 0], [ex - sx, ey - sy]]
        x, y = sx, sy
    else:
        points = item.get("points", [[0, 0], [float(item.get("width", 160)), float(item.get("height", 0))]])
        x = float(item.get("x", 0))
        y = float(item.get("y", 0))
    width = max(point[0] for point in points) - min(point[0] for point in points)
    height = max(point[1] for point in points) - min(point[1] for point in points)
    base = element_base(kind, {**item, "x": x, "y": y, "width": width, "height": height}, defaults)
    base.update(
        {
            "points": points,
            "lastCommittedPoint": None,
            "startBinding": None,
            "endBinding": None,
            "startArrowhead": item.get("startArrowhead"),
            "endArrowhead": item.get("endArrowhead", "arrow" if kind == "arrow" else None),
            "elbowed": bool(item.get("elbowed", False)),
        }
    )
    out = [base]
    if item.get("text"):
        tx, ty = label_position(item, x, y, points, defaults)
        label_font_size = int(item.get("fontSize", max(14, defaults["fontSize"] - 4)))
        label_width, label_height = estimate_text_size(str(item["text"]), label_font_size)
        out.append(
            text_element(
                {
                    "text": item["text"],
                    "x": tx - label_width / 2,
                    "y": ty - label_height / 2,
                    "width": label_width,
                    "height": label_height,
                    "fontSize": label_font_size,
                    "strokeColor": item.get("labelColor", item.get("strokeColor", defaults["strokeColor"])),
                },
                defaults,
                prefix="label",
            )
        )
    return out


def build_scene(spec: dict[str, Any]) -> dict[str, Any]:
    defaults = {**DEFAULTS, **spec.get("defaults", {})}
    elements: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    deferred_edges: list[dict[str, Any]] = []

    for item in spec.get("elements", []):
        kind = item.get("kind", item.get("type", "rectangle"))
        if kind in {"arrow", "line"}:
            deferred_edges.append(item)
            continue
        if kind == "text":
            elem = text_element(item, defaults)
            elements.append(elem)
            by_id[elem["id"]] = elem
            continue
        if kind == "frame":
            elem = element_base("frame", item, defaults)
            elem["name"] = item.get("name") or item.get("text") or ""
            elements.append(elem)
            by_id[elem["id"]] = elem
            if item.get("text"):
                elements.append(text_element({"text": item["text"], "x": elem["x"] + 16, "y": elem["y"] + 12, "fontSize": 18, "textAlign": "left"}, defaults, prefix="frame_label"))
            continue
        shape_kind = kind if kind in {"rectangle", "ellipse", "diamond"} else "rectangle"
        elem = element_base(shape_kind, item, defaults)
        if shape_kind == "rectangle":
            roundness = item.get("roundness", "round")
            elem["roundness"] = None if roundness == "sharp" else {"type": 3}
        elements.append(elem)
        by_id[elem["id"]] = elem
        if item.get("text"):
            font_size = int(item.get("fontSize", defaults["fontSize"]))
            min_font_size = int(item.get("minFontSize", 12))
            text_padding = float(item.get("textPadding", 12))
            line_height = float(item.get("lineHeight", 1.25))
            available_width = max(elem["width"] - text_padding * 2, min_font_size)
            available_height = max(elem["height"] - text_padding * 2, min_font_size * line_height)
            measured_width, measured_height = estimate_text_size(str(item["text"]), font_size, line_height)
            while (
                font_size > min_font_size
                and (measured_width > available_width or measured_height > available_height)
            ):
                font_size -= 1
                measured_width, measured_height = estimate_text_size(str(item["text"]), font_size, line_height)
            label_height = min(measured_height, elem["height"])
            label_item = {
                "text": item["text"],
                "x": elem["x"] + text_padding,
                "y": elem["y"] + (elem["height"] - label_height) / 2,
                "width": available_width,
                "height": label_height,
                "fontSize": font_size,
                "lineHeight": line_height,
                "strokeColor": item.get("textColor", item.get("strokeColor", defaults["strokeColor"])),
                "containerId": elem["id"],
                "groupIds": item.get("groupIds", []),
                "frameId": item.get("frameId"),
            }
            label = text_element(label_item, defaults, prefix="shape_label")
            elem["boundElements"] = [{"type": "text", "id": label["id"]}]
            elements.append(label)

    for item in deferred_edges:
        missing = [ref for ref in (item.get("from"), item.get("to")) if ref and ref not in by_id]
        if missing:
            raise SystemExit(f"Arrow references unknown element id(s): {', '.join(missing)}")
        elements.extend(arrow_or_line(item, defaults, by_id))

    app_state = {
        "theme": "light",
        "viewBackgroundColor": "#ffffff",
        "gridSize": None,
    }
    app_state.update(spec.get("appState", {}))
    if spec.get("title"):
        app_state["name"] = spec["title"]

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://github.com/iruochen/excalidraw-diagram-skill",
        "elements": elements,
        "appState": app_state,
        "files": spec.get("files", {}),
    }


def svg_bounds(elements: list[dict[str, Any]], padding: float) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for elem in elements:
        if elem.get("isDeleted"):
            continue
        if elem["type"] in {"arrow", "line"}:
            for px, py in elem.get("points", [[0, 0]]):
                xs.append(elem["x"] + px)
                ys.append(elem["y"] + py)
        else:
            xs.extend([elem["x"], elem["x"] + elem.get("width", 0)])
            ys.extend([elem["y"], elem["y"] + elem.get("height", 0)])
    if not xs:
        return 0, 0, 800, 600
    min_x, max_x = min(xs) - padding, max(xs) + padding
    min_y, max_y = min(ys) - padding, max(ys) + padding
    return min_x, min_y, max(max_x - min_x, 1), max(max_y - min_y, 1)


def fill_color(elem: dict[str, Any]) -> str:
    color = elem.get("backgroundColor", "transparent")
    return "none" if color == "transparent" else color


def svg_text(elem: dict[str, Any]) -> str:
    text = html.escape(elem.get("text", ""))
    lines = text.splitlines() or [""]
    size = elem.get("fontSize", 20)
    family = "Excalifont, Virgil, Comic Sans MS, Segoe Print, cursive"
    if elem.get("fontFamily") == 2:
        family = "Helvetica, Arial, sans-serif"
    elif elem.get("fontFamily") == 3:
        family = "Cascadia Mono, Menlo, monospace"
    weight = "700" if elem.get("fontString", "").startswith("bold ") else "400"
    anchor = {"left": "start", "right": "end"}.get(elem.get("textAlign"), "middle")
    x = elem["x"] + (0 if anchor == "start" else elem.get("width", 0) if anchor == "end" else elem.get("width", 0) / 2)
    y = elem["y"] + size
    tspans = []
    for i, line in enumerate(lines):
        tspans.append(f'<tspan x="{x:.2f}" dy="{0 if i == 0 else size * 1.25:.2f}">{line}</tspan>')
    return (
        f'<text font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'fill="{elem.get("strokeColor", "#1e1e1e")}" text-anchor="{anchor}" '
        f'opacity="{elem.get("opacity", 100) / 100:.3f}" x="{x:.2f}" y="{y:.2f}">'
        + "".join(tspans)
        + "</text>"
    )


def svg_shape(elem: dict[str, Any]) -> str:
    stroke = elem.get("strokeColor", "#1e1e1e")
    fill = fill_color(elem)
    width = elem.get("strokeWidth", 2)
    opacity = elem.get("opacity", 100) / 100
    common = f'stroke="{stroke}" stroke-width="{width}" fill="{fill}" opacity="{opacity:.3f}"'
    x, y, w, h = elem["x"], elem["y"], elem.get("width", 0), elem.get("height", 0)
    if elem["type"] == "ellipse":
        return f'<ellipse cx="{x + w / 2:.2f}" cy="{y + h / 2:.2f}" rx="{w / 2:.2f}" ry="{h / 2:.2f}" {common}/>'
    if elem["type"] == "diamond":
        pts = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
        points = " ".join(f"{px:.2f},{py:.2f}" for px, py in pts)
        return f'<polygon points="{points}" {common}/>'
    if elem["type"] == "frame":
        name = html.escape(elem.get("name", "Frame"))
        label = (
            f'<text x="{x + 12:.2f}" y="{y + 24:.2f}" '
            f'font-family="Excalifont, Virgil, Comic Sans MS, Segoe Print, cursive" '
            f'font-size="14" fill="#666666">{name}</text>'
            if name else ""
        )
        return (
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="8" '
            f'stroke="#888888" stroke-width="1.5" fill="none" opacity=".7"/>'
            f'{label}'
        )
    rx = 10 if elem.get("roundness") else 0
    return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{rx}" {common}/>'


def svg_edge(elem: dict[str, Any]) -> str:
    points = [(elem["x"] + px, elem["y"] + py) for px, py in elem.get("points", [])]
    if len(points) < 2:
        return ""
    d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points)
    marker = ' marker-end="url(#arrowhead)"' if elem["type"] == "arrow" and elem.get("endArrowhead") else ""
    return (
        f'<path d="{d}" stroke="{elem.get("strokeColor", "#1e1e1e")}" '
        f'stroke-width="{elem.get("strokeWidth", 2)}" fill="none" stroke-linecap="round" '
        f'stroke-linejoin="round"{marker}/>'
    )


def render_svg(scene: dict[str, Any], output: Path, padding: float = 40) -> None:
    elements = [elem for elem in scene["elements"] if not elem.get("isDeleted")]
    min_x, min_y, width, height = svg_bounds(elements, padding)
    bg = scene.get("appState", {}).get("viewBackgroundColor", "#ffffff")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="{min_x:.2f} {min_y:.2f} {width:.2f} {height:.2f}">',
        "<defs>",
        '<marker id="arrowhead" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 10 4 L 0 8 z" fill="#1e1e1e"/></marker>',
        "</defs>",
        f'<rect x="{min_x:.2f}" y="{min_y:.2f}" width="{width:.2f}" height="{height:.2f}" fill="{bg}"/>',
    ]
    for elem in elements:
        if elem["type"] in {"arrow", "line"}:
            parts.append(svg_edge(elem))
        elif elem["type"] == "text":
            parts.append(svg_text(elem))
        else:
            parts.append(svg_shape(elem))
    parts.append("</svg>\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")


def render_official_svg(scene_path: Path, output: Path) -> None:
    script = Path(__file__).with_name("export_official_svg.mjs")
    subprocess.run(["node", str(script), str(scene_path), str(output)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a .excalidraw file and optional SVG preview from a compact scene spec JSON.")
    parser.add_argument("input", type=Path, help="Input scene spec JSON")
    parser.add_argument("output", type=Path, help="Output .excalidraw path")
    parser.add_argument("--svg", type=Path, help="Optional SVG preview output path, rendered with official Excalidraw exportToSvg by default")
    parser.add_argument("--simple-svg", action="store_true", help="Use the lightweight fallback SVG renderer instead of official Excalidraw export")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output JSON")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8") as f:
        spec = json.load(f)
    scene = build_scene(spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(scene, f, ensure_ascii=False, indent=2 if args.pretty else None)
        f.write("\n")
    print(f"Wrote {args.output} with {len(scene['elements'])} elements")
    if args.svg:
        if args.simple_svg:
            render_svg(scene, args.svg)
        else:
            render_official_svg(args.output, args.svg)
        print(f"Wrote {args.svg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
