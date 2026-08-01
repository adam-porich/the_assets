# Unified card workbench contract

The supported product surfaces are `Sources`, `Cards`, and `Style Studio`.
The everyday decision is source selection followed by final-card approval.

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
- `editor_descriptors`: fields exposed by Style Studio;
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
activation changes only the active pointer; existing batches and approvals keep
their original snapshots.

## Renderer boundary

`tools/cards/registry.py` is keyed by renderer driver ID. A driver accepts a
validated style snapshot, master image, label, and optional framing override,
and returns logical art, enlarged art, a complete card, and render metadata.
Only `amiga-ocs` is registered.

The Amiga driver uses the proven deterministic implementation in
`tools/cards/amiga.py`: 168×138 logical art, 336×276 art, a shared 32-color
OCS-compatible palette, edge-aware ordered 4×4 Bayer dithering, pixel-native
210×300 logical cards, and exact 2× enlargement. Framing is resolved before
preparation and quantisation. The checked-in generation reference rendered
through this path is pixel-identical to `target-example-01.png`.

The target example is a review asset only. The production reference stack is
always identity first, followed by saved generation references. A target role
cannot enter a generation adapter request.

## Production batches

`CardProductionManager` stores both normal batches and Style Studio trials.
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
are never overwritten.

The generating phase is the neutral redraw; processing is deterministic Amiga
rendering and card assembly. Every attempt snapshots the exact resolved
request, including source-first/reference-after ordering and an explicit
`target_examples_excluded` marker. Live paid actions require consent at the
API boundary as well as in the browser.

Usage and provider response cost are the accounting source of truth. Unknown
cost remains unknown; simulation reports zero. No paid action starts without an
explicit request, and one active generation batch is allowed at a time.

## Framing, approvals, and downloads

The default framing is stored on every attempt. A framing save reads the
immutable master, resolves a bounded cover transform, and writes a new render
revision without calling the generation adapter. Previous revisions remain on
disk. An approved card whose render changes needs a new explicit approval; the
old approval record does not drift.

An approval includes source ID, attempt ID, batch ID, locked style version and
checksum, card checksum, render revision, and timestamp. The current pointer is
unique per source and style version; history is append-only. Approving another
attempt supersedes the pointer without deleting either card.

The approved bundle follows selected source order and contains only current
card PNGs plus `manifest.json`. The manifest carries attempt, style, render,
and checksum provenance. Masters are diagnostic and omitted.

## Style Studio

The active style is shown first with generation references, the target example,
palette, driver output, and checksum. The draft editor uses driver descriptors
where appropriate and keeps advanced Generation, Amiga processing, and Card
groups collapsible.

The calibration cohort is capped at three workspace sources and persists across
trials. A trial is reviewable only when every cohort item reaches final-card
`ready`. Simulation trials validate mechanics but cannot activate a production
style. Live activation rechecks that the draft checksum and referenced asset
checksums still match the trial, then locks a new immutable version and moves
the active pointer. It never regenerates existing cards.

To add a future family, implement the typed registry driver, define and validate
its renderer/card sections, provide descriptors and proof assets, and exercise
the shared batch/trial/approval contracts. No new family is user-selectable
until its driver is registered and proven.

## Historical data

Existing workspace files are not rewritten or deleted by bootstrap. They remain
outside current-style production and approval counts. The supported UI exposes
only the current workflow; old files can be inspected or recovered directly by
an operator when needed.
