# The Assets

Experimental asset pipelines shared across game projects.

## Claimant Portrait Candidate Pipeline

This repository contains a small CPU-friendly portrait harvesting and processing tool:

```bash
uv run python -m tools.portraits fetch --query "eccentric portrait hat" --count 20
uv run python -m tools.portraits process --input portrait-library/sources --size 64
uv run python -m tools.portraits background --input portrait-library/sources --modes none,classical
uv run python -m tools.portraits lookbook --input portrait-library
```

Generated data lives in `portrait-library/` and is ignored by git by default.

See [docs/portrait-pipeline.md](docs/portrait-pipeline.md) for setup, usage, and provenance notes.
