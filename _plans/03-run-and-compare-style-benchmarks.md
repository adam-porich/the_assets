# 03 — Run and compare whole-sheet style benchmarks

## Outcome

Run one recipe over the fixed benchmark from the Style Lab, show progress in
the browser, and judge the completed images as a coherent sheet. Make recipe
iteration empirical: duplicate a recipe, change one variable, run it over the
same source order, and compare the two sheets source-for-source.

This is an in-process experimental runner, not a durable production queue.
Persist enough status to explain interrupted work, but do not add Redis,
workers, retries, scheduling, or concurrency controls beyond a small fixed
limit.

## Run contract

Store each run independently:

```text
portrait-library/runs/<run-id>/
  run.json
  inputs/sources/
  inputs/references/
  <item-id>.png
  thumbnails/<item-id>.jpg
```

`run.json` contains:

- Opaque run ID, timestamps, and `queued`, `running`, `complete`, `failed`, or
  `interrupted` status.
- An immutable snapshot of the recipe, resolved prompt, selected reference
  checksums/order, benchmark source IDs/order, model, requested/effective
  aspect ratio, and effective backend capabilities.
- One item per source/output with status, opaque item ID, seed, elapsed time,
  output path, dimensions, and an error when applicable.
- A sheet verdict of `unreviewed`, `coherent`, `mixed`, or `not-useful`, plus a
  short run note.
- Optional per-item failure tags for diagnosis. These are not favourites and
  must remain secondary to the sheet verdict.

Snapshot the exact identity and reference input files into the run directory
with checksums. Prefer hard links when the files are on the same filesystem and
fall back to copies. This keeps old comparisons inspectable after the live
benchmark or recipe changes without introducing a global asset-lifecycle
system.

Write the run record after every item so polling and service restarts show the
last known state. On startup, mark a stale `queued` or `running` run as
`interrupted` and offer “Run again”; do not silently resume paid requests.

## Generation rules

- The internal request type must have separate `identity_image` and
  `style_images` fields. Do not represent all references as one unlabelled list
  until the final backend adapter boundary.
- Resolve art-direction sections in a stable labelled order. If the backend
  lacks a native negative prompt, append the recipe’s avoid text as an explicit
  “Avoid” instruction and record that mapping.
- Derive the requested ratio from the 336×276 art window (28:23). Negotiate the
  closest supported landscape ratio for the selected model, then record and
  display both requested and effective values. Never hard-code `1:1`.
- Preserve the full source while preparing the identity input. If the existing
  neutral-background preparation is retained, show that exact prepared input
  in result details and store its path in run provenance.
- Send references in their curated order. If the backend has no role-aware
  reference API, put identity first, style references after it, and make their
  meanings explicit in the resolved instruction. Record this as an adapter
  limitation rather than claiming role support.
- Validate model reference limits before starting. Show an actionable
  preflight error if identity plus the chosen pack exceeds the model limit; do
  not silently truncate the pack.
- Save the returned painterly image as the candidate used downstream. Do not
  quantize, pixelise, palette-reduce, or create `raw`, `clean`, and `final`
  choices. UI thumbnails must not replace the full generated file.

## Checklist

- [ ] Refactor the OpenRouter integration behind a small generation adapter
  with explicit capabilities: reference roles, maximum reference count, seed,
  aspect ratios, quality, and negative-prompt support.
- [ ] Add a fake adapter for deterministic tests. No automated test should
  make a paid or network generation call.
- [ ] Reuse Plan 02's recipe resolver and implement identity/style input
  separation, aspect negotiation, preflight validation, and complete resolved
  provenance around it.
- [ ] Implement a single in-process queue with a bounded worker count of one by
  default. Protect run-record writes and make the worker report progress after
  each result.
- [ ] Add `POST /api/runs`, `GET /api/runs`, `GET /api/runs/<id>`, and a small
  run-review update operation. Creation snapshots the current recipe,
  references, benchmark metadata, and exact input image files; later workspace
  edits cannot alter the run.
- [ ] Let the user choose one or two outputs per source, defaulting to one.
  Before starting, show model, source count, output count, reference count, and
  total image calls on the Run button/confirmation surface.
- [ ] Add the run view inside Style Lab. Show a stable source-ordered contact
  sheet, one progress/error cell per expected output, elapsed progress, and a
  clear partial-failure state. Poll only while a run is active.
- [ ] Make the full sheet the dominant evaluation surface. Put the question
  “Do these look like illustrations commissioned for the same set?” above the
  `Coherent`, `Mixed`, and `Not useful` actions.
- [ ] Keep per-image details behind a click/drawer. Show source, exact identity
  input, output, dimensions, model, seed, effective ratio, reference pack,
  resolved instruction, and optional failure tags such as identity drift,
  composition, palette, text, or style outlier.
- [ ] Add run history ordered newest first with recipe name, completion state,
  source count, verdict, and timestamp. Do not create a separate global
  Generations tab.
- [ ] Add a compare action for any two completed runs over the same benchmark.
  Render rows by source and columns by run, include a concise recipe-field
  diff, and warn clearly when source sets/order differ.
- [ ] Add “Duplicate recipe from this run” using the immutable recipe snapshot,
  so old experiments can be reproduced after the live recipe changes.
- [ ] Add “Use this portrait” to completed item details. It should hand the run
  item ID to Plan 04; until then it may show a clear Card Workbench pending
  state rather than invoking the old master flow.
- [ ] Add tests for recipe resolution, unsupported controls, reference-limit
  failure, requested/effective ratios, identity-first adapter mapping, run
  snapshots, progress persistence, interrupted runs, partial failures, verdict
  updates, and comparison alignment.
- [ ] Add UI tests for run preflight, progress polling, whole-sheet review,
  result details, recipe duplication, and compare warnings.

## Acceptance checks

- [ ] A one-source fake-adapter smoke run completes entirely through the UI and
  produces a persisted, refreshable result.
- [ ] A 6–10 source run renders in fixed source order and can be judged with one
  sheet-level verdict.
- [ ] Comparing two runs aligns the same people row-by-row and makes the changed
  recipe fields obvious.
- [ ] Every output records the exact recipe snapshot, full reference pack,
  source input, model mapping, seed, and effective landscape ratio.
- [ ] The full-resolution candidate is painterly and has no automatic 128px or
  32-colour post-process.
- [ ] The UI never promises unsupported negative prompts, role-aware
  references, dimensions, or reference counts.
- [ ] Python tests, UI tests, and `npm run build` pass.

## Out of scope

- Automatic aesthetic scoring, palette enforcement, identity recognition, or
  deciding that a recipe is production-ready.
- Distributed workers, billing controls, resumable queues, bulk export, and
  scheduled generation.
- Pixel-art treatment. Revisit it only after painterly sheets are consistently
  coherent.
