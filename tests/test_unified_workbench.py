from __future__ import annotations

import hashlib
import copy
import shutil
import time
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from tools.cards.amiga import amiga_palette, palette_is_ocs_12_bit
from tools.cards.registry import registry
from tools.cards.style_pipeline import StyleStore, load_checked_in_style, style_checksum, validate_style
from tools.portraits.generation import (
    AdapterCapabilities,
    FakeGenerationAdapter,
    GenerationRequest,
    GenerationResult,
    OpenRouterGenerationAdapter,
    SemanticFakeGenerationAdapter,
    simulation_model,
    unavailable_live_model,
    validate_request,
)
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


def simulation_trial_style(styles: StyleStore) -> dict:
    style = copy.deepcopy(styles.raw_version(styles.active_id()))
    style["identity"] = {**style["identity"], "state": "draft", "style_version_id": "draft_preview"}
    style["generation"] = {**style["generation"], "model_id": simulation_model()["id"], "execution_mode": "simulation", "quality": "low"}
    return validate_style(style)


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
    style = simulation_trial_style(styles)
    first, second = source(store, "one"), source(store, "two")
    calls: list[object] = []

    def factory(mode, capabilities):
        calls.append(capabilities.model)
        return ReferenceReturningAdapter(capabilities)

    manager = CardProductionManager(store, styles, factory)
    batch = manager.create([first["id"], second["id"]], style, [simulation_model()], purpose="style-trial")
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
    batch = wait_for(manager, manager.create([item["id"]], simulation_trial_style(styles), [simulation_model()], purpose="style-trial")["batch_id"])
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


def live_model() -> dict:
    return {
        "id": "provider/neutral",
        "name": "Provider neutral",
        "execution_mode": "live",
        "available": True,
        "credentials_configured": True,
        "supported_parameters": {
            "input_references": {"type": "range", "min": 1, "max": 4},
            "aspect_ratio": {"type": "enum", "values": ["1:1", "4:3"]},
            "quality": {"type": "enum", "values": ["low", "medium"]},
            "negative_prompt": {"type": "string"},
        },
        "pricing": [{"cost_usd": 0.04}],
        "provider_slug": "provider",
        "provider_tag": "neutral-endpoint",
        "endpoint_id": "endpoint-1",
    }


def test_live_request_validation_covers_mode_credentials_capacity_quality_and_aspect() -> None:
    capabilities = AdapterCapabilities.from_model(live_model())
    mapping = validate_request({"model": capabilities.model, "execution_mode": "live", "quality": "medium", "provider_aspect_ratio": "1:1"}, 2, capabilities)
    assert mapping["reference_mapping"] == "identity_first_style_after"
    assert mapping["effective_aspect_ratio"] == "1:1"
    with pytest.raises(ValueError, match="execution mode"):
        validate_request({"model": capabilities.model, "execution_mode": "simulation", "quality": "medium"}, 1, capabilities)
    with pytest.raises(ValueError, match="quality"):
        validate_request({"model": capabilities.model, "execution_mode": "live", "quality": "high"}, 1, capabilities)
    with pytest.raises(ValueError, match="aspect ratio"):
        validate_request({"model": capabilities.model, "execution_mode": "live", "quality": "medium", "provider_aspect_ratio": "16:9"}, 1, capabilities)
    with pytest.raises(ValueError, match="at most"):
        validate_request({"model": capabilities.model, "execution_mode": "live", "quality": "medium"}, 4, capabilities)
    missing_key = AdapterCapabilities.from_model({**live_model(), "credentials_configured": False})
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        validate_request({"model": missing_key.model, "execution_mode": "live", "quality": "medium"}, 1, missing_key)
    unavailable = AdapterCapabilities.from_model(unavailable_live_model("provider/missing"))
    with pytest.raises(ValueError, match="unavailable"):
        validate_request({"model": unavailable.model, "execution_mode": "live", "quality": "medium"}, 1, unavailable)


def test_openrouter_payload_is_identity_first_and_rejects_targets(tmp_path: Path) -> None:
    source_path, reference_path, target_path = (tmp_path / name for name in ("source.png", "reference.png", "target.png"))
    for path, colour in ((source_path, (1, 2, 3)), (reference_path, (4, 5, 6)), (target_path, (7, 8, 9))):
        Image.new("RGB", (4, 4), colour).save(path)
    adapter = OpenRouterGenerationAdapter(AdapterCapabilities.from_model(live_model()), api_key="test-key")
    request = GenerationRequest(source_path, [reference_path], "neutral", "avoid", "provider/neutral", "medium", 1, "1:1", tmp_path / "out.png", ("generation-reference",))
    payload = adapter.build_payload(request)
    references = payload["input_references"]
    assert len(references) == 2
    assert references[0]["image_url"]["url"].endswith(__import__("base64").b64encode(source_path.read_bytes()).decode())
    assert references[1]["image_url"]["url"].endswith(__import__("base64").b64encode(reference_path.read_bytes()).decode())
    target_request = GenerationRequest(source_path, [target_path], "neutral", "avoid", "provider/neutral", "medium", 1, "1:1", tmp_path / "out.png", ("target-example",))
    with pytest.raises(ValueError, match="review-only"):
        adapter.build_payload(target_request)


def test_live_provenance_and_consent_use_semantic_fake_without_provider_call(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    first = source(store, "semantic")
    style = styles.raw_version(styles.active_id())
    model = live_model()
    style["generation"] = {**style["generation"], "model_id": model["id"], "quality": "medium"}
    style = validate_style(style)
    manager = CardProductionManager(store, styles, lambda mode, capabilities: SemanticFakeGenerationAdapter(capabilities))
    with pytest.raises(ValueError, match="explicit consent"):
        manager.create([first["id"]], style, [model])
    batch = wait_for(manager, manager.create([first["id"]], style, [model], consent=True)["batch_id"])
    item = batch["items"][0]
    assert item["generation"]["execution_mode"] == "live"
    assert item["generation_request"]["reference_order"][0]["role"] == "identity"
    assert item["generation_request"]["reference_order"][1]["role"] == "generation-reference"
    assert item["generation_request"]["target_examples_excluded"] is True
    assert item["master_url"] and item["art_url"] and item["card_url"]
    assert batch["generation_authorization"]["consent"] is True


def test_simulation_is_preview_only_for_lock_and_normal_production(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    preview = simulation_trial_style(styles)
    preview["identity"] = {**preview["identity"], "state": "locked"}
    preview = validate_style(preview, require_locked=True)
    item = source(store, "preview")
    manager = CardProductionManager(store, styles, lambda mode, capabilities: FakeGenerationAdapter(capabilities))
    with pytest.raises(ValueError, match="preview-only"):
        manager.create([item["id"]], preview, [simulation_model()])
    draft = styles.create_or_resume_draft()
    simulation = {**draft["generation"], "model_id": simulation_model()["id"], "execution_mode": "simulation", "quality": "low"}
    styles.update_draft({"generation": simulation})
    with pytest.raises(ValueError, match="preview"):
        styles.lock_draft()
