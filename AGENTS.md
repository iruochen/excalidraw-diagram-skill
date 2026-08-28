# Agent Maintenance Notes

## Validation

After every code or scene-generation change, run the complete validation command before committing:

```bash
npm run validate
```

This command includes Python compilation, the unit regression suite, the complex routing fixture, an official Excalidraw SVG export, and `git diff --check`.

When routing, text measurement, or rendering behavior changes, also generate the complex fixture manually and visually inspect the official SVG before delivery:

```bash
python3 scripts/build_excalidraw.py \
  tests/fixtures/complex-routing.scene.json \
  /tmp/complex-routing.excalidraw \
  --svg /tmp/complex-routing.svg \
  --pretty
```

Check shape and title overlap, connector clearance, perpendicular endpoint ports, arrow labels, frame boundaries, and clipping. If any visual defect appears, add a regression assertion or fixture case before changing the implementation.

## Connector Routing Invariants

- Preserve explicit connector `points` exactly as supplied.
- Preserve the original two-point connector for unobstructed `from`/`to` edges.
- Obstacle routing must remain deterministic and avoid every visible non-frame shape with the configured margin.
- Routed connectors must use mid-edge ports and meet source and target edges perpendicularly; do not run tangentially along a node border or attach at a corner.
- Automatic connector labels must avoid visible shapes, standalone text, and frame titles. Shape-bound text does not need to be counted separately from its container.
- Explicit `labelX`/`labelY` and `labelOffsetX`/`labelOffsetY` remain authoritative.

Add regression coverage whenever one of these invariants changes or a real diagram exposes a new routing case.
