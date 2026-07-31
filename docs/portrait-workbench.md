# Portrait Workbench

The supported browser path is always visible:

```text
1 Sources → 2 Styles → 3 Frames → 4 Completed
```

The Back/Continue actions suggest a path, but hashes are refreshable and no stage is locked. Empty stages explain what is missing. Old `#lab`, `#run/<id>`, and `#cards` links redirect to their closest current stage; old `#card/<id>` links reopen the equivalent `#frames/<id>` view.

## Sources

New workspaces begin with no source images, two bundled `estate-card-v1` style references, and a low-quality live `openai/gpt-image-1-mini` recipe.

With `PEXELS_API_KEY` configured, **Load six starter images** downloads and selects Pexels photos `11013487`, `14468344`, `23024613`, `9009504`, `14650121`, and `35918726`. Loading and importing are idempotent by photo ID and checksum. Search supports presets, paging, multi-selection, bulk import, and per-photo errors. Local uploads remain available without Pexels.

`benchmark_source_ids` remains the stored ordered project selection for compatibility, but the browser presents it only as selected source images. Pexels and local-upload provenance stays attached to each source record.

## Styles and generation

The main controls are selected source thumbnails, ordered visual references, **What should change?**, variant count, **Generate**, and **Test across all sources**.

- Quick exploration starts with the first selected project source and four variants.
- Variant count accepts 1–4.
- A user can choose a few project sources for a generation batch.
- The all-sources test always creates one output per selected project source.
- `change_note` defaults to an empty string for existing recipes, is added to the resolved instruction as `Requested change: …`, and is preserved in the immutable recipe snapshot.

Model, quality, live/simulation mode, structured direction, negative direction, resolved instruction, recipe duplication, provider capabilities, and pricing metadata are under **Advanced**.

Starting a run submits the complete visible recipe plus explicit source IDs, output count, and execution mode. There is no `confirm_paid` field, paid confirmation dialog, or completed-smoke prerequisite. Live execution still requires `OPENROUTER_API_KEY`, the selected model must be available for the chosen execution mode, identity plus style references must fit its exact endpoint limit, and only one run may be active.

Every immutable run records:

- recipe, change note, resolved instruction, sources, references, and input checksums;
- live or simulation execution and exact model/provider capability mappings;
- requested and effective aspect ratios;
- per-call status, seed, timing, usage, and returned cost;
- aggregate usage and returned cost.

Progress and source-grouped results appear on Styles. Each batch shows its source, style note, reference thumbnails, and cost details. A completed result exposes **Send to Frames**. History and source-for-source comparison remain secondary tools and verdicts do not gate progress.

## Frames

Sending a run item creates a working card draft. Re-sending an item that already has a working or kept card returns that existing card instead of creating a duplicate. A previously discarded item may start a fresh draft.

`POST /api/cards/{id}/previews` returns six `CardPreviewOption` records: Bust, Tall, and Torso crossed with Painterly and Estate Pixel. Each record contains the preset, treatment, derived framing, render URL, art URL, dimensions, and render metadata.

Preview files are cached below ignored `portrait-library/cards/previews/<card-id>/`. The cache key includes:

- the current source-output checksum;
- template ID and version;
- the exact frame preset definitions;
- treatment versions;
- preview schema and card label.

Stale files are removed when the key changes. Selecting a preview copies that exact cached card and art render into the draft's saved output paths, then persists its preset, derived numeric framing, treatment, treatment version, metadata, and preview ID. This makes the chosen preview and saved render byte-identical.

The browser asks only two visual questions: crop, then finish. Numeric framing and provenance remain read-only under details. **Keep as completed** sets `decision: keep`; **Not this one** sets `decision: discard` and advances to the next working candidate.

Estate Pixel uses the established deterministic pipeline: crop the 336 × 276 art window, downsample to 112 × 92, quantize to at most 32 adaptive colours without dithering, and upscale 3× with nearest-neighbour sampling.

## Completed

Completed filters strictly to `decision: keep`. Working and discarded drafts never appear. Each entry shows the full render, stored source/style summary, a direct PNG download, and **Reconsider in Frames**. Reconsidering first changes the decision to `working`, then opens `#frames/<card-id>`.

## Workspace and compatibility

```text
portrait-library/
  workspace.json
  sources/
  references/
  runs/<run-id>/
  cards/
    previews/<card-id>/
```

Existing workspace, run, and card files remain readable. `benchmark_source_ids`, run verdicts, and persisted numeric framing remain in storage. Missing `change_note`, treatment, framing, and decision values receive compatible payload defaults. Writes use a temporary sibling followed by `Path.replace`, with process-local locking around metadata mutation. Asset requests reject absolute paths and traversal.

To reset the experimental workspace, stop the API service, delete only the repository's `portrait-library/`, and restart the service. The directory is ignored by Git.

## External services

OpenRouter model discovery resolves each image-to-image model to a definitive provider endpoint and retains its exact typed parameters, reference limit, provider tag, streaming support, and pricing lines. Generation pins that provider and sends only supported fields. Exact response usage and cost remain the accounting source of truth.

Pexels records retain photo, photographer, source-page, query, and license-page provenance. Review the [Pexels license](https://www.pexels.com/license/) before using an image beyond this experiment.
