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

## Workflow

### Inputs

Upload an image or choose a Pexels result to open the preparation dialog. The
dialog shows the original beside a prepared preview. The default `Preserve`
mode only scales and pads the original pixels and is free; `Reconstruct` enables
the paid generative cleanup prompt and quality. `OK` accepts the displayed
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
provenance. Framing changes do not call the image model.
Candidate details also lets you compare the original fixed house palette with
an adaptive OCS palette. Adaptive keeps ten stable UI anchors and selects the
remaining 22 registers from the image, while preserving the 32-colour limit.

### Collection

Favorite any number of candidates into Collection. Removing a favorite does
not delete its candidate, and rerendered framing is reflected automatically.

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
