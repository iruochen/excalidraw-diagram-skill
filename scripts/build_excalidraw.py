#!/usr/bin/env python3
"""Build an editable .excalidraw file and optional SVG preview from a compact scene spec."""

from __future__ import annotations

import argparse
import heapq
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

ROUTING_MARGIN = 20.0
LABEL_CLEARANCE = 6.0
PORT_LEAD_DISTANCE = 12.0
PORT_BORDER_CLEARANCE = 1.0
ROUTE_BEND_PENALTY = 24.0
SHAPE_TYPES = {"rectangle", "ellipse", "diamond"}


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


def shape_bounds(element: dict[str, Any], margin: float = 0) -> tuple[float, float, float, float]:
    return (
        float(element["x"]) - margin,
        float(element["y"]) - margin,
        float(element["x"] + element["width"]) + margin,
        float(element["y"] + element["height"]) + margin,
    )


def visible_shapes(by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (
            element
            for element in by_id.values()
            if element.get("type") in SHAPE_TYPES
            and not element.get("isDeleted", False)
            and float(element.get("opacity", 100)) > 0
        ),
        key=lambda element: element["id"],
    )


def visible_label_obstacles(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return shapes and unbound text that automatic connector labels must avoid."""
    return [
        element
        for element in elements
        if not element.get("isDeleted", False)
        and float(element.get("opacity", 100)) > 0
        and (
            element.get("type") in SHAPE_TYPES
            or (element.get("type") == "text" and element.get("containerId") is None)
        )
    ]


def point_inside_rect(point: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    x, y = point
    left, top, right, bottom = rect
    return left < x < right and top < y < bottom


def segment_crosses_rect(
    start: tuple[float, float],
    end: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    """Return whether a segment crosses the open interior of an axis-aligned rect."""
    left, top, right, bottom = rect
    epsilon = 1e-7
    left += epsilon
    top += epsilon
    right -= epsilon
    bottom -= epsilon
    if left >= right or top >= bottom:
        return False
    dx, dy = end[0] - start[0], end[1] - start[1]
    lower, upper = 0.0, 1.0
    for origin, delta, minimum, maximum in (
        (start[0], dx, left, right),
        (start[1], dy, top, bottom),
    ):
        if abs(delta) < epsilon:
            if origin < minimum or origin > maximum:
                return False
            continue
        near = (minimum - origin) / delta
        far = (maximum - origin) / delta
        if near > far:
            near, far = far, near
        lower = max(lower, near)
        upper = min(upper, far)
        if lower > upper:
            return False
    return lower <= upper


def path_is_clear(
    start: tuple[float, float],
    end: tuple[float, float],
    obstacles: list[tuple[float, float, float, float]],
) -> bool:
    return not any(segment_crosses_rect(start, end, obstacle) for obstacle in obstacles)


def simplify_path(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    simplified: list[tuple[float, float]] = []
    for point in points:
        if simplified and point == simplified[-1]:
            continue
        if len(simplified) >= 2:
            previous, current = simplified[-2], simplified[-1]
            if (previous[0] == current[0] == point[0]) or (previous[1] == current[1] == point[1]):
                simplified[-1] = point
                continue
        simplified.append(point)
    return simplified


def path_metrics(points: list[tuple[float, float]]) -> tuple[float, int, int]:
    distance = 0.0
    bends = 0
    previous_direction: str | None = None
    segments = 0
    for start, end in zip(points, points[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = abs(dx) + abs(dy)
        if length == 0:
            continue
        direction = "h" if abs(dx) >= abs(dy) else "v"
        bends += int(previous_direction is not None and previous_direction != direction)
        previous_direction = direction
        distance += length
        segments += 1
    return distance, bends, segments


def port_candidates(
    element: dict[str, Any], lead_distance: float
) -> list[tuple[str, tuple[float, float], tuple[float, float]]]:
    left, top, right, bottom = shape_bounds(element)
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    return [
        ("top", (center_x, top), (center_x, top - lead_distance)),
        ("right", (right, center_y), (right + lead_distance, center_y)),
        ("bottom", (center_x, bottom), (center_x, bottom + lead_distance)),
        ("left", (left, center_y), (left - lead_distance, center_y)),
    ]


def orthogonal_route(
    start: tuple[float, float],
    end: tuple[float, float],
    obstacles: list[tuple[float, float, float, float]],
) -> list[tuple[float, float]]:
    """Find a deterministic shortest rectilinear path through obstacle boundary coordinates."""
    xs = sorted({start[0], end[0], *(value for rect in obstacles for value in (rect[0], rect[2]))})
    ys = sorted({start[1], end[1], *(value for rect in obstacles for value in (rect[1], rect[3]))})
    nodes = {
        (x, y)
        for x in xs
        for y in ys
        if (x, y) in {start, end} or not any(point_inside_rect((x, y), rect) for rect in obstacles)
    }
    neighbors: dict[tuple[float, float], list[tuple[tuple[float, float], str, float]]] = {
        node: [] for node in nodes
    }
    for y in ys:
        row = sorted((node for node in nodes if node[1] == y), key=lambda node: node[0])
        for first, second in zip(row, row[1:]):
            if path_is_clear(first, second, obstacles):
                distance = second[0] - first[0]
                neighbors[first].append((second, "h", distance))
                neighbors[second].append((first, "h", distance))
    for x in xs:
        column = sorted((node for node in nodes if node[0] == x), key=lambda node: node[1])
        for first, second in zip(column, column[1:]):
            if path_is_clear(first, second, obstacles):
                distance = second[1] - first[1]
                neighbors[first].append((second, "v", distance))
                neighbors[second].append((first, "v", distance))
    for entries in neighbors.values():
        entries.sort(key=lambda entry: (entry[0][0], entry[0][1], entry[1]))

    # The tuple cost prefers shortest distance, then fewer bends and segments.
    queue: list[tuple[float, int, int, float, float, str, tuple[float, float], list[tuple[float, float]]]] = []
    heapq.heappush(queue, (0.0, 0, 0, start[0], start[1], "", start, [start]))
    best: dict[tuple[tuple[float, float], str], tuple[float, int, int]] = {(start, ""): (0.0, 0, 0)}
    while queue:
        distance, bends, segments, _, _, direction, node, path = heapq.heappop(queue)
        if best.get((node, direction)) != (distance, bends, segments):
            continue
        if node == end:
            return simplify_path(path)
        for next_node, next_direction, length in neighbors[node]:
            next_cost = (
                distance + length,
                bends + int(bool(direction) and direction != next_direction),
                segments + 1,
            )
            state = (next_node, next_direction)
            if state in best and best[state] <= next_cost:
                continue
            best[state] = next_cost
            heapq.heappush(
                queue,
                (*next_cost, next_node[0], next_node[1], next_direction, next_node, path + [next_node]),
            )
    raise RuntimeError("No orthogonal route found")


def routed_connector_points(
    start_ref: dict[str, Any],
    end_ref: dict[str, Any],
    shapes: list[dict[str, Any]],
    margin: float,
) -> tuple[float, float, list[list[float]]]:
    direct_start = edge_point(start_ref, end_ref)
    direct_end = edge_point(end_ref, start_ref)
    intervening = [shape for shape in shapes if shape["id"] not in {start_ref["id"], end_ref["id"]}]
    margin = max(float(margin), 0.0)
    padded_obstacles = [shape_bounds(shape, margin) for shape in intervening]
    if path_is_clear(direct_start, direct_end, padded_obstacles):
        return (
            direct_start[0],
            direct_start[1],
            [[0, 0], [direct_end[0] - direct_start[0], direct_end[1] - direct_start[1]]],
        )

    # Mid-edge ports plus outward lead points force perpendicular departure and arrival.
    endpoint_obstacles = padded_obstacles + [shape_bounds(start_ref), shape_bounds(end_ref)]
    middle_obstacles = padded_obstacles + [
        shape_bounds(start_ref, PORT_BORDER_CLEARANCE),
        shape_bounds(end_ref, PORT_BORDER_CLEARANCE),
    ]
    lead_distance = max(margin, PORT_LEAD_DISTANCE)
    candidates: list[
        tuple[
            tuple[float, int, float, int, int, int, tuple[tuple[float, float], ...]],
            list[tuple[float, float]],
        ]
    ] = []
    for start_rank, (_, start_port, start_lead) in enumerate(port_candidates(start_ref, lead_distance)):
        if not path_is_clear(start_port, start_lead, endpoint_obstacles):
            continue
        for end_rank, (_, end_port, end_lead) in enumerate(port_candidates(end_ref, lead_distance)):
            if not path_is_clear(end_lead, end_port, endpoint_obstacles):
                continue
            try:
                middle = orthogonal_route(start_lead, end_lead, middle_obstacles)
            except RuntimeError:
                continue
            absolute_points = simplify_path([start_port, *middle, end_port])
            distance, bends, segments = path_metrics(absolute_points)
            score = (
                distance + bends * ROUTE_BEND_PENALTY,
                bends,
                distance,
                segments,
                start_rank,
                end_rank,
                tuple(absolute_points),
            )
            candidates.append((score, absolute_points))
    if not candidates:
        raise SystemExit("Unable to route connector around overlapping shapes")
    _, absolute_points = min(candidates, key=lambda candidate: candidate[0])
    start = absolute_points[0]
    return (
        start[0],
        start[1],
        [[point[0] - start[0], point[1] - start[1]] for point in absolute_points],
    )


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


def path_anchor_and_direction(
    points: list[list[float]], position: Any
) -> tuple[tuple[float, float], tuple[float, float]]:
    anchor = point_at_path_position(points, position)
    if len(points) < 2:
        return anchor, (1, 0)
    if isinstance(position, str):
        position = {"start": 0.18, "middle": 0.5, "center": 0.5, "end": 0.82}.get(position, 0.5)
    try:
        ratio = min(max(float(position), 0), 1)
    except (TypeError, ValueError):
        ratio = 0.5
    lengths = [
        math.hypot(float(end[0]) - float(start[0]), float(end[1]) - float(start[1]))
        for start, end in zip(points, points[1:])
    ]
    target = sum(lengths) * ratio
    walked = 0.0
    for index, length in enumerate(lengths):
        if walked + length >= target and length > 0:
            start, end = points[index], points[index + 1]
            return anchor, (float(end[0]) - float(start[0]), float(end[1]) - float(start[1]))
        walked += length
    start, end = points[-2], points[-1]
    return anchor, (float(end[0]) - float(start[0]), float(end[1]) - float(start[1]))


def label_box_is_clear(
    center: tuple[float, float],
    width: float,
    height: float,
    obstacles: list[dict[str, Any]],
) -> bool:
    label_rect = (
        center[0] - width / 2 - LABEL_CLEARANCE,
        center[1] - height / 2 - LABEL_CLEARANCE,
        center[0] + width / 2 + LABEL_CLEARANCE,
        center[1] + height / 2 + LABEL_CLEARANCE,
    )
    for obstacle in obstacles:
        left, top, right, bottom = shape_bounds(obstacle)
        if not (
            label_rect[2] <= left
            or label_rect[0] >= right
            or label_rect[3] <= top
            or label_rect[1] >= bottom
        ):
            return False
    return True


def label_position(
    item: dict[str, Any],
    x: float,
    y: float,
    points: list[list[float]],
    width: float,
    height: float,
    obstacles: list[dict[str, Any]],
) -> tuple[float, float]:
    if "labelX" in item or "labelY" in item:
        fallback_x, fallback_y = point_at_path_position(points, item.get("labelPosition", 0.5))
        return (
            float(item.get("labelX", x + fallback_x)),
            float(item.get("labelY", y + fallback_y)),
        )
    position = item.get("labelPosition", 0.5)
    explicit_offset = "labelOffsetX" in item or "labelOffsetY" in item
    px, py = point_at_path_position(points, position)
    requested = (
        x + px + float(item.get("labelOffsetX", 0)),
        y + py + float(item.get("labelOffsetY", -28)),
    )
    if explicit_offset or label_box_is_clear(requested, width, height, obstacles):
        return requested

    ratios = [position, 0.35, 0.65, 0.2, 0.8, 0.5, 0.1, 0.9]
    seen: set[float] = set()
    for candidate_ratio in ratios:
        try:
            numeric_ratio = min(max(float(candidate_ratio), 0), 1)
        except (TypeError, ValueError):
            numeric_ratio = 0.5
        if numeric_ratio in seen:
            continue
        seen.add(numeric_ratio)
        (anchor_x, anchor_y), (dx, dy) = path_anchor_and_direction(points, numeric_ratio)
        horizontal = abs(dx) >= abs(dy)
        for clearance in (28.0, 40.0, 56.0, 76.0, 100.0):
            offsets = [(0, -clearance), (0, clearance)] if horizontal else [(-clearance, 0), (clearance, 0)]
            for offset_x, offset_y in offsets:
                candidate = (x + anchor_x + offset_x, y + anchor_y + offset_y)
                if label_box_is_clear(candidate, width, height, obstacles):
                    return candidate
    # A finite set of obstacles always has a clear position outside its total bounds.
    (anchor_x, anchor_y), _ = path_anchor_and_direction(points, position)
    absolute_anchor = (x + anchor_x, y + anchor_y)
    bounds = [shape_bounds(obstacle) for obstacle in obstacles]
    outer_candidates = (
        (absolute_anchor[0], min(rect[1] for rect in bounds) - height / 2 - LABEL_CLEARANCE),
        (min(rect[0] for rect in bounds) - width / 2 - LABEL_CLEARANCE, absolute_anchor[1]),
        (max(rect[2] for rect in bounds) + width / 2 + LABEL_CLEARANCE, absolute_anchor[1]),
        (absolute_anchor[0], max(rect[3] for rect in bounds) + height / 2 + LABEL_CLEARANCE),
    ) if bounds else (requested,)
    for candidate in outer_candidates:
        if label_box_is_clear(candidate, width, height, obstacles):
            return candidate
    return requested


def arrow_or_line(
    item: dict[str, Any],
    defaults: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    existing_elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    kind = "line" if item.get("kind") == "line" else "arrow"
    shapes = visible_shapes(by_id)
    label_obstacles = visible_label_obstacles(existing_elements)
    if "from" in item and "to" in item:
        start_ref = by_id[item["from"]]
        end_ref = by_id[item["to"]]
        x, y, points = routed_connector_points(
            start_ref,
            end_ref,
            shapes,
            float(item.get("routingMargin", ROUTING_MARGIN)),
        )
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
        label_font_size = int(item.get("fontSize", max(14, defaults["fontSize"] - 4)))
        label_width, label_height = estimate_text_size(str(item["text"]), label_font_size)
        tx, ty = label_position(item, x, y, points, label_width, label_height, label_obstacles)
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
            # Excalidraw renders frame names itself. A spec `text` is emitted as
            # a separate title element so it can participate in label collision
            # detection without being rendered twice by the official exporter.
            elem["name"] = item.get("name") or ""
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
        elements.extend(arrow_or_line(item, defaults, by_id, elements))

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
