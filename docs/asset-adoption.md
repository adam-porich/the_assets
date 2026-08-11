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

## Adopting Asset Workbench output

The ignored `portrait-library/` is the working catalog. Start with Collection because favorites are the current human-curated candidates:

```bash
uv run python -m tools.assets catalog --favorites
```

This inventory is machine-local because `portrait-library/` is intentionally not stored in Git. If the command reports that the production catalog is unavailable, the agent needs access to the Asset Workbench machine or an already adopted canonical asset; it must not regenerate a substitute silently.

Use `--json` when selecting programmatically. Each result supplies the stable batch and item IDs, content direction, source label, and available representations.

| Artifact | What it contains | Typical use |
| --- | --- | --- |
| `source-input` | Accepted normalized Input snapshot | Regeneration or identity reference |
| `generated` | Raw model output, normally on a chroma-key field | Generation audit or reprocessing |
| `foreground` | Full-resolution extracted alpha foreground | New layouts or renderers |
| `composite` | Full-resolution foreground plus deterministic background | Alternate downstream processing |
| `logical-art` | Native logical-pixel artwork | Exact low-resolution data |
| `art` | Integer-enlarged rendered artwork without card chrome | Recommended for another game's own UI or card frame |
| `card` | Complete assembled card image | Use only when the baked Asset Workbench frame is wanted |

Promote the selected representation with its workbench provenance:

```bash
uv run python -m tools.assets adopt-production \
  --batch batch_91a4df48e70a \
  --item item_43a94789d906 \
  --artifact art \
  --id friendly-wizard-portrait \
  --title "Friendly wizard portrait" \
  --description "Rendered claimant artwork selected for The Estate Agent."
```

The command refuses to overwrite an existing asset, copies the exact bytes into `assets/<id>/`, reconstructs generation and deterministic-render provenance from `batch.json`, and validates the result. It makes no provider call.

To consume the result from another repository such as `the_estate_agent`, copy the whole canonical folder—not only the PNG—into that repository's chosen asset location and then update its application references. The portable manifest keeps the source-repository batch/item IDs and can still be checked from this repository:

```bash
uv run python -m tools.assets validate /home/gimo/dev/the_estate_agent/<asset-directory>/<id>
```

Selection is intentionally separate from adoption: an agent may inventory and inspect anything without writing files, but must be told which candidate and representation are relevant to the consuming product.

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
