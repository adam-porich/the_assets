# 01 — Build the neutral master generation contract

## Style definition

- [x] Revise the Amiga portrait style's generation direction so it explicitly
  asks the model to redraw rather than enhance or filter the source.
- [x] Define positive constraints for a centered frontal head-and-shoulders
  bust, level shoulders, direct gaze, closed or gently resting mouth, calm
  affect, restrained clothing silhouette, quiet abstract background, and even
  studio-like lighting.
- [x] Define preservation constraints for facial geometry, apparent age, hair
  shape, skin tone, and genuinely identifying features.
- [x] Define discard constraints for source pose, facial emotion, gesture,
  props, scenery, action, dramatic lighting, camera distortion, photographic
  texture, text, borders, and card furniture.
- [x] Keep the master pre-quantisation: broad matte planes and deliberate edges
  are desirable, but visible pixel grids, dithering, scanlines, and simulated
  retro effects are not.
- [x] Version this generation contract with the renderer and card assembly so
  a prompt, reference, or model change produces a new immutable style version.

## Live model path

- [x] Restore an explicit live/simulation execution-mode control in Style
  Studio rather than relying on a free-text model ID.
- [x] Populate the live model choice from the capability catalogue and offer
  only models/endpoints that accept the identity image plus all ordered style
  references.
- [x] Keep the identity source first and
  `generation-reference-01.png` second in the provider payload, with their
  roles recorded even when the provider API only supports ordered references.
- [x] Validate mode, model, provider endpoint, quality, aspect ratio, reference
  capacity, credentials, and pricing before a trial or production batch starts.
- [x] Make a live generative style the intended production configuration;
  prevent a simulation-locked style from presenting its output as completed
  generated artwork.
- [x] Preserve explicit consent for every paid trial, production batch, retry,
  and **Try another** attempt.

## Artifact and provenance contract

- [x] Name the generated output consistently as the canonical portrait master
  in records, documentation, and diagnostics.
- [x] Snapshot the original source, generation reference, resolved instruction,
  negative instruction, model/provider capabilities, effective parameters,
  seed when supported, usage, cost, dimensions, and checksums for each attempt.
- [x] Keep source, master, logical Amiga art, enlarged Amiga art, and card as
  separate immutable artifacts.
- [x] Record enough information to distinguish a live generated master from a
  simulation preview without inspecting image bytes.
- [x] Keep target-example assets structurally excluded from provider payloads.

## Tests

- [x] Add adapter tests proving the request ordering is source first and the
  high-resolution generation reference second.
- [x] Add tests proving the target example never enters the provider request.
- [x] Add validation tests for unavailable live models, mismatched execution
  mode, insufficient reference capacity, missing credentials, and unsupported
  quality/aspect choices.
- [x] Add provenance tests covering successful, failed, retried, and additional
  attempts without requiring paid calls.
- [x] Add a fake semantic-generation adapter for end-to-end tests; do not use
  the deterministic crop/filter simulation as evidence of style transfer.
