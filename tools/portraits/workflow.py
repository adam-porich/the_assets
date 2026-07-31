"""Contracts and file-backed stores for the finish-first portrait workflow.

The stores intentionally keep immutable records as ordinary JSON files.  The
workspace remains the small mutable index; runs, selections, finishes, sets,
and generated assets are append-only history.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Iterable, Literal, TypedDict

from .generation import AdapterCapabilities, validate_request
from .workspace import WorkspaceError, WorkspaceStore, checksum, new_id, now_iso


RUN_PURPOSES = ("exploration", "finish", "set-production")
RunPurpose = Literal["exploration", "finish", "set-production"]


class CandidateSelectionItem(TypedDict, total=False):
    order: int
    run_id: str
    item_id: str
    source_id: str
    source_label: str
    output_path: str
    output_checksum_sha256: str
    source_path: str
    source_checksum_sha256: str
    recipe_snapshot: dict[str, Any]
    references_snapshot: list[dict[str, Any]]


class CandidateSelection(TypedDict, total=False):
    selection_id: str
    revision: int
    created_at: str
    updated_at: str
    source_ids: list[str]
    selected_items: list[CandidateSelectionItem]


class FinishSummary(TypedDict, total=False):
    finish_id: str
    version: int
    state: str
    trial_run_id: str
    selection_id: str
    selection_revision: int
    candidate_count: int
    cost_usd: float


class SetItem(TypedDict, total=False):
    set_item_id: str
    order: int
    source_id: str
    status: str
    anchor: bool
    art_source_path: str
    art_checksum_sha256: str


class SetSummary(TypedDict, total=False):
    set_id: str
    name: str
    finish_id: str
    state: str
    source_count: int
    complete_count: int
    failed_count: int
    cost_usd: float
RUN_PURPOSE_LABELS = {
    "exploration": "Explore",
    "finish": "Finish trial",
    "set-production": "Set production",
}
STAGES = ("sources", "explore", "finish", "set", "frames", "completed")
STAGE_LABELS = {
    "sources": "Sources",
    "explore": "Explore",
    "finish": "Finish",
    "set": "Build Set",
    "frames": "Frames",
    "completed": "Completed",
}
BASELINE_RUN_ID = "run_59c947b99f90"


def run_purpose(run: dict[str, Any] | None) -> str:
    value = str((run or {}).get("purpose") or "exploration")
    return value if value in RUN_PURPOSES else "exploration"


def run_purpose_label(purpose: str) -> str:
    return RUN_PURPOSE_LABELS.get(purpose, RUN_PURPOSE_LABELS["exploration"])


def stage_eligibility(stage: str, workspace: dict[str, Any], selection: dict[str, Any] | None = None, finishes: Iterable[dict[str, Any]] = (), sets: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    """Return stable UI-facing prerequisite state for one workflow stage."""
    selected = list(workspace.get("benchmark_source_ids") or [])
    selected_items = list((selection or {}).get("selected_items") or [])
    locked = any(item.get("state") == "locked" for item in finishes)
    active_set = workspace.get("active_set_id")
    ready_set = any(item.get("set_id") == active_set and item.get("state") == "ready" for item in sets)
    requirements = {
        "sources": (bool(selected), "Choose at least one source portrait in Sources."),
        "explore": (bool(selected), "Choose source portraits in Sources before exploring."),
        "finish": (bool(selected_items), "Select 1–3 representative Explore outputs first."),
        "set": (locked, "Lock a complete Finish cohort before building a set."),
        "frames": (ready_set, "Build a ready set before framing portraits."),
        "completed": (ready_set, "A ready active set is required before Completed can show its cards."),
    }
    allowed, message = requirements.get(stage, (False, "Unknown workflow stage."))
    return {"stage": stage, "label": STAGE_LABELS.get(stage, stage), "eligible": allowed, "message": message}


def _copy_snapshot(store: WorkspaceStore, source: Path, relative: Path) -> dict[str, Any]:
    if not source.is_file():
        raise ValueError(f"asset is missing: {source}")
    destination = store.absolute_path(relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.snapshot.tmp")
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {"relative_path": relative.as_posix(), "checksum_sha256": checksum(destination)}


class CandidateSelectionStore:
    """Validates and versions the 1–3 Explore handoff."""

    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
        self.store.ensure()

    @property
    def current_path(self) -> Path:
        return self.store.root / "candidate-selections" / "current.json"

    def current(self) -> dict[str, Any] | None:
        data = self.store.read()
        selection = data.get("candidate_selection")
        if isinstance(selection, dict):
            return selection
        return self.store.read_json(self.current_path, None)

    def _load_run_item(self, run_id: str, item_id: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
        path = self.store.root / "runs" / run_id / "run.json"
        if not path.is_file():
            raise ValueError(f"run {run_id} does not exist")
        run = self.store.read_json(path, {})
        item = next((candidate for candidate in run.get("items", []) if str(candidate.get("item_id")) == item_id), None)
        if not item:
            raise ValueError(f"run item {item_id} does not exist")
        if run_purpose(run) != "exploration":
            raise ValueError("only completed Explore outputs can be selected as Finish candidates")
        if item.get("status") != "complete" or not item.get("output_path"):
            raise ValueError("candidate must be a complete Explore output")
        output = self.store.absolute_path(str(item["output_path"]))
        if not output.is_file():
            raise ValueError("candidate output is missing")
        expected = str(item.get("output_checksum_sha256") or checksum(output))
        actual = checksum(output)
        if expected != actual:
            raise ValueError("candidate output checksum no longer matches the saved Explore item")
        item["output_checksum_sha256"] = expected
        return run, item, output

    def validate(self, refs: list[dict[str, Any] | tuple[str, str]]) -> list[dict[str, Any]]:
        if not isinstance(refs, list) or not 1 <= len(refs) <= 3:
            raise ValueError("select between 1 and 3 Explore outputs")
        normalized: list[dict[str, Any]] = []
        source_ids: set[str] = set()
        for ref in refs:
            if isinstance(ref, dict):
                run_id, item_id = str(ref.get("run_id") or ""), str(ref.get("item_id") or ref.get("run_item_id") or "")
            else:
                run_id, item_id = str(ref[0]), str(ref[1])
            if not run_id or not item_id:
                raise ValueError("each candidate needs a run_id and item_id")
            run, item, output = self._load_run_item(run_id, item_id)
            source_id = str(item.get("source_id") or "")
            if not source_id:
                raise ValueError("candidate is missing its workspace source identity")
            if source_id in source_ids:
                raise ValueError("select at most one Explore output for each source portrait")
            source_ids.add(source_id)
            source = next((candidate for candidate in run.get("sources_snapshot", []) if str(candidate.get("id")) == source_id), {})
            normalized.append({
                "order": len(normalized),
                "run_id": run_id,
                "item_id": item_id,
                "run_item_id": item_id,
                "source_id": source_id,
                "source_label": item.get("source_label") or source.get("label") or source_id,
                "output_path": str(item["output_path"]),
                "output_checksum_sha256": checksum(output),
                "output_dimensions": item.get("dimensions"),
                "source_path": source.get("relative_path"),
                "source_checksum_sha256": source.get("checksum_sha256") or source.get("input_checksum_sha256"),
                "recipe_id": run.get("recipe_id"),
                "recipe_name": run.get("recipe_name"),
                "recipe_snapshot": run.get("recipe_snapshot", {}),
                "references_snapshot": run.get("references_snapshot", []),
                "exploration_run_created_at": run.get("created_at"),
            })
        return normalized

    def save(self, refs: list[dict[str, Any] | tuple[str, str]]) -> dict[str, Any]:
        items = self.validate(refs)
        current = self.current() or {}
        selection_id = str(current.get("selection_id") or new_id("selection"))
        revision = int(current.get("revision") or 0) + 1
        created = str(current.get("created_at") or now_iso())
        record: dict[str, Any] = {
            "selection_id": selection_id,
            "revision": revision,
            "created_at": created,
            "updated_at": now_iso(),
            "source_ids": [item["source_id"] for item in items],
            "selected_items": items,
            "items": items,
        }
        revision_path = self.store.root / "candidate-selections" / f"{selection_id}-r{revision}.json"
        self.store.atomic_json(revision_path, record)
        self.store.atomic_json(self.current_path, record)
        self.store.mutate(lambda data: data.update({"candidate_selection": record}))
        return self.store.candidate_selection_payload(record) or record

    def clear_item(self, run_id: str, item_id: str) -> dict[str, Any] | None:
        current = self.current()
        if not current:
            return None
        remaining = [item for item in current.get("selected_items", []) if not (str(item.get("run_id")) == run_id and str(item.get("item_id")) == item_id)]
        if not remaining:
            self.store.atomic_json(self.current_path, None)
            self.store.mutate(lambda data: data.update({"candidate_selection": None}))
            return None
        return self.save([(str(item["run_id"]), str(item["item_id"])) for item in remaining])

    def reorder(self, refs: list[dict[str, Any] | tuple[str, str]]) -> dict[str, Any]:
        return self.save(refs)


class FinishStore:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
        self.store.ensure()

    def _path(self, finish_id: str) -> Path:
        return self.store.root / "finishes" / finish_id / "finish.json"

    def read(self, finish_id: str) -> dict[str, Any]:
        path = self._path(finish_id)
        if not path.is_file():
            raise ValueError(f"finish {finish_id} does not exist")
        return self.store.read_json(path, {})

    def list(self) -> list[dict[str, Any]]:
        records = []
        for path in (self.store.root / "finishes").glob("*/finish.json"):
            item = self.store.read_json(path, {})
            records.append(self.summary(item))
        return sorted(records, key=lambda item: str(item.get("locked_at") or item.get("created_at") or ""), reverse=True)

    @staticmethod
    def summary(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "finish_id": record.get("finish_id"),
            "version": record.get("version", 1),
            "state": record.get("state", "locked"),
            "trial_run_id": record.get("trial_run_id"),
            "selection_id": record.get("selection_id"),
            "selection_revision": record.get("selection_revision"),
            "candidate_count": len(record.get("approved_output_items", [])),
            "reference_count": len(record.get("references_snapshot", [])),
            "model": record.get("model"),
            "recipe_name": (record.get("recipe_snapshot") or {}).get("name"),
            "change_note": (record.get("recipe_snapshot") or {}).get("change_note", ""),
            "cost_usd": record.get("cost_usd", 0.0),
            "locked_at": record.get("locked_at"),
            "created_at": record.get("created_at"),
        }

    def payload(self, record: dict[str, Any]) -> dict[str, Any]:
        result = dict(record)
        for key in ("candidate_inputs", "approved_output_items"):
            values = result.get(key)
            if isinstance(values, list):
                result[key] = [
                    {**item, "output_url": self.store.asset_url(item.get("output_path")), "input_url": self.store.asset_url(item.get("input_path"))}
                    for item in values if isinstance(item, dict)
                ]
        result["summary"] = self.summary(record)
        return result

    def write(self, record: dict[str, Any]) -> dict[str, Any]:
        finish_id = str(record.get("finish_id") or "")
        if not finish_id:
            raise ValueError("finish_id is required")
        path = self._path(finish_id)
        if path.exists():
            raise ValueError("a locked finish is immutable")
        self.store.atomic_json(path, record)
        return self.payload(record)


class SetStore:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
        self.store.ensure()

    def _path(self, set_id: str) -> Path:
        return self.store.root / "sets" / set_id / "set.json"

    def read(self, set_id: str) -> dict[str, Any]:
        path = self._path(set_id)
        if not path.is_file():
            raise ValueError(f"set {set_id} does not exist")
        return self.store.read_json(path, {})

    def write(self, record: dict[str, Any]) -> dict[str, Any]:
        set_id = str(record.get("set_id") or "")
        if not set_id:
            raise ValueError("set_id is required")
        path = self._path(set_id)
        if path.exists():
            existing = self.store.read_json(path, {})
            immutable_existing = [(item.get("set_item_id"), item.get("source_id"), item.get("order")) for item in existing.get("items", [])]
            immutable_incoming = [(item.get("set_item_id"), item.get("source_id"), item.get("order")) for item in record.get("items", [])]
            if existing.get("finish_id") != record.get("finish_id") or existing.get("source_ids") != record.get("source_ids") or immutable_existing != immutable_incoming:
                raise ValueError("set membership and finish provenance are immutable")
        self.store.atomic_json(path, record)
        return self.payload(record)

    @staticmethod
    def summary(record: dict[str, Any]) -> dict[str, Any]:
        items = record.get("items", [])
        return {
            "set_id": record.get("set_id"),
            "name": record.get("name"),
            "finish_id": record.get("finish_id"),
            "state": record.get("state", "building"),
            "source_count": len(items),
            "complete_count": sum(item.get("status") == "complete" for item in items),
            "failed_count": sum(item.get("status") in {"failed", "interrupted"} for item in items),
            "production_runs": list(record.get("production_runs", [])),
            "cost_usd": record.get("cost_usd", 0.0),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "active": bool(record.get("active")),
        }

    def payload(self, record: dict[str, Any]) -> dict[str, Any]:
        result = dict(record)
        result["items"] = [
            {
                **item,
                "source_url": self.store.asset_url(item.get("source_snapshot_path")),
                "art_url": self.store.asset_url(item.get("art_source_path")),
                "output_url": self.store.asset_url(item.get("art_source_path")),
            }
            for item in record.get("items", [])
        ]
        result["summary"] = self.summary(record)
        return result

    def list(self) -> list[dict[str, Any]]:
        records = [self.store.read_json(path, {}) for path in (self.store.root / "sets").glob("*/set.json")]
        return sorted((self.summary(item) for item in records), key=lambda item: str(item.get("created_at") or ""), reverse=True)


def lock_finish(store: WorkspaceStore, trial_run: dict[str, Any], selection: dict[str, Any], finish_store: FinishStore | None = None) -> dict[str, Any]:
    """Atomically create a complete immutable finish cohort."""
    if run_purpose(trial_run) != "finish":
        raise ValueError("only a Finish trial can be locked")
    expected = list(selection.get("selected_items") or [])
    items = list(trial_run.get("items") or [])
    if trial_run.get("status") != "complete" or len(items) != len(expected) or not items or any(item.get("status") != "complete" for item in items):
        raise ValueError("the whole Finish cohort must be complete before it can be locked")
    approved: list[dict[str, Any]] = []
    for candidate, item in zip(expected, items):
        output_path = str(item.get("output_path") or "")
        output = store.absolute_path(output_path)
        if not output.is_file() or checksum(output) != str(item.get("output_checksum_sha256") or checksum(output)):
            raise ValueError("a Finish output is missing or its checksum changed; this cohort cannot be locked")
        if str(item.get("source_id")) != str(candidate.get("source_id")):
            raise ValueError("Finish items are not aligned with the selection order")
        approved.append({
            "order": len(approved),
            "source_id": candidate.get("source_id"),
            "source_label": candidate.get("source_label"),
            "selection_run_id": candidate.get("run_id"),
            "selection_item_id": candidate.get("item_id"),
            "trial_item_id": item.get("item_id"),
            "output_path": output_path,
            "output_checksum_sha256": checksum(output),
            "dimensions": item.get("dimensions"),
        })
    finish_store = finish_store or FinishStore(store)
    if any(record.get("trial_run_id") == trial_run.get("run_id") for record in finish_store.list()):
        raise ValueError("this Finish trial is already locked and cannot be mutated")
    previous = [record for record in finish_store.list() if record.get("selection_id") == selection.get("selection_id")]
    record = {
        "finish_id": new_id("finish"),
        "version": len(previous) + 1,
        "state": "locked",
        "trial_run_id": trial_run.get("run_id"),
        "selection_id": selection.get("selection_id"),
        "selection_revision": selection.get("revision"),
        "candidate_inputs": selection.get("selected_items", []),
        "approved_output_items": approved,
        "recipe_snapshot": trial_run.get("recipe_snapshot", {}),
        "references_snapshot": trial_run.get("references_snapshot", []),
        "resolved_instruction": trial_run.get("resolved_instruction", ""),
        "model": trial_run.get("model"),
        "model_metadata": trial_run.get("model_metadata", {}),
        "backend_capabilities": trial_run.get("backend_capabilities", {}),
        "backend_mapping": trial_run.get("backend_mapping", {}),
        "usage": trial_run.get("usage", {}),
        "cost_usd": trial_run.get("cost_usd", 0.0),
        "created_at": now_iso(),
        "locked_at": now_iso(),
    }
    return finish_store.write(record)


def sync_set(store: WorkspaceStore, record: dict[str, Any], run_reader: Any) -> dict[str, Any]:
    """Apply immutable production results to a set manifest after refresh."""
    if not record.get("production_runs"):
        return record
    changed = False
    by_source = {str(item.get("source_id")): item for item in record.get("items", [])}
    total_cost = 0.0
    total_usage: dict[str, float] = {}
    for run_id in record.get("production_runs", []):
        try:
            run = run_reader(run_id)
        except Exception:
            continue
        total_cost += float(run.get("cost_usd") or 0)
        for key, value in (run.get("usage") or {}).items():
            if isinstance(value, (int, float)):
                total_usage[key] = total_usage.get(key, 0.0) + float(value)
        for output in run.get("items", []):
            target = by_source.get(str(output.get("source_id")))
            if not target or target.get("anchor"):
                continue
            if output.get("status") == "complete" and output.get("output_path"):
                target.update({
                    "status": "complete",
                    "production_run_id": run_id,
                    "production_item_id": output.get("item_id"),
                    "art_source_path": output.get("output_path"),
                    "art_checksum_sha256": output.get("output_checksum_sha256") or checksum(store.absolute_path(output["output_path"])),
                    "dimensions": output.get("dimensions"),
                    "error": None,
                })
                changed = True
            elif output.get("status") in {"failed", "interrupted"}:
                target.update({"status": output.get("status"), "production_run_id": run_id, "production_item_id": output.get("item_id"), "error": output.get("error")})
                changed = True
    record["cost_usd"] = round(total_cost, 8)
    record["usage"] = {key: int(value) if value.is_integer() else round(value, 8) for key, value in total_usage.items()}
    statuses = [str(item.get("status")) for item in record.get("items", [])]
    if statuses and all(status == "complete" for status in statuses):
        record["state"] = "ready"
    elif any(status in {"failed", "interrupted"} for status in statuses):
        record["state"] = "ready-with-errors"
    else:
        record["state"] = "building"
    if changed or record.get("updated_at") != now_iso():
        record["updated_at"] = now_iso()
    return record


def finish_instruction(recipe: dict[str, Any]) -> str:
    """Resolve a Finish note before inherited art direction, explicitly."""
    note = str(recipe.get("change_note") or "").strip()
    inherited = {**recipe, "change_note": ""}
    from .recipes import resolve_recipe_instruction

    lines = [f"Requested finish change: {note}"] if note else []
    inherited_text = resolve_recipe_instruction(inherited)
    if inherited_text:
        lines.append(f"Inherited art direction:\n{inherited_text}")
    return "\n".join(lines)


def create_finish_trial(
    store: WorkspaceStore,
    manager: Any,
    selection: dict[str, Any],
    recipe_draft: dict[str, Any],
    models: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create one immutable one-output-per-candidate Finish cohort."""
    if not selection or not selection.get("selected_items"):
        raise ValueError("select at least one Explore candidate before starting a Finish trial")
    current = CandidateSelectionStore(store).current()
    if not current or current.get("selection_id") != selection.get("selection_id") or int(current.get("revision", 0)) != int(selection.get("revision", 0)):
        raise ValueError("the selected candidates changed; reload Finish and start a new trial")
    items = list(selection["selected_items"])
    workspace = store.read()
    inherited = dict(items[0].get("recipe_snapshot") or {})
    draft = {**inherited, **recipe_draft}
    draft["direction"] = {**(inherited.get("direction") or {}), **(recipe_draft.get("direction") or {})}
    draft["reference_ids"] = [str(item) for item in recipe_draft.get("reference_ids", inherited.get("reference_ids", []))]
    references = {str(item.get("id")): item for item in workspace.get("references", [])}
    style_refs = []
    for reference_id in draft["reference_ids"]:
        reference = references.get(reference_id)
        if not reference:
            raise ValueError(f"Finish draft contains an unknown reference {reference_id}")
        style_refs.append(reference)
    input_records = []
    for item in items:
        input_records.append({
            "source_id": item["source_id"],
            "label": item.get("source_label") or item["source_id"],
            "relative_path": item["output_path"],
            "input_role": "generated-artifact",
            "originating_run_id": item.get("run_id"),
            "originating_run_item_id": item.get("item_id"),
            "workspace_source_id": item.get("source_id"),
            "candidate_checksum_sha256": item.get("output_checksum_sha256"),
        })
    run = manager.create(
        draft,
        [str(item["source_id"]) for item in items],
        1,
        str(draft.get("execution_mode") or "simulation"),
        models,
        purpose="finish",
        input_records=input_records,
        style_reference_records=style_refs,
        selection_revision=int(selection["revision"]),
        reference_stack=style_refs,
        resolved_instruction_override=finish_instruction(draft),
        metadata={
            "candidate_inputs": items,
            "selection_id": selection.get("selection_id"),
            "inherited_recipe_ids": list(dict.fromkeys(str(item.get("recipe_id")) for item in items if item.get("recipe_id"))),
        },
    )
    raw = manager._read(str(run["run_id"]))
    raw["candidate_inputs"] = items
    raw["selection_id"] = selection.get("selection_id")
    raw["inherited_recipe_ids"] = list(dict.fromkeys(str(item.get("recipe_id")) for item in items if item.get("recipe_id")))
    raw["resolved_instruction"] = finish_instruction(draft)
    manager._write(raw)
    return manager.payload(raw)


class SetManager:
    """Builds and retries immutable source-ordered sets."""

    def __init__(self, store: WorkspaceStore, run_manager: Any) -> None:
        self.store = store
        self.run_manager = run_manager
        self.finishes = FinishStore(store)
        self.sets = SetStore(store)

    def _model(self, finish: dict[str, Any], models: list[dict[str, Any]]) -> dict[str, Any]:
        model_id = str(finish.get("model") or (finish.get("recipe_snapshot") or {}).get("model") or "")
        model = next((item for item in models if str(item.get("id")) == model_id), None)
        if not model:
            raise ValueError(f"{model_id} is unavailable; explicitly choose an available model before building the set")
        return model

    def _finish_refs(self, finish: dict[str, Any]) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for index, anchor in enumerate(finish.get("approved_output_items", [])):
            refs.append({
                "id": f"finish-anchor-{index}",
                "label": f"Approved finish anchor · {anchor.get('source_label') or anchor.get('source_id')}",
                "relative_path": anchor.get("output_path"),
                "checksum_sha256": anchor.get("output_checksum_sha256"),
                "role": "locked-finish-anchor",
            })
        for reference in finish.get("references_snapshot", []):
            refs.append({
                **reference,
                "id": str(reference.get("id")),
                "relative_path": reference.get("input_path") or reference.get("relative_path"),
                "role": "locked-finish-reference",
            })
        return refs

    def _sync_and_save(self, record: dict[str, Any]) -> dict[str, Any]:
        record = sync_set(self.store, record, lambda run_id: self.run_manager._read(run_id))
        record["updated_at"] = now_iso()
        self.sets.write(record)
        return self.sets.payload(record)

    def build(self, name: str, finish_id: str, source_ids: list[str] | None, models: list[dict[str, Any]], execution_mode: str | None = None) -> dict[str, Any]:
        finish = self.finishes.read(finish_id)
        if finish.get("state") != "locked":
            raise ValueError("a locked Finish is required to build a set")
        name = str(name or "").strip()
        if not name:
            raise ValueError("set name is required")
        workspace = self.store.read()
        selected = [str(item) for item in (source_ids if source_ids is not None else workspace.get("benchmark_source_ids", []))]
        if not selected:
            raise ValueError("choose at least one project source before building a set")
        if len(selected) != len(set(selected)):
            raise ValueError("set source selection contains duplicate source IDs")
        sources = {str(item.get("id")): item for item in workspace.get("sources", [])}
        if any(source_id not in sources for source_id in selected):
            raise ValueError("set source selection contains an unknown source")
        anchors = {str(item.get("source_id")): item for item in finish.get("approved_output_items", [])}
        if any(source_id not in selected for source_id in anchors):
            raise ValueError("every locked Finish anchor must remain in the ordered project source selection")
        model = self._model(finish, models)
        recipe = dict(finish.get("recipe_snapshot") or {})
        style_refs = self._finish_refs(finish)
        validate_request(recipe, len(style_refs), AdapterCapabilities.from_model(model))
        set_id = new_id("set")
        set_dir = self.store.root / "sets" / set_id
        set_dir.mkdir(parents=True, exist_ok=True)
        items: list[dict[str, Any]] = []
        input_records: list[dict[str, Any]] = []
        for index, source_id in enumerate(selected):
            source = sources[source_id]
            snapshot_relative = Path("sets") / set_id / "inputs" / "sources" / f"{source_id}{Path(source['relative_path']).suffix.lower()}"
            snapshot = _copy_snapshot(self.store, self.store.absolute_path(source["relative_path"]), snapshot_relative)
            set_item_id = f"{set_id}_item_{index + 1:02d}"
            anchor = anchors.get(source_id)
            if anchor:
                art_path = str(anchor["output_path"])
                status = "complete"
                art_checksum = str(anchor.get("output_checksum_sha256") or checksum(self.store.absolute_path(art_path)))
                production_item_id = anchor.get("trial_item_id")
                production_run_id = finish.get("trial_run_id")
            else:
                art_path, art_checksum, status = None, None, "queued"
                production_item_id, production_run_id = None, None
                input_records.append({
                    "source_id": source_id,
                    "label": source.get("label") or source_id,
                    "relative_path": snapshot_relative.as_posix(),
                    "input_role": "workspace-source-snapshot",
                })
            items.append({
                "set_item_id": set_item_id,
                "order": index,
                "source_id": source_id,
                "source_label": source.get("label") or source_id,
                "status": status,
                "anchor": bool(anchor),
                "finish_id": finish_id,
                "source_snapshot_path": snapshot["relative_path"],
                "source_checksum_sha256": snapshot["checksum_sha256"],
                "dimensions": (anchor or {}).get("dimensions") if anchor else None,
                "art_source_path": art_path,
                "art_checksum_sha256": art_checksum,
                "production_run_id": production_run_id,
                "production_item_id": production_item_id,
                "error": None,
                "reference_stack": [{"role": "identity", "source_id": source_id}, *[{"role": ref.get("role"), "id": ref.get("id"), "path": ref.get("relative_path")} for ref in style_refs]],
            })
        record = {
            "set_id": set_id,
            "name": name,
            "finish_id": finish_id,
            "state": "ready" if not input_records else "building",
            "source_ids": selected,
            "items": items,
            "production_runs": [],
            "model": model.get("id"),
            "recipe_snapshot": recipe,
            "references_snapshot": style_refs,
            "usage": {},
            "cost_usd": 0.0,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        self.sets.write(record)
        self.store.mutate(lambda data: data.update({"active_set_id": set_id}))
        if input_records:
            run = self.run_manager.create(
                recipe,
                [str(item["source_id"]) for item in input_records],
                1,
                execution_mode or str(recipe.get("execution_mode") or "simulation"),
                models,
                purpose="set-production",
                input_records=input_records,
                style_reference_records=style_refs,
                reference_stack=style_refs,
            )
            record["production_runs"] = [run["run_id"]]
            for item in record["items"]:
                if not item.get("anchor"):
                    item["production_run_id"] = run["run_id"]
            self.sets.write(record)
        return self.sets.payload(record)

    def get(self, set_id: str) -> dict[str, Any]:
        return self._sync_and_save(self.sets.read(set_id))

    def list(self) -> list[dict[str, Any]]:
        result = []
        for summary in self.sets.list():
            try:
                result.append(self.get(str(summary["set_id"]))["summary"])
            except ValueError:
                result.append(summary)
        active = self.store.read().get("active_set_id")
        for item in result:
            item["active"] = item.get("set_id") == active
        return result

    def switch(self, set_id: str) -> dict[str, Any]:
        self.sets.read(set_id)
        self.store.mutate(lambda data: data.update({"active_set_id": set_id}))
        return self.get(set_id)

    def retry(self, set_id: str, models: list[dict[str, Any]], execution_mode: str | None = None) -> dict[str, Any]:
        record = self.get(set_id)
        failed = [item for item in record.get("items", []) if not item.get("anchor") and item.get("status") in {"failed", "interrupted"}]
        if not failed:
            raise ValueError("there are no failed or interrupted set items to retry")
        recipe = dict(record.get("recipe_snapshot") or {})
        style_refs = list(record.get("references_snapshot") or [])
        input_records = [{"source_id": item["source_id"], "label": item.get("source_label"), "relative_path": item["source_snapshot_path"], "input_role": "workspace-source-snapshot"} for item in failed]
        run = self.run_manager.create(recipe, [item["source_id"] for item in failed], 1, execution_mode or str(recipe.get("execution_mode") or "simulation"), models, purpose="set-production", input_records=input_records, style_reference_records=style_refs, reference_stack=style_refs)
        record.setdefault("production_runs", []).append(run["run_id"])
        for item in failed:
            item["production_run_id"] = run["run_id"]
            item["status"] = "queued"
            item["error"] = None
        return self.sets.write(record)
