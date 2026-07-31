# Experimental Card Asset Pipeline Plan

## Intent and boundaries

This is a lightweight experiment plan for evolving the portrait tooling into a
coherent card-asset pipeline. The immediate objective is to make a small batch
of acceptable, visually related card previews—not to build a general asset
management system or a finished card-product renderer.

The central split is:

```text
source candidate -> portrait candidate -> approved portrait master
                                      -> deterministic card render -> review
```

The portrait master is independent of a card frame. A card render is a
reproducible composition of a master, a framing archetype, and a versioned
template. Current library/review data is disposable experiment data; it is
reasonable to reset it when the new contract is ready.

Keep the implementation CPU-friendly and file-based. Existing JSON manifests,
Pillow processing, the Python review server, and the React review app are
enough for this phase. Manual approval and manual anchor adjustment are desired
escape hatches, not failures of the design.

## Plan 1 — Introduce portrait masters

### Goal

Establish a reusable portrait-master asset that is selected from portrait
candidates and is not tied to a card frame or one fixed card crop.

### Why this comes first

Without a clear master asset, every later card layout would either regenerate
art or encode card-specific decisions into the portrait pipeline.

### Main design changes

- Add `portrait-library/masters/` for approved master image files and a small
  JSON record for each master. Files may be deleted and recreated during the
  experiment.
- A master record should minimally contain:
  - `master_id` (stable, human-readable identifier);
  - source photo ID and chosen candidate ID;
  - `style_id` and `style_version`;
  - source candidate/raw/final paths for provenance;
  - `master_path` and optional transparent foreground path;
  - creation timestamp and an optional short note.
- Initially create a master by copying the approved stylized output into the
  masters directory. Do not introduce a new generative operation here.
- Treat the current `stylized/*-final.png` as an experimental portrait
  candidate, not as a shipping asset. The existing source manifest remains the
  source of truth for fetched-image provenance.
- Add a minimal `approve master` action to the review API/UI or CLI. Explicit
  approval is enough; do not add permissions, users, or workflow states.

### Interfaces and data flow

`stylize` continues to produce candidates. A new promotion step consumes a
candidate ID and writes a master record. Downstream composition reads only the
master record, never a free-form stylized filename.

### Out of scope

Background removal improvements, automated quality scoring, card frames, and
asset publishing.

### Validation / definition of done

- One candidate can be promoted to a master with complete provenance.
- A master can be regenerated from its recorded candidate without changing its
  identifier or downstream references.
- No card-specific crop or frame is baked into master creation.

### Dependencies

None.

### Decision before implementation

Use opaque masters initially, retaining the existing rembg foreground and mask
as optional source material. Add transparent-master output only if it is needed
for a template; it should not delay the first card previews.

## Plan 2 — Make the house style explicit and versioned

### Goal

Replace the current loose prompt/preset notion with one small, inspectable
production style contract for the experiment.

### Why it comes now

Masters need a meaningful declaration of what visual system they belong to
before they can be compared as a coherent set.

### Main design changes

- Add `tools/portraits/styles/estate-card-v1.json` (or an equivalent
  `portrait-library/styles/` experiment directory) as the canonical house-style
  definition. Keep the existing prompt preset while migrating; it remains a
  generation implementation detail.
- The style definition should include:
  - stable ID and version;
  - short visual intent and approved reference-image paths;
  - the generation prompt and negative prompt used for the experiment;
  - named palette roles: background, shadow, midtone, highlight, outline, and
    accent, with a compact palette or bounded palette family;
  - target logical resolution, preferred detail density, and contrast intent;
  - any deterministic master post-processing settings.
- Reuse `estate-neutral.json` and the current preset's post-processing as
  starting inputs. The initial production style should be one style only.
- Record the selected `style_id`/version on every generated candidate and
  master. A style-reference image selected in the UI must be copied or named
  in the style definition, rather than existing only as a transient field.
- Keep the current styles gallery as an inspiration/test surface. It is not the
  authority for production style selection.

### Interfaces and data flow

Generation chooses a prompt preset plus a house style. The house style supplies
the fixed references and post-processing contract; the preset can evolve while
the style remains the review-facing identity. Master promotion refuses or
warns when a candidate lacks a style version.

### Out of scope

Supporting many styles, training a model, and enforcing subjective aesthetic
quality automatically.

### Validation / definition of done

- The project can identify exactly which style contract produced each master.
- Four to eight existing favorites can be reviewed against the same written
  reference and palette rules.
- Changing the style produces a new version rather than silently changing old
  masters.

### Dependencies

Plan 1.

### Decision before implementation

Choose one initial target: a dark, low-resolution fantasy-card portrait style
with strong silhouettes. Do not mix painterly, photorealistic, and pixel-art
targets in the same experimental batch.

## Plan 3 — Add portrait composition anchors

### Goal

Record enough composition information on a portrait master to place it into a
card window predictably.

### Why it comes now

The frame must be separate from generation, but a compositor cannot make a
good crop from a master without face, headroom, and silhouette guidance.

### Main design changes

- Add a `composition` object to the master record, expressed as normalized
  coordinates (`0..1`) relative to the master image. Keep it compact:
  - eye or face anchor;
  - head bounding box;
  - shoulder line or shoulder bounds;
  - subject/silhouette bounding box;
  - optional preferred empty-space direction.
- Add a manually editable composition sidecar or API endpoint. Initial values
  can be suggested from the existing face detection/crop utilities, but manual
  approval is authoritative.
- Define three named archetypes at the metadata level only:
  `standard-bust`, `tall-silhouette`, and `wide-torso`.
- Assign each approved master one preferred archetype, while allowing it to be
  tested in the others. Do not duplicate the portrait image for each crop.

### Interfaces and data flow

Master approval creates or requires composition metadata. The future compositor
receives `master_id`, `template_id`, and `archetype_id`, then derives the crop
and translation entirely from these records.

### Out of scope

Perfect automatic landmarks, pose classification, mesh warping, or image
regeneration to repair an unsuitable source.

### Validation / definition of done

- A reviewer can see the anchors overlaid on a master and correct them.
- The same master can be cropped differently for the three archetypes without
  editing the master pixels.
- No pixel coordinates are embedded in a reusable style or template definition.

### Dependencies

Plans 1–2.

### Decision before implementation

Normalize all anchor geometry to the master image, not to any preview size.
This keeps templates resolution-independent.

## Plan 4 — Define lightweight card templates and portrait slots

### Goal

Create a minimal, versioned description of the card presentation layer.

### Why it comes now

Templates are the other half of deterministic composition. Defining them before
rendering avoids hard-coding a particular frame into the review app.

### Main design changes

- Add `tools/cards/templates/` containing one experiment template,
  `estate-card-v1`, plus static frame/mask assets. A template is a small JSON
  definition and image layers, not a full card-layout engine.
- Specify in the template:
  - template ID/version and target preview size;
  - art-window rectangle or mask asset;
  - layer order: base/background, portrait art, art mask, frame, then optional
    simple placeholder text regions;
  - named slots that accept the three portrait archetypes;
  - per-archetype normalized crop/scaling rules and safe headroom range;
  - a deterministic background treatment for opaque masters.
- Start with a single art-window family and visually simple placeholder title,
  type, and rules boxes. They exist to establish card context, not card-game
  typography.
- Keep the frame entirely out of portrait prompts, master processing, and the
  master image file.

### Interfaces and data flow

The compositor loads a template by ID and an archetype rule by name. It does not
need to know any source-image or generator details.

### Out of scope

Rules-complete MTG card layout, multiple factions/rarities, runtime UI, and
free-form visual template editing.

### Validation / definition of done

- Template files can be versioned and loaded without modifying portrait code.
- The art window and frame can be changed while retaining the same master.
- All three archetypes have a documented slot rule, even if only one is used in
the first batch.

### Dependencies

Plans 1–3.

### Decision before implementation

Use one fixed preview resolution for the experiment, with optional enlarged
nearest-neighbour review output. Avoid solving scalable print production now.

## Plan 5 — Stand up deterministic card composition

### Goal

Render complete card previews from approved masters and templates using no
generative image step.

### Why it comes now

This is the first point at which the desired set-level coherence can be seen.

### Main design changes

- Add a small `tools.cards` module or a clearly separated cards package beside
  `tools.portraits`; do not fold card rules into `img2img.py`.
- Add a `render-card` command/API operation accepting:
  `master_id`, `template_id`, `archetype_id`, and optional lightweight card
  label data (name/type for preview only).
- Render to `portrait-library/cards/` or a future neutral `asset-library/cards/`
  directory. Write a sidecar/manifest record containing master/style/template/
  archetype versions and the resolved crop transform.
- Use Pillow for resizing, cropping, masking, compositing, and palette
  handling. Make transformations deterministic and avoid introducing a graphics
  service or a GPU dependency.
- Render the opaque master within the art window first. Add alpha foreground
  layering only if testing shows it materially improves the result.

### Interfaces and data flow

`approved master + composition metadata + template + archetype -> card render`.
The renderer never calls an image model and does not modify the master.

### Out of scope

AI inpainting after placement, automatic frame-aware painting, batch release
systems, and game integration.

### Validation / definition of done

- Re-running the same request yields the same render and provenance record.
- One master can produce at least two different card-context previews without
  regenerating or overwriting it.
- Changing a template or style version creates a distinct render identity.

### Dependencies

Plans 1–4.

### Decision before implementation

Decide whether card output IDs are content-addressed or simple readable IDs.
For this experiment, readable IDs with version components are sufficient.

## Plan 6 — Shift review to full-card context

### Goal

Make full-card renders the main review surface while retaining access to the
source and master for diagnosis.

### Why it comes now

Head size, headroom, silhouette, contrast against the frame, and placement are
not reliably judged from isolated portraits.

### Main design changes

- Add a Card/Set tab to the existing React review app. Its primary grid is card
  renders, grouped or filtered by template and archetype.
- A card detail view should show: full card, master, source candidate, anchor
  overlay, and compact provenance. This reuses the current candidate-detail
  pattern rather than creating a separate review product.
- Add only three review states for the experiment: `keep`, `reject`, and
  `approved`. Approval is explicit and may be stored in the same
  `portrait-review/review.json` initially.
- Support a small note on a render such as “face too large” or “needs tall
  archetype.” Do not add a formal issue workflow.
- Keep the static lookbook as a generated fallback, but make it render the same
  full-card grid and links to its provenance.

### Interfaces and data flow

The review server exposes card render records alongside the existing library
payload. Approval belongs to a render (master + template + archetype), not just
to a raw candidate.

### Out of scope

Multi-user collaboration, authentication, comments/threads, and approval
policy enforcement.

### Validation / definition of done

- A reviewer can approve or reject a card in context and trace it back to its
  master and source.
- A reviewer can identify a bad placement independently from a bad portrait.
- The card grid is usable for comparing a small set (roughly 8–20 cards).

### Dependencies

Plans 1–5.

### Decision before implementation

Reset or migrate the current `review.json` deliberately. Since the data is
experimental, a reset with a documented new schema is preferable to preserving
ambiguous candidate-only decisions.

## Plan 7 — Add small, explainable set checks

### Goal

Provide a batch view and a few deterministic warnings that expose obvious
inconsistency before human review.

### Why it comes now

Once card previews exist, the unit of quality becomes the set rather than an
individual portrait.

### Main design changes

- Add a simple set manifest listing card render IDs. A set can initially be a
  JSON file or a command argument; no database is needed.
- Add a `validate-set` command/report that checks:
  - shared approved house-style and template versions;
  - expected output dimensions and readable provenance;
  - master composition presence;
  - face/head position and scale within each archetype's declared safe range;
  - palette/color-count bounds when relevant;
  - missing or duplicate card render IDs.
- Report warnings and errors in JSON plus a readable HTML/text summary. These
  checks are prompts for review, not an automatic aesthetic verdict.
- Add an optional contact-sheet or set grid to the review app/lookbook, ordered
  consistently to make drift obvious.

### Interfaces and data flow

A set manifest references immutable render records. Validation reads manifests
and pixels but does not alter any asset or review decision.

### Out of scope

Embedding-model similarity, learned style scoring, training data, and hard
release gates.

### Validation / definition of done

- A batch of 8–20 previews can be rendered and reviewed as one grid.
- The validator catches missing versions, wrong dimensions, unsafe anchor
placement, and obvious palette-contract violations.
- Human review remains the final decision for visual coherence.

### Dependencies

Plans 1–6.

### Decision before implementation

Treat all numeric ranges as archetype-specific warnings at first. Tighten them
only after seeing a real batch; do not encode guessed art rules as failures.

## Plan 8 — Establish the experimental-to-production lane

### Goal

Make the successful experiment reproducible without constraining ongoing
portrait exploration.

### Why it comes last

The boundary should be based on the pipeline that actually produces acceptable
assets, not on a speculative structure.

### Main design changes

- Document two explicit lanes:
  - **experimental:** fetch, source exploration, style-reference trials,
    model/prompt comparison, and arbitrary candidates;
  - **production experiment:** selected candidate -> approved master -> one
    house style -> template/archetype -> deterministic render -> set review.
- Keep experimental outputs in the existing portrait-library working area.
  Production-experiment manifests should reference only approved masters,
  templates, styles, and renders.
- Once Plans 1–7 work, reset generated library/review data and run a clean
  small batch through the new lane. Preserve any good old images only by
  deliberately promoting them again.
- Update README and `docs/portrait-pipeline.md` to describe the new pipeline
  and identify legacy commands as exploratory.

### Interfaces and data flow

The production experiment reads explicit IDs and versioned definitions. It may
reuse any experimental candidate only through the master-promotion step.

### Out of scope

Package publishing, a production database, game-repository deployment,
permissions, lifecycle automation, and archival policy.

### Validation / definition of done

- A clean batch can be recreated from its style/template/master/set manifests.
- Experimental changes cannot silently change an already rendered card.
- The project has one documented happy path for producing and reviewing a small
  coherent card set.

### Dependencies

Plans 1–7.

### Decision before implementation

Do the reset only after one end-to-end test card has passed through the new
flow. The current data is disposable, but it remains useful as a smoke-test
fixture until then.

## Suggested implementation cadence

Implement Plans 1–5 as one narrow vertical slice for a single existing
favorite: promote it to a master, author anchors, define the first template,
and render all three archetypes. Then implement Plan 6 and review those card
previews before adding a batch. Plans 7–8 should follow only after the first
few cards are visually promising.

If a portrait model cannot meet the house-style contract, investigate a new
backend only at that point and only for the specific observed failure (for
example, poor identity retention or non-compliant palette). The deterministic
master/template/compositor contracts remain unchanged.
