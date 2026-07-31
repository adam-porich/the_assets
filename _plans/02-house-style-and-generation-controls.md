# 02 — Make the house style enforceable

## Outcome

`estate-card-v1` becomes a reproducible, reviewable generation and master
contract rather than a label attached at promotion time.

## Scope

- Keep one production-experiment style only.
- Reuse the existing style-reference gallery for exploration, but promote only
  explicitly selected references into the house-style definition.
- Avoid model training, ControlNet, or a new hosted backend until a measured
  failure requires one.

## Checklist

- [x] Select and store a small fixed house-style reference pack in
  `tools/portraits/styles/estate-card-v1.json`.
- [x] Record the house-style ID/version on every new candidate, not only a
  promoted master.
- [x] Make generation choose the house style explicitly and resolve its prompt,
  negative prompt, references, palette roles, and master post-processing.
- [x] Add a simple Style contract view to the web UI: references, palette
  roles, logical size, and generation preset.
- [x] Audit the selected image backend's documented request shape and map only
  supported controls into its payload.
- [x] Stop presenting unsupported `strength`, `steps`, `guidance`, or size
  fields as effective generation controls; label them provenance-only or omit
  them from the active UI.
- [x] Add backend capability metadata for identity/reference count, seed,
  dimensions, and any supported image-to-image strength control.
- [x] Run a fixed source benchmark using the same style contract and compare
  results as a grid in the review app.
- [x] Record explicit reject reasons for text, weak silhouette, palette drift,
  and poor identity retention.
- [x] Add tests ensuring a candidate/master records its resolved style version
  and reference pack.

## Acceptance checks

- [x] A reviewer can identify the exact fixed style contract behind every new
  candidate and master.
- [x] The UI exposes only controls that the selected backend can actually
  honor.
- [x] A small benchmark batch is generated from one style version and reviewed
  together without hidden reference drift.

## Decision needed before work

Choose the initial fixed reference pack and whether the house-style prompt
supersedes or extends `estate-pixel-claimant-v1`. Keep the result to one
versioned contract for the first benchmark.
