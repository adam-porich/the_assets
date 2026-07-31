# 05 — Remove the legacy workflow and finish the vertical slice

## Outcome

Leave one coherent, documented application for exploring portrait style and
card framing. Delete the superseded review pipeline instead of carrying
compatibility code, tracked experiments, dead endpoints, or duplicate CLI
paths.

Run this plan only after Plans 01–04 pass their acceptance checks. Removal is
part of the requested clean reset; the old favourites and generated images do
not need preservation.

## Intended final path

```text
Open Style Lab
→ find/upload and fix 6–10 benchmark sources
→ upload/order 4–6 curated style references
→ edit or duplicate an art-direction recipe
→ run the complete benchmark
→ judge/compare the whole sheet
→ choose one result
→ drag/zoom it in a card
→ keep the experimental card
```

Starting the two local services is the only terminal-only requirement. Every
art-direction and review action above must be visible and usable in the web UI.

## Checklist

- [ ] Trace every frontend request and keep only the workspace, model, source,
  reference, recipe, run, asset, and card-draft routes used by the new views.
- [ ] Delete old review endpoints and helpers for review status, selection,
  favourite copying, style-image generation, preset listing, global generation
  listing, master promotion/composition, card approval/validation, set
  creation, and set validation.
- [ ] Delete all old React types, state, handlers, components, and CSS for the
  five tabs, favourite/trash review states, generated style gallery, prompt
  cards, global generations, masters, geometry forms, approvals, validation,
  and sets.
- [ ] Remove the old master/set pipeline from `tools/cards/pipeline.py`, leaving
  only the template loading and direct card-draft renderer implemented in Plan
  04. Rename/split the module if that makes its remaining purpose clearer.
- [ ] Remove candidate post-processing and manifest fields for `raw`, `clean`,
  `final`, pixel size, palette count, strength, steps, and guidance wherever
  they exist only for the deleted workflow. Retain a backend field only when it
  is actually effective or necessary provenance.
- [ ] Remove obsolete CLI subcommands and aliases for static lookbooks,
  favourite/reject/add review, selection, scoring, master promotion, old card
  rendering, validation, and sets. Keep one clearly named server command and
  only developer diagnostics that support the new UI.
- [ ] Delete the static lookbook implementation and other legacy portrait
  processing code once a reference search confirms nothing in the new server,
  runner, tests, or docs imports it. Do not retain dead modules “just in case.”
- [ ] Delete `portrait-review/` and its favourites, JSON, and reference PNGs if
  any survived Plan 01. Confirm `git ls-files portrait-review` is empty.
- [ ] Remove or replace the old preset/style JSON files. Keep one code-shipped
  starter recipe without reference images and keep the card template used by
  the direct renderer.
- [ ] Rewrite tests around the new contracts. Delete tests whose only purpose
  is backwards compatibility, old review status, favourites, lookbook output,
  raw/final promotion, master anchors, approvals, validation, or sets.
- [ ] Add one backend integration test covering empty workspace → imported
  sources/references → duplicated recipe → fake benchmark run → card draft →
  framing update → keep decision.
- [ ] Add one UI integration test covering the same visible path with mocked
  HTTP responses. Assert that failures are shown in their relevant surface and
  no terminal/JSON intervention is suggested.
- [ ] Rewrite `README.md` around the UI-first workflow, startup commands,
  required environment keys, generated-data location, and a short statement
  that the workbench is experimental rather than production tooling.
- [ ] Replace the obsolete pipeline documents with one concise
  `docs/portrait-workbench.md` describing workspace layout, recipe/run
  provenance, backend limitations, card framing, reset procedure, and Pexels
  licensing caveats. Historical archived notes may remain as history.
- [ ] Update service/deploy files and user-facing names from “Portrait Review”
  to “Portrait Workbench” where appropriate. Preserve the current ports/base
  path unless there is a concrete hosting conflict.
- [ ] Search the repository for the deleted concepts and inspect each remaining
  hit. Expected historical hits in `_notes/archived/` are acceptable; active
  source and current docs should not teach the old workflow.
- [ ] Run the full Python test suite, UI tests, TypeScript build, and a local
  server/API smoke test from an empty temporary workspace.
- [ ] Run one fake-adapter browser smoke flow and, when credentials and curated
  references are available, one paid one-source generation smoke test. Never
  make paid generation part of automated tests.
- [ ] Remove any manual smoke-test output from the repository and confirm the
  worktree contains only intentional source/docs changes before committing.

## Acceptance checks

- [ ] A new contributor can follow `README.md` from an empty clone and reach a
  useful Style Lab empty state without knowing the old architecture.
- [ ] The complete intended final path can be performed in the browser; only
  service startup and environment configuration require the terminal.
- [ ] The browser starts from one workspace bootstrap and uses no old API
  endpoint.
- [ ] Repository search finds no active use of favourites, raw/clean/final
  promotion, portrait masters, manual composition anchors, approvals, sets, or
  old validation.
- [ ] No generated portraits or style references are tracked by git.
- [ ] Python tests, UI tests, `npm run build`, and the empty-workspace smoke test
  all pass.

## Out of scope

- Proving that the current artistic recipe is final. The delivered tool makes
  that empirical work fast and visible; it does not predetermine the answer.
- Production asset approval, export, model training, automatic consistency
  scoring, authentication, hosted storage, and multi-user operation.
- Reintroducing pixelisation before painterly benchmark sheets are coherent.
