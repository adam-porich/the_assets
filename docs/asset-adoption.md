# Canonical asset adoption

Runtime files are experiments until they are deliberately adopted. Adoption copies the exact file worth keeping into Git with enough provenance to identify it, audit its use, and trace how it was made.

## Canonical layout

Each asset owns one directory and one immutable primary file:

```text
assets/<asset-id>/
├── asset.json
└── source.<original-extension>
```

Use a stable lowercase kebab-case ID. Preserve the highest-quality original bytes and extension; do not adopt a thumbnail or preview unless that preview is intentionally the finished work. A materially changed file is a new asset with a new ID. Derivatives and related files are separate assets connected through lineage.

The manifest contract is [the version 1 JSON Schema](../schemas/asset-v1.schema.json). Existing manifests under `assets/` are copyable examples.

## Agent checklist

When asked to adopt an asset:

1. Identify the exact source file and what role makes it worth retaining.
2. Capture the original filename, creator/provider, stable source URL or external ID, and acquisition or creation timestamp when available.
3. Capture rights: license, license URL, attribution, and usage constraints. If any of this is unknown, say so, explain what is missing, and set `review_required` to `true`.
4. For generated work, capture the generator/provider, exact model, complete prompt, parameters, and ordered canonical input/reference asset IDs with their checksums.
5. For deterministic derivatives, capture the tool/process and canonical parent assets.
6. Copy the selected bytes to `assets/<asset-id>/source.<ext>`, create `asset.json`, and calculate byte size and SHA-256 from the copied file.
7. Update consumers to point at the canonical source. Consumer-specific roles and recipes belong in their own configuration, not in `asset.json`.
8. Run `uv run python -m tools.assets validate` and the affected tests before committing.

Never invent missing provenance. Use `status: "incomplete"` when some history is known or `status: "unknown"` when it is not. Unknown rights are permitted for internal work only when visibly marked for review.

## Complete generated example

```json
{
  "$schema": "../../schemas/asset-v1.schema.json",
  "schema_version": 1,
  "id": "example-generated-texture",
  "title": "Example generated texture",
  "description": "A seamless stone texture adopted for the environment renderer.",
  "file": {
    "path": "source.png",
    "media_type": "image/png",
    "bytes": 123456,
    "sha256": "<64 lowercase hexadecimal characters>",
    "dimensions": {"width": 1024, "height": 1024}
  },
  "provenance": {
    "kind": "generated",
    "status": "complete",
    "original_filename": "provider-output.png",
    "provider": "OpenAI",
    "created_at": "2026-08-11T00:00:00Z",
    "generation": {
      "generator": "OpenAI image generation",
      "model": "exact-model-id",
      "prompt": "The complete prompt sent to the model.",
      "parameters": {"quality": "high"},
      "inputs": [
        {"asset_id": "canonical-input-id", "sha256": "<input checksum>", "role": "identity"}
      ]
    }
  },
  "rights": {
    "status": "known",
    "review_required": false,
    "license": "Project-owned generated output",
    "notes": "Approved for use under the project's provider terms."
  },
  "adoption": {
    "adopted_at": "2026-08-11T00:00:00Z",
    "from_path": "portrait-library/production/<batch>/masters/<file>"
  }
}
```

For an acquired asset, use `kind: "acquired"` and record its source and rights instead of `generation`. For an unknown source, use `kind: "unknown"`, `status: "unknown"`, and explanatory notes.
