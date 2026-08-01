# 01 — Build the neutral master generation contract

## Style definition

- [ ] Revise the Amiga portrait style's generation direction so it explicitly
  asks the model to redraw rather than enhance or filter the source.
- [ ] Define positive constraints for a centered frontal head-and-shoulders
  bust, level shoulders, direct gaze, closed or gently resting mouth, calm
  affect, restrained clothing silhouette, quiet abstract background, and even
  studio-like lighting.
- [ ] Define preservation constraints for facial geometry, apparent age, hair
  shape, skin tone, and genuinely identifying features.
- [ ] Define discard constraints for source pose, facial emotion, gesture,
  props, scenery, action, dramatic lighting, camera distortion, photographic
  texture, text, borders, and card furniture.
- [ ] Keep the master pre-quantisation: broad matte planes and deliberate edges
  are desirable, but visible pixel grids, dithering, scanlines, and simulated
  retro effects are not.
- [ ] Version this generation contract with the renderer and card assembly so
  a prompt, reference, or model change produces a new immutable style version.

## Live model path

- [ ] Restore an explicit live/simulation execution-mode control in Style
  Studio rather than relying on a free-text model ID.
- [ ] Populate the live model choice from the capability catalogue and offer
  only models/endpoints that accept the identity image plus all ordered style
  references.
- [ ] Keep the identity source first and
  `generation-reference-01.png` second in the provider payload, with their
  roles recorded even when the provider API only supports ordered references.
- [ ] Validate mode, model, provider endpoint, quality, aspect ratio, reference
  capacity, credentials, and pricing before a trial or production batch starts.
- [ ] Make a live generative style the intended production configuration;
  prevent a simulation-locked style from presenting its output as completed
  generated artwork.
- [ ] Preserve explicit consent for every paid trial, production batch, retry,
  and **Try another** attempt.

## Artifact and provenance contract

- [ ] Name the generated output consistently as the canonical portrait master
  in records, documentation, and diagnostics.
- [ ] Snapshot the original source, generation reference, resolved instruction,
  negative instruction, model/provider capabilities, effective parameters,
  seed when supported, usage, cost, dimensions, and checksums for each attempt.
- [ ] Keep source, master, logical Amiga art, enlarged Amiga art, and card as
  separate immutable artifacts.
- [ ] Record enough information to distinguish a live generated master from a
  simulation preview without inspecting image bytes.
- [ ] Keep target-example assets structurally excluded from provider payloads.

## Tests

- [ ] Add adapter tests proving the request ordering is source first and the
  high-resolution generation reference second.
- [ ] Add tests proving the target example never enters the provider request.
- [ ] Add validation tests for unavailable live models, mismatched execution
  mode, insufficient reference capacity, missing credentials, and unsupported
  quality/aspect choices.
- [ ] Add provenance tests covering successful, failed, retried, and additional
  attempts without requiring paid calls.
- [ ] Add a fake semantic-generation adapter for end-to-end tests; do not use
  the deterministic crop/filter simulation as evidence of style transfer.
