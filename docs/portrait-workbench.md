# Portrait Workbench

The supported path is deliberately short:

```text
Sources → Style pack → Art direction → Generate → Frame this portrait → Keep
```

Live generation and local simulation are distinct execution modes. A simulation is a deterministic, lightly painterly image-processing fixture used to exercise the workflow; it must not be judged or described as generated artwork.

## Fast setup

New workspaces start with:

- a live `openai/gpt-image-1-mini` recipe at low quality;
- the two checked-in `estate-card-v1` style references, copied into the workspace with bundled provenance;
- no source portraits.

With `PEXELS_API_KEY` configured, **Load starter benchmark** downloads and selects Pexels photos `11013487`, `14468344`, `23024613`, `9009504`, `14650121`, and `35918726`. The operation is idempotent. Search also supports presets, paging, multi-selection, bulk import, automatic benchmark inclusion, and per-photo errors when only part of a selection downloads.

Style references can be selected, reordered, renamed, replaced, and uploaded. The identity source counts alongside them for model reference limits.

## Trustworthy execution

The server reads OpenRouter's image-model catalogue and resolves each image-to-image model to one definitive provider endpoint. Model metadata retains the endpoint's exact typed `supported_parameters`, reference limit, provider tag, streaming support, and pricing lines. The generation request pins that provider and sends only fields present in its descriptor. See [OpenRouter image generation and model discovery](https://openrouter.ai/docs/guides/overview/multimodal/image-generation).

A saved model that disappears from the catalogue stays visible as unavailable. The browser never replaces it with the first returned model. Live execution also requires `OPENROUTER_API_KEY`; an environment setting cannot silently turn it into simulation.

**Save and run** submits the complete visible recipe draft with explicit source IDs, output count, and execution mode. The server normalizes and persists that draft, then snapshots the same value into the run. Every run records:

- live or simulation provenance;
- recipe, instruction, sources, references, and input checksums;
- exact endpoint capabilities and adapter mappings;
- requested 28:23 and effective provider aspect ratios;
- per-call usage and cost plus aggregated run usage and cost.

Before a multi-source paid benchmark is allowed for a model, one live source must complete successfully with that model. Every live launch has a confirmation showing mode, model, source count, style-reference count, image calls, and available pricing metadata. Exact response cost remains the accounting source of truth.

## Run review and framing

Every completed result tile exposes **Frame this portrait**. The details drawer repeats that action and retains run provenance. Selecting it creates a card draft directly from the immutable full painterly run output; there are no masters, promotion stages, or approval gates.

The workbench stores cover framing as zoom plus normalized x/y offsets. Both browser and Pillow use the shared 336 × 276 art window contract and clamp the image so the window cannot expose empty pixels. Bust, Tall, and Torso are editable starting frames.

Card drafts offer two treatments:

- `painterly`: the framed generation source;
- `estate-pixel-v1`: crop the 336 × 276 art window, downsample to 112 × 92, quantize deterministically to at most 32 adaptive colours without dithering, then upscale 3× with nearest-neighbour sampling.

The server writes a treated art-window file and the browser displays that exact Pillow artifact after each debounced framing save. While dragging, the browser temporarily displays the immutable source transform. Keep and reopen preserve framing, treatment version, source-run provenance, render checksums, and output paths.

## Workspace

```text
portrait-library/
  workspace.json
  sources/
  references/
  runs/<run-id>/
  cards/
```

Writes use a temporary sibling followed by `Path.replace`, with process-local locking around metadata mutation. Asset requests reject absolute paths and traversal.

This experimental workspace has no backwards migration. To reset it, stop the API service, delete only the repository's `portrait-library/`, restart the service, and load the starter benchmark in the browser. Never automate a paid smoke test; confirm and run that manually in the UI.

## Pexels

Pexels records retain photo, photographer, source-page, query, and license-page provenance. Review the [Pexels license](https://www.pexels.com/license/) before using an image beyond this experiment.
