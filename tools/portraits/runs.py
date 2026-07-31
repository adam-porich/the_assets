from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .generation import GenerationRequest, adapter_for, model_capabilities, resolved_run_instruction, validate_request
from .recipes import recipe_from_payload, resolve_recipe_instruction
from .workspace import WorkspaceError, WorkspaceStore, checksum, new_id, now_iso


class RunManager:
    def __init__(self, store: WorkspaceStore, adapter_factory: Callable[[str], Any] | None = None) -> None:
        self.store = store
        self.store.ensure()
        self.adapter_factory = adapter_factory or adapter_for
        self._run_lock = threading.RLock()
        self._worker_active = False
        self.mark_interrupted()

    def _run_path(self, run_id: str) -> Path:
        return self.store.root / "runs" / run_id / "run.json"

    def _read(self, run_id: str) -> dict[str, Any]:
        path = self._run_path(run_id)
        if not path.exists():
            raise ValueError(f"run {run_id} does not exist")
        return self.store.read_json(path, {})

    def _write(self, run: dict[str, Any]) -> None:
        self.store.atomic_json(self._run_path(str(run["run_id"])), run)

    def mark_interrupted(self) -> None:
        runs_dir = self.store.root / "runs"
        for path in runs_dir.glob("*/run.json") if runs_dir.exists() else []:
            run = self.store.read_json(path, {})
            if run.get("status") in {"queued", "running"}:
                run["status"] = "interrupted"
                run["error"] = "The workbench stopped while this run was active. Start it again to make a new paid request."
                run["updated_at"] = now_iso()
                self.store.atomic_json(path, run)

    def _snapshot_file(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            destination.hardlink_to(source)
        except OSError:
            shutil.copy2(source, destination)

    def create(self, recipe_id: str | None = None, outputs_per_source: int = 1) -> dict[str, Any]:
        if outputs_per_source not in {1, 2}:
            raise ValueError("outputs_per_source must be 1 or 2")
        with self._run_lock:
            if self._worker_active:
                raise ValueError("one run is already active; wait for it to finish before starting another")
            workspace = self.store.read()
            selected_recipe_id = recipe_id or workspace.get("active_recipe_id")
            recipe = next((item for item in workspace.get("recipes", []) if item.get("id") == selected_recipe_id), None)
            if not recipe:
                raise ValueError("select a recipe before starting a run")
            source_ids = list(workspace.get("benchmark_source_ids") or [])
            if not source_ids:
                raise ValueError("add at least one source to the benchmark before starting a run")
            sources = {str(item["id"]): item for item in workspace.get("sources", [])}
            references = {str(item["id"]): item for item in workspace.get("references", [])}
            missing_sources = [source_id for source_id in source_ids if source_id not in sources]
            if missing_sources:
                raise ValueError("benchmark contains a missing source")
            reference_ids = list(recipe.get("reference_ids") or [])
            missing_references = [reference_id for reference_id in reference_ids if reference_id not in references]
            if missing_references:
                raise ValueError("recipe contains a missing style reference")
            capabilities = model_capabilities(str(recipe["model"]))
            mapping = validate_request(recipe, len(reference_ids), capabilities)
            run_id = new_id("run")
            run_dir = self.store.root / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            source_snapshot: list[dict[str, Any]] = []
            for source_id in source_ids:
                source = sources[source_id]
                destination = Path("runs") / run_id / "inputs" / "sources" / f"{source_id}{Path(source['relative_path']).suffix.lower()}"
                self._snapshot_file(self.store.absolute_path(source["relative_path"]), self.store.absolute_path(destination))
                source_snapshot.append({**source, "input_path": destination.as_posix(), "input_checksum_sha256": checksum(self.store.absolute_path(destination))})
            reference_snapshot: list[dict[str, Any]] = []
            for reference_id in reference_ids:
                reference = references[reference_id]
                destination = Path("runs") / run_id / "inputs" / "references" / f"{reference_id}{Path(reference['relative_path']).suffix.lower()}"
                self._snapshot_file(self.store.absolute_path(reference["relative_path"]), self.store.absolute_path(destination))
                reference_snapshot.append({**reference, "input_path": destination.as_posix(), "input_checksum_sha256": checksum(self.store.absolute_path(destination))})
            items = []
            for source in source_snapshot:
                for output_index in range(outputs_per_source):
                    item_id = new_id("item")
                    items.append({
                        "item_id": item_id,
                        "source_id": source["id"],
                        "source_label": source.get("label"),
                        "output_index": output_index,
                        "status": "queued",
                        "output_path": None,
                        "dimensions": None,
                        "seed": None,
                        "elapsed_seconds": None,
                        "error": None,
                    })
            run = {
                "run_id": run_id,
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "status": "queued",
                "recipe_id": recipe["id"],
                "recipe_name": recipe["name"],
                "recipe_snapshot": recipe,
                "resolved_instruction": resolved_run_instruction(recipe, capabilities),
                "benchmark_source_ids": source_ids,
                "sources_snapshot": source_snapshot,
                "references_snapshot": reference_snapshot,
                "model": recipe["model"],
                "quality": recipe["quality"],
                "requested_aspect_ratio": mapping["requested_aspect_ratio"],
                "effective_aspect_ratio": mapping["effective_aspect_ratio"],
                "backend_capabilities": capabilities.to_json(),
                "backend_mapping": {"references": mapping["reference_mapping"], "avoid": mapping["negative_prompt_mapping"]},
                "outputs_per_source": outputs_per_source,
                "total_calls": len(items),
                "completed_calls": 0,
                "items": items,
                "verdict": "unreviewed",
                "note": "",
            }
            self._write(run)
            self._worker_active = True
            threading.Thread(target=self._work, args=(run_id,), daemon=True, name=f"portrait-run-{run_id}").start()
            return self.payload(run)

    def _work(self, run_id: str) -> None:
        try:
            run = self._read(run_id)
            run["status"] = "running"
            run["started_at"] = now_iso()
            run["updated_at"] = now_iso()
            self._write(run)
            adapter = self.adapter_factory(str(run["model"]))
            style_paths = [self.store.absolute_path(item["input_path"]) for item in run.get("references_snapshot", [])]
            for item in run["items"]:
                try:
                    item["status"] = "running"
                    item["started_at"] = now_iso()
                    run["updated_at"] = now_iso()
                    self._write(run)
                    source = next(source for source in run["sources_snapshot"] if source["id"] == item["source_id"])
                    output_relative = Path("runs") / run_id / f"{item['item_id']}.png"
                    seed = int(uuid.UUID(item["item_id"].split("_")[-1] + "0" * 20).int % (2**31)) if item["item_id"].startswith("item_") else abs(hash(item["item_id"])) % (2**31)
                    result = adapter.generate(GenerationRequest(
                        identity_image=self.store.absolute_path(source["input_path"]),
                        style_images=style_paths,
                        instruction=run["resolved_instruction"],
                        model=run["model"],
                        quality=run["quality"],
                        seed=seed,
                        effective_aspect_ratio=run["effective_aspect_ratio"],
                        output_path=self.store.absolute_path(output_relative),
                    ))
                    thumbnail_relative = Path("runs") / run_id / "thumbnails" / f"{item['item_id']}.jpg"
                    thumbnail_path = self.store.absolute_path(thumbnail_relative)
                    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
                    with Image.open(self.store.absolute_path(output_relative)) as image:
                        thumbnail = image.convert("RGB")
                        thumbnail.thumbnail((480, 360), Image.Resampling.LANCZOS)
                        thumbnail.save(thumbnail_path, format="JPEG", quality=88)
                    item.update({"status": "complete", "output_path": output_relative.as_posix(), "thumbnail_path": thumbnail_relative.as_posix(), "dimensions": result.dimensions, "seed": result.seed, "elapsed_seconds": result.elapsed_seconds, "backend": result.backend, "model": result.model, "error": None})
                except Exception as exc:
                    item.update({"status": "failed", "error": str(exc)})
                run["completed_calls"] = sum(1 for candidate in run["items"] if candidate.get("status") in {"complete", "failed"})
                run["updated_at"] = now_iso()
                self._write(run)
            run["status"] = "complete" if all(item.get("status") == "complete" for item in run["items"]) else "failed"
            run["finished_at"] = now_iso()
            run["updated_at"] = now_iso()
            self._write(run)
        except Exception as exc:
            run = self._read(run_id)
            run["status"] = "failed"
            run["error"] = str(exc)
            run["updated_at"] = now_iso()
            self._write(run)
        finally:
            with self._run_lock:
                self._worker_active = False

    def payload(self, run: dict[str, Any]) -> dict[str, Any]:
        result = dict(run)
        result["items"] = []
        for item in run.get("items", []):
            item_payload = dict(item)
            item_payload["output_url"] = self.store.asset_url(item.get("output_path"))
            item_payload["thumbnail_url"] = self.store.asset_url(item.get("thumbnail_path"))
            item_payload["source_url"] = self.store.asset_url(next((source.get("input_path") for source in run.get("sources_snapshot", []) if source.get("id") == item.get("source_id")), None))
            result["items"].append(item_payload)
        result["sources_snapshot"] = [{**source, "input_url": self.store.asset_url(source.get("input_path"))} for source in run.get("sources_snapshot", [])]
        result["references_snapshot"] = [{**reference, "input_url": self.store.asset_url(reference.get("input_path"))} for reference in run.get("references_snapshot", [])]
        return result

    def get(self, run_id: str) -> dict[str, Any]:
        return self.payload(self._read(run_id))

    def list(self) -> list[dict[str, Any]]:
        result = []
        for path in sorted((self.store.root / "runs").glob("*/run.json"), key=lambda candidate: candidate.stat().st_mtime, reverse=True):
            run = self.store.read_json(path, {})
            result.append({
                "run_id": run.get("run_id"), "recipe_id": run.get("recipe_id"), "recipe_name": run.get("recipe_name"),
                "status": run.get("status"), "source_count": len(run.get("benchmark_source_ids", [])),
                "verdict": run.get("verdict", "unreviewed"), "created_at": run.get("created_at"),
                "completed_calls": run.get("completed_calls", 0), "total_calls": run.get("total_calls", 0),
            })
        return result

    def update_review(self, run_id: str, verdict: str, note: str = "") -> dict[str, Any]:
        if verdict not in {"unreviewed", "coherent", "mixed", "not-useful"}:
            raise ValueError("unknown sheet verdict")
        run = self._read(run_id)
        run["verdict"], run["note"], run["updated_at"] = verdict, note.strip()[:500], now_iso()
        self._write(run)
        return self.payload(run)

    def duplicate_recipe(self, run_id: str) -> dict[str, Any]:
        run = self._read(run_id)
        snapshot = dict(run.get("recipe_snapshot") or {})
        recipe_id = new_id("recipe")
        now = now_iso()
        recipe = recipe_from_payload({**snapshot, "name": f"{snapshot.get('name', 'Recipe')} · from {run_id[-6:]}"}, recipe_id, now)
        self.store.mutate(lambda data: data["recipes"].append(recipe))
        return recipe

    def compare(self, first_id: str, second_id: str) -> dict[str, Any]:
        first, second = self._read(first_id), self._read(second_id)
        aligned = first.get("benchmark_source_ids") == second.get("benchmark_source_ids")
        first_by_source = {item.get("source_id"): item for item in first.get("items", []) if item.get("output_index") == 0}
        second_by_source = {item.get("source_id"): item for item in second.get("items", []) if item.get("output_index") == 0}
        rows = [{"source_id": source_id, "first": self.payload({**first, "items": [first_by_source[source_id]]})["items"][0] if source_id in first_by_source else None, "second": self.payload({**second, "items": [second_by_source[source_id]]})["items"][0] if source_id in second_by_source else None} for source_id in dict.fromkeys(list(first.get("benchmark_source_ids", [])) + list(second.get("benchmark_source_ids", [])))]
        fields = ("medium_brushwork", "lighting", "background", "composition", "colour", "detail", "identity", "avoid", "model", "quality")
        first_recipe, second_recipe = first.get("recipe_snapshot", {}), second.get("recipe_snapshot", {})
        changes = []
        for field in fields:
            first_value = first_recipe.get("direction", {}).get(field, first_recipe.get(field))
            second_value = second_recipe.get("direction", {}).get(field, second_recipe.get(field))
            if first_value != second_value:
                changes.append({"field": field, "first": first_value, "second": second_value})
        return {"first": self.payload(first), "second": self.payload(second), "same_benchmark": aligned, "rows": rows, "recipe_changes": changes}

