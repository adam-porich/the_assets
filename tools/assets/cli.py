from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "assets"
SCHEMA_PATH = ROOT / "schemas" / "asset-v1.schema.json"


def _label(path: Path) -> Path:
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_manifests(paths: Iterable[str] = ()) -> list[Path]:
    requested = [Path(value) for value in paths]
    if not requested:
        return sorted(ASSET_ROOT.glob("*/asset.json"))
    manifests: list[Path] = []
    for requested_path in requested:
        path = requested_path if requested_path.is_absolute() else ROOT / requested_path
        if path.is_dir():
            direct_manifest = path / "asset.json"
            if direct_manifest.is_file():
                manifests.append(direct_manifest)
            else:
                manifests.extend(sorted(path.glob("*/asset.json")))
        else:
            manifests.append(path)
    return sorted(set(manifests))


def validate_assets(paths: Iterable[str] = ()) -> list[str]:
    errors: list[str] = []
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{SCHEMA_PATH}: cannot load schema: {exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    manifests = discover_manifests(paths)
    if not manifests:
        return ["no asset.json manifests found"]

    records: dict[str, tuple[Path, dict[str, Any]]] = {}
    for manifest in manifests:
        label = _label(manifest)
        try:
            record = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{label}: cannot load manifest: {exc}")
            continue
        for failure in sorted(validator.iter_errors(record), key=lambda item: list(item.absolute_path)):
            location = ".".join(str(part) for part in failure.absolute_path) or "<root>"
            errors.append(f"{label}: {location}: {failure.message}")
        asset_id = record.get("id")
        if not isinstance(asset_id, str):
            continue
        if asset_id != manifest.parent.name:
            errors.append(f"{label}: id must match directory name {manifest.parent.name!r}")
        if asset_id in records:
            errors.append(f"{label}: duplicate asset id {asset_id!r} also used by {records[asset_id][0]}")
        records[asset_id] = (manifest, record)

        file_record = record.get("file") or {}
        relative_source = Path(str(file_record.get("path") or ""))
        source = manifest.parent / relative_source
        if relative_source.parent != Path(".") or source.parent.resolve() != manifest.parent.resolve():
            errors.append(f"{label}: file.path must name a direct child of the asset directory")
            continue
        if not source.is_file():
            errors.append(f"{label}: source file does not exist: {relative_source}")
            continue
        unexpected = sorted(path.name for path in manifest.parent.iterdir() if path.is_file() and path not in {manifest, source})
        if unexpected:
            errors.append(f"{label}: unexpected files in asset directory: {', '.join(unexpected)}")
        if file_record.get("bytes") != source.stat().st_size:
            errors.append(f"{label}: file.bytes does not match {relative_source}")
        digest = _sha256(source)
        if file_record.get("sha256") != digest:
            errors.append(f"{label}: file.sha256 does not match {relative_source}")
        guessed_type = mimetypes.guess_type(source.name)[0]
        if guessed_type and file_record.get("media_type") != guessed_type:
            errors.append(f"{label}: file.media_type must be {guessed_type!r} for {source.name}")
        if str(file_record.get("media_type") or "").startswith("image/"):
            try:
                with Image.open(source) as image:
                    actual_dimensions = {"width": image.width, "height": image.height}
                    image.verify()
                if file_record.get("dimensions") != actual_dimensions:
                    errors.append(f"{label}: file.dimensions does not match {relative_source}")
            except Exception as exc:
                errors.append(f"{label}: source is not a readable image: {exc}")

    for asset_id, (manifest, record) in records.items():
        provenance = record.get("provenance") or {}
        lineage = provenance.get("generation") or provenance.get("derivation") or {}
        for index, item in enumerate(lineage.get("inputs") or []):
            target_id = item.get("asset_id")
            if target_id not in records:
                errors.append(f"{_label(manifest)}: lineage input {index} refers to unknown asset {target_id!r}")
                continue
            expected = records[target_id][1].get("file", {}).get("sha256")
            if item.get("sha256") != expected:
                errors.append(f"{_label(manifest)}: lineage input {index} checksum does not match {target_id!r}")
        if asset_id in {item.get("asset_id") for item in lineage.get("inputs") or []}:
            errors.append(f"{_label(manifest)}: asset cannot list itself as a lineage input")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate canonical adopted assets")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate manifests, source files, and lineage")
    validate.add_argument("paths", nargs="*", help="asset.json files or asset directories; defaults to all assets")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors = validate_assets(args.paths)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Validated {len(discover_manifests(args.paths))} canonical assets")
    return 0
