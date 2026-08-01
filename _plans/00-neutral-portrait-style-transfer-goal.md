# 00 — Restore neutral portrait style transfer

## Goal

- [ ] Keep the normal product path as **Sources → Cards**.
- [ ] Make every selected source pass through a real image-generation step
  before deterministic Amiga rendering and card assembly.
- [ ] Treat the source as identity evidence, not as a pose, expression,
  lighting, background, or photographic-composition template.
- [ ] Produce a canonical neutral portrait master with the same visual intent
  as `generation-reference-01.png`: frontal head-and-shoulders composition,
  calm expression, direct gaze, broad connected tonal planes, restrained
  background, and no narrative action.
- [ ] Render that master through the existing Amiga OCS driver so the 336×276
  art resembles `target-example-01.png`, then assemble the card.
- [ ] Keep the generated master and Amiga art as inspectable provenance; keep
  the finished card as the everyday review and approval object.

## Pipeline contract

- [ ] Make the production order explicit and executable:

  ```text
  source image
    → generative neutralisation/style transfer
    → immutable canonical portrait master
    → deterministic Amiga OCS render
    → 336×276 Amiga art
    → card assembly
    → 420×600 finished card
  ```

- [ ] Use `generation-reference-01.png` as the generation-stage style and
  composition reference.
- [ ] Use `target-example-01.png` only as the expected post-render appearance
  and review/golden-test target; never send it to the generation provider.
- [ ] Preserve recognizable facial structure, apparent age, hair silhouette,
  and distinguishing features while deliberately reducing source-specific
  pose, expression, gesture, camera perspective, scene, and mood.
- [ ] Do not promise exact identity preservation: the stage is intentionally
  interpretive, and reviewers approve the final card rather than a biometric
  likeness.

## Product decisions

- [ ] Do not add a mandatory intermediate workflow page or approval gate.
- [ ] Do not allow production to silently use the deterministic simulation as
  if it were generated art.
- [ ] Keep simulation available for free engineering tests, visibly labelled
  as a non-generative preview only.
- [ ] Require an explicit user action before paid generation and show the
  selected live model, call count, and estimated/known cost.
- [ ] Keep one generation attempt per source by default; **Try another** makes
  a new immutable neutral master and card for that source.
- [ ] Keep framing changes deterministic and free: they rerender the selected
  master without another generation call.

## Definition of done

- [ ] A fresh configured workspace can select sources and produce cards using
  a live img2img-capable model through the normal Sources action.
- [ ] The produced masters visibly converge on the neutral reference pose and
  treatment instead of copying arbitrary source pose and emotion.
- [ ] Every final card is traceable to its source, generation request,
  generated master, Amiga render, and style version.
- [ ] The current Sources/Cards UI remains the primary workflow and retains its
  present visual design.
- [ ] Automated tests, a small visual cohort, documentation, plan archival,
  commit, and push are complete.
