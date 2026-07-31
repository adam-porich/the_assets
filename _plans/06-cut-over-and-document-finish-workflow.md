# 06 — Cut over and document the finish-first workflow

## Outcome

Leave one coherent primary workflow, complete compatibility handling, and
documentation that explains why finish selection precedes set-wide generation.
Old experiments remain inspectable without teaching or enabling the superseded
mixed-completion path.

Run this plan only after Plans 01–05 pass their acceptance checks.

## Intended final path

```text
choose source portraits
→ explore recipes and outputs
→ select 1–3 representative candidates
→ iterate one finish across the candidate cohort
→ lock the coherent finish
→ keep those anchors and generate the remaining sources
→ frame/treat active-set portraits
→ keep cards in the active coherent Completed set
```

## Checklist

- [ ] Trace frontend requests and remove the primary UI's remaining ability to
  create cards from arbitrary exploration run items.
- [ ] Retain only the minimum legacy card endpoint/read behavior needed to open
  existing saved URLs; label it deprecated in code and keep it out of current
  API types where practical.
- [ ] Confirm all current UI copy uses Explore, Finish, Build Set, Frames,
  Treatment, and Completed consistently. Remove copy that calls card
  pixelisation a finish or treats Completed as a global card pile.
- [ ] Update README startup/workflow guidance and
  `docs/portrait-workbench.md` with the six-stage flow, contracts, immutable
  provenance, retry behavior, active-set semantics, and reset procedure.
- [ ] Document generated-artifact identity inputs for finish trials and the
  identity → finish anchors → base references ordering for set production.
- [ ] Document compatibility behavior: missing run purposes become
  exploration, old cards become legacy, and historical data is never
  destructively migrated into a coherent set.
- [ ] Verify the current workspace opens `run_59c947b99f90` as the baseline
  exploration batch when present and allows its outputs to seed Finish through
  the normal selection UI.
- [ ] Add one backend integration test covering exploration output → candidate
  selection → finish trial → lock → set build → card drafts → keep → active
  Completed filtering, using only the fake adapter.
- [ ] Add one UI integration test covering the same visible six-stage path,
  including a second finish/set that proves Completed never mixes them.
- [ ] Test an existing version-1 workspace fixture with mixed kept cards and
  verify they remain reachable only as legacy history.
- [ ] Run the full Python and UI suites, TypeScript/Vite build, and a local API
  smoke test from both empty and legacy temporary workspaces.
- [ ] Perform one manual live smoke test only when credentials are available:
  one candidate, one finish trial, one remaining source, and one completed
  card. Record exact cost in scratch notes and do not commit generated assets.
- [ ] Search active source/docs for obsolete four-stage navigation, **Send to
  Frames** from Explore, and card-level **Finish** terminology. Historical
  archived notes may retain the old language.
- [ ] Remove smoke artifacts, confirm generated workspace data remains ignored,
  and leave only intentional source, test, and documentation changes.

## Acceptance checks

- [ ] A new user can complete the six-stage path in the browser without editing
  JSON or invoking a workflow CLI.
- [ ] `run_59c947b99f90` can seed candidate selection without being rewritten or
  declared a locked finish automatically.
- [ ] A locked finish always predates and fully determines its set-production
  work.
- [ ] Completed defaults to one active coherent set, and a two-set regression
  test proves outputs never mix.
- [ ] Existing runs and cards remain inspectable through documented legacy
  behavior.
- [ ] `uv run pytest`, `npm test`, `npm run build`, and both workspace smoke
  tests pass.

## Out of scope

- Automatic selection, automatic finish scoring, model training, and visual
  similarity metrics.
- Authentication, remote storage, distributed workers, and multi-user edits.
- Destructive cleanup of historical user-generated assets.
