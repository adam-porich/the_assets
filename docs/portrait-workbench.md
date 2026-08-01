# Source, pipeline, and card workbench contract

The supported product surfaces are `Sources`, `Pipelines`, and `Cards`.
The everyday loop keeps a source cohort stable, changes a pipeline, and
compares the produced cards. Approval is not part of the current UI.

## Style pipeline

`tools/cards/styles/amiga-ocs-portrait-v1.json` is the checked-in definition
for the live neutral portrait style version. It contains these sections:

- `identity`: stable family ID, opaque version ID, numeric display version,
  label, and draft/locked state;
- `generation`: model ID, execution mode, quality, structured direction, avoid
  text, requested aspect policy, and reference limit;
- `reference_pack`: ordered assets with the closed role set
  `generation-reference` and `target-example`;
- `composition`: logical art size, normalized centering, and default framing;
- `renderer`: driver ID, preprocess, palette, palette space, dither matrix and
  thresholds;
- `card_assembly`: driver ID, logical card size, output scale, and layout/text;
- `editor_descriptors`: fields exposed by the Pipelines editor;
- `provenance` and `checksums`: source information and canonical style/asset
  checksums.

The generation direction is deliberately structured: identity cues to retain,
composition to normalize, expression/pose to discard, rendering language, and
avoid instructions. It asks an img2img-capable model to redraw the source as
an interpretive frontal, calm, head-and-shoulders portrait. It does not promise
biometric identity preservation and does not ask the provider to produce pixel
effects or card furniture.

Validation rejects invalid dimensions, out-of-range framing/centering, bad
palette colors, duplicate IDs, unknown roles, missing generation references,
unsupported driver IDs, invalid model settings, and unsafe paths. The canonical
checksum excludes mutable storage paths and state, then hashes the normalized
configuration and every referenced asset checksum.

`StyleStore` materializes the initial definition at bootstrap under
`styles/versions/<style-version-id>/references/`. A draft is stored separately.
Locked files are never edited. Locking creates a new opaque version and
activation changes only the active pointer; existing batches keep their
original snapshots and remain available in the comparison history.

## Renderer boundary

`tools/cards/registry.py` is keyed by renderer driver ID. A driver accepts a
validated style snapshot, master image, label, and optional framing override,
and returns logical art, enlarged art, a complete card, and render metadata.
Only `amiga-ocs` is registered.

The Amiga driver uses the proven deterministic implementation in
`tools/cards/amiga.py`: 168×138 logical art, 336×276 art, a shared 32-color
OCS-compatible palette, edge-aware ordered 4×4 Bayer dithering, pixel-native
210×300 logical cards, and exact 2× enlargement. Framing is resolved before
preparation and quantisation. The active generation reference is the face-free
`generation-reference-02.png` style board, so it contributes palette, matte
planes, edges, and background treatment without introducing a second subject.
The older face-bearing `generation-reference-01.png` remains only as a
historical renderer-proof input; rendered through this path it is
pixel-identical to `target-example-01.png`.

The target example is a review asset only. The production reference stack is
always identity first, followed by saved generation references. A target role
cannot enter a generation adapter request.

## Production batches

`CardProductionManager` stores both normal batches and pipeline comparison trials.
Normal batches use `purpose: "card-production"` and a locked active style;
trials use `purpose: "style-trial"` and a draft snapshot. A batch snapshots
source membership/order, source bytes, style configuration, reference bytes,
model capabilities, provider mapping, and the expected call count before the
worker starts.

Each source begins with one immutable attempt and a stable lineage. Attempt
stages are `queued`, `generating`, `processing`, `ready`, `failed`, and
`interrupted`. A generated master is never ready until its render bundle and
checksums have been atomically saved. `Try another` appends one attempt for one
source. Retry appends attempts only for failed/interrupted sources. Successes
are never overwritten. The workspace bootstrap exposes every ready attempt;
historical generations are not reduced to one latest item per source.

The generating phase is the neutral redraw; processing is deterministic Amiga
rendering and card assembly. Every attempt snapshots the exact resolved
request, including source-first/reference-after ordering and an explicit
`target_examples_excluded` marker. Live paid actions keep an authorization
record at the API boundary. In the browser the call count and unit cost sit
beside the explicit run action, which starts without a second modal.

Usage and provider response cost are the accounting source of truth. Unknown
cost remains unknown; simulation reports zero. No paid action starts without an
explicit request, and one active generation batch is allowed at a time.

## Framing and retained compatibility data

The default framing is stored on every attempt. A framing save reads the
immutable master, resolves a bounded cover transform, and writes a new render
revision without calling the generation adapter. Previous revisions remain on
disk. The supported UI treats every ready render as a result and does not gate
it with approval or bundling.

Historical approval records and their API methods remain readable for workspace
compatibility, but the product no longer writes or surfaces them. They can be
removed in a later storage migration once old workspaces no longer depend on
that schema.

## Pipelines

Saved pipelines and the working pipeline are shown as peer assets with result
samples, generation references, target example, palette, driver output, and
checksum. A pipeline anatomy diagram exposes each stage from input identity to
assembled card. The draft editor keeps Generation, Amiga processing, and Card
groups collapsible.

The calibration cohort is capped at three workspace sources and persists across
trials. A trial is reviewable only when every cohort item reaches final-card
`ready`. The Cards matrix has two strategy columns: live image-model attempts
are **Interpretive redraw**, while simulation-era deterministic previews are
the **Direct render** baseline. Pipeline checksums and attempt numbers remain
on each candidate inside the strategy gallery, so configuration history is
available without turning every edit into a column. Simulation trials validate
mechanics but cannot activate a production pipeline. Live activation rechecks
that the draft checksum and referenced asset checksums still match the trial,
then locks a new immutable version and moves the active pointer. It never
regenerates existing cards.

To add a future family, implement the typed registry driver, define and validate
its renderer/card sections, provide descriptors and proof assets, and exercise
the shared batch/trial contracts. No new family is user-selectable
until its driver is registered and proven.

## Historical data

Existing workspace files are not rewritten or deleted by bootstrap. Ready
historical cards are exposed in the source-by-strategy comparison when their
source still belongs to the current cohort; other old files remain directly
inspectable by an operator.
