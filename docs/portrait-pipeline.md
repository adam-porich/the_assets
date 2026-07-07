# Portrait Candidate Pipeline

This is an experimental claimant portrait source and img2img stylization pipeline. It searches Pexels through the official API, downloads selected portrait candidates with provenance metadata, prepares crops with `rembg`, sends controlled composites to a pluggable img2img backend, and generates a static HTML lookbook.

It does not integrate portraits into any game.

## WSL2 Setup

Run the repository from the WSL filesystem, not `/mnt/c`, for better filesystem performance:

```bash
mkdir -p ~/src
cd ~/src/the_assets
uv sync --extra dev
```

Optional face detection uses OpenCV. The pipeline still works without it by using deterministic centre crops.

```bash
uv sync --extra dev --extra face
```

Optional model-based background removal uses `rembg` as a separate extra. Do not install it for the base pipeline:

```bash
uv sync --extra dev --extra background
```

Do not install CUDA, PyTorch, Stable Diffusion, or ComfyUI as base dependencies for this repository. The target machine is an old i7-3770K / GTX 680 Windows host running primarily in WSL2, so experiments must stay short. The default claimant preset uses 384x384, 6 steps, 1 candidate per source, and the `stylize` command defaults to `--limit 3`.

## Pexels API Key

Create an API key from Pexels and export it before fetching:

```bash
export PEXELS_API_KEY="..."
```

The key is read only from `PEXELS_API_KEY`. Do not commit `.env` or the key. `.env.example` documents the variable name, but this project does not require a dotenv dependency.

Alternatively, put the same assignment in `~/.env` or a local ignored `.env` file in the repository root:

```bash
PEXELS_API_KEY="..."
```

If both files exist, the repo-local `.env` wins. An already exported shell variable wins over both files.

## Fetch Sources

```bash
uv run python -m tools.portraits fetch \
  --query "characterful portrait unusual hat" \
  --count 20 \
  --orientation portrait
```

Useful options:

```bash
uv run python -m tools.portraits fetch --query "stern older person portrait" --count 20 --dry-run
uv run python -m tools.portraits fetch --query "formal uniform portrait" --page 2 --per-page 40
```

Search presets live in `tools/portraits/presets.txt`. They are experimental prompts for cheap query iteration, not guaranteed-good searches.

The fetch command uses the official Pexels API. It does not scrape the Pexels website.

## Process Candidates

This legacy command remains available for cheap deterministic checks, but it is no longer the primary evaluation path.

```bash
uv run python -m tools.portraits process \
  --input portrait-library/sources \
  --size 64 \
  --variants clean16,clean24,dither24,edge24
```

Supported sizes:

```bash
--size 48
--size 64
--size 96
```

Background options:

```bash
--background keep
--background flatten
--background vignette
```

Optional fixed palette:

```bash
uv run python -m tools.portraits process \
  --input portrait-library/sources \
  --palette tools/portraits/palettes/estate-neutral.json
```

Default outputs are deterministic for the same source file and settings.

## Background Benchmark

Run rembg preparation directly. Classical background removal was too noisy on real portrait inputs and is no longer part of the normal CLI workflow.

```bash
uv run --extra background python -m tools.portraits background \
  --input portrait-library/sources \
  --modes model \
  --size 64
```

Available modes:

```text
model      rembg mask; requires uv sync --extra background
none       debugging baseline only
```

The primary preparation path is:

```text
crop -> rembg mask -> transparent foreground -> controlled RGB composite
```

For each source and mode, the benchmark writes:

```text
portrait-library/
  masks/
  foregrounds/
  backgrounds/
  candidates/
```

The lookbook shows the mask itself, the transparent foreground, the controlled composite, duration, and any mode error. Inspecting the mask is still useful, but the main experiment is now whether img2img improves claimant portraits enough to justify its cost.

## Img2img Stylization

Stylization uses a pluggable backend. The recommended hosted backend is `openrouter`, which sends the rembg composite as an OpenRouter Image API reference image and downloads the returned image into `portrait-library/stylized/`.

Configure OpenRouter in the shell or `~/.env`:

```bash
OPENROUTER_API_KEY="..."
OPENROUTER_IMAGE_MODEL="openai/gpt-image-1-mini"
OPENROUTER_IMAGE_QUALITY="low"
```

The default model is `openai/gpt-image-1-mini` at `low` quality because the current goal is cheap experimentation. Override `OPENROUTER_IMAGE_MODEL` if a different OpenRouter image model gives better stylized claimant portraits.

The fallback backend is `external`: the portrait tool writes an img2img request JSON file and calls a configured command. That command can wrap OpenVINO, ComfyUI, Automatic1111, a cloud runner, or any later backend without changing the manifest shape.

Configure the external command in the shell or `~/.env`:

```bash
export PORTRAIT_IMG2IMG_COMMAND="/path/to/img2img-wrapper"
```

The wrapper receives the request JSON path as its final argument and must print JSON to stdout:

```json
{
  "results": [
    {
      "image_path": "portrait-library/stylized/pexels-123-estate-pixel-claimant-v1-42-raw.png",
      "backend": "external",
      "model": "your-model-name",
      "seed": 42,
      "strength": 0.45,
      "steps": 6,
      "guidance": 6,
      "prompt": "...",
      "negative_prompt": "...",
      "elapsed_seconds": 8.4
    }
  ]
}
```

Run one source:

```bash
uv run --extra background python -m tools.portraits stylize \
  --input portrait-library \
  --preset estate-pixel-claimant-v1 \
  --backend openrouter \
  --photo-id 123
```

Run a short batch. The default limit is already 3 to avoid accidental long CPU jobs:

```bash
uv run --extra background python -m tools.portraits stylize \
  --input portrait-library \
  --preset estate-pixel-claimant-v1 \
  --backend openrouter \
  --review-status add
```

Override carefully:

```bash
uv run --extra background python -m tools.portraits stylize \
  --input portrait-library \
  --preset estate-pixel-claimant-v1 \
  --backend openrouter \
  --limit 3 \
  --count 1
```

Prompt presets live in:

```text
tools/portraits/presets/
  estate-pixel-claimant-v1.json
```

The current preset is intentionally conservative for CPU experiments: 384x384, 6 steps, 1 candidate per source.

Each stylized candidate records:

```json
{
  "source_photo_id": 123,
  "background_mode": "neutral-dark",
  "mask_mode": "rembg",
  "preset": "estate-pixel-claimant-v1",
  "backend": "external",
  "model": "...",
  "prompt": "...",
  "negative_prompt": "...",
  "seed": 12345,
  "strength": 0.45,
  "steps": 6,
  "guidance": 6,
  "elapsed_seconds": 8.4,
  "created_at": "...",
  "input_composite_path": "...",
  "output_path": "...",
  "final_output_path": "..."
}
```

## Harvest

Fetch, process, and build a lookbook in one command:

```bash
uv run python -m tools.portraits harvest \
  --query "eccentric portrait costume" \
  --count 20 \
  --process \
  --lookbook
```

## Generated Files

```text
portrait-library/
  manifest.json
  sources/
    pexels-123-original.jpg
  crops/
    pexels-123-crop.png
  candidates/
  masks/
  foregrounds/
  composites/
  stylized/
    pexels-123-estate-pixel-claimant-v1-42-raw.png
    pexels-123-estate-pixel-claimant-v1-42-final.png
  lookbook/
    index.html
    thumbnails/
```

Open generated results from WSL in Windows Explorer:

```bash
explorer.exe "$(wslpath -w portrait-library)"
explorer.exe "$(wslpath -w portrait-library/lookbook/index.html)"
```

## Lookbook

```bash
uv run python -m tools.portraits lookbook --input portrait-library
```

The lookbook groups each source with its crop, rembg preparation, img2img candidates, and selected/tagged candidates.

If legacy background benchmarks or deterministic variants exist, they are shown below the primary img2img review area.

The top of the lookbook has a sticky horizontal picker for jumping between source images, plus filters for:

```text
all
favorites
added
rejected
unreviewed
```

Because the lookbook is static HTML, its Favorite, Reject, Add, and Lookbook controls copy CLI commands. Run the copied command in WSL, then regenerate the lookbook.

It has no external JavaScript dependency.

## Source Review

Use source review before spending time on background removal and filters:

```bash
uv run python -m tools.portraits favorite --photo-id 123 --note "great hat and silhouette"
uv run python -m tools.portraits reject --photo-id 456 --note "too corporate"
uv run python -m tools.portraits add --photo-id 789 --note "send to background benchmark"
```

Equivalent explicit command:

```bash
uv run python -m tools.portraits review --photo-id 123 --status favorite
uv run python -m tools.portraits review --photo-id 123 --status clear
```

The intended workflow is:

```text
1. Source review: favorite / reject / add
2. Rembg preparation: inspect mask and controlled composite
3. Img2img review: choose whether a generated claimant candidate is good enough to keep
```

## Manual Selection

```bash
uv run python -m tools.portraits select \
  --photo-id 123 \
  --variant estate-pixel-claimant-v1:12345 \
  --tag audit \
  --tag claimant
```

Selection updates `manifest.json`; it does not duplicate candidate files. Regenerate the lookbook afterward to see the selection highlighted:

```bash
uv run python -m tools.portraits lookbook --input portrait-library
```

## Manual Scoring

Record comparison scores in `manifest.json`:

```bash
uv run python -m tools.portraits score \
  --photo-id 123 \
  --pipeline estate-pixel-claimant-v1:12345 \
  --likeness 4 \
  --silhouette 3 \
  --pixel-art-quality 4 \
  --game-fit 4 \
  --manual-cleanup-needed minor \
  --notes "hat survived, collar needs cleanup"
```

Scores appear in the lookbook. The intended scoring scale is:

```text
likeness: 1-5
silhouette: 1-5
pixel-art quality: 1-5
game fit: 1-5
manual cleanup needed: none / minor / major
```

## Provenance And Licensing Caveats

Each downloaded source records Pexels provenance including photo ID, source page, photographer, photographer URL, selected image URL, original image URL, dimensions, checksum, query, local filename, processing status, face bounding box when detected, and the Pexels license page.

This metadata is provenance for later review. It is not proof of permanent licensing.

Pexels permits free use and modification, but recognizable people must not be portrayed offensively or used to imply endorsement. For a fictional infernal-bureaucracy game, treat this library as experimental art: retain provenance, strongly stylize portraits, avoid using source photographs untouched, flag especially prominent or sensitive portraits for replacement before release, and do not automatically assign insulting, criminal, or defamatory descriptions to identifiable source people.

This document is not legal advice.
