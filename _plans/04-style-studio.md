# 04 — Build Style Studio around final-card trials

## Outcome

Retain the ability to evolve the house style without sending normal card work
through an art-director maze. Style Studio edits one draft derived from the
active version, tests the complete generation-and-render pipeline, compares
final cards, and activates only a reviewed complete trial.

## Style Studio entry and hierarchy

- [ ] Open Style Studio from the active-style header chip, not from the primary
  Sources → Cards path.
- [ ] Lead with the active version, a concise description, generation reference
  thumbnails, target example, palette strip, and the checked-in Amiga proof
  target. Clearly label the target as **review only — never sent to the model**.
- [ ] Provide one **Edit as new version** action. Editing a locked version creates
  or resumes a separate draft and never changes production behavior.
- [ ] Keep version history and raw provenance collapsed. Make the active version
  and current draft impossible to confuse.

## Draft editing

- [ ] Put one plain-language **What should change?** field first. Preserve the
  structured generation direction as effective fields rather than concatenating
  an untraceable prompt.
- [ ] Provide an ordered **Generation references** strip with add, replace,
  remove, and reorder actions. Show the model's exact reference limit including
  the identity source.
- [ ] Show target examples in a separate read-only region with no control that
  can move them into the generation stack.
- [ ] Put effective controls in three collapsed advanced groups:
  **Generation** (model, quality, direction, avoid), **Amiga processing**
  (preprocess, palette, logical size, dither, centering), and **Card** (template
  and assembly values).
- [ ] Render controls from the driver's editor descriptors where practical and
  show validation beside the field. Do not expose a raw JSON editor as the only
  way to make a normal style adjustment.
- [ ] Resolve model capabilities when execution mode/model changes and expose
  only supported provider controls. Preserve effective values in the draft
  snapshot and identify ignored/invalid historical values.
- [ ] Show the normalized style checksum and changed sections in a compact draft
  summary, not as the main editing interface.

## Calibration cohort

- [ ] Let the user pin up to three representative workspace sources as the
  calibration cohort. Seed sensible choices from current selected sources, but
  never pretend source selection is a style ingredient.
- [ ] Keep the cohort stable across draft trials until the user changes it so
  comparisons remain meaningful.
- [ ] Require at least one source and a valid draft. Show exact paid calls before
  **Test complete style** starts.
- [ ] A style trial must generate one master per calibration source and
  immediately apply draft framing, Amiga processing, and card assembly. There is
  no master-only success state.
- [ ] Reuse the production worker, renderer registry, provenance, polling,
  partial failure behavior, and simulation adapter; do not create a second
  proof-only execution path.

## Compare and activate

- [ ] Display active-version and draft-trial final cards side by side, aligned
  by calibration source. Final cards are primary; master/art differences are
  available behind each pair.
- [ ] Show a concise configuration diff grouped by Generation, References,
  Processing, and Card. Include style/checksum IDs and trial cost in details.
- [ ] Never allow item-level mixing into a style version. A trial is reviewable
  and lockable only when every cohort item is ready through card assembly.
- [ ] Provide **Make this the active style** only on a complete trial whose draft
  and asset checksums still match. The server revalidates before atomically
  locking the version and moving the active pointer.
- [ ] Keep previous versions immutable and selectable for inspection. Switching
  back to an older locked version is explicit and does not rewrite approvals.
- [ ] After activation, offer to create a new production batch for selected
  sources. Do not silently regenerate existing approved cards.

## Extensibility boundary

- [ ] Keep Style Studio's trial, compare, lock, history, and activation flow
  independent of `amiga-ocs`.
- [ ] Use driver-provided label, preview/target assets, output description,
  validation, and editor descriptors for engine-specific controls.
- [ ] Confirm in a contract test that a minimal fake renderer can participate in
  draft validation and a style trial without edits to trial/approval stores.
- [ ] Do not ship a user-visible “New style family” button, alternate engine,
  generic node graph, 8-bit presets, ASCII renderer, or plugin marketplace now.
  Future families should be code-registered and separately proven first.

## Tests and acceptance

- [ ] Add store/API tests for draft derivation, ordered reference edits, target
  exclusion, calibration persistence, trial completeness, checksum drift,
  immutable lock, activation, rollback, and incomplete/failed trial rejection.
- [ ] Add UI tests for entering from the style chip, active-versus-draft clarity,
  field validation, reference limit, trial progress, aligned final-card compare,
  activation, and no implicit production regeneration.
- [ ] Add a fake-adapter integrated trial test proving the same master produces
  the same Amiga art/card in Style Studio and production.
- [ ] Verify a changed dither/palette/framing value changes the draft style
  checksum and final output while leaving the active version and its cards
  byte-identical until activation.
- [ ] Ensure target examples are visible but absent from every captured provider
  payload.
- [ ] Run Python tests, `npm test -- --run`, `npm run build`, and
  `git diff --check` before marking this plan complete.
