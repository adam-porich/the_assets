# Portrait Workbench

The workbench has one durable browser path:

```text
Style Lab → benchmark → references → recipe → run sheet → card framing → draft decision
```

It intentionally has no favourite queue, master promotion, approval gate, set builder, static lookbook, or pixel-art post-processing stage.

## Workspace

The service lazily creates:

```text
portrait-library/
  workspace.json
  sources/
  references/
  prepared/
  runs/<run-id>/
  cards/
```

`workspace.json` contains small source, reference, and recipe metadata plus the benchmark order and active recipe. A run snapshots its exact recipe, resolved instruction, source/reference inputs, checksums, model capabilities, requested 28:23 card-window ratio, effective backend ratio, and per-item progress. Card drafts point directly to a completed run item and store only the visible framing transform and experimental decision.

Writes use a temporary sibling followed by `Path.replace`, with a process-local lock around workspace mutation. Asset requests reject absolute paths and traversal before reading.

## Backends

`fake/painterly-deterministic` is local and deterministic, so it is the default smoke-test path. OpenRouter models are exposed when the API key is configured. The adapter keeps the identity image separate from the ordered style references until the backend boundary, validates reference limits, negotiates the closest supported landscape ratio, and records whether role-aware references or native negative prompts are available. If a backend lacks those controls, the run records the explicit adapter mapping in its provenance.

Generated outputs are saved as full painterly PNGs. Thumbnails are display-only JPEGs; there is no raw/clean/final promotion or automatic quantisation.

## Card framing

The direct renderer uses the `estate-card-v1` frame and a 336 × 276 art window. Bust, Tall, and Torso are initial zoom/offset presets. The shared formula calculates a cover scale, multiplies it by zoom, centres the scaled source, applies normalized offsets, and clamps the image bounds so empty pixels cannot enter the window. The browser gives immediate movement; Pillow writes the saved render after debounced changes.

## Reset

This is pre-live experimental data. Stop the service and remove only the generated workspace if a clean slate is needed:

```bash
rm -rf portrait-library
```

The next server start recreates an empty workspace and its seeded recipe. Do not remove the repository or unrelated directories.

## Pexels

Pexels search results show photographer and source-page provenance before download. Imported files are experimental inputs; review the [Pexels license](https://www.pexels.com/license/) and any applicable usage requirements before using an image outside this workbench.
