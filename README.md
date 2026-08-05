# Portrait Workbench

Portrait Workbench turns selected source portraits into finished, pixel-native
cards through one explicit path:

```text
Sources → Pipelines → Candidates → Collection
```

Each runnable pipeline owns its generation direction, ordered image references,
framing, fixed-palette rendering, and card assembly as one versioned contract.
One pipeline is the active default used by Sources, but either saved pipeline
can generate candidates.

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

The workbench has two real live pipelines: **Face-free Style Board** and
**Portrait Style Reference**. The latter uses the original portrait reference
from historical Pipelines 01/02; otherwise it shares the current generation and
rendering path. Saved revisions live inside their pipeline instead of appearing
as extra peer pipelines. A working revision can run a three-source calibration
cohort before it is saved.

### Candidates

New uploads and Pexels additions are pinned into Candidates automatically, with
the newest source pack shown first so it is ready to generate immediately.
Each source has a card pack showing its three newest production candidates.
The Generate tile opens the two real pipeline choices and creates the next card
for that source; when it is ready, it enters the pack and the oldest visible
card rolls out. Older ready attempts remain retained, while draft calibration
trials stay in the pipeline editor and simulation output is not presented as a
candidate. Source identity and pack counts are available from the compact
Source hover above Generate, leaving the tray width for larger cards. Open a
candidate to inspect its source, generated master, rendered art, final card, and
provenance. While generation runs, a card-shaped loading slot holds the incoming
card's place at the front of its source pack. **Generate again** adds an attempt
immediately; framing changes rerender the existing master without another model
call.

### Collection

Favorite any number of candidates to save them in Collection. Collection keeps
references to the durable production assets, so it does not duplicate image
files. Removing a favorite does not delete its candidate. If a favorite is
reframed, Collection follows the candidate's latest render revision.

## Routes

The refreshable hashes are `#sources`, `#pipelines`,
`#pipelines/<pipeline-id>`, `#candidates`,
`#candidates/<batch-id>/<item-id>`, and `#collection`. Old `#cards` hashes
redirect to Candidates.

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

Live runs, comparison cohorts, retries, and **Generate again** are explicit button
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
favorites.json
downloads/...
```

To reset local development, stop the server and delete only this repository's
ignored `portrait-library/` directory, then restart the server. No reset is
performed by normal workflow actions.

The targeted migration used to remove superseded simulation pipelines and
their batches is idempotent:

```bash
uv run python -m tools.portraits cleanup-workspace --input portrait-library
```

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
