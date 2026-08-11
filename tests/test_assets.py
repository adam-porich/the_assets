from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from tools.assets.cli import ROOT, validate_assets
from tools.assets.production import adopt_production_asset, catalog


def _record(asset_id: str, source: Path) -> dict:
    return {
        "$schema": "../../schemas/asset-v1.schema.json",
        "schema_version": 1,
        "id": asset_id,
        "title": "Test asset",
        "description": "A canonical asset used to exercise validation.",
        "file": {
            "path": source.name,
            "media_type": "image/png",
            "bytes": source.stat().st_size,
            "sha256": "68ca995a8d308963278a2047863886b382adc8cd1230d05952c017b659838efe",
            "dimensions": {"width": 1254, "height": 1254},
        },
        "provenance": {
            "kind": "unknown",
            "status": "unknown",
            "original_filename": "historical.png",
            "notes": "The test intentionally models an unknown historical source.",
        },
        "rights": {
            "status": "unknown",
            "review_required": True,
            "notes": "Rights require review.",
        },
        "adoption": {
            "adopted_at": "2026-08-11T00:00:00Z",
            "from_path": "legacy/historical.png",
        },
    }


def _write_asset(parent: Path, asset_id: str, record: dict | None = None) -> tuple[Path, dict]:
    directory = parent / asset_id
    directory.mkdir(parents=True)
    source = directory / "source.png"
    shutil.copy2(ROOT / "assets/amiga-ocs-generation-reference-01/source.png", source)
    value = record or _record(asset_id, source)
    (directory / "asset.json").write_text(json.dumps(value), encoding="utf-8")
    return directory, value


def test_all_repository_assets_validate() -> None:
    assert validate_assets() == []


def test_validator_detects_source_integrity_mismatch(tmp_path: Path) -> None:
    directory, record = _write_asset(tmp_path, "integrity-test")
    record["file"]["bytes"] += 1
    record["file"]["sha256"] = "0" * 64
    record["file"]["dimensions"]["width"] += 1
    (directory / "asset.json").write_text(json.dumps(record), encoding="utf-8")
    errors = validate_assets([str(directory)])
    assert any("file.bytes does not match" in error for error in errors)
    assert any("file.sha256 does not match" in error for error in errors)
    assert any("file.dimensions does not match" in error for error in errors)


def test_unknown_rights_must_be_reviewed(tmp_path: Path) -> None:
    directory, record = _write_asset(tmp_path, "rights-test")
    record["rights"]["review_required"] = False
    (directory / "asset.json").write_text(json.dumps(record), encoding="utf-8")
    assert any("True was expected" in error for error in validate_assets([str(directory)]))


def test_complete_generated_asset_requires_recipe(tmp_path: Path) -> None:
    directory, record = _write_asset(tmp_path, "generated-test")
    record["provenance"] = {
        "kind": "generated",
        "status": "complete",
        "original_filename": "output.png",
        "created_at": "2026-08-11T00:00:00Z",
    }
    (directory / "asset.json").write_text(json.dumps(record), encoding="utf-8")
    assert any("generation" in error for error in validate_assets([str(directory)]))


def test_generated_lineage_resolves_id_and_checksum(tmp_path: Path) -> None:
    _, parent = _write_asset(tmp_path, "parent-asset")
    child_dir, child = _write_asset(tmp_path, "child-asset")
    child["provenance"] = {
        "kind": "generated",
        "status": "complete",
        "original_filename": "output.png",
        "provider": "Example provider",
        "created_at": "2026-08-11T00:00:00Z",
        "generation": {
            "generator": "Example generator",
            "model": "example-model-v1",
            "prompt": "Generate the exact requested output.",
            "parameters": {},
            "inputs": [{"asset_id": "parent-asset", "sha256": parent["file"]["sha256"], "role": "reference"}],
        },
    }
    (child_dir / "asset.json").write_text(json.dumps(child), encoding="utf-8")
    assert validate_assets([str(tmp_path)]) == []
    broken = copy.deepcopy(child)
    broken["provenance"]["generation"]["inputs"][0]["sha256"] = "f" * 64
    (child_dir / "asset.json").write_text(json.dumps(broken), encoding="utf-8")
    assert any("generation input 0 checksum" in error for error in validate_assets([str(tmp_path)]))


def _production_library(path: Path) -> tuple[Path, str, str]:
    library = path / "library"
    batch_id = "batch_test"
    item_id = "item_test"
    batch_dir = library / "production" / batch_id
    source = ROOT / "assets/amiga-ocs-generation-reference-01/source.png"
    runtime_paths = {
        "input": batch_dir / "inputs/sources/input_test.png",
        "generated": batch_dir / "raw-foregrounds/item_test.png",
        "composite": batch_dir / "renders/item_test-r1-composite.png",
        "art": batch_dir / "renders/item_test-r1-art.png",
    }
    for destination in runtime_paths.values():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    digest = "68ca995a8d308963278a2047863886b382adc8cd1230d05952c017b659838efe"
    batch = {
        "batch_id": batch_id,
        "created_at": "2026-08-11T00:00:00Z",
        "finished_at": "2026-08-11T00:01:00Z",
        "items": [{
            "item_id": item_id,
            "phase": "complete",
            "accepted": True,
            "source_label": "Test source",
            "content_direction": "A useful claimant portrait.",
            "source_input_path": runtime_paths["input"].relative_to(library).as_posix(),
            "raw_foreground_path": runtime_paths["generated"].relative_to(library).as_posix(),
            "master_path": runtime_paths["composite"].relative_to(library).as_posix(),
            "art_path": runtime_paths["art"].relative_to(library).as_posix(),
            "generation_request": {"instruction": "Draw the exact subject.", "model": "provider/model", "quality": "medium", "seed": 7},
            "generation": {"backend": "test-provider", "model": "provider/model", "effective_aspect_ratio": "1:1"},
            "reference_stack": [{
                "role": "identity", "source_id": "input_test",
                "input_path": runtime_paths["input"].relative_to(library).as_posix(), "checksum_sha256": digest,
            }],
            "render_metadata": {"driver_id": "amiga-ocs", "driver_version": 3},
            "render_revision": 1,
            "palette_mode": "adaptive-hybrid",
            "framing": {"zoom": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        }],
    }
    (batch_dir / "batch.json").write_text(json.dumps(batch), encoding="utf-8")
    (library / "favorites.json").write_text(json.dumps({"version": 1, "items": [{"batch_id": batch_id, "item_id": item_id}]}), encoding="utf-8")
    return library, batch_id, item_id


def test_catalog_finds_curated_runtime_artifacts(tmp_path: Path) -> None:
    library, batch_id, item_id = _production_library(tmp_path)
    records = catalog(library, favorites_only=True)
    assert [(record["batch_id"], record["item_id"]) for record in records] == [(batch_id, item_id)]
    assert records[0]["favorite"] is True
    assert set(records[0]["artifacts"]) == {"source-input", "generated", "composite", "art"}


def test_adopt_production_builds_portable_valid_manifest(tmp_path: Path) -> None:
    library, batch_id, item_id = _production_library(tmp_path)
    destination = adopt_production_asset(
        library, tmp_path / "exports", batch_id=batch_id, item_id=item_id, artifact="art",
        asset_id="estate-claimant", title="Estate claimant", description="Selected game artwork.",
    )
    assert validate_assets([str(destination)]) == []
    manifest = json.loads((destination / "asset.json").read_text(encoding="utf-8"))
    assert manifest["adoption"]["runtime_ids"] == {"batch_id": batch_id, "item_id": item_id, "artifact": "art"}
    assert manifest["provenance"]["generation"]["prompt"] == "Draw the exact subject."
    assert manifest["provenance"]["generation"]["inputs"][0]["runtime_id"] == "input_test"
    assert manifest["provenance"]["derivation"]["parameters"]["render_metadata"]["driver_version"] == 3


def test_adopt_production_refuses_to_overwrite(tmp_path: Path) -> None:
    library, batch_id, item_id = _production_library(tmp_path)
    output = tmp_path / "exports"
    arguments = dict(batch_id=batch_id, item_id=item_id, artifact="generated", asset_id="estate-claimant", title="Estate claimant", description="Selected game artwork.")
    adopt_production_asset(library, output, **arguments)
    with pytest.raises(ValueError, match="refusing to replace"):
        adopt_production_asset(library, output, **arguments)


def test_adopt_production_rejects_unsafe_asset_id(tmp_path: Path) -> None:
    library, batch_id, item_id = _production_library(tmp_path)
    with pytest.raises(ValueError, match="lowercase kebab-case"):
        adopt_production_asset(
            library, tmp_path / "exports", batch_id=batch_id, item_id=item_id, artifact="art",
            asset_id="../outside", title="Unsafe", description="Must not escape the output root.",
        )
