# Asset Workbench

Asset Workbench turns prepared image Inputs into pixel-native cards:

```text
Inputs → Pipeline → Candidates → Collection
```

## Start it

```bash
uv run python -m tools.portraits workbench-server
npm install
npm run dev
```

Set `PEXELS_API_KEY` to enable image search and `OPENROUTER_API_KEY` for live
image generation. Runtime data is stored in the ignored `portrait-library/`.

Files promoted from runtime experiments into durable repository assets follow
the canonical `asset.json` plus `source.<ext>` contract documented in
[docs/asset-adoption.md](docs/asset-adoption.md). Validate them with
`uv run python -m tools.assets validate`.

### For agents adopting generated work

List the current human-curated Collection, including every available artifact
representation and its stable batch/item IDs:

```bash
uv run python -m tools.assets catalog --favorites
```

Then follow the [workbench adoption procedure](docs/asset-adoption.md#adopting-asset-workbench-output)
to promote the chosen `foreground`, `art`, `card`, or other representation with
its full generation lineage. For `the_estate_agent`, `art` is the normal choice
when its own UI supplies the frame; copy the resulting complete asset folder so
the provenance manifest travels with the image.

## Workflow

### Inputs

Upload an image or choose a Pexels result to open the preparation dialog. The
dialog shows the original beside a generative preparation preview and exposes
the cleanup prompt and quality. `OK` accepts the displayed
result without another call. Only accepted Inputs are
available to Pipeline and Candidates. Clicking an existing Input reopens it for
inspection or replacement.

### Pipeline

Pipelines now contain one style prompt. They combine a prepared Input with
ordered style-only references, then pass the generated master through the
deterministic Amiga renderer and card assembler. Pipeline trials can compare up
to three accepted Inputs and cost one provider call per Input.

### Candidates

Each Input has a pack showing its three newest accepted cards. `Generate new`
opens a preparation dialog where you choose the pipeline, add an optional
content direction while its style prompt stays locked,
generate a preview, and rerun until the result is worth accepting. Only `OK ·
Add to pack` promotes that preview into the pack. Older accepted candidates
remain stored when they scroll out. Open a
candidate to inspect the Input, styled master, rendered art, final card, and
provenance. Generation produces an isolated foreground; deterministic renderer
presets supply the background afterward. Background and palette changes do not
call the image model and can be previewed before saving a new render revision.
Candidate details also lets you compare the original fixed house foreground
palette with an adaptive OCS foreground palette. Adaptive keeps ten stable UI
anchors and selects the remaining 22 registers from the subject. The background
uses its own derived 16-colour OCS palette, so it cannot consume or shift the
foreground colours.

### Collection

Favorite any number of candidates into Collection. Removing a favorite does
not delete its candidate, and saved rerenders are reflected automatically.

### Batches

`Batches` is the raw generation archive. It lists every attempt, including
unaccepted previews and failed runs, and opens all retained pipeline artifacts:
Input, raw model output, matted foreground, background composite, logical art,
rendered art, and card. Artifact images link to their full-resolution files.

## Routes

The refreshable hashes are `#inputs`, `#pipelines`,
`#pipelines/<pipeline-id>`, `#candidates`,
`#candidates/<batch-id>/<item-id>`, and `#collection`. Legacy `#sources` and
`#cards` hashes redirect to their current surfaces.

## Provenance and storage

Accepted Inputs retain the original image, normalized image, prompts, model,
quality, usage, costs, checksums, and timestamps. Production batches snapshot
the accepted normalized bytes plus their pipeline and reference configuration.
Target examples are renderer proofs and are never sent to providers.

```text
portrait-library/inputs/<input-id>/...
portrait-library/styles/versions/<style-version>/...
portrait-library/production/<batch>/inputs/...
portrait-library/production/<batch>/masters/...
portrait-library/production/<batch>/renders/...
portrait-library/favorites.json
```

Only one image-generation operation runs at a time. Live normalization,
candidate previews, trials, retries, and `Generate another` require explicit
consent.

## Verification

```bash
uv run --extra dev pytest -q
npm test -- --run
npm run build
git diff --check
```

The detailed contract is in [docs/portrait-workbench.md](docs/portrait-workbench.md).

## Hosting

The workbench is served at `/assets/`. Its app binds to `127.0.0.1:5182`, its API
binds to `127.0.0.1:8765`, and Tailscale Serve maps the app path to the frontend.
