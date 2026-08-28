# Scene Spec Reference

Use this compact JSON format as the input to `scripts/build_excalidraw.py`. The same spec can produce both an editable `.excalidraw` file and an SVG image preview rendered by official Excalidraw export utilities.

## Top Level

```json
{
  "title": "Optional title",
  "appState": {
    "theme": "light",
    "viewBackgroundColor": "#ffffff"
  },
  "defaults": {
    "strokeColor": "#1e1e1e",
    "backgroundColor": "transparent",
    "roughness": 1.4,
    "fontSize": 20,
    "fontFamily": 5
  },
  "elements": []
}
```

`fontFamily: 5` (`Excalifont`) is the required default unless the user explicitly asks for another typography style.

## Common Element Fields

- `id`: optional stable id for references.
- `kind`: `rectangle`, `ellipse`, `diamond`, `text`, `arrow`, `line`, or `frame`.
- `x`, `y`, `width`, `height`: element bounds.
- `text`: label text. For shape elements, the script creates a separate centered text element.
- `strokeColor`, `backgroundColor`, `fillStyle`, `strokeWidth`, `strokeStyle`, `roughness`, `opacity`: Excalidraw style fields.
- `fontFamily`: use `5` for official Excalifont, `1` for Virgil, `2` for Helvetica, or `3` for Cascadia.
- `textPadding`: optional shape-label padding; defaults to `12`.
- `minFontSize`: optional lower bound when a shape label must shrink to fit; defaults to `12`.
- `lineHeight`: optional line-height multiplier; defaults to `1.25`.
- `groupIds`: optional array of group ids.
- `frameId`: optional frame id.

## Shapes

```json
{ "id": "web", "kind": "rectangle", "x": 80, "y": 80, "width": 200, "height": 90, "text": "Web App", "backgroundColor": "#e8f3ff" }
```

`rectangle` supports `roundness: "round"` or `roundness: "sharp"`.

## Text

```json
{ "kind": "text", "x": 80, "y": 40, "text": "Checkout Architecture", "fontSize": 28, "fontWeight": "bold" }
```

The script estimates text bounds. Use explicit `width` and `height` when layout needs precision.

## Arrows And Lines

Arrows can be positioned explicitly:

```json
{ "kind": "arrow", "x": 120, "y": 100, "points": [[0, 0], [180, 0]], "text": "event" }
```

Or connected between ids:

```json
{ "kind": "arrow", "from": "web", "to": "api", "text": "HTTPS" }
```

When using `from` and `to`, the script connects the source and destination edges. It keeps the original simple straight connector when the route is unobstructed. If that connector would cross another visible rectangle, ellipse, or diamond, the script deterministically creates an orthogonal route around all intervening shapes with a 20px default clearance. Obstacle routes jointly select the midpoint of the source and destination's top, right, bottom, or left edge, so their first and last segments meet the selected edge perpendicularly without touching a corner or running along the node border. Frames are not routing obstacles. Set `routingMargin` on the arrow or line to change the clearance.

Explicit `points` are never rewritten by automatic routing.

Automatic labels follow the final routed path and try alternate sides and path positions rather than overlap a shape, standalone text, or frame title. Shape-bound labels are already covered by their container and are not counted twice. Explicit `labelX`/`labelY` or `labelOffsetX`/`labelOffsetY` remain authoritative manual overrides.

Arrow and line labels can be controlled explicitly:

- `labelX`, `labelY`: absolute scene coordinates for the label. Use these for crowded diagrams.
- `labelPosition`: where to anchor the label along the full path. Accepts `start`, `middle`, `center`, `end`, or a number from `0` to `1`.
- `labelOffsetX`, `labelOffsetY`: offset from the computed path anchor. Defaults to `0` and `-28`.
- `routingMargin`: obstacle clearance for `from`/`to` connectors. Defaults to `20`; ignored when `points` are explicit.

Examples:

```json
{ "kind": "arrow", "from": "api", "to": "queue", "text": "enqueue", "labelPosition": "start", "labelOffsetY": -36 }
```

```json
{ "kind": "arrow", "x": 120, "y": 100, "points": [[0, 0], [200, 0], [200, 160]], "text": "retry", "labelPosition": 0.75, "labelOffsetX": 18 }
```

```json
{ "kind": "arrow", "from": "failed", "to": "start", "text": "manual retry", "labelX": 80, "labelY": 260 }
```

## Frames

```json
{ "id": "backend-frame", "kind": "frame", "x": 320, "y": 40, "width": 520, "height": 320, "text": "Backend" }
```

Frames create an Excalidraw frame plus a small title text near the top-left.

## Example

```json
{
  "title": "RAG pipeline",
  "defaults": { "roughness": 1.5, "fontSize": 19 },
  "elements": [
    { "kind": "text", "x": 80, "y": 30, "text": "RAG pipeline", "fontSize": 30, "fontWeight": "bold" },
    { "id": "docs", "kind": "rectangle", "x": 80, "y": 110, "width": 180, "height": 80, "text": "Documents", "backgroundColor": "#fff4cc" },
    { "id": "embed", "kind": "rectangle", "x": 350, "y": 110, "width": 190, "height": 80, "text": "Embedding job", "backgroundColor": "#e8f3ff" },
    { "id": "store", "kind": "ellipse", "x": 630, "y": 105, "width": 190, "height": 90, "text": "Vector store", "backgroundColor": "#e8ffe8" },
    { "id": "query", "kind": "rectangle", "x": 220, "y": 290, "width": 180, "height": 80, "text": "User query", "backgroundColor": "#f3e8ff" },
    { "id": "llm", "kind": "rectangle", "x": 520, "y": 290, "width": 190, "height": 80, "text": "LLM answer", "backgroundColor": "#ffe8ef" },
    { "kind": "arrow", "from": "docs", "to": "embed", "text": "chunk" },
    { "kind": "arrow", "from": "embed", "to": "store", "text": "index" },
    { "kind": "arrow", "from": "query", "to": "store", "text": "retrieve" },
    { "kind": "arrow", "from": "store", "to": "llm", "text": "context" },
    { "kind": "arrow", "from": "query", "to": "llm", "text": "prompt" }
  ]
}
```

If a requested shape is not supported directly, approximate it with a supported primitive and keep it editable.

## Output Commands

Image preview plus editable source:

```bash
python3 scripts/build_excalidraw.py diagram.scene.json diagram.excalidraw --svg diagram.svg
```

Fallback SVG preview without official rendering:

```bash
python3 scripts/build_excalidraw.py diagram.scene.json diagram.excalidraw --svg diagram.svg --simple-svg
```

Editable source only:

```bash
python3 scripts/build_excalidraw.py diagram.scene.json diagram.excalidraw
```
