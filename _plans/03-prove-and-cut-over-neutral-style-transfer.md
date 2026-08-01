# 03 — Prove and cut over neutral style transfer

## Visual calibration

- [ ] Choose a fixed local cohort containing varied head angles, expressions,
  lighting, backgrounds, ages, skin tones, hair, and clothing.
- [ ] With explicit authorization for paid calls, run the same locked draft on
  the full cohort and retain every source, master, Amiga art, and card in the
  trial record.
- [ ] Review whether the generated masters converge on the reference's frontal
  bust, calm affect, direct gaze, restrained background, broad tonal planes,
  and consistent crop.
- [ ] Review whether recognizable identity cues survive without preserving the
  source's exact emotion, pose, scene, or camera treatment.
- [ ] Review the post-render 336×276 art against `target-example-01.png` for
  palette, edge hierarchy, dithering, value grouping, background restraint,
  and silhouette readability.
- [ ] Adjust generation direction and references before renderer settings when
  failures are semantic; adjust the deterministic renderer only when the
  canonical masters are already correct.

## Acceptance guardrails

- [x] Define a short human rubric with independent checks for identity,
  neutralisation, composition, master quality, Amiga treatment, and card
  legibility.
- [x] Reject a draft when outputs merely filter the source photograph, retain
  strong expressions/poses, invent distracting narrative details, become
  generic faces, or attempt to generate their own pixel effects/card frame.
- [x] Require cohort-level coherence; do not activate a version by selecting
  isolated successes from different prompt/reference configurations.
- [x] Preserve failed and rejected attempts as provenance without exposing
  them as approved cards.
- [x] Confirm framing adjustments cannot hide a failed neutralisation step and
  never trigger generation.

## Cutover and documentation

- [ ] Activate the proven live style as a new immutable version without
  rewriting existing batches or approvals.
- [x] Update README and workbench documentation to describe the canonical
  master and show the exact source → neutral master → Amiga art → card path.
- [x] Add a checked-in review sheet or manifest showing the calibration cohort
  at every artifact stage; do not commit paid provider credentials or
  unrestricted workspace data.
- [x] Run Python tests, UI tests, TypeScript build, `git diff --check`, and an
  empty-workspace smoke test.
- [ ] Move these completed plans to `_notes/archived`, commit the implementation
  in coherent increments, push the branch, and leave the worktree clean.
