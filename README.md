# Portrait Workbench

Portrait Workbench turns selected source portraits into finished, pixel-native
cards through one explicit path:

```text
Sources → Cards
```

The active house style is **Amiga OCS Portrait v1**. Its locked pipeline owns
the generation direction, ordered image references, framing, fixed-palette
rendering, and card assembly as one versioned contract. Style Studio is opened
from the active-style chip when that contract needs to evolve.

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
simulation remains available only for free Style Studio preview trials.

## Browser surfaces

### Sources

Upload, search, inspect provenance, and select an ordered set of source images.
The page shows the exact number of calls, model, execution mode, and available
cost before the primary **Make N cards with Amiga OCS Neutral Portrait v2** action.

### Cards

Each selected source gets one immutable live generation attempt by default. A
card slot first redraws the source into a canonical neutral portrait master,
then stays in progress until that master has been rendered into 336×276 art
and a complete 420×600 card. Reviewers can approve a ready card, make one
additional **Try another** attempt, adjust framing without generation, retry a
failed source, download an individual PNG, or download the ordered approved
bundle and manifest.

### Style Studio

The header chip opens Style Studio. A draft is derived from the active locked
version. It can change the generation direction, ordered generation references,
Amiga processing values, and card values. Up to three representative sources
can run an integrated trial. Only a complete trial whose draft checksum still
matches can be locked and activated.

## Routes

The refreshable hashes are `#sources`, `#cards`, `#cards/<batch-id>/<item-id>`,
and `#style`. Superseded hashes redirect to the nearest current surface and do
not expose an additional workflow.

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

The canonical master is an inspectable provenance artifact; the final card is
the everyday approval artifact. Every locked style, batch, attempt, render
revision, and approval records the source snapshot, resolved instruction and
negative instruction, ordered reference mapping, model/provider capabilities,
execution mode, usage/cost, framing transform, and output checksums. Target
examples are visible for review and golden tests, but are structurally
excluded from provider payloads.

Live production, trials, retries, and **Try another** each require an explicit
confirmation. The Sources action shows the selected live model, call count,
and known/unknown cost before it can be used. Simulation output is labelled as
a preview and cannot be used to lock or activate a production style.

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

The Amiga proof uses the registered production renderer:

```bash
uv run python -m tools.cards.amiga_proof \
  --input "stage-reference=tools/cards/assets/amiga-ocs-portrait-v1/generation-reference-01.png" \
  --output-dir /tmp/amiga-proof
```

Future renderer families can register another driver implementing the typed
renderer/assembler interface and its validated style sections. The current
release registers only `amiga-ocs`; alternate raster families remain examples
for that extension boundary, not user-facing options.
