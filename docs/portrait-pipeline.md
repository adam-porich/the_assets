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

Optional model-based background removal uses `rembg` as a separate extra. Do not install it for the base pipeline:

```bash
uv sync --extra dev --extra background
```

Do not install CUDA, PyTorch, Stable Diffusion, or ComfyUI for this pipeline. The target machine is an old i7-3770K / GTX 680 Windows host running primarily in WSL2, so this tool intentionally keeps the base path CPU-friendly and Pillow-first.

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

Run a controlled background-removal comparison before deciding whether heavier processing is worth it:

```bash
uv run python -m tools.portraits background \
  --input portrait-library/sources \
  --modes none,classical \
  --size 64
```

Available modes:

```text
none       no removal; records a full white mask and neutral composite baseline
classical  deterministic corner-colour edge flood mask with feathering
model      optional rembg mask; requires uv sync --extra background
```

Model mode is intentionally opt-in:

```bash
uv run python -m tools.portraits background \
  --input portrait-library/sources \
  --modes none,classical,model
```

For each source and mode, the benchmark writes:

```text
portrait-library/
  masks/
  foregrounds/
  backgrounds/
  candidates/
```

The lookbook shows the mask itself, the transparent foreground, the neutral-background composite, pixel variants derived from that composite, duration, and any mode error. Inspecting the mask is the point of this benchmark; otherwise it is hard to tell whether a bad portrait came from segmentation or later stylisation.

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

If background benchmarks exist, they are shown below each source with mask previews and timings.

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
2. Background removal: compare none / classical / model masks
3. Filter review: compare low-resolution variants from the best source or background mode
```

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

## Manual Scoring

Record comparison scores in `manifest.json`:

```bash
uv run python -m tools.portraits score \
  --photo-id 123 \
  --pipeline classical/edge24 \
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
