# Portrait Workbench

Portrait Workbench turns selected source portraits into finished, pixel-native
cards through one explicit path:

```text
Sources → Pipelines → Cards
```

The active house pipeline owns the generation direction, ordered image
references, framing, fixed-palette rendering, and card assembly as one
versioned contract. Saved versions and working configurations are first-class
assets with their own produced-card history.

## Start it

```bash
uv run python -m tools.portraits workbench-server
npm install
npm run dev
```

The API creates an ignored `portrait-library/` workspace and materializes the
checked-in live Amiga neutral-portrait style and its reference assets without
making a generation call. Set `PEXELS_API_KEY` to enable Pexels search and
starter imports, and configure `OPENROUTER_API_KEY` before live generation.
The capability catalogue is resolved from OpenRouter image endpoints; a local
simulation remains available only for free pipeline preview trials.

## Browser surfaces

### Sources

Upload, search, inspect provenance, and select an ordered set of source images.
The page keeps that identity set stable while pipelines change. It shows the
active pipeline, exact call count, model, and available unit cost before a run.
Generation starts immediately from the explicit run action.

### Pipelines

Saved versions and the current working pipeline sit side-by-side with sample
outputs. The pipeline anatomy makes the complete source + reference → generated
master → Amiga art → assembled card path visible. A working configuration can
change the model direction, ordered references, renderer values, and card
values, then run the same three-source comparison cohort repeatedly. Each
checksum keeps its own result column.

### Cards

Cards are shown as a source-by-pipeline matrix: rows keep identity constant and
columns expose each stored pipeline checksum. Open a result to inspect its
source, generated master, rendered art, final card, and provenance. **New
result** adds an attempt immediately; framing changes rerender the existing
master without another model call. Approval and bundle gates are intentionally
absent while the visual pipeline is still being developed.

## Routes

The refreshable hashes are `#sources`, `#pipelines`,
`#pipelines/<pipeline-id>`, `#cards`, and
`#cards/<batch-id>/<item-id>`. Superseded style hashes redirect to Pipelines.

## Pipeline and provenance

The production order is:

```text
identity source + ordered generation references
  → img2img master
  → resolved framing
  → master preparation
  → OCS palette mapping with edge-aware 4×4 Bayer dithering
  → 168×138 logical art
  → exact 2× enlargement to 336×276 art
  → pixel-native 210×300 logical card
  → exact 2× enlargement to 420×600 card
```

The canonical master and final card are inspectable provenance artifacts.
Every locked pipeline, batch, attempt, and render revision records the source
snapshot, resolved instruction and negative instruction, ordered reference
mapping, model/provider capabilities, execution mode, usage/cost, framing
transform, and output checksums. Target examples are visible as renderer proof
assets, but are structurally excluded from provider payloads.

Live runs, comparison cohorts, retries, and **New result** are explicit button
actions and do not add a second confirmation modal. The UI keeps model, call
count, and known/unknown cost adjacent to the run action, and the API records
authorization for live calls. Simulation output is labelled as a preview and
cannot be used to save and activate a production pipeline.

Workspace data is stored below `portrait-library/`:

```text
styles/versions/<style-version>/style.json
production/<batch>/batch.json
production/<batch>/inputs/...
production/<batch>/masters/...
production/<batch>/renders/...
approvals/approvals.json
downloads/...
```

To reset local development, stop the server and delete only this repository's
ignored `portrait-library/` directory, then restart the server. No reset is
performed by normal workflow actions.

## Verification

```bash
uv run --extra dev pytest -q
npm test -- --run
npm run build
git diff --check
```

The historical Amiga renderer proof uses the registered production renderer
and keeps the face-bearing stage reference out of live provider requests:

```bash
uv run python -m tools.cards.amiga_proof \
  --input "stage-reference=tools/cards/assets/amiga-ocs-portrait-v1/generation-reference-01.png" \
  --output-dir /tmp/amiga-proof
```

Future renderer families can register another driver implementing the typed
renderer/assembler interface and its validated style sections. The current
release registers only `amiga-ocs`; alternate raster families remain examples
for that extension boundary, not user-facing options.
