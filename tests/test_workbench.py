from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image

from tools.cards.pipeline import calculate_cover_transform, create_card_draft, update_card_draft
from tools.portraits.generation import model_capabilities, negotiate_aspect_ratio, validate_request
from tools.portraits.recipes import STARTER_RECIPE, resolve_recipe_instruction
from tools.portraits.server import _ensure_starter_recipe
from tools.portraits.runs import RunManager
from tools.portraits.workspace import WorkspaceError, WorkspaceStore


def fixture_image(path: Path, size: tuple[int, int] = (160, 220)) -> None:
    Image.new("RGB", size, "#996b55").save(path)


def ready_store(tmp_path: Path) -> tuple[WorkspaceStore, dict]:
    store = WorkspaceStore(tmp_path / "portrait-library")
    _ensure_starter_recipe(store)
    path = tmp_path / "source.png"
    fixture_image(path)
    source = store.add_image_record("source", "Fixture source", path.name, path.read_bytes(), "image/png")
    store.mutate(lambda data: data.update({"benchmark_source_ids": [source["id"]]}))
    return store, source


def wait_for(manager: RunManager, run_id: str) -> dict:
    deadline = time.time() + 5
    while time.time() < deadline:
        run = manager.get(run_id)
        if run["status"] not in {"queued", "running"}:
            return run
        time.sleep(.02)
    return manager.get(run_id)


def test_empty_workspace_bootstraps_atomically_and_serializes_stably(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "portrait-library")
    assert not store.workspace_path.exists()
    assert store.read() == {"version": 1, "sources": [], "benchmark_source_ids": [], "references": [], "recipes": [], "active_recipe_id": None}
    first = store.workspace_path.read_text()
    store.write(store.read())
    assert store.workspace_path.read_text() == first


def test_asset_paths_cannot_escape_workspace(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "portrait-library")
    with pytest.raises(WorkspaceError):
        store.absolute_path("../outside.png")
    with pytest.raises(WorkspaceError):
        store.absolute_path("/etc/passwd")


def test_upload_validates_decoding_and_preserves_upload_provenance(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "portrait-library")
    bad = tmp_path / "bad.txt"
    bad.write_text("not an image")
    with pytest.raises(WorkspaceError, match="readable image"):
        store.add_image_record("source", "Bad", bad.name, bad.read_bytes(), "image/png")
    good = tmp_path / "good.png"
    fixture_image(good)
    source = store.add_image_record("source", "Good", "original-name.png", good.read_bytes(), "image/png")
    assert source["provenance"]["kind"] == "upload"
    assert source["relative_path"].startswith("sources/source_")


def test_recipe_resolution_is_labeled_and_backend_preflight_is_explicit() -> None:
    instruction = resolve_recipe_instruction({**STARTER_RECIPE, "direction": STARTER_RECIPE["direction"], "avoid": "No type"})
    assert instruction.startswith("Medium Brushwork:")
    assert "Avoid: No type" in instruction
    capabilities = model_capabilities("fake/painterly-deterministic")
    assert negotiate_aspect_ratio(capabilities.aspect_ratios) == "5:4"
    mapping = validate_request({"model": capabilities.model, "quality": "low", "avoid": "No text"}, 2, capabilities)
    assert mapping["requested_aspect_ratio"] == "28:23"
    with pytest.raises(ValueError, match="at most"):
        validate_request({"model": "fake/painterly-deterministic", "quality": "low"}, 20, capabilities)


def test_fake_run_persists_snapshot_progress_and_result(tmp_path: Path) -> None:
    store, source = ready_store(tmp_path)
    manager = RunManager(store)
    created = manager.create()
    completed = wait_for(manager, created["run_id"])
    assert completed["status"] == "complete"
    assert completed["benchmark_source_ids"] == [source["id"]]
    assert completed["effective_aspect_ratio"] == "5:4"
    assert completed["items"][0]["status"] == "complete"
    assert completed["items"][0]["output_url"].startswith("asset/runs/")
    assert (store.root / "runs" / created["run_id"] / "run.json").exists()


def test_card_draft_uses_direct_framing_and_updates_without_master(tmp_path: Path) -> None:
    store, _ = ready_store(tmp_path)
    manager = RunManager(store)
    run = wait_for(manager, manager.create()["run_id"])
    card = create_card_draft(store, run["run_id"], run["items"][0]["item_id"], preset="tall")
    assert card["archetype"] == "tall"
    assert card["decision"] == "working"
    assert (store.root / card["render_path"]).exists()
    updated = update_card_draft(store, card["card_id"], {"framing": {"zoom": 1.4, "offset_x": 0.2, "offset_y": -0.1}, "decision": "keep"})
    assert updated["decision"] == "keep"
    assert updated["framing"]["zoom"] == 1.4


def test_cover_transform_clamps_empty_pixels_and_is_deterministic() -> None:
    transform = calculate_cover_transform((160, 220), (336, 276), zoom=1.2, offset_x=99, offset_y=-99)
    assert transform["image_bounds"][0] <= 0
    assert transform["image_bounds"][1] <= 0
    assert transform["image_bounds"][2] >= 336
    assert transform["image_bounds"][3] >= 276
    assert transform == calculate_cover_transform((160, 220), (336, 276), zoom=1.2, offset_x=99, offset_y=-99)
