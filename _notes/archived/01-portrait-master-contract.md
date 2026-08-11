# 01 — Preserve a reusable portrait master

## Outcome

An approved master retains enough clean art around the character to support the
standard-bust, tall-silhouette, and wide-torso card archetypes. It is no longer
created by blindly copying the tightly cropped `*-final.png` output.

## Scope

- Keep `masters.json` and the existing master-promotion/card-render interfaces.
- Treat the current 128px final image as a review derivative, not the preferred
  master source.
- Keep this file-based and Pillow-based. Do not introduce a new model or an
  image database.

## Checklist

- [x] Define the master source policy: preferred candidate source, fallback
  source, target size, and acceptable text/background rules.
- [x] Add explicit candidate source choices to promotion: raw generation,
  clean master derivative, or legacy final crop.
- [x] Add `master_source_kind`, original dimensions, and source crop bounds to
  master provenance.
- [x] Make the deterministic master derivative preserve aspect ratio and its
  full usable canvas; do not call `ImageOps.fit` during master creation.
- [x] Add a lightweight rejection reason for candidates with generated text,
  inadequate headroom, or a clipped silhouette.
- [x] Add editable/visible head box, shoulder line, and silhouette bounds to
  the Cards workbench, alongside the existing face anchor.
- [x] Overlay the saved composition geometry on the selected master in the UI.
- [x] Update card crop logic to use the whole composition record, not only the
  face anchor plus a fixed bias.
- [x] Render the three archetypes from at least three masters and compare their
  framing in the Cards grid.
- [x] Add unit tests for non-destructive master preparation and predictable
  archetype crop transforms.

## Acceptance checks

- [x] A master can yield visibly distinct and intentional standard, tall, and
  wide renders without regeneration.
- [x] Promoting a master cannot silently discard source pixels through a fixed
  square crop.
- [x] Each selected master has a reviewable composition record and provenance.

## Decision needed before work

Decide the preferred master source for the initial experiment. Start with a
full-canvas, post-processed derivative of a raw candidate only if it is free of
generated labels; otherwise retain the current final as a documented fallback.
