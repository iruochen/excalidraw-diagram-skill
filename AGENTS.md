# Agent Maintenance Notes

## Validation

Run the full project test suite before committing changes:

```bash
npm test
```

For Python changes, also run:

```bash
python3 -m py_compile scripts/build_excalidraw.py tests/test_build_excalidraw.py
git diff --check
```

## Connector Routing Invariants

- Preserve explicit connector `points` exactly as supplied.
- Preserve the original two-point connector for unobstructed `from`/`to` edges.
- Obstacle routing must remain deterministic and avoid every visible non-frame shape with the configured margin.
- Routed connectors must use mid-edge ports and meet source and target edges perpendicularly; do not run tangentially along a node border or attach at a corner.
- Automatic connector labels must avoid visible shapes, standalone text, and frame titles. Shape-bound text does not need to be counted separately from its container.
- Explicit `labelX`/`labelY` and `labelOffsetX`/`labelOffsetY` remain authoritative.

Add regression coverage whenever one of these invariants changes or a real diagram exposes a new routing case.
