# 04 — Build the remaining portraits from a locked finish

## Outcome

Create one coherent, named portrait set from a locked finish. Keep the approved
finish outputs as the final artwork for their anchor subjects and generate
only the remaining selected project sources.

## Set build rules

- Set creation snapshots the current ordered project source selection and one
  immutable finish ID.
- Every source has exactly one set item. Anchor-source items point directly to
  their approved finish-trial outputs.
- Remaining sources are generated in a `set-production` run using the locked
  finish recipe and this ordered reference stack:
  1. the current source photo as identity;
  2. approved finish outputs in candidate order as the strongest style
     references;
  3. the locked finish's original style references in their saved order.
- Reference-limit validation happens before set creation and never silently
  truncates anchors or base references.
- The set is `building`, `ready-with-errors`, or `ready`. Successful items are
  immutable; retry creates a new production run only for failed/missing items.

## Checklist

- [ ] Add set creation validation for locked finish state, non-empty source
  snapshot, anchor/source correspondence, unique source IDs, asset checksums,
  provider availability, reference limits, and active-run concurrency.
- [ ] Atomically create the set manifest and anchor set items before queuing
  remaining work so refresh always explains what exists and what is pending.
- [ ] Extend generation requests with the exact locked anchor-first reference
  stack and record that mapping per production item.
- [ ] Skip generation for every anchor source and preserve its approved finish
  output byte-for-byte as the set item's art source.
- [ ] Add the set-production runner, incremental status/cost updates, restart
  interruption behavior, and aggregate accounting across retry runs.
- [ ] Add retry for failed or interrupted set items. Reject attempts to rerun a
  successful item or to change recipe/references under the existing set ID.
- [ ] Add **Build Set** controls showing the set name, locked finish, anchor
  subjects, remaining subjects, reference count, model, and exact number of
  paid image calls.
- [ ] Build a source-ordered Set stage with anchor/generated badges, progress,
  errors, retry actions, provenance details, and a coherent contact sheet.
- [ ] Set a newly created set as active. Add explicit switching among historical
  sets without changing their finish or item membership.
- [ ] Disable **Continue to Frames** until every source has a successful set
  item. A partial set remains inspectable and retryable.
- [ ] Add fake-adapter tests for reference order, anchor skipping, source
  snapshot immutability, no remaining sources, reference-limit failure,
  partial failure, retry idempotency, aggregate cost, and active-set switching.
- [ ] Add UI tests for preflight summary, progress, anchor badges, partial
  failure/retry, ready gating, historical set switching, and refresh.

## Acceptance checks

- [ ] Building from a locked finish makes no generation call for the approved
  anchor subjects and generates each remaining selected source once.
- [ ] Each generated item records the original identity first, locked finish
  anchors next, and original references last in exact order.
- [ ] Retrying failures cannot duplicate or replace successful set items.
- [ ] Changing the workspace source selection after launch cannot alter the
  set's membership or order.
- [ ] `uv run pytest`, `npm test`, and `npm run build` pass.

## Out of scope

- Framing, treatment, card labels, and Completed decisions.
- Generating multiple alternatives per remaining source.
- Mutating an existing set to adopt a newer finish.
