# 00 — Complete the unified card workbench

## Goal

Replace the current six-stage portrait workflow with an understandable product
whose normal path is:

```text
choose source images → make finished cards with the active house style → approve cards
```

The active house style is **Amiga OCS Portrait v1**. A generated img2img master,
framing/crop, deterministic processing, and card assembly are one versioned
pipeline from the user's point of view. The browser presents finished cards as
the review unit; intermediate masters remain available only in details and in
Style Studio.

The same product must retain a deliberate Style Studio loop:

```text
edit a draft style → test the complete pipeline on a small cohort
→ compare final cards with the active version → make the draft active
```

This plan set is intended to be given to one high-reasoning implementation
agent as a persistent goal. Complete Plans 01–05 in order. Do not stop after
adding contracts, mockups, or parallel v2 code: the final active UI must use the
new workflow end to end.

## Goal prompt for Luna xhigh

> Complete the plan set beginning at
> `_plans/00-unified-card-workbench-goal.md`. Read all six plans and
> `AGENTS.md`, then execute Plans 01–05 in order. Continue until the unified
> source-to-cards workflow, integrated Amiga OCS output, Style Studio, tests,
> documentation, visual proof, plan archival, commit, and push all satisfy the
> written definition of done. Do not implement alternate style families and do
> not make paid generation calls without separate user authorization.

## Product decisions already made

- [ ] Treat source selection and card approval as the two everyday decisions.
- [ ] Make one finished candidate per selected source by default; **Try another**
  creates one additional immutable attempt for that source.
- [ ] Show final cards first everywhere. Raw img2img masters are diagnostic
  artifacts, not candidates that can be approved.
- [ ] Ship Amiga OCS Portrait v1 as the sole active style family and initial
  locked style version.
- [ ] Keep the style pipeline extensible by renderer/assembler driver ID and
  validated configuration. Do not implement 8-bit, ASCII, ANSI, C64, or other
  style families in this plan set.
- [ ] Keep target examples visually available to reviewers but technically
  impossible to send as generation references.
- [ ] Apply framing before deterministic quantisation. A framing adjustment
  rerenders the existing master without making another paid generation call.
- [ ] Preserve exact provenance, immutable inputs/outputs, reference ordering,
  provider usage, and cost even when those details are collapsed in the UI.
- [ ] Preserve existing workspace files non-destructively. Historical Explore,
  Finish, Set, and old card records may be exposed as read-only legacy history,
  but they are not part of the new primary workflow.
- [ ] Require an explicit click before any paid generation. Automated tests use
  the simulation/fake adapter only.

## Target information architecture

- [ ] Use only **Sources** and **Cards** as the primary navigation.
- [ ] Put the active style name/version in a header chip that opens **Style
  Studio**; Style Studio is not another required production stage.
- [ ] Keep run history and provenance as secondary drawers/details rather than
  primary navigation stages.
- [ ] Remove the active UI language and routes for Explore, Finish, Build Set,
  Frames, candidate handoff, locked Finish anchors, and treatments.
- [ ] Keep direct hashes refreshable for Sources, Cards, Style Studio, and an
  individual card. Redirect old hashes to the nearest useful new view.

## Definition of done

- [ ] A fresh workspace opens with Amiga OCS Portrait v1 active and explains
  how to add/select sources.
- [ ] From selected sources, one explicit action creates a production batch;
  every successful generation is automatically processed into Amiga art and a
  complete card before it appears as ready.
- [ ] A reviewer can approve one current-style card per source, try another,
  adjust framing without regeneration, download approved PNGs, and see progress
  without visiting another stage.
- [ ] A style editor can change generation direction/references and Amiga
  processing settings, run an integrated cohort trial, compare final cards, and
  activate only a complete trial.
- [ ] The known generation reference renders byte-for-byte to the checked-in
  target example through the same production rendering path.
- [ ] Existing painterly source outputs used in the proof produce a coherent
  final-card grid through the integrated application path, not a proof-only CLI.
- [ ] Python tests, UI tests, TypeScript build, empty-workspace smoke test, and
  fake-adapter end-to-end workflow all pass.
- [ ] Current README and docs describe only the new primary workflow.
- [ ] A visual review artifact demonstrates the final Sources, Cards, and Style
  Studio screens and includes cards comparable to the approved Amiga proof.
- [ ] All completed plan files are moved to `_notes/archived/`; implementation
  changes are committed and pushed, and the worktree is clean.

## Execution discipline

- [ ] Read the whole plan set and current `AGENTS.md` before implementation.
- [ ] Work sequentially through Plans 01–05, updating checkboxes only after the
  corresponding behavior and tests exist.
- [ ] Reuse current generation, workspace, atomic-write, capability, and run
  infrastructure where it serves the target contract; remove superseded paths
  after cutover rather than maintaining two editable workflows.
- [ ] Commit and push coherent, passing increments. Do not commit credentials,
  paid test output, `portrait-library/`, caches, or build products.
- [ ] If a detail is unspecified, choose the option that keeps the normal path
  closest to source selection → finished-card review → approval.

## Plan order

- [ ] Complete **01 — Build the unified style pipeline contract**.
- [ ] Complete **02 — Build card production and approval**.
- [ ] Complete **03 — Replace the UI with the source-to-cards workflow**.
- [ ] Complete **04 — Build Style Studio around final-card trials**.
- [ ] Complete **05 — Cut over, prove the result, and archive the plans**.
