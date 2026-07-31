# Portrait Workbench

Portrait Workbench is a browser-first experiment for comparing painterly portrait recipes and framing a promising result in a lightweight card context. It is deliberately exploratory, not production asset approval tooling.

## Start it

```bash
uv run python -m tools.portraits workbench-server
npm install
npm run dev
```

Open the Vite URL and use Style Lab. The Python service creates an ignored `portrait-library/` workspace on first start, seeds two bundled estate style references, and creates a low-quality `openai/gpt-image-1-mini` live recipe. Set `PEXELS_API_KEY` to load the six-source starter benchmark or search Pexels. Set `OPENROUTER_API_KEY` only when you are ready to confirm a paid live generation. The separate Simulation mode is local and free, but its filtered output is a workflow fixture—not generated artwork.

The Vite app keeps its existing `/butler/assets/` base path and the API defaults to `127.0.0.1:8765`. Set `ASSET_REVIEW_PORT` if the API uses another port.

## Browser workflow

1. Load the starter benchmark, or bulk-import/upload an ordered source set.
2. Confirm the bundled style pack and adjust reference selection or order if needed.
3. Choose explicit Live generation or Simulation, edit the recipe, then use **Save and run**.
4. For live work, complete and confirm a one-source paid smoke test before unlocking the full benchmark.
5. Review the source-ordered sheet and choose **Frame this portrait** on any completed tile.
6. Adjust the 336 × 276 frame, choose Painterly or deterministic Estate Pixel treatment, then Keep or Discard the draft.

Runs record exact recipe/model provenance, live or simulation mode, provider capabilities, usage, and returned cost. Card drafts retain their source run, framing, treatment version, render metadata, and output. Every workspace asset URL is checked to remain below `portrait-library/`.

See [docs/portrait-workbench.md](docs/portrait-workbench.md) for the workspace contract, backend limitations, framing formula, and reset procedure.
