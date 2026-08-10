from __future__ import annotations

import hashlib
import copy
import shutil
import time
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from tools.cards.amiga import adaptive_hybrid_palette, amiga_palette, palette_is_ocs_12_bit
from tools.cards.backgrounds import choose_chroma_key, composite_foreground, extract_foreground
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
    GenerationResult,
    OpenRouterGenerationAdapter,
    SemanticFakeGenerationAdapter,
    simulation_model,
    unavailable_live_model,
    validate_request,
)
from tools.portraits.production import CardProductionManager
from tools.portraits.normalisation import InputNormalisationManager
from tools.portraits.server import _cards
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


def wait_for(manager: CardProductionManager, batch_id: str) -> dict:
    for _ in range(600):
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
    assert "sole source of content" in prompt
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


def test_adaptive_hybrid_palette_keeps_ocs_limits_and_is_deterministic() -> None:
    style = load_checked_in_style()
    image = Image.new("RGB", (96, 96))
    image.putdata([((x * 5) % 256, (y * 7) % 256, ((x + y) * 9) % 256) for y in range(96) for x in range(96)])
    house = amiga_palette(style)
    resolved = adaptive_hybrid_palette(image, house)
    first = registry.render(style, image, "colour study")
    second = registry.render(style, image, "colour study")
    assert len(resolved) == 32
    assert palette_is_ocs_12_bit(resolved)
    assert resolved != house
    assert first.metadata["palette_mode"] == "adaptive-hybrid"
    assert len(first.metadata["resolved_palette"]) == 32
    assert len(set(first.art.getdata())) <= 32
    assert len(set(first.card.getdata())) <= 32
    assert first.art.tobytes() == second.art.tobytes()
    assert first.card.tobytes() == second.card.tobytes()


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


def test_layered_background_palettes_do_not_change_foreground() -> None:
    style = load_checked_in_style()
    foreground = Image.new("RGBA", (336, 276))
    for x in range(90, 246):
        for y in range(45, 276):
            foreground.putpixel((x, y), (34, 102, 187, 255))

    warm, _, _ = registry.render_layered(style, foreground, "warm-parchment", "Subject")
    cool, _, _ = registry.render_layered(style, foreground, "cool-slate", "Subject")
    noir, _, _ = registry.render_layered(style, foreground, "noir", "Subject")

    assert warm.metadata["palette_mode"] == "layered-adaptive"
    assert len(warm.metadata["background_palette"]) <= 16
    assert warm.metadata["foreground_palette"] == cool.metadata["foreground_palette"] == noir.metadata["foreground_palette"]
    assert warm.logical_art.crop((55, 40, 113, 138)).tobytes() == cool.logical_art.crop((55, 40, 113, 138)).tobytes() == noir.logical_art.crop((55, 40, 113, 138)).tobytes()
    assert warm.logical_art.tobytes() != cool.logical_art.tobytes() != noir.logical_art.tobytes()


class ReferenceReturningAdapter(FakeGenerationAdapter):
    def generate(self, request):
        result = super().generate(request)
        shutil.copy2(request.style_images[0] if request.style_images else request.identity_image, request.output_path)
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
    assert manager.list()[0]["selected_source_ids"] == [first["id"], second["id"]]
    assert [item["status"] for item in result["items"]] == ["ready", "ready"]
    assert result["requested_paid_calls"] == 2
    assert all(item["card_url"] and item["art_url"] for item in result["items"])
    assert all(reference["role"] != "target-example" for item in result["items"] for reference in item["reference_stack"])
    assert calls == [simulation_model()["id"]]
    assert _cards(manager) == []
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
    rerendered = manager.rerender(batch["batch_id"], production_item["item_id"], {"zoom": 1.25, "offset_x": 0.1, "offset_y": 0}, "fixed-house", "cool-slate")
    assert calls == 1
    assert rerendered["items"][0]["render_revision"] == 2
    assert rerendered["items"][0]["card_checksum_sha256"] != old_checksum
    assert len(rerendered["items"][0]["render_revisions"]) == 2
    assert rerendered["items"][0]["palette_mode"] == "fixed-house"
    assert rerendered["items"][0]["background_id"] == "cool-slate"
    assert rerendered["style_snapshot"]["renderer"]["palette_mode"] == "adaptive-hybrid"
    assert rerendered["progress"]["approved_cards"] == 0
    manager.approve(batch["batch_id"], production_item["item_id"])


def test_render_preview_does_not_change_stored_candidate(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    style = styles.ensure_initial()
    item_source = source(store)
    manager = CardProductionManager(store, styles, lambda mode, capabilities: FakeGenerationAdapter(capabilities))
    model = {**live_model(), "id": style["generation"]["model_id"]}
    batch = wait_for(manager, manager.create([item_source["id"]], style, [model], consent=True)["batch_id"])
    item = batch["items"][0]

    preview = manager.preview_render(batch["batch_id"], item["item_id"], {"zoom": 1.2, "offset_x": 0.1, "offset_y": 0}, "fixed-house", "cool-slate")
    stored = manager.get(batch["batch_id"])["items"][0]

    assert preview["card_url"] != item["card_url"]
    assert preview["background_id"] == "cool-slate"
    assert stored["render_revision"] == item["render_revision"] == 1
    assert stored["card_checksum_sha256"] == item["card_checksum_sha256"]
    assert stored["background_id"] == item["background_id"] == "warm-parchment"


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
    batch = wait_for(manager, manager.create([first["id"]], style, [model], consent=True, prompt_override="Keep the book square to camera.", content_direction="Add one cracked corner.")["batch_id"])
    item = batch["items"][0]
    assert item["generation"]["execution_mode"] == "live"
    assert item["generation_stages"] == []
    assert item["generation_request"]["reference_order"][0]["role"] == "identity"
    assert item["generation_request"]["reference_order"][1]["role"] == "generation-reference"
    assert item["generation_request"]["target_examples_excluded"] is True
    assert item["generation_request"]["instruction"].startswith("Keep the book square to camera.\n\nAdditional content direction from the user: Add one cracked corner.")
    assert "Foreground isolation contract" in item["generation_request"]["instruction"]
    assert item["content_direction"] == "Add one cracked corner."
    assert item["foreground_url"] and item["master_url"] and item["background_id"] == "warm-parchment"
    assert item["render_metadata"]["framing"]["resolved"] == item["background_metadata"]["framing"]
    assert item["render_metadata"]["palette_mode"] == "layered-adaptive"
    assert item["master_url"] and item["art_url"] and item["card_url"]
    assert not item["normalised_url"] and batch["paid_calls"] == 1
    assert batch["generation_authorization"]["consent"] is True
    assert _cards(manager) == []
    manager.accept_candidate(batch["batch_id"], item["item_id"])
    candidate = _cards(manager)[0]
    assert candidate["pipeline_id"] == FACE_FREE_PIPELINE_ID
    assert candidate["pipeline_label"] == "Amiga Style Transfer"


def test_multiple_favorites_persist_and_follow_latest_render(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    item = source(store, "favorite")
    style = styles.raw_pipeline(FACE_FREE_PIPELINE_ID)
    model = live_model()
    style["generation"] = {**style["generation"], "model_id": model["id"], "quality": "medium"}
    style = validate_style(style, require_locked=True)
    manager = CardProductionManager(store, styles, lambda mode, capabilities: SemanticFakeGenerationAdapter(capabilities))
    batch = wait_for(manager, manager.create([item["id"]], style, [model], consent=True)["batch_id"])
    first = batch["items"][0]
    another = wait_for(manager, manager.try_another(batch["batch_id"], item["id"], consent=True)["batch_id"])
    second = another["items"][-1]
    manager.accept_candidate(batch["batch_id"], first["item_id"])
    manager.accept_candidate(batch["batch_id"], second["item_id"])
    manager.favourite(batch["batch_id"], first["item_id"])
    manager.favourite(batch["batch_id"], second["item_id"])
    assert len(manager.favourites()) == 2
    rerendered = manager.rerender(batch["batch_id"], first["item_id"], {"zoom": 1.2, "offset_x": 0, "offset_y": 0})
    assert next(candidate for candidate in rerendered["items"] if candidate["item_id"] == first["item_id"])["favorite"] is True
    assert sum(bool(candidate.get("favorite")) for candidate in _cards(manager)) == 2
    assert manager.unfavourite(batch["batch_id"], first["item_id"]) is True
    assert len(manager.favourites()) == 1


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


class FailOnceSemanticAdapter(SemanticFakeGenerationAdapter):
    def __init__(self, capabilities: AdapterCapabilities, state: dict[str, bool]) -> None:
        super().__init__(capabilities)
        self.state = state

    def generate(self, request):
        if not self.state["failed"]:
            self.state["failed"] = True
            raise RuntimeError("semantic test provider failed once")
        return super().generate(request)


class FailStyliseOnceAdapter(SemanticFakeGenerationAdapter):
    def __init__(self, capabilities: AdapterCapabilities, state: dict[str, bool]) -> None:
        super().__init__(capabilities)
        self.state = state

    def generate(self, request):
        if request.style_images and not self.state["failed"]:
            self.state["failed"] = True
            raise RuntimeError("style stage failed once")
        return super().generate(request)


def test_retry_reuses_the_accepted_input_and_costs_one_new_call(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    item = source(store, "checkpoint")
    state = {"failed": False}
    manager = CardProductionManager(store, styles, lambda mode, capabilities: FailStyliseOnceAdapter(capabilities, state))
    failed = wait_for(manager, manager.create([item["id"]], simulation_trial_style(styles), [simulation_model()], purpose="style-trial")["batch_id"])
    assert failed["status"] == "failed" and not failed["items"][0]["normalised_url"]
    assert failed["paid_calls"] == 0
    retried = wait_for(manager, manager.retry_failed(failed["batch_id"])["batch_id"])
    latest = manager.latest_items(retried)[0]
    assert retried["status"] == "ready" and retried["requested_paid_calls"] == 2
    assert latest["generation_stages"] == []
    assert retried["paid_calls"] == 1


def test_failed_retry_and_try_another_keep_attempt_provenance(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "library")
    styles = StyleStore(store)
    item = source(store, "retryable")
    preview = simulation_trial_style(styles)
    state = {"failed": False}
    manager = CardProductionManager(store, styles, lambda mode, capabilities: FailOnceSemanticAdapter(capabilities, state))
    failed = wait_for(manager, manager.create([item["id"]], preview, [simulation_model()], purpose="style-trial")["batch_id"])
    failed_item = failed["items"][0]
    assert failed["status"] == "failed"
    assert failed_item["generation_request"]["target_examples_excluded"] is True
    retried = wait_for(manager, manager.retry_failed(failed["batch_id"])["batch_id"])
    assert retried["status"] == "ready"
    ready_item = retried["items"][-1]
    assert ready_item["attempt_number"] == 2
    assert ready_item["lineage_id"] == failed_item["lineage_id"]
    another = wait_for(manager, manager.try_another(retried["batch_id"], item["id"])["batch_id"])
    attempts = [candidate for candidate in another["items"] if candidate["source_id"] == item["id"]]
    assert len(attempts) == 3
    assert [candidate["attempt_number"] for candidate in attempts] == [1, 2, 3]
    assert len({candidate["master_url"] for candidate in attempts if candidate.get("master_url")}) == 2
    assert another["progress"]["total_attempts"] == 3
    assert _cards(manager) == []
