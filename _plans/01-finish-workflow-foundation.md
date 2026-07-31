# 01 — Establish finish workflow contracts

## Outcome

Add the durable contracts and six-stage application shell needed by the later
plans without changing how existing exploration runs or cards behave.

The intended path is:

```text
Sources → Explore → Finish → Build Set → Frames → Completed
```

Implement the plans in numeric order. Plans 02–05 depend on the identifiers,
provenance, and compatibility defaults defined here. Plan 06 removes obsolete
primary paths only after the replacement flow passes end to end.

## Decisions

- A **finish** is the generative painterly look. Painterly/Estate Pixel remains
  a deterministic card **treatment**, not a finish.
- Exploration runs, finish trials, and set-production runs remain immutable.
- A finish is approved as a complete cohort, never by mixing outputs from
  different trials.
- A workspace may retain many historical sets but has at most one active set.
- Existing generated data is preserved. Records without new provenance receive
  compatible legacy defaults when read.

## Contracts

- Extend runs with `purpose`: `exploration`, `finish`, or `set-production`.
  Missing values read as `exploration`.
- Add a small `candidate_selection` record containing 1–3 run-item references,
  their unique source IDs, timestamps, and the exploration recipe/run
  provenance needed to initialize Finish.
- Store immutable finish records under `portrait-library/finishes/`. A finish
  records its ID/version, trial run, selected candidate inputs, approved output
  items, recipe/reference snapshots, resolved instruction, model mapping,
  checksums, usage/cost, and lock timestamp.
- Store sets under `portrait-library/sets/`. A set records its name, finish ID,
  ordered source snapshot, state, item records, production runs, timestamps,
  and aggregate usage/cost.
- Add `active_set_id` to the workspace. Missing values read as `null`.
- Add `set_id`, `set_item_id`, and `finish_id` to new cards. Existing cards
  without them are legacy cards and are not silently assigned to a set.

## Checklist

- [ ] Define and document normalized Python and TypeScript types for candidate
  selection, finish summaries/details, sets, set items, and the three run
  purposes.
- [ ] Add file-backed finish and set stores using the workspace's existing
  atomic JSON-write, locking, relative-path, and asset-URL rules.
- [ ] Add read-time compatibility defaults for the current version-1 workspace,
  runs without `purpose`, and cards without set provenance. Do not rewrite
  immutable historical run files just to add a default.
- [ ] Extend the bootstrap payload with candidate selection, finish summaries,
  set summaries, and `active_set_id` while keeping current fields readable by
  the client during the staged implementation.
- [ ] Add read-only list/detail endpoints for finishes and sets so later plans
  can add mutations without changing response shapes.
- [ ] Expand hash routing and the stage navigator to the six named stages. Give
  unfinished stages useful empty states and links back to their prerequisite.
- [ ] Route old `#styles` links to Explore and keep existing `#frames/<id>` and
  `#completed` links refreshable.
- [ ] Centralize run-purpose labels and stage eligibility helpers rather than
  scattering string checks through React components and server routes.
- [ ] Add store/API tests for empty defaults, atomic writes, unknown IDs,
  duplicate IDs, path safety, and serialization round trips.
- [ ] Add UI routing tests for all six stages, legacy hashes, refresh, and empty
  prerequisite states.
- [ ] Keep existing exploration, preview, framing, and completed tests passing
  throughout this foundation change.

## Acceptance checks

- [ ] An existing workspace opens without destructive migration and its old
  runs are classified as exploration history.
- [ ] A new workspace exposes empty candidate/finish/set state and no active
  set.
- [ ] All six stages are directly navigable and accurately explain what is
  missing.
- [ ] No new mutation can yet start a finish trial or build a set.
- [ ] `uv run pytest`, `npm test`, and `npm run build` pass.

## Out of scope

- Candidate selection controls, finish generation, set generation, and active
  Completed filtering.
- Editing or deleting historical runs and cards.
