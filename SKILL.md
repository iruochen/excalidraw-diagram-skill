---
name: generate-excalidraw
description: Generate Excalidraw-style diagram images and editable .excalidraw files from natural-language descriptions, architecture sketches, flowcharts, system diagrams, wireframes, whiteboard-style notes, or requests to avoid brittle ad hoc SVG-only diagram generation. Use when Codex should create a diagram image by default, or create/modify/save an Excalidraw scene JSON when the user asks for an editable .excalidraw file.
---

# Generate Excalidraw

## Overview

Create Excalidraw-style diagram images by default, and editable `.excalidraw` files when the user asks for a source/editable file.

Use the bundled script to turn a compact scene spec into valid Excalidraw JSON with ids, seeds, version fields, app state, common element defaults, and an official Excalidraw SVG preview rendered through `@excalidraw/excalidraw`'s `exportToSvg`.

## Workflow

1. Interpret the user's drawing request as a small set of semantic elements: containers, labels, arrows, groups, frames, and notes.
2. Draft a scene spec JSON using `references/scene-spec.md` only when you need the exact schema or examples.
3. Save the scene spec in the workspace or outputs folder.
4. Use `fontFamily: 5` (`Excalifont`) by default for the whole scene unless the user explicitly requests another typography style.
5. If the user asks for an image, run with `--svg` and return/show the official SVG preview as the main answer:

```bash
python3 scripts/build_excalidraw.py input.scene.json output.excalidraw --svg output.svg
```

6. Render the preview and inspect it before delivery. Check every title, shape label, arrow label, and frame boundary for clipping, overlap, or incorrect centering. If the preview is wrong, revise the scene and render again.
7. If the user explicitly asks for `.excalidraw`, source, editable file, or "can open in Excalidraw", return the `.excalidraw` file as the main artifact. Otherwise, return the image preview and keep the `.excalidraw` as an implementation artifact unless useful to mention.

## Output Rules

- User asks for "图片", "image", "图", "preview", or just describes a diagram: produce and show an SVG image preview.
- User asks for `.excalidraw`, "可编辑", "源文件", "Excalidraw 文件", or wants to continue editing: produce and link the `.excalidraw` file.
- If both are requested, produce both.
- In the Codex desktop app, show local SVG output with Markdown image syntax using an absolute path: `![diagram](/absolute/path/output.svg)`.
- If PNG is specifically requested, first create SVG; then convert to PNG with an available local tool (`rsvg-convert`, `magick`, browser screenshot, or another existing project tool). Do not hand-code a separate raster renderer.
- The default `--svg` path must use the official Excalidraw exporter. Use `--simple-svg` only as a fallback if the official Node export fails, and always inspect fallback output because its font metrics can differ.

## Drawing Guidelines

- Prefer editable Excalidraw primitives over static embedded SVG.
- Use real Excalidraw `rectangle`, `ellipse`, `diamond`, `arrow`, `line`, and `text` elements.
- For architecture and flow diagrams, make structure first: left-to-right or top-to-bottom, consistent spacing, direct arrows, concise labels.
- Default to a hand-drawn visual system: `roughness` around `1.2` to `1.8`, `strokeStyle: "solid"`, official font family `5` (`Excalifont`), and muted fills. Only change the font family when the user explicitly requests a non-hand-drawn style.
- Give multiline shape labels enough vertical space. Prefer boxes at least `number of lines × font size × 1.25 + 24px` high.
- Keep at least 12px of internal text padding and at least 28px between arrow labels and nearby shapes.
- Keep arrow labels short. Move them with `labelOffsetX`, `labelOffsetY`, or explicit `labelX`/`labelY` when automatic placement overlaps another element.
- Do not put both a frame `text` label and a separate title at the same coordinates.
- Keep labels as separate text elements unless the text must move as part of a shape.
- Use stable custom ids in the scene spec when arrows should connect to specific boxes.
- Use `frame` elements for large bounded sections or alternative flows.
- If the user asks to modify an existing `.excalidraw`, read its JSON, preserve unrelated elements, and change only the requested parts.

## Script Input

The script accepts a compact JSON scene spec. Minimal example:

```json
{
  "title": "Login flow",
  "elements": [
    { "id": "user", "kind": "rectangle", "x": 80, "y": 100, "width": 160, "height": 70, "text": "User" },
    { "id": "api", "kind": "rectangle", "x": 360, "y": 100, "width": 180, "height": 70, "text": "API" },
    { "kind": "arrow", "from": "user", "to": "api", "text": "POST /login" }
  ]
}
```

Use `python3 .../build_excalidraw.py --help` for CLI options.

## Static Export Notes

The normal SVG preview is rendered by the official Excalidraw package, so rough strokes, arrowheads, text placement, and embedded fonts should match Excalidraw much more closely than hand-written SVG. The script still contains a lightweight fallback renderer behind `--simple-svg`; avoid it unless the official exporter is unavailable.

Before returning any preview, render it to a viewable image if necessary and visually inspect:

- no text extends beyond its box;
- multiline text is vertically centered;
- arrows do not cross labels;
- frame titles appear once;
- all diagram content fits inside the SVG viewBox;
- the default font visibly reads as hand-drawn.
