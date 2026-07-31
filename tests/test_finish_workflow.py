from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from tools.cards.pipeline import ensure_set_card_drafts, update_card_draft
from tools.portraits.generation import simulation_model
from tools.portraits.recipes import recipe_from_payload
from tools.portraits.runs import RunManager
from tools.portraits.workflow import (
    CandidateSelectionStore,
    FinishStore,
    SetManager,
    create_finish_trial,
    lock_finish,
)
from tools.portraits.workspace import WorkspaceStore, now_iso


def _png(colour: str) -> bytes:
    image = Image.new("RGB", (96, 128), colour)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _fixture(tmp_path: Path, count: int = 2) -> tuple[WorkspaceStore, list[dict], dict, list[dict]]:
    store = WorkspaceStore(tmp_path / "portrait-library")
    store.ensure()
    sources = []
    for index, colour in enumerate(("red", "blue", "green")[:count]):
        source = store.add_image_record("source", f"Portrait {index}", f"source-{index}.png", _png(colour), "image/png")
        sources.append(source)
    store.mutate(lambda data: data.update({"benchmark_source_ids": [item["id"] for item in sources]}))
    reference = store.add_image_record("reference", "Style reference", "reference.png", _png("purple"), "image/png")
    recipe = recipe_from_payload({
        "name": "Simulation study", "model": "fake/painterly-deterministic", "execution_mode": "simulation", "quality": "low",
        "change_note": "", "direction": {"identity": "retain the apparent identity"}, "avoid": "", "reference_ids": [reference["id"]],
    }, "recipe_test", now_iso())
    store.mutate(lambda data: (data["recipes"].append(recipe), data.update({"active_recipe_id": recipe["id"]})))
    return store, sources, recipe, [simulation_model()]


def _wait(manager: RunManager, run_id: str) -> dict:
    for _ in range(500):
        run = manager.get(run_id)
        if run["status"] not in {"queued", "running"}:
            return run
        time.sleep(0.01)
    raise AssertionError("run did not finish")


def test_candidate_selection_versions_and_rejects_duplicate_source(tmp_path: Path) -> None:
    store, sources, recipe, models = _fixture(tmp_path, 2)
    manager = RunManager(store)
    first = _wait(manager, manager.create(recipe, [sources[0]["id"]], 2, "simulation", models)["run_id"])
    second = _wait(manager, manager.create(recipe, [sources[1]["id"]], 1, "simulation", models)["run_id"])
    selection_store = CandidateSelectionStore(store)
    selection = selection_store.save([{"run_id": first["run_id"], "item_id": first["items"][0]["item_id"]}])
    assert selection["revision"] == 1
    with pytest.raises(ValueError, match="one.*source"):
        selection_store.save([{"run_id": first["run_id"], "item_id": first["items"][0]["item_id"]}, {"run_id": first["run_id"], "item_id": first["items"][1]["item_id"]}])
    revised = selection_store.save([{"run_id": first["run_id"], "item_id": first["items"][0]["item_id"]}, {"run_id": second["run_id"], "item_id": second["items"][0]["item_id"]}])
    assert revised["revision"] == 2
    assert [item["source_id"] for item in revised["selected_items"]] == [sources[0]["id"], sources[1]["id"]]


def test_finish_lock_set_production_and_active_set_cards(tmp_path: Path) -> None:
    store, sources, recipe, models = _fixture(tmp_path, 2)
    manager = RunManager(store)
    exploration = _wait(manager, manager.create(recipe, [sources[0]["id"]], 1, "simulation", models)["run_id"])
    selection = CandidateSelectionStore(store).save([{"run_id": exploration["run_id"], "item_id": exploration["items"][0]["item_id"]}])
    trial = create_finish_trial(store, manager, selection, {**recipe, "change_note": "unify the dusk finish"}, models)
    trial = _wait(manager, trial["run_id"])
    assert trial["purpose"] == "finish"
    assert len(trial["items"]) == 1
    assert trial["sources_snapshot"][0]["input_role"] == "generated-artifact"
    assert trial["sources_snapshot"][0]["input_checksum_sha256"] == selection["selected_items"][0]["output_checksum_sha256"]
    assert trial["resolved_instruction"].startswith("Requested finish change:")
    finish = lock_finish(store, trial, selection)
    assert FinishStore(store).read(finish["finish_id"])["state"] == "locked"
    with pytest.raises(ValueError, match="immutable"):
        FinishStore(store).write(finish)

    portrait_set = SetManager(store, manager).build("Coherent set", finish["finish_id"], [item["id"] for item in sources], models)
    assert portrait_set["state"] == "building"
    assert portrait_set["items"][0]["anchor"] is True
    assert portrait_set["items"][1]["anchor"] is False
    production = _wait(manager, portrait_set["production_runs"][0])
    portrait_set = SetManager(store, manager).get(portrait_set["set_id"])
    assert portrait_set["state"] == "ready"
    generated = next(item for item in portrait_set["items"] if not item["anchor"])
    assert [item["role"] for item in generated["reference_stack"]] == ["identity", "locked-finish-anchor", "locked-finish-reference"]
    cards = ensure_set_card_drafts(store, portrait_set["set_id"])
    assert len(cards) == 2
    assert all(card["set_id"] == portrait_set["set_id"] and card["finish_id"] == finish["finish_id"] for card in cards)
    kept = update_card_draft(store, cards[0]["card_id"], {"decision": "keep"})
    assert kept["set_item_id"] == cards[0]["set_item_id"]
    assert kept["finish_id"] == finish["finish_id"]
