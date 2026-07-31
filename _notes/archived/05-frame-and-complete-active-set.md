# 05 — Frame and complete one active coherent set

## Outcome

Make Frames and Completed operate on the active set instead of arbitrary run
items. Completed becomes a coherent set view tied to one locked generative
finish, while older sets and pre-set cards remain available as history.

## Decisions

- A ready set supplies every working card source. New cards are keyed by
  `set_item_id`, not by an arbitrary run item.
- Bust/Tall/Torso remains the composition question.
- Painterly/Estate Pixel remains the deterministic **Treatment** question and
  is never labelled Finish.
- Keep/discard/reconsider changes card review state only. Set membership,
  finish provenance, and art-source provenance remain immutable.
- Completed defaults strictly to kept cards from `active_set_id`.

## Checklist

- [x] Change card creation to accept a set item, validate that the parent set is
  ready, and persist `set_id`, `set_item_id`, and `finish_id` alongside the
  complete source provenance.
- [x] Enforce at most one non-discarded card per set item. Reopening or
  re-sending returns the existing working/kept card; a discarded item may start
  a new draft with explicit lineage.
- [x] Create or expose working drafts for all active-set items when entering
  Frames so the user does not manually send portraits one by one from Set.
- [x] Filter the Frames candidate list to the active set and show progress as
  working, kept, and discarded counts against total set items.
- [x] Preserve exact deterministic preview caching and byte-identical selected
  renders while adding finish/set IDs to the cache/provenance inputs where
  needed.
- [x] Rename every current UI/documentation use of card `finish` to
  `Treatment`; retain the stored `treatment` and `treatment_version` fields.
- [x] Make Completed identify the active set and locked finish, show only its
  kept cards by default, and preserve ordered source membership.
- [x] Add an active-set switcher/history entry point. Switching sets updates
  Frames and Completed without changing cards or deleting renders.
- [x] Place old cards without set provenance in a clearly labelled **Legacy
  cards** history section. Never mix them into the active Completed grid.
- [x] Keep direct PNG downloads, provenance, reconsider, keep, and discard
  behavior working within the active set.
- [x] Add backend tests for set-item validation, deduplication, immutable
  provenance, active-set filtering, reconsider, discarded lineage, and legacy
  reads.
- [x] Add UI tests for automatic active-set drafts, treatment terminology,
  frame selection, keep/discard progression, Completed filtering, set
  switching, legacy history, downloads, and refresh.

## Acceptance checks

- [x] Frames cannot create a new primary-flow card from an exploration or
  finish run item directly.
- [x] Every active Completed card traces to one set item and the same locked
  finish as the active set.
- [x] Historical and legacy cards remain accessible but never appear mixed
  into the current Completed set.
- [x] Reconsidering a card cannot detach it from or move it between sets.
- [x] `uv run pytest`, `npm test`, and `npm run build` pass.

## Out of scope

- Enforcing one deterministic Treatment across the set; Finish coherence is
  generative in this iteration.
- Production approval, bulk export, print layout, or deleting old sets.
