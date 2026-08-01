# 03 — Replace the UI with the source-to-cards workflow

## Outcome

Make the application's normal path self-evident without teaching the internal
pipeline. The user chooses source portraits, explicitly makes finished cards
with the active house style, and approves those cards on one review screen.

## Application shell and routes

- [x] Replace the six-stage numbered navigation with two primary links:
  **Sources** and **Cards**.
- [x] Add a compact header chip showing `Amiga OCS Portrait v1 · active`; clicking
  it opens `#style`. Do not present Style Studio as a required numbered step.
- [x] Support refreshable `#sources`, `#cards`, `#cards/<card-or-attempt-id>`, and
  `#style` routes using the existing lightweight hash approach.
- [x] Redirect `#explore`, `#styles`, `#finish`, and `#set` to the most useful
  current view with a one-time explanatory notice. Redirect `#frames` and
  `#completed` to Cards. Keep old card deep links readable when possible.
- [x] Remove stage counts such as “batches,” “waiting,” and “Stage 4 of 6.” The
  header should summarize selected sources, active style, and current approvals.
- [x] Keep global refresh and operation/error feedback, with errors adjacent to
  the action that failed.

## Sources screen

- [x] Preserve Pexels search/import, upload, provenance, delete confirmation,
  project library, selection, and ordering; source management is already useful.
- [x] Reduce its initial visual weight: put search/upload management in a clear
  **Add source images** region or disclosure and make the selected project
  sources the main content once any exist.
- [x] Do not add quality scoring or force a calibration/source taxonomy. The
  current evidence says varied portrait sources work well through the pipeline.
- [x] Show one dominant action beneath the selected-source summary:
  **Make N cards with Amiga OCS Portrait v1**.
- [x] Before the click, show the exact number of generation calls, execution
  mode/model, and known/unknown cost status in concise supporting text.
- [x] Disable the action with a specific explanation when there are no selected
  sources, no active style, invalid references, missing credentials/model, or
  another paid run is active.
- [x] On success, navigate directly to Cards and show live per-source progress.
- [x] If current-style approvals already exist, offer **Make missing cards** for
  unapproved selected sources as the default; make full regeneration secondary
  and explicit.

## Cards screen

- [x] Make final 420×600 cards the largest elements. Do not lead with source,
  master, generated art, run recipe, or treatment controls.
- [x] Group attempts by source in selected-source order. Show one current attempt
  per source, with previous attempts accessible without mixing subjects.
- [x] Display queued/generating/processing/ready/failed progress directly in the
  card slot so the user can understand that generation and processing are one
  operation.
- [x] Give each ready card one primary **Approve card** action. After approval,
  show an unambiguous approved state and make **Change choice** secondary.
- [x] Provide **Try another** for one additional paid attempt and **Adjust
  framing** for a deterministic no-generation rerender. Label their cost
  difference clearly.
- [x] Keep framing lightweight: one large live card, drag/reposition, zoom,
  reset-to-style-default, save/error feedback, and return to the source's
  attempts. Do not restore a separate Frames gallery or Bust/Tall/Torso and
  treatment grids.
- [x] Keep source/master/art toggle, model, prompt, references, usage, checksums,
  and transforms in a collapsed **How this was made** drawer.
- [x] Show batch-level progress and `approved / selected` at the top. When all
  are approved, emphasize **Download approved cards** and keep individual PNG
  downloads on each card.
- [x] Make failed items actionable in place with **Retry failed**. A failure for
  one source must not hide or block ready approvals for others.
- [x] When the active style differs from the batch style, show both versions and
  offer a deliberate new-style batch; never relabel old cards as current.

## Interaction and accessibility

- [x] Keep only one visually dominant primary action per decision region. Use
  links/disclosures for provenance, history, and destructive/rare operations.
- [x] Use native buttons/links/inputs with clear focus states, labels, pressed or
  selected semantics, status announcements, and keyboard framing controls.
- [x] Preserve browser refresh/reopen while a run is active and while a framing
  save is pending. Poll only active work and stop polling at terminal states.
- [x] Avoid confirmation modals for reversible approval changes. Confirm paid
  full regeneration and destructive source deletion in context.
- [x] Keep the desktop card grid excellent and make the normal review path
  usable on a narrow screen without horizontal stage navigation.

## Remove the old path

- [x] Delete or rewrite active React state/types/components for candidate
  selection, Finish trials, Finish locks, Set building, frame treatment grids,
  and separate Completed cards once their replacements are connected.
- [x] Remove user-facing Painterly and Estate Pixel treatment choices from the
  new UI. Do not call Amiga processing a treatment.
- [x] Remove buttons that merely move between old stages: Continue to Explore,
  Continue to Finish, Lock this Finish, Build Set, Open Frames, and Keep as
  Completed.
- [x] Keep legacy provenance/history read-only and visually separated if it is
  retained; it must not increase the normal button count or approval totals.

## UI tests and acceptance

- [x] Replace the “guided six-stage workflow” tests with a visible end-to-end
  test: select sources → click Make cards → observe progress → approve each card
  → download manifest/bundle.
- [x] Add UI tests for empty workspace, disabled paid action explanations,
  partial failure/retry, Try another confirmation, style-version mismatch,
  approval supersession, refresh/reopen, and individual/bundle downloads.
- [x] Add UI tests proving Adjust framing calls only the render endpoint and
  retains the exact approved checksum until the new revision is approved.
- [x] Assert that the active shell contains no Explore, Finish, Build Set,
  Frames, Completed, Painterly, Estate Pixel, or “Stage N of 6” navigation.
- [x] Assert final-card images are the primary ready-item image while master and
  provenance images begin collapsed.
- [x] Review the UI at common desktop and narrow widths, including visible focus
  and long source labels.
- [x] Run `npm test -- --run`, `npm run build`, and `git diff --check` before
  marking this plan complete.
