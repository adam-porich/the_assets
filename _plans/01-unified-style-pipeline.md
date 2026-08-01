# 01 — Build the unified style pipeline contract

## Outcome

Make “Amiga OCS Portrait v1” an executable, immutable pipeline that owns the
complete transformation:

```text
identity source + ordered generation references
→ img2img master
→ framing/crop and master preparation
→ fixed-palette Amiga rendering
→ pixel-native card assembly
```

The generation request and deterministic renderer must be versioned together.
No active record may call only the prompt/reference portion “the style” while
treating quantisation or card assembly as an unrelated treatment.

## Style definition

- [ ] Introduce one validated style-pipeline schema with these sections:
  identity/version/state/label, generation, reference pack, composition,
  renderer, card assembly, editor descriptors, and provenance/checksums.
- [ ] Give every persisted locked version an opaque `style_version_id` as well
  as the stable family ID `amiga-ocs-portrait`; do not infer immutability from a
  mutable recipe name or an integer alone.
- [ ] Put the current model ID, execution mode, quality, structured direction,
  avoid text, requested aspect policy, and ordered generation references inside
  the generation section.
- [ ] Put logical art/card sizes, output scale, palette, palette space,
  preprocess values, centering/default framing, dithering matrix/strength/edge
  threshold, and card layout values inside the renderer/card sections.
- [ ] Extend or supersede
  `tools/cards/styles/amiga-ocs-portrait-v1.json` with this complete definition.
  Do not keep a second mutable recipe that can drift from it.
- [ ] Validate all dimensions, normalized framing values, palette colors,
  engine IDs, reference roles, model/reference limits, and effective parameters
  before a draft can run or a version can lock.
- [ ] Compute a canonical style checksum over normalized configuration and all
  referenced asset checksums. Record it on every trial, production item, render,
  and approved card.

## Reference roles and snapshots

- [ ] Model reference-pack entries as either `generation-reference` or
  `target-example`; do not represent the role as descriptive free text alone.
- [ ] Seed the generation reference and target example currently recorded in
  `tools/cards/assets/amiga-ocs-portrait-v1/pack.json` into the initial style.
- [ ] Ensure a generation request is always ordered as identity source first,
  followed by `generation-reference` assets in saved order.
- [ ] Reject any attempt to put a `target-example` in a provider request. The
  processed target is for human comparison and golden tests only.
- [ ] Snapshot reference files below every locked workspace style version and
  record their checksums; later upload/replacement cannot mutate that version.
- [ ] Keep the original source, prequantisation master, logical art, enlarged
  art, and card as separate immutable artifacts with distinct roles and hashes.

## Renderer interface and Amiga engine

- [ ] Add a small renderer/assembler registry keyed by driver ID. It must accept
  a validated style snapshot, master image, label, and optional framing override
  and return a typed render bundle plus metadata.
- [ ] Make the interface neutral about palette, glyphs, dithering, and raster
  method so a future 8-bit or ASCII engine can implement it without changing
  generation, trials, approvals, or the normal Cards UI.
- [ ] Register only the `amiga-ocs` driver now. Unknown drivers fail clearly;
  there is no generic fallback that silently changes appearance.
- [ ] Move the behavior proven in `tools/cards/amiga.py` behind this interface:
  168×138 logical art, 336×276 2× art, 210×300 logical card, 420×600 2× card,
  shared 32-color OCS 12-bit palette, edge-aware 4×4 Bayer dithering, and exact
  nearest-neighbor enlargement.
- [ ] Keep palette mapping, preprocess, edge behavior, typography, and card
  assembly deterministic and driven by the style snapshot rather than module
  constants that a saved version does not identify.
- [ ] Apply crop/framing before master preparation and quantisation. Return the
  resolved transform in render metadata.
- [ ] Do not route Amiga output through the current `painterly` or
  `estate-pixel-v1` treatment selector. Those values are legacy history only.
- [ ] Keep `amiga_proof.py` usable as a diagnostic wrapper over the same engine;
  it must not contain a separate rendering implementation.

## Style store

- [ ] Add atomic storage for one editable draft, immutable locked versions, and
  one active version ID under `portrait-library/`.
- [ ] On a fresh workspace, materialize the checked-in Amiga definition and
  assets as locked version 1 and select it as active without a generation call.
- [ ] Editing always creates/updates a draft derived from a locked version.
  Locked files and records cannot be changed through API or direct store calls.
- [ ] Activating a newly locked version changes only the active pointer. It must
  not rewrite old runs, cards, approvals, or assets.
- [ ] Preserve unknown renderer configuration when reading a future style, but
  require a registered driver before it can run.

## Editor descriptors for future styles

- [ ] Let a renderer describe editable groups with a small set of field types
  such as text, number/range, color, select, boolean, ordered colors, and asset
  list. Backend validation remains authoritative.
- [ ] Provide descriptors for the effective Amiga parameters only. Do not expose
  fake controls or provider parameters the selected model cannot honor.
- [ ] Keep the workflow and persisted pipeline independent from these display
  descriptors so a future specialist editor can replace the generic form.
- [ ] Do not implement alternative palettes, ASCII glyph ramps, fonts, ANSI
  export, CRT effects, or additional renderer registrations in this plan.

## Tests and acceptance

- [ ] Add schema/store tests for normalization, canonical checksum stability,
  immutable versions, active-pointer changes, asset snapshots, invalid roles,
  missing drivers, path safety, and atomic failure behavior.
- [ ] Add engine contract tests for dimensions, one fixed palette across art and
  card, OCS channel compatibility, deterministic bytes, edge-aware dithering,
  and exact 2× nearest-neighbor pixels.
- [ ] Add a golden test that renders
  `generation-reference-01.png` through the registered production engine and
  exactly matches `target-example-01.png`.
- [ ] Add a test proving target examples never enter the generation adapter's
  input-reference list.
- [ ] Add a test proving a framing change rerenders the existing master and
  changes render provenance without invoking the generation adapter.
- [ ] Keep the existing proof images visually unchanged unless an intentional
  style version 2 is reviewed and documented; this plan integrates v1 rather
  than silently redesigning it.
- [ ] Run the relevant Python tests and `git diff --check` before marking this
  plan complete.
