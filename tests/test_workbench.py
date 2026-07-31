from __future__ import annotations

import base64
import hashlib
import io
import json
import time
from pathlib import Path

import pytest
import requests
from PIL import Image

from tools.cards.pipeline import (
    ART_WINDOW,
    PIXEL_LOGICAL_SIZE,
    apply_estate_pixel_treatment,
    calculate_cover_transform,
    card_detail,
    create_card_draft,
    update_card_draft,
)
from tools.portraits.generation import (
    AdapterCapabilities,
    GenerationResult,
    OpenRouterGenerationAdapter,
    adapter_for,
    negotiate_aspect_ratio,
    normalize_live_model,
    simulation_model,
    validate_request,
)
from tools.portraits.recipes import resolve_recipe_instruction
from tools.portraits.runs import RunManager
from tools.portraits.server import _ensure_starter_recipe, bulk_import_sources
from tools.portraits.workspace import WorkspaceError, WorkspaceStore


def fixture_image(path: Path, size: tuple[int, int] = (160, 220), colour: str = "#996b55") -> None:
    Image.new("RGB", size, colour).save(path)


def ready_store(tmp_path: Path) -> tuple[WorkspaceStore, dict]:
    store = WorkspaceStore(tmp_path / "portrait-library")
    _ensure_starter_recipe(store)
    path = tmp_path / "source.png"
    fixture_image(path)
    source = store.add_image_record("source", "Fixture source", path.name, path.read_bytes(), "image/png")
    store.mutate(lambda data: data.update({"benchmark_source_ids": [source["id"]]}))
    return store, source


def simulation_draft(store: WorkspaceStore, **patch: object) -> dict:
    saved = store.read()["recipes"][0]
    return {**saved, "model": "fake/painterly-deterministic", "execution_mode": "simulation", "quality": "low", **patch}


def create_simulation(manager: RunManager, store: WorkspaceStore, source_ids: list[str], draft: dict | None = None) -> dict:
    return manager.create(draft or simulation_draft(store), source_ids, 1, "simulation", [simulation_model()])


def wait_for(manager: RunManager, run_id: str) -> dict:
    deadline = time.time() + 8
    while time.time() < deadline:
        run = manager.get(run_id)
        if run["status"] not in {"queued", "running"}:
            return run
        time.sleep(0.02)
    return manager.get(run_id)


def test_empty_workspace_bootstraps_and_seeds_live_recipe_and_style_pack(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "portrait-library")
    assert store.read() == {"version": 1, "sources": [], "benchmark_source_ids": [], "references": [], "recipes": [], "active_recipe_id": None}
    _ensure_starter_recipe(store)
    data = store.read()
    assert data["recipes"][0]["model"] == "openai/gpt-image-1-mini"
    assert data["recipes"][0]["execution_mode"] == "live"
    assert data["recipes"][0]["quality"] == "low"
    assert data["recipes"][0]["reference_ids"] == ["reference_estate_card_v1_firelit", "reference_estate_card_v1_armoured"]
    assert [item["provenance"]["kind"] for item in data["references"]] == ["bundled", "bundled"]
    assert all(store.absolute_path(item["relative_path"]).is_file() for item in data["references"])


def test_asset_paths_cannot_escape_workspace(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "portrait-library")
    with pytest.raises(WorkspaceError):
        store.absolute_path("../outside.png")
    with pytest.raises(WorkspaceError):
        store.absolute_path("/etc/passwd")


def test_upload_validates_decoding_and_deduplicates(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "portrait-library")
    bad = tmp_path / "bad.txt"
    bad.write_text("not an image")
    with pytest.raises(WorkspaceError, match="readable image"):
        store.add_image_record("source", "Bad", bad.name, bad.read_bytes(), "image/png")
    good = tmp_path / "good.png"
    fixture_image(good)
    source = store.add_image_record("source", "Good", "original-name.png", good.read_bytes(), "image/png")
    duplicate = store.add_image_record("source", "Duplicate", "duplicate.png", good.read_bytes(), "image/png")
    assert source["provenance"]["kind"] == "upload"
    assert duplicate["id"] == source["id"]
    assert duplicate["deduplicated"] is True
    assert len(store.read()["sources"]) == 1


def test_dynamic_capability_descriptors_and_reference_limits_are_exact() -> None:
    raw_model = {"id": "vendor/image", "name": "Image", "architecture": {"input_modalities": ["text", "image"]}}
    endpoint = {
        "provider_slug": "vendor", "provider_tag": "vendor/primary", "supports_streaming": True,
        "supported_parameters": {
            "input_references": {"type": "range", "min": 0, "max": 3},
            "aspect_ratio": {"type": "enum", "values": ["1:1", "3:2"]},
            "quality": {"type": "enum", "values": ["low"]},
        },
        "pricing": [{"billable": "output_image", "unit": "image", "cost_usd": 0.03}],
    }
    model = normalize_live_model(raw_model, endpoint)
    capabilities = AdapterCapabilities.from_model(model)
    assert capabilities.max_references == 3
    assert capabilities.provider_tag == "vendor/primary"
    assert negotiate_aspect_ratio(capabilities.aspect_ratios) == "1:1"
    mapping = validate_request({"model": model["id"], "quality": "low"}, 2, capabilities)
    assert mapping["sent_parameters"] == ["input_references", "aspect_ratio", "quality"]
    with pytest.raises(ValueError, match="at most 3"):
        validate_request({"model": model["id"], "quality": "low"}, 3, capabilities)


def test_live_adapter_sends_only_supported_parameters_and_captures_cost(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = normalize_live_model(
        {"id": "vendor/image", "name": "Image"},
        {
            "provider_slug": "vendor", "provider_tag": "vendor", "supports_streaming": False,
            "supported_parameters": {"input_references": {"type": "range", "min": 0, "max": 2}, "n": {"type": "range", "min": 1, "max": 1}},
            "pricing": [],
        },
    )
    captured: dict = {}
    buffer = io.BytesIO()
    Image.new("RGB", (20, 10), "red").save(buffer, format="PNG")

    class Response:
        ok = True
        status_code = 200
        text = ""

        @staticmethod
        def json() -> dict:
            return {"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}], "usage": {"total_tokens": 12, "cost": 0.0123}}

    def fake_post(*args: object, **kwargs: object) -> Response:
        captured.update(kwargs["json"])  # type: ignore[index]
        return Response()

    monkeypatch.setattr("tools.portraits.generation.requests.post", fake_post)
    source = tmp_path / "source.png"
    fixture_image(source)
    output = tmp_path / "output.png"
    adapter = OpenRouterGenerationAdapter(AdapterCapabilities.from_model(model), api_key="test")
    from tools.portraits.generation import GenerationRequest
    result = adapter.generate(GenerationRequest(source, [], "paint", "no type", model["id"], "low", 42, "provider-default", output))
    assert set(captured) == {"model", "prompt", "input_references", "n", "provider"}
    assert captured["provider"] == {"only": ["vendor"], "allow_fallbacks": False}
    assert result.cost_usd == 0.0123
    assert result.usage["total_tokens"] == 12
    assert output.is_file()


def test_execution_mode_never_uses_environment_to_substitute_simulation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORTRAIT_WORKBENCH_FAKE_GENERATION", "1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    live = normalize_live_model(
        {"id": "vendor/live", "name": "Live"},
        {"provider_slug": "vendor", "provider_tag": "vendor", "supported_parameters": {"input_references": {"type": "range", "max": 1}}, "pricing": []},
    )
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        adapter_for("live", AdapterCapabilities.from_model(live))
    assert adapter_for("simulation", AdapterCapabilities.from_model(simulation_model())).name == "simulation"


def test_atomic_run_persists_visible_draft_snapshot_and_explicit_sources(tmp_path: Path) -> None:
    store, source = ready_store(tmp_path)
    manager = RunManager(store)
    draft = simulation_draft(store, name="Visible unsaved name")
    draft["direction"] = {**draft["direction"], "lighting": "Visible new light"}
    completed = wait_for(manager, create_simulation(manager, store, [source["id"]], draft)["run_id"])
    assert completed["status"] == "complete"
    assert completed["execution_mode"] == "simulation"
    assert completed["recipe_snapshot"]["name"] == "Visible unsaved name"
    assert completed["recipe_snapshot"]["direction"]["lighting"] == "Visible new light"
    assert store.read()["recipes"][0]["name"] == "Visible unsaved name"
    assert completed["benchmark_source_ids"] == [source["id"]]
    assert completed["items"][0]["backend"] == "simulation"
    assert completed["cost_usd"] == 0


def test_live_full_benchmark_requires_paid_confirmation_and_completed_smoke(tmp_path: Path) -> None:
    store, source = ready_store(tmp_path)
    second_path = tmp_path / "second.png"
    fixture_image(second_path, colour="blue")
    second = store.add_image_record("source", "Second", second_path.name, second_path.read_bytes(), "image/png")
    manager = RunManager(store)
    live_model = normalize_live_model(
        {"id": "vendor/live", "name": "Live"},
        {"provider_slug": "vendor", "provider_tag": "vendor", "supported_parameters": {"input_references": {"type": "range", "max": 9}, "quality": {"type": "enum", "values": ["low"]}}, "pricing": []},
    )
    draft = {**store.read()["recipes"][0], "model": "vendor/live", "execution_mode": "live"}
    with pytest.raises(ValueError, match="paid-run confirmation"):
        manager.create(draft, [source["id"]], 1, "live", [live_model], False)
    with pytest.raises(ValueError, match="one-source live smoke"):
        manager.create(draft, [source["id"], second["id"]], 1, "live", [live_model], True)


class CostAdapter:
    def __init__(self, capabilities: AdapterCapabilities) -> None:
        self.capabilities = capabilities

    def generate(self, request: object) -> GenerationResult:
        output_path = request.output_path  # type: ignore[attr-defined]
        Image.new("RGB", (32, 24), "green").save(output_path)
        return GenerationResult(str(output_path), "priced-fixture", request.model, request.seed, 0.01, [32, 24], request.effective_aspect_ratio, {"total_tokens": 25, "cost": 0.045}, 0.045)  # type: ignore[attr-defined]


def test_run_aggregates_returned_usage_and_cost(tmp_path: Path) -> None:
    store, source = ready_store(tmp_path)
    manager = RunManager(store, lambda _mode, capabilities: CostAdapter(capabilities))
    completed = wait_for(manager, create_simulation(manager, store, [source["id"]])["run_id"])
    assert completed["usage"] == {"total_tokens": 25, "cost": 0.045}
    assert completed["cost_usd"] == 0.045
    assert completed["items"][0]["cost_usd"] == 0.045


def test_bulk_import_deduplicates_and_reports_partial_download_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = WorkspaceStore(tmp_path / "portrait-library")
    image = io.BytesIO()
    Image.new("RGB", (50, 80), "purple").save(image, format="JPEG")

    class Response:
        def __init__(self, ok: bool) -> None:
            self.content = image.getvalue()
            self.headers = {"Content-Type": "image/jpeg"}
            self.ok = ok

        def raise_for_status(self) -> None:
            if not self.ok:
                raise requests.HTTPError("download unavailable")

    monkeypatch.setattr("tools.portraits.server.requests.get", lambda url, timeout: Response("failed" not in str(url)))
    candidate = {"pexels_photo_id": 11, "selected_image_url": "https://image/11", "photographer": "A"}
    result = bulk_import_sources(store, [candidate, candidate, {"pexels_photo_id": 12, "selected_image_url": "https://image/failed"}], True)
    assert (result["imported"], result["deduplicated"], result["failed"]) == (1, 1, 1)
    assert len(store.read()["sources"]) == 1
    assert len(store.read()["benchmark_source_ids"]) == 1
    assert "download unavailable" in result["results"][2]["error"]


def test_shared_framing_fixtures_match_browser_contract() -> None:
    fixtures = json.loads((Path(__file__).parents[1] / "src/ui/fixtures/card-render.json").read_text())
    for fixture in fixtures["framing"]:
        result = calculate_cover_transform(fixture["image_size"], tuple(fixtures["art_window"]), **fixture["frame"])
        assert result["image_bounds"] == fixture["image_bounds"]
        assert result["image_bounds"][0] <= 0 and result["image_bounds"][1] <= 0
        assert result["image_bounds"][2] >= ART_WINDOW[0] and result["image_bounds"][3] >= ART_WINDOW[1]


def test_estate_pixel_treatment_is_deterministic_palette_limited_and_nearest_upscaled() -> None:
    source = Image.new("RGB", ART_WINDOW)
    source.putdata([((x * 17) % 256, (y * 29) % 256, ((x + y) * 11) % 256) for y in range(ART_WINDOW[1]) for x in range(ART_WINDOW[0])])
    first = apply_estate_pixel_treatment(source)
    second = apply_estate_pixel_treatment(source)
    assert hashlib.sha256(first.tobytes()).digest() == hashlib.sha256(second.tobytes()).digest()
    logical = first.resize(PIXEL_LOGICAL_SIZE, Image.Resampling.NEAREST)
    assert len(logical.getcolors(maxcolors=PIXEL_LOGICAL_SIZE[0] * PIXEL_LOGICAL_SIZE[1]) or []) <= 32
    pixels = first.load()
    for y in range(0, ART_WINDOW[1], 3):
        for x in range(0, ART_WINDOW[0], 3):
            block = {pixels[x + dx, y + dy] for dx in range(3) for dy in range(3)}
            assert len(block) == 1


def test_full_simulation_to_frame_pixel_keep_and_reopen(tmp_path: Path) -> None:
    store, source = ready_store(tmp_path)
    manager = RunManager(store)
    run = wait_for(manager, create_simulation(manager, store, [source["id"]])["run_id"])
    card = create_card_draft(store, run["run_id"], run["items"][0]["item_id"], preset="tall")
    updated = update_card_draft(store, card["card_id"], {"framing": {"zoom": 1.4, "offset_x": 0.2, "offset_y": -0.1}, "treatment": "estate-pixel-v1", "decision": "keep"})
    reopened = card_detail(store, card["card_id"])
    assert reopened["decision"] == "keep"
    assert reopened["framing"] == updated["framing"]
    assert reopened["treatment"] == "estate-pixel-v1"
    assert reopened["treatment_version"] == "estate-pixel-v1"
    assert reopened["source_run_provenance"]["run_id"] == run["run_id"]
    assert reopened["render_metadata"]["palette_colours"] <= 32
    assert store.absolute_path(reopened["render_path"]).is_file()
    assert store.absolute_path(reopened["art_render_path"]).is_file()


def test_recipe_instruction_keeps_avoid_as_explicit_direction() -> None:
    instruction = resolve_recipe_instruction({"direction": {"lighting": "quiet"}, "avoid": "No type"})
    assert instruction.startswith("Lighting:")
    assert "Avoid: No type" in instruction
