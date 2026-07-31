# Portrait Workbench

Portrait Workbench is a browser-first graphics experiment organized as a forgiving four-stage workflow:

**1 Sources → 2 Styles → 3 Frames → 4 Completed**

It keeps immutable generation runs, recipes, card records, usage, cost, and provenance underneath a visual workflow intended for quick judgment rather than production approval.

## Start it

```bash
uv run python -m tools.portraits workbench-server
npm install
npm run dev
```

Open the Vite URL. The Python service creates an ignored `portrait-library/` workspace, seeds two bundled estate style references, and creates a low-quality `openai/gpt-image-1-mini` live recipe. Set `PEXELS_API_KEY` for Pexels search and the six starter source images. Set `OPENROUTER_API_KEY` for live generation. Simulation remains an explicit local workflow fixture, not generated artwork.

The Vite app keeps its `/butler/assets/` base path and the API defaults to `127.0.0.1:8765`. Set `ASSET_REVIEW_PORT` if the API uses another port.

## Browser workflow

1. **Sources:** search Pexels, load starters, upload images, inspect provenance, and choose an ordered project set.
2. **Styles:** choose a few sources, order visual references, describe **What should change?**, and generate 1–4 variants. Quick exploration defaults to four variants of the first source; **Test across all sources** creates one result for each selected project source.
3. **Frames:** send a successful result, visually choose Bust/Tall/Torso, then Painterly/Estate Pixel. The six choices are exact deterministic previews rather than browser approximations.
4. **Completed:** keep finished cards, download their PNGs, or reconsider them in Frames.

There are no navigation locks, paid confirmation modal, smoke-test gate, or review verdict gate. Real validation still blocks missing keys, unavailable models, excess references, invalid output counts, and overlapping active runs. Exact returned usage and cost remain recorded in run details.

See [docs/portrait-workbench.md](docs/portrait-workbench.md) for the data contracts, preview caching, compatibility behavior, and reset procedure.
