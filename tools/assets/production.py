from __future__ import annotations

import copy
import hashlib
import json
import mimetypes
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ARTIFACT_FIELDS = {
    "source-input": "source_input_path",
    "normalised": "normalised_path",
    "generated": "raw_foreground_path",
    "foreground": "foreground_path",
    "composite": "master_path",
    "logical-art": "logical_art_path",
    "art": "art_path",
    "card": "card_path",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_library_path(library: Path, value: str) -> Path:
    library = library.resolve()
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"runtime asset path must remain inside {library}: {value}")
    result = (library / relative).resolve()
    if not result.is_relative_to(library):
        raise ValueError(f"runtime asset path escapes {library}: {value}")
    if not result.is_file():
        raise ValueError(f"runtime asset is missing: {result}")
    return result


def _artifact_paths(item: dict[str, Any]) -> dict[str, str]:
    result = {name: str(item.get(field)) for name, field in ARTIFACT_FIELDS.items() if item.get(field)}
    if "generated" not in result and item.get("master_path") and not item.get("foreground_path"):
        result["generated"] = str(item["master_path"])
        result.pop("composite", None)
    return result


def catalog(library: Path, *, favorites_only: bool = False) -> list[dict[str, Any]]:
    library = library.resolve()
    if not (library / "production").is_dir():
        raise ValueError(f"workbench production catalog is unavailable: {library / 'production'}")
    favorite_records = _read_json(library / "favorites.json").get("items", []) if (library / "favorites.json").is_file() else []
    favorites = {(str(entry.get("batch_id")), str(entry.get("item_id"))) for entry in favorite_records}
    records: list[dict[str, Any]] = []
    for batch_path in sorted((library / "production").glob("batch_*/batch.json")):
        batch = _read_json(batch_path)
        batch_id = str(batch.get("batch_id") or batch_path.parent.name)
        for item in batch.get("items") or []:
            item_id = str(item.get("item_id") or "")
            is_favorite = (batch_id, item_id) in favorites
            artifacts = _artifact_paths(item)
            if favorites_only and not is_favorite:
                continue
            if not artifacts:
                continue
            records.append({
                "batch_id": batch_id,
                "item_id": item_id,
                "source_label": item.get("source_label") or item.get("source_id"),
                "content_direction": item.get("content_direction"),
                "created_at": item.get("created_at") or batch.get("created_at"),
                "phase": item.get("phase"),
                "accepted": bool(item.get("accepted")),
                "favorite": is_favorite,
                "artifacts": artifacts,
            })
    return sorted(records, key=lambda entry: (str(entry.get("created_at") or ""), entry["batch_id"], entry["item_id"]), reverse=True)


def _runtime_input(reference: dict[str, Any]) -> dict[str, str] | None:
    runtime_id = reference.get("source_id") or reference.get("reference_id")
    source_path = reference.get("input_path")
    digest = reference.get("checksum_sha256") or reference.get("input_checksum_sha256")
    if not runtime_id or not source_path or not digest:
        return None
    return {"runtime_id": str(runtime_id), "source_path": str(source_path), "sha256": str(digest), "role": str(reference.get("role") or "input")}


def _generation(item: dict[str, Any]) -> dict[str, Any] | None:
    request = item.get("generation_request") or {}
    result = item.get("generation") or {}
    prompt = request.get("instruction") or item.get("prompt_override")
    model = request.get("model") or result.get("model")
    if not prompt or not model:
        return None
    inputs = [value for reference in item.get("reference_stack") or [] if (value := _runtime_input(reference))]
    parameters = {
        key: value for key, value in {
            "quality": request.get("quality"),
            "seed": request.get("seed") or result.get("seed"),
            "effective_aspect_ratio": request.get("effective_aspect_ratio") or result.get("effective_aspect_ratio"),
            "content_direction": item.get("content_direction"),
        }.items() if value is not None
    }
    return {
        "generator": str(result.get("backend") or "Asset Workbench image generation"),
        "model": str(model),
        "prompt": str(prompt),
        "parameters": parameters,
        "inputs": inputs,
    }


def _immediate_parent(item: dict[str, Any], artifact: str) -> tuple[str, str] | None:
    candidates = {
        "foreground": (("raw_foreground_path", "generated-output"), ("master_path", "generated-output")),
        "composite": (("foreground_path", "isolated-foreground"),),
        "logical-art": (("master_path", "composite"), ("foreground_path", "isolated-foreground")),
        "art": (("master_path", "composite"), ("foreground_path", "isolated-foreground")),
        "card": (("art_path", "rendered-art"),),
    }
    for field, role in candidates.get(artifact, ()):
        if item.get(field):
            return str(item[field]), role
    return None


def _derivation(library: Path, item: dict[str, Any], artifact: str) -> dict[str, Any] | None:
    parent = _immediate_parent(item, artifact)
    if not parent:
        return None
    parent_path, role = parent
    source = _resolve_library_path(library, parent_path)
    render = item.get("render_metadata") or {}
    process = {
        "foreground": "Extract alpha foreground from the generated chroma-key output.",
        "composite": "Composite the isolated foreground onto the selected deterministic background.",
        "logical-art": "Reduce the composite to the renderer's logical pixel dimensions and palette.",
        "art": "Render and enlarge the logical artwork using the recorded deterministic renderer settings.",
        "card": "Assemble the rendered artwork into the deterministic card frame.",
    }[artifact]
    parameters = {
        key: copy.deepcopy(value) for key, value in {
            "matte_metadata": item.get("matte_metadata") if artifact == "foreground" else None,
            "background_id": item.get("background_id") if artifact == "composite" else None,
            "background_metadata": item.get("background_metadata") if artifact == "composite" else None,
            "framing": item.get("framing"),
            "palette_mode": item.get("palette_mode") if artifact in {"logical-art", "art", "card"} else None,
            "render_metadata": item.get("render_metadata") if artifact in {"logical-art", "art", "card"} else None,
            "render_revision": item.get("render_revision") if artifact in {"logical-art", "art", "card"} else None,
        }.items() if value is not None
    }
    return {
        "tool": str(render.get("driver_id") or ("Asset Workbench card assembler" if artifact == "card" else "Asset Workbench")),
        "process": process,
        "parameters": parameters,
        "inputs": [{"runtime_id": f"{item.get('item_id')}:{role}", "source_path": parent_path, "sha256": _sha256(source), "role": role}],
    }


def adopt_production_asset(
    library: Path,
    output_root: Path,
    *,
    batch_id: str,
    item_id: str,
    artifact: str,
    asset_id: str,
    title: str,
    description: str,
) -> Path:
    library = library.resolve()
    output_root = output_root.resolve()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", asset_id):
        raise ValueError("asset ID must use lowercase kebab-case")
    if not re.fullmatch(r"batch_[A-Za-z0-9]+", batch_id):
        raise ValueError("invalid production batch ID")
    if not title.strip() or not description.strip():
        raise ValueError("title and description are required")
    batch_path = library / "production" / batch_id / "batch.json"
    batch = _read_json(batch_path)
    item = next((entry for entry in batch.get("items") or [] if str(entry.get("item_id")) == item_id), None)
    if not item:
        raise ValueError(f"item {item_id!r} does not exist in {batch_id!r}")
    artifacts = _artifact_paths(item)
    if artifact not in artifacts:
        available = ", ".join(sorted(artifacts)) or "none"
        raise ValueError(f"artifact {artifact!r} is unavailable; choose one of: {available}")
    source_path = _resolve_library_path(library, artifacts[artifact])
    destination = output_root / asset_id
    if destination.exists():
        raise ValueError(f"refusing to replace existing asset directory: {destination}")
    extension = source_path.suffix.lower() or ".bin"
    destination.mkdir(parents=True)
    copied_source = destination / f"source{extension}"
    try:
        shutil.copy2(source_path, copied_source)
        media_type = mimetypes.guess_type(copied_source.name)[0] or "application/octet-stream"
        file_record: dict[str, Any] = {
            "path": copied_source.name,
            "media_type": media_type,
            "bytes": copied_source.stat().st_size,
            "sha256": _sha256(copied_source),
        }
        if media_type.startswith("image/"):
            with Image.open(copied_source) as image:
                file_record["dimensions"] = {"width": image.width, "height": image.height}

        generation = _generation(item)
        generated_artifacts = {"generated", "normalised"}
        derivation = _derivation(library, item, artifact)
        complete = bool(generation) and (artifact in generated_artifacts or derivation is not None)
        provenance: dict[str, Any] = {
            "kind": "generated" if artifact in generated_artifacts else "derived",
            "status": "complete" if complete else "incomplete",
            "original_filename": source_path.name,
            "provider": str((item.get("generation") or {}).get("backend") or "Asset Workbench"),
            "created_at": str(item.get("finished_at") or batch.get("finished_at") or batch.get("created_at")),
        }
        if generation:
            provenance["generation"] = generation
        if derivation:
            provenance["derivation"] = derivation
        if not complete:
            provenance["notes"] = "The workbench record did not retain enough information to reconstruct complete generation and immediate derivation provenance."

        manifest = {
            "$schema": "https://raw.githubusercontent.com/adam-porich/the_assets/master/schemas/asset-v1.schema.json",
            "schema_version": 1,
            "id": asset_id,
            "title": title,
            "description": description,
            "file": file_record,
            "provenance": provenance,
            "rights": {
                "status": "unknown",
                "review_required": True,
                "notes": "Generated-output rights must be reviewed against the recorded provider terms before external distribution.",
            },
            "adoption": {
                "adopted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "from_path": str(artifacts[artifact]),
                "runtime_ids": {"batch_id": batch_id, "item_id": item_id, "artifact": artifact},
            },
        }
        (destination / "asset.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return destination
