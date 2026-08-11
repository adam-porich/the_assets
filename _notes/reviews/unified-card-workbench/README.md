# Unified card workbench review

This review set exercises the integrated application path with the checked-in
Amiga generation reference and the existing local source library. No paid
provider call was made; the production screenshots use the deterministic
simulation adapter.

Screens:

- [Sources](screens/sources.png) — selected source library, active-style chip,
  exact call count, and the single Make cards action.
- [Cards in progress](screens/cards-in-progress.png) — live queued/processing
  slots with final-card-first layout and collapsed provenance.
- [Ready and approved Cards](screens/cards.png) — 420×600 final card, approval
  progress, and ordered download action.
- [Style Studio](screens/style.png) — active version, palette, generation
  reference, review-only target example, and draft entry point.
- [Amiga pipeline sheet](amiga-ocs-v1-pipeline-sheet.png) — the same registered
  renderer applied to the stage reference and six existing painterly masters.
- [Amiga card set](amiga-ocs-v1-card-set.png) — final-card output comparison.

The ready-card screenshot was produced from a local simulation batch and one
explicit approval. The in-progress screen was captured while an eight-source
simulation batch had one item in processing and the remaining items queued.
The API response and batch files are intentionally not included in this review
directory; they remain ignored workspace data.

The stage-reference output is pixel-identical to
`tools/cards/assets/amiga-ocs-portrait-v1/target-example-01.png`. The other
six rows are a visual consistency check over existing source outputs; their
input files are local ignored workspace artifacts, not committed test data.
