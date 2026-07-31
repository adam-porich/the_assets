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

- [x] Add a card detail view with card render, master, original candidate,
  source image, and composition overlay side-by-side.
- [x] Let reviewers enter a short card-context note and classify it as
  placement, master quality, style, or template feedback.
- [x] Add a set manifest that references selected card render IDs and has a
  readable set name/version.
- [x] Add a Cards view filter for a selected set and a deterministic contact
  sheet/lookbook export.
- [x] Extend `validate-cards` with per-archetype warning ranges for face size,
  face position, silhouette occupancy, and expected template/art dimensions.
- [x] Render validation output in the UI and as a durable report attached to a
  set manifest.
- [x] Add explicit `approved` master and card render states; promotion into a
  set must consume only those states.
- [x] Separate experimental outputs from approved-set manifests by reference,
  not by copying every image into a new system.
- [x] Document one clean end-to-end command/UI path from candidate review to
  approved experimental set.
- [x] Verify a fresh end-to-end test card passes through the completed flow
  before any deliberately requested destructive reset; preserve the current
  exploratory library until that reset is explicitly requested.
- [x] Add tests covering set-manifest validation, approved-only selection, and
  deterministic contact-sheet ordering.

## Acceptance checks

- [x] A reviewer can trace an approved card to its candidate, master, style,
  anchors, template, and validation result from the web UI.
- [x] A set of 8–20 renders can be reviewed in one stable grid and checked for
  visible/provenance drift.
- [x] Experimental candidates cannot become part of an approved set without an
  explicit master/card approval.

## Decision needed before work

Choose the first realistic experimental set size and decide whether the first
set allows all three archetypes or begins with standard-bust only. This sets
the initial validation ranges and review workload.
