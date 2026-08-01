# 02 — Build card production and approval

## Outcome

Replace Explore → candidate selection → Finish → Build Set → Frames with one
production operation. A batch applies the active style pipeline to selected
sources and does not report an item ready until its final Amiga card exists.

## Production records

- [x] Extend the existing immutable run infrastructure rather than adding an
  unrelated queue. Add explicit `card-production` and `style-trial` purposes and
  stop using missing purpose values for new records.
- [x] Snapshot the exact source membership/order and locked style version at
  batch creation. Changing source selection or active style later cannot mutate
  the batch.
- [x] Default a new production batch to one generation attempt per selected
  source. Record a stable attempt number and lineage for later **Try another**
  actions.
- [x] Give each item explicit stage/status values covering queued, generating,
  processing, ready, failed, and interrupted. A generated master without final
  art/card is not complete or approvable.
- [x] For each successful provider result, atomically save the master and run it
  through the style's renderer/assembler in the same worker operation. Persist
  the full render bundle and checksums before setting the item to ready.
- [x] Snapshot resolved generation instruction, identity and reference mapping,
  model capabilities, provider endpoint, seed if effective, usage, cost, style
  checksum, render metadata, and elapsed generation/processing times.
- [x] Keep exact returned provider usage/cost as the source of truth. Display
  unknown cost as unknown rather than zero.

## Generation and failure behavior

- [x] Reuse the current model discovery, capability validation, identity-first
  request mapping, one-active-run protection, background execution, polling,
  and atomic writes.
- [x] Validate the complete style request and exact paid call count before batch
  creation. Never silently truncate generation references.
- [x] Do not start a batch when no source is selected, no locked active style
  exists, the model is unavailable, references exceed the endpoint limit, or
  another paid run is active.
- [x] Let a partial batch finish with ready and failed items side by side.
  **Retry failed** creates attempts only for failed/interrupted sources and
  never replaces successful artifacts or approvals.
- [x] Implement **Try another** as one new immutable generation attempt for one
  source using the batch's style snapshot, even if a different style is now
  active. A clearly separate action may start that source under the new style.
- [x] Make simulation output pass through the real registered renderer so tests
  and local UX exercise the complete pipeline.

## Framing without a Frames stage

- [x] Store the style's default centering/framing on every attempt and render it
  automatically.
- [x] Support an optional per-attempt framing override using the existing
  normalized cover transform conventions where possible.
- [x] Rerender art and card from the immutable master when framing changes.
  Do not call the generation adapter and do not present painterly/pixel
  treatments or Bust/Tall/Torso as required choices.
- [x] Clamp framing so the art window has no empty pixels, write outputs
  atomically, and preserve previous render revisions for provenance/recovery.
- [x] Make reset-to-style-default available and deterministic.

## Approval model

- [x] Allow only a ready final card to be approved. Approval records source ID,
  attempt ID, batch ID, locked style version/checksum, card checksum, timestamp,
  and current render revision.
- [x] Maintain at most one current approval per source and style version while
  keeping replaced approvals as immutable history.
- [x] Approving another attempt for the same source/style supersedes the current
  pointer; it does not delete either card.
- [x] A framing change to an approved card creates a render revision and requires
  an explicit approval of that revision; do not let the approved checksum drift.
- [x] Report batch progress as selected sources, ready cards, approved cards,
  failed sources, and paid calls. “All approved” means every source in that
  batch has a current approval for the batch's style version.
- [x] Provide individual PNG download plus one deterministic ZIP/download bundle
  for current approvals in source order. Include a JSON manifest with checksums
  and provenance; do not include raw masters unless explicitly requested in a
  diagnostic export.

## Minimal API surface

- [x] Define typed API payloads for style bootstrap, production batch create,
  batch detail/progress, one-source retry, one-source new attempt, framing
  rerender, approve/supersede, and approved bundle download.
- [x] Keep normal create payloads small: selected source IDs and the active
  locked style ID are enough. The server resolves all style settings.
- [x] Return final card/art URLs directly on ready items. Put master URLs,
  provider mapping, raw config, and checksums in an explicit details object.
- [x] Reject client attempts to override a locked pipeline through production
  endpoints. Style changes belong to a draft and Style Studio trial.
- [x] Ensure asset URLs reject absolute paths and traversal as the current store
  does.

## Compatibility and tests

- [x] Read old runs, finishes, sets, and cards without rewriting them. Mark them
  as legacy in API history and exclude them from current-style approval counts.
- [x] Do not use locked Finish outputs as production style references in the new
  path. The active style version owns its reference pack directly.
- [x] Add backend integration tests for selected sources → production batch →
  generating → processing → final cards → approvals → ordered download bundle.
- [x] Add tests for exact reference order, style snapshots, one attempt per
  source, no implicit paid calls, partial failure/retry, interruption, duplicate
  approval, supersession, and checksum drift.
- [x] Add a spy-adapter test proving framing rerender makes zero generation
  calls.
- [x] Add an end-to-end fixture whose adapter returns the checked-in generation
  reference and whose ready output matches the checked-in Amiga target.
- [x] Confirm all successful production cards are 420×600, all art is 336×276,
  and every reported palette/render invariant comes from the locked style.
- [x] Run the relevant Python tests and `git diff --check` before marking this
  plan complete.
