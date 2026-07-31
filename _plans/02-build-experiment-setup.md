# 02 — Build experiment setup in the Style Lab

## Outcome

Let a user configure the complete input to a style experiment in the browser:
find or upload source portraits, fix a 6–10 image benchmark, curate an ordered
style-reference pack, and edit a named generation recipe. There are no
favourites and no standalone Source, Style, or Prompt screens.

This plan uses the version 1 workspace from Plan 01. It should end with a useful
setup tool even before generation is connected in Plan 03.

## Style Lab layout

Use one responsive page with three visually connected areas:

1. A persistent benchmark strip showing the selected sources in evaluation
   order.
2. A recipe panel containing art-direction fields, model/quality, aspect
   policy, and the selected reference pack.
3. A main experiment area which shows setup guidance now and becomes the run
   sheet in Plan 03.

Source search/import and reference management should open in drawers or inline
panels from this page. They are supporting actions, not application tabs.

## Recipe contract

Store artist-facing concepts, not a backend request payload:

```json
{
  "recipe_id": "opaque-id",
  "name": "Estate painterly study 01",
  "model": "provider/model",
  "quality": "low",
  "direction": {
    "medium_brushwork": "...",
    "lighting": "...",
    "background": "...",
    "composition": "...",
    "colour": "...",
    "detail": "...",
    "identity": "..."
  },
  "avoid": "...",
  "aspect_policy": "card-window",
  "reference_ids": [],
  "created_at": "...",
  "updated_at": "..."
}
```

`card-window` means “derive the requested composition from the current card
template art window.” It is not a promise that every model accepts the exact
ratio. Plan 03 records and displays the closest effective backend value.

Seed one editable recipe definition in code with concrete, restrained guidance
for medium, brushwork, lighting, background, composition, colour, detail, and
identity retention. Avoid vague phrases such as only “MTG card art.” Do not
seed or retain any of the existing style images.

## Checklist

- [ ] Add visual Pexels search to the Style Lab. Return result thumbnails and
  provenance before download, let the user choose individual results, and add
  only those chosen images to the workspace.
- [ ] Add local image upload as a source fallback so the primary workflow is
  usable without a Pexels key. Validate content type and image decoding, choose
  a safe service-generated filename, and retain the original filename only as
  metadata.
- [ ] Show all imported sources in a compact picker with source preview and
  provenance details. The only primary source action is add/remove from the
  benchmark; deletion is an explicit secondary action with confirmation.
- [ ] Persist benchmark membership and ordering in
  `benchmark_source_ids`. Support drag/reorder or simple move-left/move-right
  controls, and show “6–10 recommended” without blocking a cheaper smoke test.
- [ ] Add reference-image upload, preview, label editing, ordering, and
  deletion. Display “4–6 consistent references recommended” and the exact
  count passed to the recipe; do not generate reference images in this flow.
- [ ] Prevent deleting a source/reference file while it is still referenced,
  or remove the reference atomically after an explicit confirmation. Never
  leave dangling workspace IDs.
- [ ] Build the recipe editor from the contract above. Use plain art-direction
  labels and short help text explaining what visual decision each field
  controls.
- [ ] Add recipe create, rename, duplicate, update, and select actions. Recipe
  duplication must copy values and reference ordering into a new opaque ID so
  an experiment can change one variable without overwriting its baseline.
- [ ] Add one backend-neutral `resolve_recipe_instruction` helper and use it to
  show a read-only “resolved instruction preview” below the editor. This is an
  understandable concatenation of the art-direction sections and avoid text,
  not JSON and not the OpenRouter payload. Plan 03 must reuse this helper.
- [ ] Fetch the current image-capable model list through the backend, cache a
  small fallback list for offline UI rendering, and show only model and quality
  here. Do not expose strength, steps, guidance, width, height, seed, or input
  reference URLs as recipe controls.
- [ ] Add resource-style API operations for sources, benchmark ordering,
  references, and recipes. Return the refreshed workspace object after each
  mutation so client and server state cannot drift.
- [ ] Provide visible pending, success, validation, missing-key, and empty
  states for search, upload, deletion, and save. Do not use `window.prompt()` or
  browser alerts.
- [ ] Add backend tests for Pexels selection, generic upload, invalid uploads,
  reference ordering, recipe duplication, and referential integrity.
- [ ] Add focused UI tests for empty setup, benchmark membership, reference
  ordering, recipe editing, and failure feedback. Keep the test dependencies
  small; use the existing Vitest/jsdom setup where possible.

## Acceptance checks

- [ ] From an empty workspace, a user can assemble and reorder a benchmark
  using either Pexels search or local uploads without opening a terminal.
- [ ] A user can curate an ordered reference pack and understand exactly which
  images the next recipe will use.
- [ ] A user can duplicate a recipe, change one art-direction field, refresh,
  and see both versions intact.
- [ ] The Style Lab recommends 6–10 benchmark sources and 4–6 references but
  permits a one-source smoke test.
- [ ] The active screen contains no favourite/reject workflow, generated style
  gallery, preset picker, or raw prompt tab.
- [ ] Python tests, UI tests, and `npm run build` pass.

## Out of scope

- Calling an image model, background jobs, generated-result review, and run
  comparison.
- Deciding the final artistic reference pack. The software must support real
  curation without blocking completion on that subjective choice.
- Automatic source-quality, identity, or licensing approval. Continue to show
  provenance and the existing experimental-use warning.
