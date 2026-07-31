# Portrait Workbench

Portrait Workbench is a browser-first experiment for comparing painterly portrait recipes and framing a promising result in a lightweight card context. It is deliberately exploratory, not production asset approval tooling.

## Start it

```bash
uv run python -m tools.portraits workbench-server
npm install
npm run dev
```

Open the Vite URL and use Style Lab. The Python service creates an ignored `portrait-library/` workspace on first start. Use the local upload path for a smoke test, or set `PEXELS_API_KEY` to search Pexels. Set `OPENROUTER_API_KEY` when using an image model; the default deterministic painterly model needs no key and is useful for UI validation.

The Vite app keeps its existing `/butler/assets/` base path and the API defaults to `127.0.0.1:8765`. Set `ASSET_REVIEW_PORT` if the API uses another port.

## Browser workflow

1. In Style Lab, add source portraits from Pexels or local files and put a fixed order into the benchmark.
2. Upload and order a small, consistent style-reference pack.
3. Edit or duplicate the seeded artist-facing recipe and inspect its resolved instruction preview.
4. Run the benchmark, wait for the source-ordered sheet, and assign one sheet-level verdict.
5. Compare completed sheets, choose one result, and use it in Card Workbench.
6. Drag, zoom, or nudge the image in the 336 × 276 art window. Framing saves automatically; Keep and Discard are exploratory draft decisions.

Only `workspace.json`, source/reference metadata, immutable run snapshots, and card drafts live under `portrait-library/`. Every image URL served by the API is checked to remain below that directory. Pexels provenance and its experimental-use licensing caveat remain attached to imported sources.

See [docs/portrait-workbench.md](docs/portrait-workbench.md) for the workspace contract, backend limitations, framing formula, and reset procedure.
