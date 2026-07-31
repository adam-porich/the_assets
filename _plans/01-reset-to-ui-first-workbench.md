# 01 — Reset to a UI-first portrait workbench

## Outcome

Replace the current review-oriented data model and five-tab application with a
small foundation for two browser-visible activities:

1. **Style Lab** — assemble a fixed source benchmark, define a generation
   recipe, run it, and compare the resulting sheet.
2. **Card Workbench** — take one result into a card and adjust its framing
   directly.

This is an exploratory tool. It does not need migration, backwards
compatibility, production approvals, sets, accounts, a database, or a job
orchestration service.

Implement the plans in numeric order. Plans 02–04 build on the contracts in
this file; Plan 05 removes the old implementation after its replacement is
working.

## Decisions already made

- Keep React/Vite, the Python HTTP service, Pillow rendering, Pexels source
  provenance, OpenRouter generation, and the existing card template concept.
- Use one ignored, file-backed workspace at `portrait-library/`.
- Treat the existing contents of `portrait-library/` and all tracked files in
  `portrait-review/` as disposable. The user has explicitly approved this
  reset; do not migrate them.
- Do not expose internal IDs, manifests, file variants, portrait masters,
  anchors, review states, or generation payload details in the normal path.
- Do not build a replacement static lookbook or CLI workflow. The browser is
  the product surface for this experiment.
- Save painterly generation output without pixelisation or palette reduction.
  Thumbnail creation may resize non-destructively for display.

## Workspace contract

Create this structure lazily when the service first starts:

```text
portrait-library/
  workspace.json
  sources/
  references/
  prepared/
  runs/
  cards/
```

`workspace.json` is version 1 and contains only small metadata:

```json
{
  "version": 1,
  "sources": [],
  "benchmark_source_ids": [],
  "references": [],
  "recipes": [],
  "active_recipe_id": null
}
```

- A source stores an opaque service-generated ID, label, relative image path,
  dimensions, creation time, and a provenance object. Pexels-specific fields
  belong inside provenance; local uploads use `{ "kind": "upload" }`.
- A style reference stores an opaque ID, label, relative image path, checksum,
  and display position.
- A recipe stores an opaque ID, readable name, model, quality, structured art
  direction, avoid text, aspect policy, ordered reference IDs, and timestamps.
- Run records and card drafts are added in later plans under their own
  directories. Do not grow `workspace.json` into an image or result database.
- All stored paths are relative to `portrait-library/`; API payloads provide
  safe asset URLs separately.

Use atomic JSON writes (temporary sibling followed by `Path.replace`) and a
process-local lock around workspace mutations. Invalid or missing files should
produce an actionable API error, not a partially reset workspace.

## Checklist

- [ ] Confirm the repository root and the exact `portrait-library/` and
  `portrait-review/` targets, then remove their current generated/tracked
  contents. Do not remove any broader directory.
- [ ] Remove `portrait-review/` from the durable-data design and keep all new
  workspace images and metadata under the already ignored
  `portrait-library/` path.
- [ ] Add a focused workspace store module rather than extending
  `manifest.py` or the current review tree. Include schema validation, atomic
  reads/writes, opaque ID generation, safe relative-path handling, and an
  empty-workspace bootstrap.
- [ ] Split the HTTP layer out of the current 700-line review server so route
  parsing, JSON responses, asset serving, and workspace operations are not in
  one file. The server may remain based on the Python standard library.
- [ ] Add `GET /api/workspace` returning the complete small setup state plus
  safe URLs and summary links for runs/cards. Do not make the client issue ten
  startup requests to reconstruct one screen.
- [ ] Serve only files below `portrait-library/` through `/asset/...`; resolve
  and verify the target remains under that root before reading it.
- [ ] Replace the monolithic `App.tsx` with a thin application shell, shared
  API/types modules, and separate view/component files. Do not add a state
  management or routing dependency.
- [ ] Make the default view **Style Lab**. Use simple hash or query-string
  navigation so a run or card can be refreshed and reopened without React
  Router.
- [ ] Remove the Source, Style, Prompt, Generations, and Cards tab bar. The new
  shell should contain a clear workspace title, Style Lab home link, a
  secondary link to saved card drafts, global operation/error feedback, and
  the current view.
- [ ] Implement the empty state in the real UI: explain that sources,
  references, and a recipe are needed, and link to the controls delivered in
  Plan 02. It must not refer the user to a CLI command or JSON file.
- [ ] Add store and API tests using a temporary workspace, including first
  start, atomic mutation, rejected path traversal, missing assets, and stable
  serialization.
- [ ] Keep `uv run python -m tools.portraits review-server` working until Plan
  05 renames or trims the command, and make `npm run build` pass after the new
  shell lands.

## Acceptance checks

- [ ] Starting with no `portrait-library/` creates a valid empty workspace and
  loads a useful Style Lab screen.
- [ ] Refreshing the browser uses one workspace bootstrap request and preserves
  the selected view in the URL.
- [ ] No tracked favourite, review, or style image remains in
  `portrait-review/`.
- [ ] The normal UI contains none of: master ID, raw/clean/final, face anchor,
  head box, shoulder line, silhouette box, set ID, or approval state.
- [ ] Python tests and the TypeScript/Vite build pass.

## Out of scope

- Generation, benchmark execution, run comparison, and card manipulation.
- Final removal of old endpoints and modules; keep them unreachable from the
  new UI until Plan 05 deletes them.
- Authentication, multi-user locking, remote storage, migrations, and recovery
  of the discarded assets.
