# Portrait Workbench contract

The supported browser path is:

```text
Sources → Explore → Finish → Build Set → Frames → Completed
```

Hashes remain refreshable. Empty stages explain their missing prerequisite.
The old `#styles`, `#lab`, `#run/<id>`, and `#cards` links continue to open
Explore or Frames; old `#card/<id>` links reopen `#frames/<id>`.

## Sources and Explore

`benchmark_source_ids` is the ordered project source selection retained for
compatibility. Source records retain checksums, dimensions, local paths, and
Pexels or upload provenance.

Explore runs have `purpose: "exploration"`. A missing purpose is read as
`exploration` without rewriting the historical `run.json`. Runs snapshot the
visible recipe, resolved instruction, ordered references, source inputs,
provider mapping, usage, cost, and each output checksum.

The baseline exploration run `run_59c947b99f90` is shown first when it exists;
otherwise the newest complete exploration run is the starting batch. No
subjective output is selected automatically.

## Candidate selection

The current `candidate_selection` is a small versioned record backed by
`candidate-selections/<selection-id>-r<revision>.json` and
`candidate-selections/current.json`. It contains 1–3 complete Explore items,
one per workspace source, in display order. Every item snapshots its run item,
source identity, output path/checksum, source checksum, recipe, and references.

Selecting, removing, or reordering creates a new revision. Existing Finish
trials and locked Finishes retain their original selection revision. The
service rejects non-Explore runs, incomplete or missing output files, checksum
drift, duplicate source IDs, duplicate IDs, and selections outside the 1–3
limit.

## Finish

`POST /api/finish-trials` creates an immutable run with
`purpose: "finish"`, `selection_revision`, exactly one item per candidate, and
one generated output per item. A generated Explore output is copied below the
trial's `inputs/candidates/` directory as an identity input; it is not
pretended to be a workspace source. The trial records the originating Explore
run/item, workspace source identity, candidate checksum, inherited recipe
provenance, ordered style references, model mapping, usage, and cost.

Finish instructions resolve in stable order: the new
`Requested finish change: …` note, then inherited art direction. If selected
candidates came from different recipes, the first candidate initializes the
draft and the differing recipe provenance remains in the snapshots.

Trials are reviewed as candidate-aligned cohort sheets. Comparison is allowed
only between complete trials from the same selection revision. Locking verifies
that every expected item is complete, remains in selection order, and still
has its saved output checksum. It then atomically creates
`finishes/<finish-id>/finish.json` with a version, trial, candidate inputs,
approved outputs, snapshots, model mapping, usage, cost, and lock timestamp.
Locked Finishes are immutable; a later trial creates another version. No item
from one trial can be mixed with an item from another.

## Build Set

Sets are stored under `sets/<set-id>/set.json`. Creation snapshots the current
ordered project source selection and one locked Finish. Every source gets one
set item before remaining work is queued. Anchor items point to their approved
Finish output and preserve its bytes and checksum.

For each remaining source, set production sends references in exactly this
order:

```text
identity: current source snapshot
style: approved Finish outputs in candidate order
style: original Finish references in saved order
```

Reference-limit validation counts the identity plus every anchor and base
reference before creation; anchors and references are never silently
truncated. Set production runs have `purpose: "set-production"` and record the
same stack on each item. No generation call is made for anchors.

Sets are `building`, `ready-with-errors`, or `ready`. Successful items are
immutable. Retry creates a new production run only for failed/interrupted
items, preserves successful item paths, and aggregates usage and cost across
all production attempts. Source membership and order cannot change under a set
ID. The newest set becomes `active_set_id`; historical sets can be switched
explicitly without mutating their Finish or items.

## Frames and Completed

A ready active set automatically receives one working card draft per set item.
New cards persist `set_id`, `set_item_id`, `finish_id`, complete source
provenance, and the set item's immutable art source. At most one working or
kept card exists per set item. A discarded item may create a new draft with
explicit lineage; reconsidering never detaches it from the set.

Frames asks composition (Bust, Tall, Torso) and deterministic Treatment
(Painterly or Estate Pixel). Treatment is never labelled Finish. Preview cache
keys include source checksum, set/Finish provenance, template version, frame
presets, Treatment versions, schema, and card label. Selecting a preview copies
the exact cached PNG and art render into the card's saved paths, preserving
byte-identical output.

Completed defaults strictly to kept cards whose `set_id` equals
`active_set_id`, in set source order. It shows the active set and locked Finish
and retains direct downloads, provenance, reconsider, keep, and discard
behavior. Cards without the three set provenance IDs are legacy cards: they
remain reachable through history and saved URLs, but never enter the active
Completed grid.

## Workspace and compatibility

```text
portrait-library/
  workspace.json
  sources/
  references/
  runs/<run-id>/
  candidate-selections/
  finishes/<finish-id>/finish.json
  sets/<set-id>/set.json
  cards/previews/<card-id>/
```

Existing version-1 workspaces open without destructive migration. Missing run
purposes become Explore history, missing `active_set_id` is `null`, and old
cards receive legacy payload defaults without being assigned to a set. Old
numeric framing, treatment, run verdicts, and source selection remain stored.
All metadata writes use a temporary sibling followed by `Path.replace`, with
process-local locking. Asset requests reject absolute paths and traversal.

To reset the experimental workspace, stop the API service, delete only this
repository's ignored `portrait-library/`, and restart the service. Historical
generated assets are not deleted by normal workflow actions.

## External services

OpenRouter discovery resolves each image-to-image model to a definitive
provider endpoint and retains typed parameters, reference limits, provider
tag, streaming support, and pricing. Generation pins that provider and sends
only supported fields. Exact response usage and cost remain the accounting
source of truth. Pexels records retain photo, photographer, source-page,
query, and license-page provenance.
