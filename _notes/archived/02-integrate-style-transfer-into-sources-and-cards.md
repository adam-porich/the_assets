# 02 — Integrate style transfer into Sources and Cards

## Sources

- [x] Preserve the current source selection grid and primary **Make cards**
  action.
- [x] Show that the active style uses live image generation, including the
  model, number of calls, and available cost, before the action is enabled.
- [x] Use concise supporting copy that explains each source will be redrawn as
  a neutral Amiga portrait before card assembly.
- [x] Block production with a specific actionable message when the active style
  is simulation-only, unavailable, over its reference limit, or missing its
  provider credentials.
- [x] Keep the paid-generation confirmation proportional to the batch and do
  not add another setup step to the normal flow.

## Cards

- [x] Keep finished cards first and preserve the current grid, approval,
  retry, **Try another**, framing, and download interactions.
- [x] Use the existing generating/processing states to make the two phases
  understandable: first redrawing the neutral portrait, then applying Amiga
  rendering and card assembly.
- [x] In **How this was made**, show source, canonical master, 336×276 Amiga
  art, model/mode, generation reference, style checksum, and render revision.
- [x] Keep those details collapsed by default; do not make users approve the
  master separately.
- [x] Ensure **Try another** creates a fresh generative master, while framing
  adjustments continue to reuse the current master without a paid call.

## Style Studio

- [x] Add a clear live/simulation selector and capability-backed model selector
  while preserving the current Style Studio layout and visual language.
- [x] Present the high-resolution generation reference beside its rendered
  Amiga target so the before/after house-style contract is obvious.
- [x] Expose the effective neutralisation direction in editable groups:
  identity to retain, composition to normalize, expression/pose to discard,
  rendering language, and avoid instructions.
- [x] Keep generation references ordered and target examples review-only.
- [x] Run draft trials through the complete source → master → Amiga art → card
  path and compare their final cards with the active style.
- [x] Allow activation only after a complete live cohort trial still matches
  the draft checksum; simulation trials may validate mechanics but cannot
  qualify a production style.

## UI tests

- [x] Test live model selection, execution-mode changes, unavailable-model and
  missing-key messages, call counts, and paid-action confirmation.
- [x] Test that a normal production click invokes the active live style and
  navigates directly to Cards.
- [x] Test phase-specific progress, collapsed artifact provenance, generative
  **Try another**, and generation-free framing.
- [x] Test that simulation output is unmistakably labelled as a preview and
  cannot be activated for production by accident.
