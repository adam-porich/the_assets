from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .generation import (
    AdapterCapabilities,
    GenerationRequest,
    adapter_for,
    resolved_run_instruction,
    stable_seed,
    validate_request,
)
from .recipes import recipe_from_payload
from .workspace import WorkspaceStore, checksum, new_id, now_iso


class RunManager:
    def __init__(self, store: WorkspaceStore, adapter_factory: Callable[[str, AdapterCapabilities], Any] | None = None) -> None:
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
                run["error"] = "The workbench stopped while this run was active. Start it again to make a new request."
                run["updated_at"] = now_iso()
                self.store.atomic_json(path, run)

    def _snapshot_file(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            destination.hardlink_to(source)
        except OSError:
            shutil.copy2(source, destination)

    def has_completed_live_smoke(self, model: str) -> bool:
        for path in (self.store.root / "runs").glob("*/run.json"):
            run = self.store.read_json(path, {})
            if (
                run.get("status") == "complete"
                and run.get("execution_mode") == "live"
                and run.get("model") == model
                and len(run.get("benchmark_source_ids") or []) == 1
            ):
                return True
        return False

    def create(
        self,
        recipe_draft: dict[str, Any],
        source_ids: list[str],
        outputs_per_source: int,
        execution_mode: str,
        models: list[dict[str, Any]],
        confirm_paid: bool = False,
    ) -> dict[str, Any]:
        if outputs_per_source not in {1, 2}:
            raise ValueError("outputs_per_source must be 1 or 2")
        if execution_mode not in {"live", "simulation"}:
            raise ValueError("execution_mode must be live or simulation")
        if not isinstance(recipe_draft, dict) or not recipe_draft.get("id"):
            raise ValueError("the complete current recipe draft is required")
        source_ids = [str(item) for item in source_ids]
        if not source_ids:
            raise ValueError("choose at least one source before starting a run")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_ids must not contain duplicates")

        with self._run_lock:
            if self._worker_active:
                raise ValueError("one run is already active; wait for it to finish before starting another")
            workspace = self.store.read()
            current_recipe = next((item for item in workspace.get("recipes", []) if item.get("id") == recipe_draft["id"]), None)
            if not current_recipe:
                raise ValueError("the selected recipe no longer exists")
            normalized_recipe = recipe_from_payload(
                {**current_recipe, **recipe_draft, "execution_mode": execution_mode, "created_at": current_recipe.get("created_at")},
                str(current_recipe["id"]),
                now_iso(),
            )
            model = next(
                (
                    item for item in models
                    if item.get("id") == normalized_recipe["model"] and item.get("execution_mode") == execution_mode
                ),
                None,
            )
            if not model:
                raise ValueError(f"{normalized_recipe['model']} is not a {execution_mode} model; choose an explicit replacement")
            capabilities = AdapterCapabilities.from_model(model)
            sources = {str(item["id"]): item for item in workspace.get("sources", [])}
            references = {str(item["id"]): item for item in workspace.get("references", [])}
            missing_sources = [source_id for source_id in source_ids if source_id not in sources]
            if missing_sources:
                raise ValueError("source_ids contains a missing source")
            reference_ids = list(normalized_recipe.get("reference_ids") or [])
            missing_references = [reference_id for reference_id in reference_ids if reference_id not in references]
            if missing_references:
                raise ValueError("recipe contains a missing style reference")
            mapping = validate_request(normalized_recipe, len(reference_ids), capabilities)
            if execution_mode == "live" and not confirm_paid:
                raise ValueError("live generation needs explicit paid-run confirmation")
            if execution_mode == "live" and len(source_ids) > 1 and not self.has_completed_live_smoke(normalized_recipe["model"]):
                raise ValueError("complete a one-source live smoke test with this model before starting a paid benchmark")

            def persist(data: dict[str, Any]) -> None:
                data["recipes"] = [normalized_recipe if item.get("id") == normalized_recipe["id"] else item for item in data["recipes"]]
                data["active_recipe_id"] = normalized_recipe["id"]

            self.store.mutate(persist)

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
            items: list[dict[str, Any]] = []
            for source in source_snapshot:
                for output_index in range(outputs_per_source):
                    items.append({
                        "item_id": new_id("item"), "source_id": source["id"], "source_label": source.get("label"),
                        "output_index": output_index, "status": "queued", "output_path": None, "dimensions": None,
                        "seed": None, "elapsed_seconds": None, "usage": {}, "cost_usd": 0.0, "error": None,
                    })
            created = now_iso()
            run = {
                "run_id": run_id, "created_at": created, "updated_at": created, "status": "queued",
                "recipe_id": normalized_recipe["id"], "recipe_name": normalized_recipe["name"],
                "recipe_snapshot": normalized_recipe, "resolved_instruction": resolved_run_instruction(normalized_recipe, capabilities),
                "benchmark_source_ids": source_ids, "sources_snapshot": source_snapshot, "references_snapshot": reference_snapshot,
                "execution_mode": execution_mode, "model": normalized_recipe["model"], "quality": normalized_recipe["quality"],
                "model_metadata": model, "requested_aspect_ratio": mapping["requested_aspect_ratio"],
                "effective_aspect_ratio": mapping["effective_aspect_ratio"], "backend_capabilities": capabilities.to_json(),
                "backend_mapping": {
                    "references": mapping["reference_mapping"], "avoid": mapping["negative_prompt_mapping"],
                    "quality": mapping["quality_mapping"], "sent_parameters": mapping["sent_parameters"],
                },
                "outputs_per_source": outputs_per_source, "total_calls": len(items), "completed_calls": 0,
                "usage": {}, "cost_usd": 0.0, "items": items, "verdict": "unreviewed", "note": "",
            }
            self._write(run)
            self._worker_active = True
            threading.Thread(target=self._work, args=(run_id,), daemon=True, name=f"portrait-run-{run_id}").start()
            return self.payload(run)

    @staticmethod
    def _sum_usage(run: dict[str, Any]) -> dict[str, Any]:
        totals: dict[str, float] = {}
        for item in run.get("items", []):
            for key, value in (item.get("usage") or {}).items():
                if isinstance(value, (int, float)):
                    totals[key] = totals.get(key, 0) + value
        return {key: int(value) if float(value).is_integer() and key != "cost" else round(value, 8) for key, value in totals.items()}

    def _work(self, run_id: str) -> None:
        try:
            run = self._read(run_id)
            run.update({"status": "running", "started_at": now_iso(), "updated_at": now_iso()})
            self._write(run)
            capabilities = AdapterCapabilities.from_model(run["model_metadata"])
            adapter = self.adapter_factory(str(run["execution_mode"]), capabilities)
            style_paths = [self.store.absolute_path(item["input_path"]) for item in run.get("references_snapshot", [])]
            for item in run["items"]:
                try:
                    item.update({"status": "running", "started_at": now_iso()})
                    run["updated_at"] = now_iso()
                    self._write(run)
                    source = next(source for source in run["sources_snapshot"] if source["id"] == item["source_id"])
                    output_relative = Path("runs") / run_id / f"{item['item_id']}.png"
                    seed = stable_seed(str(item["item_id"]))
                    result = adapter.generate(GenerationRequest(
                        identity_image=self.store.absolute_path(source["input_path"]), style_images=style_paths,
                        instruction=run["resolved_instruction"], negative_prompt=str(run["recipe_snapshot"].get("avoid") or ""),
                        model=run["model"], quality=run["quality"], seed=seed,
                        effective_aspect_ratio=run["effective_aspect_ratio"], output_path=self.store.absolute_path(output_relative),
                    ))
                    thumbnail_relative = Path("runs") / run_id / "thumbnails" / f"{item['item_id']}.jpg"
                    thumbnail_path = self.store.absolute_path(thumbnail_relative)
                    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
                    with Image.open(self.store.absolute_path(output_relative)) as image:
                        thumbnail = image.convert("RGB")
                        thumbnail.thumbnail((480, 360), Image.Resampling.LANCZOS)
                        thumbnail.save(thumbnail_path, format="JPEG", quality=88)
                    item.update({
                        "status": "complete", "output_path": output_relative.as_posix(),
                        "thumbnail_path": thumbnail_relative.as_posix(), "dimensions": result.dimensions,
                        "seed": result.seed, "elapsed_seconds": result.elapsed_seconds, "backend": result.backend,
                        "model": result.model, "usage": result.usage, "cost_usd": result.cost_usd, "error": None,
                    })
                except Exception as exc:
                    item.update({"status": "failed", "error": str(exc)})
                run["completed_calls"] = sum(1 for candidate in run["items"] if candidate.get("status") in {"complete", "failed"})
                run["usage"] = self._sum_usage(run)
                run["cost_usd"] = round(sum(float(candidate.get("cost_usd") or 0) for candidate in run["items"]), 8)
                run["updated_at"] = now_iso()
                self._write(run)
            run["status"] = "complete" if all(item.get("status") == "complete" for item in run["items"]) else "failed"
            run.update({"finished_at": now_iso(), "updated_at": now_iso()})
            self._write(run)
        except Exception as exc:
            run = self._read(run_id)
            run.update({"status": "failed", "error": str(exc), "updated_at": now_iso()})
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
                "execution_mode": run.get("execution_mode", "simulation"), "model": run.get("model"),
                "cost_usd": run.get("cost_usd", 0.0),
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
        recipe_id, now = new_id("recipe"), now_iso()
        recipe = recipe_from_payload({**snapshot, "name": f"{snapshot.get('name', 'Recipe')} · from {run_id[-6:]}"}, recipe_id, now)
        self.store.mutate(lambda data: data["recipes"].append(recipe))
        return recipe

    def compare(self, first_id: str, second_id: str) -> dict[str, Any]:
        first, second = self._read(first_id), self._read(second_id)
        aligned = first.get("benchmark_source_ids") == second.get("benchmark_source_ids")
        first_by_source = {item.get("source_id"): item for item in first.get("items", []) if item.get("output_index") == 0}
        second_by_source = {item.get("source_id"): item for item in second.get("items", []) if item.get("output_index") == 0}
        source_ids = dict.fromkeys(list(first.get("benchmark_source_ids", [])) + list(second.get("benchmark_source_ids", [])))
        rows = [
            {
                "source_id": source_id,
                "first": self.payload({**first, "items": [first_by_source[source_id]]})["items"][0] if source_id in first_by_source else None,
                "second": self.payload({**second, "items": [second_by_source[source_id]]})["items"][0] if source_id in second_by_source else None,
            }
            for source_id in source_ids
        ]
        fields = ("medium_brushwork", "lighting", "background", "composition", "colour", "detail", "identity", "avoid", "model", "quality", "execution_mode")
        first_recipe, second_recipe = first.get("recipe_snapshot", {}), second.get("recipe_snapshot", {})
        changes = []
        for field in fields:
            first_value = first_recipe.get("direction", {}).get(field, first_recipe.get(field))
            second_value = second_recipe.get("direction", {}).get(field, second_recipe.get(field))
            if first_value != second_value:
                changes.append({"field": field, "first": first_value, "second": second_value})
        return {"first": self.payload(first), "second": self.payload(second), "same_benchmark": aligned, "rows": rows, "recipe_changes": changes}
