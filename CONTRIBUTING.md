# Contributing

Thanks for helping improve Excalidraw Diagram Skill.

## Before you start

- Search existing issues before opening a new one.
- Keep changes focused and preserve scene compatibility when possible.
- For behavior changes, add or update a test.
- Do not commit `node_modules`, Python caches, or local generated files.

## Local setup

```bash
git clone https://github.com/iruochen/excalidraw-diagram-skill.git
cd excalidraw-diagram-skill
npm ci
npm test
npm run example
```

## Pull requests

1. Fork the repository and create a topic branch.
2. Explain the problem and the chosen approach.
3. Include before/after previews for visual changes.
4. Confirm that `npm test` and `npm run example` pass.
5. Keep public documentation in sync with scene-spec changes.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
