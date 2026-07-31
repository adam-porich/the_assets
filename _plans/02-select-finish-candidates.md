# 02 — Select representative finish candidates in Explore

## Outcome

Turn successful exploration outputs into an explicit 1–3 portrait handoff to
Finish. Selection happens before any finish trial or set-wide production run.

`run_59c947b99f90` remains the initial baseline exploration batch in the
current workspace; the user can choose its strongest outputs without copying
or rewriting the run.

## Selection rules

- A selection contains 1–3 complete run items from exploration runs.
- Each selected item must represent a different workspace source.
- Items may come from different exploration runs so useful prior work is not
  discarded.
- The service snapshots the selected item path/checksum, source identity,
  exploration run and recipe, references, and display order.
- Changing selection after finish work exists starts a new selection revision;
  it does not mutate trials or locked finishes derived from an older revision.

## Checklist

- [ ] Add a candidate-selection mutation that validates run purpose, item
  completion, output existence/checksum, unique source IDs, and the 1–3 count.
- [ ] Persist a stable selection ID/revision and return the refreshed selection
  through bootstrap and a focused API response.
- [ ] Add selection actions to exploration result cards with clear selected
  order, source identity, run context, and a visible `1–3 selected` counter.
- [ ] Prevent selection of a second output for the same source and explain the
  conflict beside the attempted item.
- [ ] Add a compact persistent selection tray to Explore. Support remove and
  reorder without navigating away from the current run.
- [ ] Make **Continue to Finish** the only primary downstream action for
  exploration results. Disable it until at least one valid candidate is saved.
- [ ] Remove **Send to Frames** from the normal exploration result surface.
  Keep the underlying legacy card endpoint temporarily for compatibility until
  Plan 06.
- [ ] Make run history distinguish exploration runs from later run purposes and
  exclude non-exploration runs from candidate selection.
- [ ] On the existing local workspace, surface `run_59c947b99f90` as the
  baseline/current exploration batch without preselecting subjective winners.
  Fall back to the newest complete exploration run when that ID is absent.
- [ ] Add backend tests for mixed-run selection, duplicate-source rejection,
  incomplete/missing items, count limits, ordering, and immutable revision
  provenance.
- [ ] Add UI tests for selecting, replacing, reordering, validation feedback,
  refresh persistence, baseline opening, and the Finish navigation gate.

## Acceptance checks

- [ ] The user can open `run_59c947b99f90`, choose 1–3 outputs from different
  people, refresh, and see the same ordered selection.
- [ ] Arbitrary exploration results no longer enter Frames through the primary
  workflow.
- [ ] Existing trials/finishes retain their original selection when the active
  selection changes later.
- [ ] `uv run pytest`, `npm test`, and `npm run build` pass.

## Out of scope

- Generating or approving finish trials.
- Automatically scoring or choosing the best candidates.
- Requiring all selected candidates to originate in one run.
