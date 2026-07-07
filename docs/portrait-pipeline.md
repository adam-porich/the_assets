# Portrait Candidate Pipeline

This is an experimental claimant portrait source and pixel-art-style candidate pipeline. It searches Pexels through the official API, downloads selected portrait candidates with provenance metadata, produces deterministic low-resolution review images, and generates a static HTML lookbook.

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

Do not install CUDA, PyTorch, Stable Diffusion, ComfyUI, or background-removal packages for this pipeline. The target machine is an old i7-3770K / GTX 680 Windows host running primarily in WSL2, so this tool intentionally uses CPU-friendly Pillow processing.

## Pexels API Key

Create an API key from Pexels and export it before fetching:

```bash
export PEXELS_API_KEY="..."
```

The key is read only from `PEXELS_API_KEY`. Do not commit `.env` or the key. `.env.example` documents the variable name, but this project does not require a dotenv dependency.

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
    pexels-123-clean16-64.png
    pexels-123-clean24-64.png
    pexels-123-dither24-64.png
    pexels-123-edge24-64.png
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

The lookbook groups each source with its crop and processed variants, showing photographer, Pexels ID, query, dimensions, status, links, candidate filenames, and selected/tagged candidates.

It has no external JavaScript dependency.

## Manual Selection

```bash
uv run python -m tools.portraits select \
  --photo-id 123 \
  --variant edge24 \
  --tag audit \
  --tag claimant
```

Selection updates `manifest.json`; it does not duplicate candidate files. Regenerate the lookbook afterward to see the selection highlighted:

```bash
uv run python -m tools.portraits lookbook --input portrait-library
```

## Provenance And Licensing Caveats

Each downloaded source records Pexels provenance including photo ID, source page, photographer, photographer URL, selected image URL, original image URL, dimensions, checksum, query, local filename, processing status, face bounding box when detected, and the Pexels license page.

This metadata is provenance for later review. It is not proof of permanent licensing.

Pexels permits free use and modification, but recognizable people must not be portrayed offensively or used to imply endorsement. For a fictional infernal-bureaucracy game, treat this library as experimental art: retain provenance, strongly stylize portraits, avoid using source photographs untouched, flag especially prominent or sensitive portraits for replacement before release, and do not automatically assign insulting, criminal, or defamatory descriptions to identifiable source people.

This document is not legal advice.
