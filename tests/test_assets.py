from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from tools.assets.cli import ROOT, validate_assets


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
    assert any("lineage input 0 checksum" in error for error in validate_assets([str(tmp_path)]))
