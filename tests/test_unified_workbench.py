from __future__ import annotations

import hashlib
import copy
import time
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from tools.cards.amiga import adaptive_hybrid_palette, amiga_palette, palette_is_ocs_12_bit
from tools.cards.backgrounds import choose_chroma_key, composite_foreground, extract_foreground, validate_foreground_clearance
from tools.cards.registry import registry
from tools.cards.style_pipeline import (
    FACE_FREE_PIPELINE_ID,
    FACE_FREE_REFERENCE_CHECKSUM,
    PORTRAIT_REFERENCE_CHECKSUM,
    PORTRAIT_REFERENCE_PIPELINE_ID,
    StyleStore,
    load_checked_in_style,
    style_checksum,
    validate_style,
)
from tools.portraits.generation import (
    AdapterCapabilities,
    FakeGenerationAdapter,
    GenerationRequest,
    OpenRouterGenerationAdapter,
    simulation_model,
    unavailable_live_model,
    validate_request,
)
from tools.portraits.production import CardProductionManager, prepare_wide_identity_reference
from tools.portraits.normalisation import InputNormalisationManager
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
    record = store.add_image_record("input", name, f"{name}.png", content, "image/png")
    accepted = {"id": f"accepted-{record['id']}", "status": "ready", "relative_path": record["original_path"], "checksum_sha256": record["original_checksum_sha256"], "prompt": "test normalisation", "quality": "low", "model_id": simulation_model()["id"]}
    store.mutate(lambda data: next(item for item in data["inputs"] if item["id"] == record["id"]).update({"status": "ready", "accepted_normalisation": accepted}))
    return {**record, "status": "ready", "accepted_normalisation": accepted}


def simulation_trial_style(styles: StyleStore) -> dict:
    style = copy.deepcopy(styles.raw_version(styles.active_id()))
    style["identity"] = {**style["identity"], "state": "draft", "style_version_id": "draft_preview"}
    style["generation"] = {**style["generation"], "model_id": simulation_model()["id"], "execution_mode": "simulation", "quality": "low"}
    return validate_style(style)


def test_input_normalisation_requires_preview_then_accepts_it(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    content = (ASSETS / "generation-reference-01.png").read_bytes()
    pending = store.add_image_record("input", "Book", "book.png", content, "image/png")
    manager = InputNormalisationManager(store, lambda mode, capabilities: FakeGenerationAdapter(capabilities))
    started = manager.start(pending["id"], "Preserve the exact object.", "low", simulation_model(), consent=False)
    attempt_id = started["normalisation_attempts"][-1]["id"]
    for _ in range(200):
        current = manager.get(pending["id"])
        if current["normalisation_attempts"][-1]["status"] not in {"queued", "running"}:
            break
        time.sleep(0.02)
    assert current["status"] == "pending"
    assert current["normalisation_attempts"][-1]["status"] == "ready"
    accepted = manager.accept(pending["id"], attempt_id)
    assert accepted["status"] == "ready"
    assert accepted["image_url"] and accepted["accepted_normalisation"]["prompt"] == "Preserve the exact object."


def test_style_schema_checksum_store_and_asset_snapshots(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    active = styles.active()
    assert active["schema_version"] == 3
    prompt = active["generation"]["prompt"].lower()
    assert "head-and-shoulders" not in prompt and "redraw the person" not in prompt
    assert prompt == "redraw input 1 as a vivid, characterful fantasy portrait. use the reference board only for rendering style."
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
    assert {pipeline["pipeline_id"] for pipeline in styles.pipelines()} == {FACE_FREE_PIPELINE_ID}
    version = styles.versions()[-1]
    assert version["model_id"] == locked["generation"]["model_id"]
    assert version["execution_mode"] == "live"
    assert version["reference_count"] == 1
    assert version["renderer_id"] == "amiga-ocs"


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


def test_one_universal_pipeline_uses_the_subject_neutral_reference(tmp_path: Path) -> None:
    styles = StyleStore(WorkspaceStore(tmp_path / "library"))
    pipelines = styles.pipelines()
    assert [pipeline["pipeline_id"] for pipeline in pipelines] == [FACE_FREE_PIPELINE_ID]
    assert [pipeline["active"] for pipeline in pipelines] == [True]
    reference = next(asset["checksum_sha256"] for asset in pipelines[0]["style"]["reference_pack"]["assets"] if asset["role"] == "generation-reference")
    assert reference == FACE_FREE_REFERENCE_CHECKSUM
    assert pipelines[0]["style"]["schema_version"] == 3


def test_amiga_registered_engine_is_deterministic_and_matches_golden() -> None:
    style = load_checked_in_style()
    style["renderer"]["palette_mode"] = "fixed-house"
    with Image.open(ASSETS / "generation-reference-01.png") as master:
        historical_framing = {"mode": "legacy", "zoom": 1, "offset_x": 0, "offset_y": 0}
        first = registry.render(style, master, "stage reference", historical_framing)
        second = registry.render(style, master, "stage reference", historical_framing)
    assert first.art.size == (352, 198)
    assert first.art.tobytes() == second.art.tobytes()
    assert hashlib.sha256(first.art.tobytes()).hexdigest() == hashlib.sha256(second.art.tobytes()).hexdigest()
    assert first.metadata["artwork_kind"] == "rendered-art"
    assert palette_is_ocs_12_bit(amiga_palette(style))
    assert len(set(first.art.getdata())) <= 32
    with pytest.raises(ValueError, match="no renderer"):
        registry.get("unknown-driver")


def test_adaptive_palette_retains_small_foreground_accents() -> None:
    image = Image.new("RGB", (100, 100), (238, 221, 187))
    for x in range(42, 58):
        for y in range(42, 58): image.putpixel((x, y), (10, 120, 220))
    resolved = adaptive_hybrid_palette(image, amiga_palette(load_checked_in_style()))
    assert any(blue > red * 1.5 and blue > green for red, green, blue in resolved)


def test_foreground_matte_and_backgrounds_are_independent() -> None:
    source = Image.new("RGB", (120, 120), (0, 255, 0))
    for x in range(35, 85):
        for y in range(20, 120): source.putpixel((x, y), (170, 65, 35))
    name, key = choose_chroma_key(source)
    assert name == "magenta"
    foreground, matte = extract_foreground(source, (0, 255, 0))
    assert matte["mode"] == "chroma-matte" and foreground.getpixel((0, 0))[3] == 0
    style = load_checked_in_style()
    warm, warm_meta = composite_foreground(foreground, style, "warm-parchment")
    cool, cool_meta = composite_foreground(foreground, style, "cool-slate")
    assert warm.size == cool.size == tuple(style["backgrounds"]["composite_size"])
    assert warm.tobytes() != cool.tobytes()
    assert warm_meta["subject_bbox"] == cool_meta["subject_bbox"]
    top_cropped = Image.new("RGBA", (100, 120))
    for x in range(20, 80):
        for y in range(120): top_cropped.putpixel((x, y), (170, 65, 35, 255))
    _, cropped_meta = composite_foreground(top_cropped, style, "warm-parchment")
    assert cropped_meta["touching_edges"] == ["top"]
    assert cropped_meta["fit_mode"] == "edge-bleed"
    assert cropped_meta["placement"][1] == 0
    assert cropped_meta["placement"][3] >= style["backgrounds"]["composite_size"][1]
    assert warm_meta["fit_mode"] == "contained"


def test_foreground_matte_removes_shaded_chroma_field() -> None:
    source = Image.new("RGB", (120, 120))
    for y in range(120):
        shade = 80 + y
        for x in range(120):
            source.putpixel((x, y), (4, min(255, shade), 7))
    for x in range(35, 85):
        for y in range(20, 120):
            source.putpixel((x, y), (170, 65, 35))

    foreground, matte = extract_foreground(source, (0, 255, 0))

    assert matte["mode"] == "chroma-matte"
    assert foreground.getpixel((0, 0))[3] == 0
    assert foreground.getpixel((0, 119))[3] == 0
    assert foreground.getpixel((60, 60))[3] == 255
    assert matte["bbox"] == [35, 20, 85, 120]


def test_foreground_clearance_rejects_irreplaceable_edge_crops() -> None:
    validate_foreground_clearance({"mode": "chroma-matte", "bbox": [40, 20, 160, 100]}, (200, 120))
    with pytest.raises(ValueError, match="top edge"):
        validate_foreground_clearance({"mode": "chroma-matte", "bbox": [40, 0, 160, 100]}, (200, 120))
    with pytest.raises(ValueError, match="side edge"):
        validate_foreground_clearance({"mode": "chroma-matte", "bbox": [0, 20, 160, 100]}, (200, 120))


def test_wide_identity_reference_exposes_generation_safe_area(tmp_path: Path) -> None:
    source, destination = tmp_path / "source.png", tmp_path / "guide.png"
    Image.new("RGB", (400, 400), (10, 20, 30)).save(source)
    prepare_wide_identity_reference(source, destination)
    with Image.open(destination) as guide:
        assert guide.size == (1536, 864)
        assert guide.getpixel((0, 0)) == (244, 242, 236)
        assert guide.getpixel((guide.width // 2, guide.height // 2)) == (10, 20, 30)


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


def test_production_requires_model_to_support_requested_art_ratio(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    manager = CardProductionManager(store, styles)
    style = load_checked_in_style()
    style["generation"] = {
        **style["generation"],
        "model_id": live_model()["id"],
        "requested_aspect_policy": "16:9",
        "provider_aspect_ratio": "16:9",
    }
    with pytest.raises(ValueError, match="does not support aspect ratio 16:9"):
        manager._validate_start(style, ["input-any"], [live_model()], "card-production")


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


def test_card_trash_is_soft_and_clears_favorite(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    manager = CardProductionManager(store, styles)
    batch_id, item_id = "batch-test", "item-test"
    store.atomic_json(store.root / "production" / batch_id / "batch.json", {"batch_id": batch_id, "items": [{"item_id": item_id, "status": "ready"}]})
    manager.favourite(batch_id, item_id)
    manager.hide(batch_id, item_id)
    assert manager.favourites() == []
    assert manager._hidden_data()["items"][0]["item_id"] == item_id
    assert manager.restore(batch_id, item_id) is True
    assert manager._hidden_data()["items"] == []


def test_card_text_defaults_and_persists_without_changing_artwork(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    manager = CardProductionManager(store, StyleStore(store))
    batch_id = "batch-text"
    item = manager._new_item({"id": "source-1", "label": "Ada", "input_path": "input.png", "input_checksum_sha256": "input"}, 1, "lineage", [])
    item["card_text"]["lines"] = ["Pipeline", batch_id, "Attempt 1"]
    item["art_checksum_sha256"] = "durable-art"
    record = {"batch_id": batch_id, "purpose": "card-production", "selected_source_ids": ["source-1"], "style_snapshot": load_checked_in_style(), "items": [item]}
    manager._write(record)

    updated = manager.update_card_text(batch_id, item["item_id"], {"title": "Ada Prime", "lines": ["One", "Two"]})
    assert item["card_text"] == {"title": "Ada", "lines": ["Pipeline", batch_id, "Attempt 1"]}
    assert updated["card_text"] == {"title": "Ada Prime", "lines": ["One", "Two"]}
    assert updated["art_checksum_sha256"] == "durable-art"
    six_lines = manager.update_card_text(batch_id, item["item_id"], {"title": "Ada Prime", "lines": [str(index) for index in range(6)]})
    assert len(six_lines["card_text"]["lines"]) == 6
    with pytest.raises(ValueError, match="at most 6 lines"):
        manager.update_card_text(batch_id, item["item_id"], {"title": "Ada Prime", "lines": [str(index) for index in range(7)]})
    with pytest.raises(ValueError, match="title is required"):
        manager.update_card_text(batch_id, item["item_id"], {"title": "", "lines": []})
