# The Assets

Experimental asset pipelines shared across game projects.

## Claimant Portrait Candidate Pipeline

This repository contains a small CPU-friendly portrait harvesting and processing tool:

```bash
uv run python -m tools.portraits fetch --query "eccentric portrait hat" --count 20
uv run --extra background python -m tools.portraits background --input portrait-library/sources --modes model
uv run --extra background python -m tools.portraits stylize --input portrait-library --preset estate-pixel-claimant-v1 --backend openrouter --limit 3
uv run python -m tools.portraits lookbook --input portrait-library
```

Generated data lives in `portrait-library/` and is ignored by git by default.
Durable review decisions live in `portrait-review/review.json` and are tracked.

Run the React review app:

```bash
uv run python -m tools.portraits review-server
npm run dev
```

See [docs/portrait-pipeline.md](docs/portrait-pipeline.md) for setup, usage, and provenance notes.

## Experimental Card Context

Portrait candidates can now be promoted into reusable masters and placed into a
deterministic experimental card frame. This keeps the portrait generator and
the card presentation separate:

```bash
uv run python -m tools.portraits promote-master \
  --input portrait-library \
  --photo-id 123 \
  --candidate-id 'estate-pixel-claimant-v1:42' \
  --master-id claimant-123

uv run python -m tools.portraits render-card \
  --input portrait-library \
  --master-id claimant-123 \
  --archetype standard-bust \
  --label "Archive Claimant"
```

The review app's **Cards** tab shows these card-context previews. The first
template (`estate-card-v1`) and house style (`estate-card-v1`) are deliberately
small experimental contracts, documented in
[the card-pipeline plan](docs/card-asset-pipeline-plan.md).

Run `uv run python -m tools.portraits validate-cards` to check a small card
batch for missing provenance, mixed versions, or invalid render dimensions.
