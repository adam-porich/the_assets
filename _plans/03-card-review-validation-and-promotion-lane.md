# 03 — Finish card-context review and the approved lane

## Outcome

The UI can diagnose an individual card in context, and a small batch can be
validated and promoted as a coherent experimental set without mixing it with
unapproved experiments.

## Scope

- Build on masters, styles, templates, and card renders already in place.
- Keep approvals manual and file-backed in the existing review/manifest JSON.
- Do not add accounts, a database, game export, or a full MTG rules renderer.

## Checklist

- [ ] Add a card detail view with card render, master, original candidate,
  source image, and composition overlay side-by-side.
- [ ] Let reviewers enter a short card-context note and classify it as
  placement, master quality, style, or template feedback.
- [ ] Add a set manifest that references selected card render IDs and has a
  readable set name/version.
- [ ] Add a Cards view filter for a selected set and a deterministic contact
  sheet/lookbook export.
- [ ] Extend `validate-cards` with per-archetype warning ranges for face size,
  face position, silhouette occupancy, and expected template/art dimensions.
- [ ] Render validation output in the UI and as a durable report attached to a
  set manifest.
- [ ] Add explicit `approved` master and card render states; promotion into a
  set must consume only those states.
- [ ] Separate experimental outputs from approved-set manifests by reference,
  not by copying every image into a new system.
- [ ] Document one clean end-to-end command/UI path from candidate review to
  approved experimental set.
- [ ] Reset disposable review/library state only after a fresh end-to-end test
  card passes through the completed flow.
- [ ] Add tests covering set-manifest validation, approved-only selection, and
  deterministic contact-sheet ordering.

## Acceptance checks

- [ ] A reviewer can trace an approved card to its candidate, master, style,
  anchors, template, and validation result from the web UI.
- [ ] A set of 8–20 renders can be reviewed in one stable grid and checked for
  visible/provenance drift.
- [ ] Experimental candidates cannot become part of an approved set without an
  explicit master/card approval.

## Decision needed before work

Choose the first realistic experimental set size and decide whether the first
set allows all three archetypes or begins with standard-bust only. This sets
the initial validation ranges and review workload.
