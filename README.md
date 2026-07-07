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
