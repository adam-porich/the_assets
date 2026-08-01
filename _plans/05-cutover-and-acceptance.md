# 05 — Cut over, prove the result, and archive the plans

## Outcome

Leave one supported application whose UI and output embody the new workflow.
Remove superseded active code, prove that the integrated app produces the Amiga
quality target, document it, and hand back a clean pushed repository.

Run this plan only after Plans 01–04 pass their phase acceptance checks.

## Active-path cleanup

- [ ] Trace every frontend request and backend route used by Sources, Cards, and
  Style Studio. Remove unused mutable endpoints for candidate selection, Finish
  trials/locks, Set building, old card treatments, and preset preview grids.
- [ ] Delete unused React components/types/tests for the six-stage workflow,
  including `FinishLab.tsx` and `SetViews.tsx` when no active imports remain.
- [ ] Simplify or split `tools/portraits/workflow.py` and
  `tools/cards/pipeline.py` after the new stores are in use. Delete dead Finish,
  Set, Painterly, and Estate Pixel production helpers rather than leaving two
  supported pipelines.
- [ ] Preserve historical files under existing `portrait-library/` directories;
  removal of code/routes must not delete user-generated data. Keep a minimal
  read-only legacy reader only if the new UI exposes legacy history.
- [ ] Stop seeding the old Estate reference pack in fresh workspaces. Seed the
  Amiga style/reference contract instead. Do not delete old workspace references
  or mutate old recipe snapshots.
- [ ] Search active source/docs for Explore, Finish, Build Set, Frames,
  Completed, Painterly, Estate Pixel, candidate selection, and locked anchors.
  Inspect every hit; historical archived notes may retain those terms.
- [ ] Remove generated caches, `__pycache__`, local screenshots not selected for
  review, and temporary smoke-test workspaces from the change set.

## Documentation

- [ ] Rewrite `README.md` around the three visible surfaces, startup commands,
  environment keys, explicit paid actions, active style, workspace location,
  downloads, and reset procedure.
- [ ] Rewrite `docs/portrait-workbench.md` with the unified style-version,
  production-item, approval, render-revision, reference-role, and compatibility
  contracts.
- [ ] Document the exact current pipeline order and make clear that the master
  is internal while the final card is the approval artifact.
- [ ] Document how to add a future renderer family at the registry/contract
  level, using 8-bit or ASCII only as non-implemented examples.
- [ ] Document how to regenerate the Amiga proof through the shared renderer and
  how to run the golden test. Do not document the proof CLI as a separate
  production workflow.

## Automated verification

- [ ] Run the complete Python suite with `uv run --extra dev pytest -q`.
- [ ] Run the complete UI suite with `npm test -- --run`.
- [ ] Run `npm run build` and `git diff --check`.
- [ ] From an empty temporary workspace, start the server, fetch bootstrap,
  verify Amiga OCS v1 is active, use the simulation adapter to create cards,
  approve them, and download/validate the ordered manifest and PNG bundle.
- [ ] Run an existing-workspace smoke test proving old assets are untouched and
  legacy records do not enter current approval counts.
- [ ] Confirm no automated test makes a paid external request and no credential
  value appears in logs or tracked files.

## Visual proof

- [ ] Drive the real integrated app with the known stage reference and the six
  existing painterly masters listed in
  `_notes/reviews/amiga-ocs-v1/README.md`, using a fake/import adapter where
  necessary to avoid paid calls.
- [ ] Confirm the integrated stage-reference final art is byte-identical to
  `tools/cards/assets/amiga-ocs-portrait-v1/target-example-01.png`.
- [ ] Compare the integrated card grid with
  `_notes/reviews/amiga-ocs-v1/amiga-ocs-v1-card-set.png`; investigate any
  rendering difference rather than accepting “similar enough” silently.
- [ ] Review the actual browser at desktop and narrow widths. Verify the normal
  path can be explained as choose images → make cards → approve cards without
  referring to internal run stages.
- [ ] Save a concise review set under `_notes/reviews/unified-card-workbench/`
  containing Sources, in-progress Cards, ready/approved Cards, Style Studio
  compare, and a README with exact fixture/provenance and any intentional visual
  differences.
- [ ] Check the review screens for button overload: advanced provenance and
  style controls begin collapsed, rare actions are secondary, and each decision
  region has one obvious next action.

## Optional live smoke

- [ ] If credentials are configured and the user has separately authorized a
  paid smoke call, run exactly one source through the active production path and
  record usage/cost without committing the generated asset. Otherwise record
  that the live smoke was intentionally skipped; it is not a completion blocker.

## Final handoff

- [ ] Update every checklist in Plans 00–05 to reflect verified work.
- [ ] Move all completed plan files from `_plans/` to `_notes/archived/` in the
  same final change. Leave no completed plan in `_plans/`.
- [ ] Confirm the final worktree contains only intended source, test, docs, and
  selected review artifacts.
- [ ] Commit and push all implementation and archival changes according to
  `AGENTS.md`; confirm the branch is clean and tracks the pushed commit.
- [ ] Report the active style version/checksum, final routes, test results,
  visual-review links, commit hash, and any skipped optional live smoke call.
