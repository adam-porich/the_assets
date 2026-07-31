# 03 — Iterate and lock finish cohorts

## Outcome

Make Finish a first-class visual review stage. Each trial applies one proposed
finish to every selected candidate, produces exactly one output per candidate,
and is accepted or rejected as a complete cohort.

## Finish trial contract

- A trial is an immutable run with `purpose: finish` and one item for each
  selected candidate in selection order.
- Each candidate output becomes the identity input for its trial item. The
  trial snapshots the candidate file/checksum and the inherited ordered style
  references.
- The finish draft starts from the selected candidates' exploration recipe.
  If candidates span recipes, initialize from the first selected candidate and
  show the differing provenance rather than merging recipes implicitly.
- The visible Finish controls are a plain-language finish change note, ordered
  references, model, quality, and advanced structured direction. One trial
  always requests one image per candidate.
- Only a fully complete trial may be locked. Locking creates an immutable,
  versioned finish record; later edits create another trial/finish.

## Checklist

- [ ] Extend run creation so finish inputs can be immutable generated artifacts
  as well as workspace source files, without pretending they are source IDs.
- [ ] Add `POST /api/finish-trials` with selection revision and complete visible
  recipe draft. Reuse model discovery, reference-limit validation, single-run
  concurrency, progress persistence, interruption handling, usage, and cost.
- [ ] Snapshot candidate inputs beneath the trial directory and record their
  originating run item, workspace source, checksum, and role.
- [ ] Resolve finish prompts in a stable order and clearly distinguish the new
  requested finish change from inherited art direction.
- [ ] Add Finish-stage setup showing the selected candidate images, inherited
  references, editable finish direction, exact call count, and validation.
- [ ] Render trial history as candidate-aligned cohort sheets. Put the whole
  cohort comparison first and per-image provenance/cost behind details.
- [ ] Support side-by-side comparison of any two complete trials derived from
  the same selection revision, aligned by candidate.
- [ ] Add **Lock this finish** to complete trials. The server must verify every
  expected item is complete and its output checksum still matches before
  atomically creating the finish record.
- [ ] Show the locked finish's version, anchor outputs, direction summary,
  references, model, cost, and immutable status. Do not expose an edit action
  on a locked finish.
- [ ] When the user changes candidate selection, show older trials and locks as
  history but require a new trial for the new revision.
- [ ] Add fake-adapter backend tests for generated-artifact inputs, identity-
  first mapping, snapshots, exact item count/order, partial failure,
  interruption, comparison alignment, lock validation, and immutability.
- [ ] Add UI tests for draft initialization, trial launch/progress, cohort
  comparison, partial failure, locking, refresh, and new-version iteration.

## Acceptance checks

- [ ] A 1–3 candidate selection can produce repeated finish trials with exactly
  one result per candidate.
- [ ] The user can compare trials as coherent cohorts and lock only one complete
  trial at a time.
- [ ] Every finish can be traced to exact candidate files, source portraits,
  recipe/reference snapshots, model mapping, checksums, usage, and cost.
- [ ] No item-level mixing action can create a finish.
- [ ] `uv run pytest`, `npm test`, and `npm run build` pass.

## Out of scope

- Generating the remaining project sources.
- Automatic aesthetic or identity scoring.
- Treating Painterly/Estate Pixel as a finish choice.
