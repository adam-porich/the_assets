from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from tools.cards.amiga import amiga_palette, palette_is_ocs_12_bit
from tools.cards.registry import registry
from tools.cards.style_pipeline import StyleStore, load_checked_in_style, style_checksum, validate_style
from tools.portraits.generation import FakeGenerationAdapter, GenerationResult, simulation_model
from tools.portraits.production import CardProductionManager
from tools.portraits.workspace import WorkspaceError, WorkspaceStore


ROOT = Path(__file__).parents[1]
ASSETS = ROOT / "tools/cards/assets/amiga-ocs-portrait-v1"


def source(store: WorkspaceStore, name: str = "portrait") -> dict:
    path = ROOT / "tools/cards/assets/amiga-ocs-portrait-v1/generation-reference-01.png"
    if name == "portrait":
        content = path.read_bytes()
    else:
        from io import BytesIO
        with Image.open(path) as opened:
            image = opened.convert("RGB")
            pixel = image.getpixel((0, 0)); image.putpixel((0, 0), (pixel[0], pixel[1], (pixel[2] + sum(ord(char) for char in name)) % 256))
            buffer = BytesIO(); image.save(buffer, format="PNG"); content = buffer.getvalue()
    return store.add_image_record("source", name, f"{name}.png", content, "image/png")


def wait_for(manager: CardProductionManager, batch_id: str) -> dict:
    for _ in range(200):
        record = manager.get(batch_id)
        if record["status"] not in {"queued", "running", "processing"}:
            return record
        time.sleep(0.02)
    raise AssertionError("production worker did not finish")


def test_style_schema_checksum_store_and_asset_snapshots(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    active = styles.active()
    assert active["identity"]["style_version_id"]
    assert active["identity"]["state"] == "locked"
    assert style_checksum(active) == active["checksums"]["style_sha256"]
    assert {asset["role"] for asset in active["reference_pack"]["assets"]} == {"generation-reference", "target-example"}
    assert all((tmp_path / "library" / asset["relative_path"]).is_file() for asset in active["reference_pack"]["assets"])
    with pytest.raises(WorkspaceError):
        store.absolute_path("../outside.png")
    draft = styles.create_or_resume_draft()
    changed = {**draft["renderer"], "dither": {**draft["renderer"]["dither"], "strength": 0.3}}
    edited = styles.update_draft({"renderer": changed})
    assert edited["checksums"]["style_sha256"] != active["checksums"]["style_sha256"]
    assert styles.active()["checksums"]["style_sha256"] == active["checksums"]["style_sha256"]
    locked = styles.lock_draft()
    assert locked["identity"]["state"] == "locked"
    assert all(asset["relative_path"].startswith(f"styles/versions/{locked['identity']['style_version_id']}/") for asset in locked["reference_pack"]["assets"])
    styles.activate(locked["identity"]["style_version_id"])
    assert styles.active()["identity"]["style_version_id"] == locked["identity"]["style_version_id"]
    assert len(styles.versions()) == 2


def test_legacy_simulation_style_is_migrated_to_current_locked_version(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    original = styles.raw_version(styles.active_id())
    original["generation"]["model_id"] = "fake/painterly-deterministic"
    original["checksums"]["style_sha256"] = style_checksum(original)
    store.atomic_json(styles._style_path(original["identity"]["style_version_id"]), original)

    migrated = styles.active()

    assert migrated["generation"]["model_id"] == load_checked_in_style()["generation"]["model_id"]
    assert migrated["identity"]["style_version_id"] != original["identity"]["style_version_id"]
    assert styles.raw_version(original["identity"]["style_version_id"])["generation"]["model_id"] == "fake/painterly-deterministic"
    assert len(styles.versions()) == 2


def test_amiga_registered_engine_is_deterministic_and_matches_golden() -> None:
    style = load_checked_in_style()
    with Image.open(ASSETS / "generation-reference-01.png") as master:
        first = registry.render(style, master, "stage reference")
        second = registry.render(style, master, "stage reference")
    with Image.open(ASSETS / "target-example-01.png") as target:
        assert first.art.size == (336, 276)
        assert first.card.size == (420, 600)
        assert first.art.tobytes() == target.tobytes()
    assert first.art.tobytes() == second.art.tobytes()
    assert first.card.tobytes() == second.card.tobytes()
    assert palette_is_ocs_12_bit(amiga_palette(style))
    assert len(set(first.art.getdata())) <= 32
    with pytest.raises(ValueError, match="no renderer"):
        registry.get("unknown-driver")


class ReferenceReturningAdapter(FakeGenerationAdapter):
    def generate(self, request):
        result = super().generate(request)
        shutil.copy2(request.style_images[0], request.output_path)
        return GenerationResult(**{**result.__dict__, "dimensions": [1254, 1254], "output_path": str(request.output_path)})


def test_production_is_one_integrated_operation_and_excludes_target(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    style = styles.raw_version(styles.active_id())
    first, second = source(store, "one"), source(store, "two")
    calls: list[object] = []

    def factory(mode, capabilities):
        calls.append(capabilities.model)
        return ReferenceReturningAdapter(capabilities)

    manager = CardProductionManager(store, styles, factory)
    batch = manager.create([first["id"], second["id"]], style, [simulation_model()])
    result = wait_for(manager, batch["batch_id"])
    assert result["status"] == "ready"
    assert [item["status"] for item in result["items"]] == ["ready", "ready"]
    assert result["requested_paid_calls"] == 2
    assert all(item["card_url"] and item["art_url"] for item in result["items"])
    assert all(reference["role"] != "target-example" for item in result["items"] for reference in item["reference_stack"])
    assert calls == [simulation_model()["id"]]
    approvals = [manager.approve(result["batch_id"], item["item_id"]) for item in result["items"]]
    assert len(approvals) == 2
    refreshed = manager.get(result["batch_id"])
    assert refreshed["progress"]["approved_cards"] == 2
    bundle = manager.bundle(result["batch_id"])
    assert bundle["manifest"]["items"][0]["source_id"] == first["id"]
    assert (tmp_path / "library" / "downloads" / f"{result['batch_id']}-approved.zip").is_file()


def test_framing_rerenders_without_generation_and_approval_is_revisioned(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    calls = 0

    def factory(mode, capabilities):
        nonlocal calls
        calls += 1
        return FakeGenerationAdapter(capabilities)

    manager = CardProductionManager(store, styles, factory)
    item = source(store)
    batch = wait_for(manager, manager.create([item["id"]], styles.raw_version(styles.active_id()), [simulation_model()])["batch_id"])
    production_item = batch["items"][0]
    manager.approve(batch["batch_id"], production_item["item_id"])
    old_checksum = production_item["card_checksum_sha256"]
    rerendered = manager.rerender(batch["batch_id"], production_item["item_id"], {"zoom": 1.25, "offset_x": 0.1, "offset_y": 0})
    assert calls == 1
    assert rerendered["items"][0]["render_revision"] == 2
    assert rerendered["items"][0]["card_checksum_sha256"] != old_checksum
    assert len(rerendered["items"][0]["render_revisions"]) == 2
    assert rerendered["progress"]["approved_cards"] == 0
    manager.approve(batch["batch_id"], production_item["item_id"])


def test_style_validation_rejects_target_only_and_bad_dimensions() -> None:
    style = load_checked_in_style()
    bad = {**style, "reference_pack": {**style["reference_pack"], "assets": [asset for asset in style["reference_pack"]["assets"] if asset["role"] == "target-example"]}}
    with pytest.raises(ValueError, match="generation-reference"):
        validate_style(bad)
    bad_size = {**style, "composition": {**style["composition"], "centering": [1.5, 0.4]}}
    with pytest.raises(ValueError, match="centering"):
        validate_style(bad_size)
