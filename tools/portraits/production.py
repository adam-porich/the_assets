from __future__ import annotations

import copy
import json
import shutil
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from tools.cards.backgrounds import choose_chroma_key, composite_foreground, extract_foreground
from tools.cards.registry import RenderBundle, registry
from tools.cards.style_pipeline import StyleStore, style_checksum, validate_style

from .generation import AdapterCapabilities, GenerationRequest, adapter_for, stable_seed, validate_request
from .workspace import WorkspaceError, WorkspaceStore, checksum, new_id, now_iso


TERMINAL_ITEM_STATES = {"ready", "failed", "interrupted"}


def generation_instruction(direction: dict[str, Any]) -> str:
    """Resolve structured style direction into the exact prompt sent to a provider."""
    labels = {
        "identity_to_retain": "Identity to retain",
        "composition_to_normalize": "Composition to normalize",
        "expression_pose_to_discard": "Expression and pose to discard",
        "rendering_language": "Rendering language",
        "intent": "Intent",
        "composition": "Composition",
        "rendering": "Rendering",
        "lighting": "Lighting",
        "palette_direction": "Palette direction",
    }
    return "\n".join(
        f"{labels.get(str(key), str(key).replace('_', ' ').title())}: {str(value).strip()}"
        for key, value in direction.items()
        if str(value).strip()
    )


class CardProductionManager:
    """The one worker used by card production and complete style trials."""

    def __init__(self, store: WorkspaceStore, style_store: StyleStore | None = None, adapter_factory: Callable[[str, AdapterCapabilities], Any] | None = None) -> None:
        self.store = store
        self.store.ensure()
        self.styles = style_store or StyleStore(store)
        self.adapter_factory = adapter_factory or adapter_for
        self._lock = threading.RLock()
        self._active_batch: str | None = None
        self.mark_interrupted()

    @property
    def is_active(self) -> bool:
        return self._active_batch is not None

    def _path(self, batch_id: str) -> Path:
        if not batch_id or "/" in batch_id or "\\" in batch_id or ".." in batch_id:
            raise WorkspaceError("unsafe production batch ID")
        return self.store.root / "production" / batch_id / "batch.json"

    def _read(self, batch_id: str) -> dict[str, Any]:
        path = self._path(batch_id)
        record = self.store.read_json(path, None)
        if not isinstance(record, dict):
            raise ValueError(f"production batch {batch_id} does not exist")
        return record

    def _write(self, record: dict[str, Any]) -> None:
        self.store.atomic_json(self._path(str(record["batch_id"])), record)

    @staticmethod
    def _copy(source: Path, destination: Path) -> None:
        if not source.is_file():
            raise ValueError(f"input asset is missing: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        shutil.copy2(source, temporary)
        temporary.replace(destination)

    @staticmethod
    def _save_image(image: Image.Image, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        image.save(temporary, format="PNG", optimize=True)
        temporary.replace(path)

    def mark_interrupted(self) -> None:
        production = self.store.root / "production"
        for path in production.glob("*/batch.json") if production.exists() else []:
            record = self.store.read_json(path, {})
            if record.get("status") in {"queued", "running", "processing"}:
                record["status"] = "interrupted"
                record["error"] = "The worker stopped while this batch was active. Retry failed items to make new attempts."
                for item in record.get("items", []):
                    if item.get("status") not in TERMINAL_ITEM_STATES:
                        item["status"] = "interrupted"
                        item["phase"] = "interrupted"
                        item["error"] = record["error"]
                record["updated_at"] = now_iso()
                self.store.atomic_json(path, record)

    def _model(self, style: dict[str, Any], models: list[dict[str, Any]]) -> dict[str, Any]:
        generation = style["generation"]
        model_id, mode = str(generation["model_id"]), str(generation["execution_mode"])
        model = next((item for item in models if str(item.get("id")) == model_id and str(item.get("execution_mode")) == mode), None)
        if not model:
            raise ValueError(f"{model_id} is not an available {mode} model")
        return model

    def _validate_start(self, style: dict[str, Any], source_ids: list[str], models: list[dict[str, Any]], purpose: str) -> tuple[dict[str, Any], AdapterCapabilities, dict[str, Any], list[dict[str, Any]]]:
        if not source_ids:
            raise ValueError("select at least one source image")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("selected source IDs must be unique")
        model = self._model(style, models)
        capabilities = AdapterCapabilities.from_model(model)
        generation = style["generation"]
        if purpose == "card-production" and str(generation.get("execution_mode")) != "live":
            raise ValueError("the active production style must use live image generation; simulation is preview-only")
        generation_refs = [asset for asset in style["reference_pack"]["assets"] if asset.get("role") == "generation-reference"]
        mapping = validate_request({"model": generation["model_id"], "quality": generation["quality"], "execution_mode": generation["execution_mode"]}, len(generation_refs), capabilities)
        return model, capabilities, mapping, generation_refs

    def create(self, source_ids: list[str], style: dict[str, Any], models: list[dict[str, Any]], *, purpose: str = "card-production", consent: bool = False, prompt_override: str | None = None, content_direction: str | None = None, background_id: str | None = None) -> dict[str, Any]:
        if purpose not in {"card-production", "style-trial"}:
            raise ValueError("production purpose must be card-production or style-trial")
        style = validate_style(copy.deepcopy(style), require_locked=purpose == "card-production")
        with self._lock:
            if self._active_batch:
                raise ValueError("one paid generation batch is already active; wait for it to finish")
            workspace = self.store.read()
            sources = {str(item["id"]): item for item in workspace.get("inputs", []) if item.get("accepted_normalisation")}
            source_ids = [str(item) for item in source_ids]
            if any(source_id not in sources for source_id in source_ids):
                raise ValueError("selected input IDs contain a missing or unprepared Input")
            model, capabilities, mapping, generation_refs = self._validate_start(style, source_ids, models, purpose)
            if capabilities.execution_mode == "live" and not consent:
                raise ValueError("explicit consent is required before starting paid image generation")
            batch_id = new_id("batch")
            batch_dir = self._path(batch_id).parent
            source_snapshots: list[dict[str, Any]] = []
            for source_id in source_ids:
                source = sources[source_id]
                source_path = self.store.absolute_path(str((source.get("accepted_normalisation") or {}).get("relative_path") or ""))
                destination = batch_dir / "inputs" / "sources" / f"{source_id}{source_path.suffix.lower() or '.png'}"
                self._copy(source_path, destination)
                original_source = self.store.absolute_path(str(source.get("original_path") or ""))
                original_destination = batch_dir / "inputs" / "originals" / f"{source_id}{original_source.suffix.lower() or '.png'}"
                self._copy(original_source, original_destination)
                source_snapshots.append({**copy.deepcopy(source), "input_path": destination.relative_to(self.store.root).as_posix(), "input_checksum_sha256": checksum(destination), "original_input_path": original_destination.relative_to(self.store.root).as_posix(), "original_input_checksum_sha256": checksum(original_destination)})
            reference_snapshots: list[dict[str, Any]] = []
            for reference in generation_refs:
                path = self.store.absolute_path(str(reference.get("relative_path") or ""))
                destination = batch_dir / "inputs" / "references" / f"{reference['id']}{path.suffix.lower() or '.png'}"
                self._copy(path, destination)
                reference_snapshots.append({**copy.deepcopy(reference), "input_path": destination.relative_to(self.store.root).as_posix(), "input_checksum_sha256": checksum(destination)})
            created = now_iso()
            items = []
            for source in source_snapshots:
                lineage_id = new_id("lineage")
                items.append(self._new_item(source, 1, lineage_id, reference_snapshots, prompt_override=prompt_override, content_direction=content_direction, background_id=background_id or style.get("backgrounds", {}).get("default_id")))
            record = {
                "batch_id": batch_id, "purpose": purpose, "created_at": created, "updated_at": created,
                "status": "queued", "style_snapshot": style, "style_version_id": style["identity"]["style_version_id"],
                "style_checksum_sha256": style["checksums"]["style_sha256"], "selected_source_ids": source_ids,
                "source_snapshots": source_snapshots, "reference_snapshots": reference_snapshots,
                "model": model, "model_capabilities": capabilities.to_json(), "backend_mapping": mapping,
                "generation_authorization": {"required": capabilities.execution_mode == "live", "consent": bool(consent), "granted_at": now_iso() if consent else None, "purpose": purpose},
                "requested_paid_calls": len(source_ids) * (2 if int(style.get("schema_version", 1)) == 2 else 1), "paid_calls": 0, "usage": {}, "cost_usd": 0.0,
                "items": items, "calibration_source_ids": source_ids if purpose == "style-trial" else None,
                "requires_acceptance": purpose == "card-production",
            }
            self._write(record)
            self._active_batch = batch_id
            threading.Thread(target=self._work, args=(batch_id,), daemon=True, name=f"card-production-{batch_id}").start()
            return self.payload(record)

    def _new_item(self, source: dict[str, Any], attempt_number: int, lineage_id: str, references: list[dict[str, Any]], *, prompt_override: str | None = None, content_direction: str | None = None, background_id: str | None = None) -> dict[str, Any]:
        return {
            "item_id": new_id("item"), "source_id": source["id"], "source_label": source.get("label") or source["id"],
            "attempt_number": attempt_number, "lineage_id": lineage_id, "status": "queued", "phase": "queued", "error": None,
            "source_input_path": source["input_path"], "source_input_checksum_sha256": source["input_checksum_sha256"],
            "reference_stack": [{"role": "identity", "source_id": source["id"], "input_path": source["input_path"], "checksum_sha256": source["input_checksum_sha256"]}, *[
                {"role": "generation-reference", "reference_id": reference["id"], "label": reference.get("label") or reference["id"], "input_path": reference["input_path"], "checksum_sha256": reference["input_checksum_sha256"]} for reference in references
            ]],
            "framing": None, "background_id": background_id, "background_metadata": {}, "matte_metadata": {}, "render_revision": 0, "render_revisions": [], "raw_foreground_path": None, "foreground_path": None, "master_path": None, "master_checksum_sha256": None,
            "logical_art_path": None, "art_path": None, "card_path": None, "card_checksum_sha256": None,
            "generation": {}, "generation_request": {}, "generation_stages": [], "normalised_path": None, "normalised_checksum_sha256": None, "render_metadata": {}, "usage": {}, "cost_usd": None,
            "prompt_override": prompt_override.strip() if prompt_override and prompt_override.strip() else None,
            "content_direction": content_direction.strip() if content_direction and content_direction.strip() else None, "accepted": False,
        }

    def _work(self, batch_id: str) -> None:
        try:
            record = self._read(batch_id)
            record.update({"status": "running", "started_at": now_iso(), "updated_at": now_iso()}); self._write(record)
            capabilities = AdapterCapabilities.from_model(record["model"])
            adapter = self.adapter_factory(str(record["style_snapshot"]["generation"]["execution_mode"]), capabilities)
            for item in record["items"]:
                if item.get("status") not in {"queued"}:
                    continue
                try:
                    item.update({"status": "generating", "phase": "normalising", "started_at": now_iso()}); self._write(record)
                    source_path = self.store.absolute_path(str(item["source_input_path"]))
                    master_relative = Path("production") / batch_id / "masters" / f"{item['item_id']}.png"
                    self.store.absolute_path(master_relative).parent.mkdir(parents=True, exist_ok=True)
                    reference_paths = [self.store.absolute_path(str(reference["input_path"])) for reference in record["reference_snapshots"]]
                    generation = record["style_snapshot"]["generation"]
                    generation_refs = record["reference_snapshots"]
                    if int(record["style_snapshot"].get("schema_version", 1)) == 2:
                        normalised_relative = Path(str(item.get("normalised_path") or Path("production") / batch_id / "normalised" / f"{item['item_id']}.png"))
                        self.store.absolute_path(normalised_relative).parent.mkdir(parents=True, exist_ok=True)
                        stage_specs = [("stylise", self.store.absolute_path(normalised_relative), reference_paths, tuple(["generation-reference"] * len(generation_refs)), self.store.absolute_path(master_relative))]
                        if not item.get("normalised_path"):
                            item["generation_stages"] = []
                            stage_specs.insert(0, ("normalise", source_path, [], (), self.store.absolute_path(normalised_relative)))
                        for stage_index, (stage_name, stage_input, stage_images, stage_roles, output_path) in enumerate(stage_specs):
                            item["phase"] = "stylising" if stage_name == "stylise" else "normalising"; self._write(record)
                            prompt = str(generation["stages"][stage_name]["prompt"])
                            request = GenerationRequest(identity_image=stage_input, style_images=stage_images, instruction=prompt, negative_prompt="", model=str(generation["model_id"]), quality=str(generation["quality"]), seed=stable_seed(f"{item['item_id']}:{stage_name}"), effective_aspect_ratio=str(record["backend_mapping"]["effective_aspect_ratio"]), output_path=output_path, reference_roles=stage_roles)
                            reference_order = [{"order": 0, "role": "source" if stage_name == "normalise" else "normalised", "checksum_sha256": item["source_input_checksum_sha256"] if stage_name == "normalise" else item["normalised_checksum_sha256"]}]
                            if stage_name == "stylise":
                                reference_order.extend({"order": index, "role": "generation-reference", "reference_id": reference["id"], "checksum_sha256": reference["input_checksum_sha256"]} for index, reference in enumerate(generation_refs, 1))
                            stage = {"stage": stage_name, "request": {"instruction": prompt, "model": request.model, "quality": request.quality, "seed": request.seed, "effective_aspect_ratio": request.effective_aspect_ratio, "reference_order": reference_order, "target_examples_excluded": True}}
                            item["generation_stages"].append(stage); item["generation_request"] = stage["request"]; self._write(record)
                            result = adapter.generate(request)
                            stage["result"] = {"backend": result.backend, "model": result.model, "execution_mode": capabilities.execution_mode, "seed": result.seed, "elapsed_seconds": result.elapsed_seconds, "dimensions": result.dimensions, "effective_aspect_ratio": result.effective_aspect_ratio, "usage": result.usage, "cost_usd": result.cost_usd}
                            stage["output_path"] = output_path.relative_to(self.store.root).as_posix(); stage["output_checksum_sha256"] = checksum(output_path)
                            if stage_name == "normalise":
                                item["normalised_path"] = stage["output_path"]; item["normalised_checksum_sha256"] = stage["output_checksum_sha256"]
                            self._write(record)
                        costs = [stage["result"].get("cost_usd") for stage in item["generation_stages"] if isinstance(stage["result"].get("cost_usd"), (int, float))]
                        elapsed = sum(float(stage["result"].get("elapsed_seconds") or 0) for stage in item["generation_stages"])
                        usage_keys = {key for stage in item["generation_stages"] for key, value in (stage.get("result", {}).get("usage") or {}).items() if isinstance(value, (int, float))}
                        usage = {key: sum(float(stage.get("result", {}).get("usage", {}).get(key, 0) or 0) for stage in item["generation_stages"]) for key in usage_keys}
                        final = item["generation_stages"][-1]["result"]
                        item.update({"generation_request": item["generation_stages"][-1]["request"], "master_path": master_relative.as_posix(), "master_checksum_sha256": checksum(self.store.absolute_path(master_relative)), "generation": {**final, "elapsed_seconds": elapsed, "stages": 2, "cost_usd": sum(costs) if costs else None}, "usage": usage, "cost_usd": sum(costs) if costs else None})
                    else:
                        base_instruction = str(item.get("prompt_override") or generation["prompt"])
                        direction = str(item.get("content_direction") or "").strip()
                        instruction = f"{base_instruction}\n\nAdditional content direction from the user: {direction}" if direction else base_instruction
                        foreground_pipeline = int(record["style_snapshot"].get("renderer", {}).get("driver_version", 1)) >= 3
                        output_relative = Path("production") / batch_id / "raw-foregrounds" / f"{item['item_id']}.png" if foreground_pipeline else master_relative
                        self.store.absolute_path(output_relative).parent.mkdir(parents=True, exist_ok=True)
                        if foreground_pipeline:
                            with Image.open(source_path) as opened:
                                chroma_name, chroma = choose_chroma_key(opened)
                            item["chroma_key"] = {"name": chroma_name, "hex": "#%02x%02x%02x" % chroma}
                            instruction += f"\n\nForeground isolation contract: output only the subject against a perfectly flat solid {item['chroma_key']['hex']} chroma-key background. Keep the complete subject silhouette inside the frame with clear padding. The key background must have no texture, gradient, vignette, scenery, floor, shadow, halo, or reflected key colour. Do not use {item['chroma_key']['hex']} on the subject."
                        request = GenerationRequest(
                            identity_image=source_path, style_images=reference_paths,
                            instruction=instruction if int(record["style_snapshot"].get("schema_version", 1)) == 3 else generation_instruction(generation["direction"]),
                            negative_prompt=str(generation.get("avoid") or ""), model=str(generation["model_id"]), quality=str(generation["quality"]),
                            seed=stable_seed(str(item["item_id"])), effective_aspect_ratio=str(record["backend_mapping"]["effective_aspect_ratio"]),
                            output_path=self.store.absolute_path(output_relative),
                            reference_roles=tuple(["generation-reference"] * len(generation_refs)),
                        )
                        item["generation_request"] = {"instruction": request.instruction, "content_direction": item.get("content_direction"), "model": request.model, "quality": request.quality, "seed": request.seed, "target_examples_excluded": True, "reference_order": [{"order": 0, "role": "identity", "source_id": item["source_id"]}, *[{"order": index, "role": "generation-reference", "reference_id": reference["id"]} for index, reference in enumerate(generation_refs, 1)]]}
                        result = adapter.generate(request)
                        if foreground_pipeline:
                            item["phase"] = "extracting-foreground"; self._write(record)
                            foreground_relative = Path("production") / batch_id / "foregrounds" / f"{item['item_id']}.png"
                            foreground_path = self.store.absolute_path(foreground_relative); foreground_path.parent.mkdir(parents=True, exist_ok=True)
                            with Image.open(self.store.absolute_path(output_relative)) as opened:
                                foreground, matte = extract_foreground(opened, tuple(bytes.fromhex(item["chroma_key"]["hex"].removeprefix("#"))))
                            foreground.save(foreground_path, format="PNG")
                            item.update({"raw_foreground_path": output_relative.as_posix(), "foreground_path": foreground_relative.as_posix(), "foreground_checksum_sha256": checksum(foreground_path), "matte_metadata": matte})
                        else:
                            item.update({"master_path": master_relative.as_posix(), "master_checksum_sha256": checksum(self.store.absolute_path(master_relative))})
                        item.update({"generation": {"backend": result.backend, "model": result.model, "execution_mode": capabilities.execution_mode, "seed": result.seed, "elapsed_seconds": result.elapsed_seconds, "dimensions": result.dimensions, "effective_aspect_ratio": result.effective_aspect_ratio, "usage": result.usage, "cost_usd": result.cost_usd}, "usage": result.usage, "cost_usd": result.cost_usd})
                    item.update({"status": "processing", "phase": "rendering"}); self._write(record)
                    self._render_item(record, item, None)
                    item["status"] = "ready"; item["phase"] = "complete"; item["finished_at"] = now_iso(); item["error"] = None
                except Exception as exc:
                    item.update({"status": "failed", "phase": "failed", "error": str(exc), "finished_at": now_iso()})
                self._update_totals(record); record["updated_at"] = now_iso(); self._write(record)
            self._update_totals(record)
            statuses = [item.get("status") for item in self.latest_items(record)]
            record["status"] = "ready" if statuses and all(status == "ready" for status in statuses) else "ready-with-errors" if any(status == "ready" for status in statuses) else "failed"
            record["finished_at"] = now_iso(); record["updated_at"] = now_iso(); self._write(record)
        except Exception as exc:
            try:
                record = self._read(batch_id); record.update({"status": "failed", "error": str(exc), "updated_at": now_iso()}); self._write(record)
            except Exception:
                pass
        finally:
            with self._lock:
                if self._active_batch == batch_id:
                    self._active_batch = None

    def _update_totals(self, record: dict[str, Any]) -> None:
        record["paid_calls"] = sum(sum(1 for stage in item.get("generation_stages", []) if stage.get("result") and not stage["result"].get("reused")) if item.get("generation_stages") else (1 if item.get("generation") else 0) for item in record.get("items", []))
        record["usage"] = {key: value for key, value in {key: sum(float(item.get("usage", {}).get(key, 0) or 0) for item in record["items"] if isinstance(item.get("usage", {}).get(key), (int, float))) for key in {key for item in record["items"] for key in (item.get("usage") or {})}}.items()}
        costs = [float(stage["result"]["cost_usd"]) for item in record["items"] for stage in item.get("generation_stages", []) if isinstance(stage.get("result", {}).get("cost_usd"), (int, float)) and not stage["result"].get("reused")]
        costs.extend(float(item["cost_usd"]) for item in record["items"] if not item.get("generation_stages") and isinstance(item.get("cost_usd"), (int, float)))
        record["cost_usd"] = round(sum(costs), 8) if costs else None

    @staticmethod
    def latest_items(record: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the current attempt for each selected source, preserving source order."""
        latest: dict[str, dict[str, Any]] = {}
        for item in record.get("items", []):
            source_id = str(item.get("source_id"))
            previous = latest.get(source_id)
            if previous is None or int(item.get("attempt_number", 0)) >= int(previous.get("attempt_number", 0)):
                latest[source_id] = item
        return [latest[str(source_id)] for source_id in record.get("selected_source_ids", []) if str(source_id) in latest]

    def _render_item(self, record: dict[str, Any], item: dict[str, Any], framing: dict[str, float] | None, palette_mode: str | None = None, background_id: str | None = None) -> None:
        style = validate_style(copy.deepcopy(record["style_snapshot"]), require_locked=record["purpose"] == "card-production")
        if palette_mode:
            style["renderer"]["palette_mode"] = palette_mode
            style = validate_style(style, require_locked=record["purpose"] == "card-production")
        revision = int(item.get("render_revision") or 0) + 1
        base = Path("production") / record["batch_id"] / "renders" / f"{item['item_id']}-r{revision}"
        resolved_background = background_id or item.get("background_id") or style.get("backgrounds", {}).get("default_id")
        if item.get("foreground_path"):
            with Image.open(self.store.absolute_path(str(item["foreground_path"]))) as opened:
                master, background_metadata = composite_foreground(opened.convert("RGBA"), style, str(resolved_background), framing)
            master_relative = base.with_name(base.name + "-composite.png")
            self._save_image(master, self.store.absolute_path(master_relative))
            item.update({"master_path": master_relative.as_posix(), "master_checksum_sha256": checksum(self.store.absolute_path(master_relative)), "background_id": resolved_background, "background_metadata": background_metadata})
            render_framing = None
        else:
            with Image.open(self.store.absolute_path(str(item["master_path"]))) as opened:
                master = opened.convert("RGB")
            render_framing = framing
        bundle: RenderBundle = registry.render(style, master, str(item["source_label"]), render_framing)
        logical_path, art_path, card_path = base.with_name(base.name + "-logical.png"), base.with_name(base.name + "-art.png"), base.with_name(base.name + "-card.png")
        self._save_image(bundle.logical_art, self.store.absolute_path(logical_path)); self._save_image(bundle.art, self.store.absolute_path(art_path)); self._save_image(bundle.card, self.store.absolute_path(card_path))
        item.update({"render_revision": revision, "framing": framing or style["composition"]["default_framing"], "palette_mode": style["renderer"].get("palette_mode", "fixed-house"), "logical_art_path": logical_path.as_posix(), "art_path": art_path.as_posix(), "card_path": card_path.as_posix(), "card_checksum_sha256": checksum(self.store.absolute_path(card_path)), "render_metadata": bundle.metadata})
        item.setdefault("render_revisions", []).append({"revision": revision, "master_path": item.get("master_path"), "logical_art_path": logical_path.as_posix(), "art_path": art_path.as_posix(), "card_path": card_path.as_posix(), "card_checksum_sha256": item["card_checksum_sha256"], "framing": copy.deepcopy(item["framing"]), "background_id": item.get("background_id"), "background_metadata": copy.deepcopy(item.get("background_metadata")), "palette_mode": item["palette_mode"], "render_metadata": bundle.metadata, "created_at": now_iso()})

    def payload(self, record: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(record)
        result["progress"] = self.progress(record)
        favourites = {(str(item.get("batch_id")), str(item.get("item_id"))): item for item in self._favourite_data().get("items", [])}
        current_approvals = self._approval_data().get("current", {})
        result["progress"]["approved_cards"] = sum(1 for source_id in record.get("selected_source_ids", []) if f"{source_id}:{record.get('style_version_id')}" in current_approvals)
        for item in result.get("items", []):
            source_snapshot = next((source for source in result.get("source_snapshots", []) if str(source.get("id")) == str(item.get("source_id"))), {})
            favourite = favourites.get((str(record.get("batch_id")), str(item.get("item_id"))))
            item["favorite"] = bool(favourite)
            item["favorited_at"] = favourite.get("favorited_at") if favourite else None
            item["approved"] = current_approvals.get(f"{item.get('source_id')}:{record.get('style_version_id')}", {}).get("attempt_id") == item.get("item_id")
            for field in ("normalised_path", "raw_foreground_path", "foreground_path", "master_path", "logical_art_path", "art_path", "card_path"):
                item[field.replace("_path", "_url")] = self.store.asset_url(item.get(field))
            for stage in item.get("generation_stages", []):
                stage["output_url"] = self.store.asset_url(stage.get("output_path"))
            item["source_url"] = self.store.asset_url(item.get("source_input_path"))
            item["source_original_url"] = self.store.asset_url(source_snapshot.get("original_input_path") or source_snapshot.get("original_path"))
            item["reference_urls"] = [self.store.asset_url(reference.get("input_path")) for reference in item.get("reference_stack", []) if reference.get("role") == "generation-reference"]
            for reference in item.get("reference_stack", []):
                reference["url"] = self.store.asset_url(reference.get("input_path"))
        result["style_snapshot"] = self.styles.payload(result["style_snapshot"])
        return result

    @staticmethod
    def progress(record: dict[str, Any]) -> dict[str, Any]:
        items = record.get("items", [])
        current = CardProductionManager.latest_items(record)
        return {"selected_sources": len(record.get("selected_source_ids", [])), "ready_cards": sum(item.get("status") == "ready" for item in current), "approved_cards": 0, "failed_sources": len({item.get("source_id") for item in current if item.get("status") in {"failed", "interrupted"}}), "paid_calls": int(record.get("paid_calls") or 0), "total_attempts": len(items)}

    def get(self, batch_id: str) -> dict[str, Any]:
        return self.payload(self._read(batch_id))

    def list(self) -> list[dict[str, Any]]:
        records = []
        for path in (self.store.root / "production").glob("*/batch.json"):
            record = self.store.read_json(path, {})
            if isinstance(record, dict):
                item = {key: record.get(key) for key in ("batch_id", "purpose", "status", "style_version_id", "style_checksum_sha256", "selected_source_ids", "created_at", "updated_at", "cost_usd", "paid_calls", "requested_paid_calls")}
                item["progress"] = self.progress(record); records.append(item)
        return sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def _append_attempt(self, record: dict[str, Any], source_id: str, *, reuse_normalised: bool = False) -> dict[str, Any]:
        sources = {str(source["id"]): source for source in record["source_snapshots"]}
        source = sources.get(source_id)
        if not source:
            raise ValueError("source is not part of this batch")
        existing = [item for item in record["items"] if str(item.get("source_id")) == source_id]
        lineage = str(existing[0].get("lineage_id") if existing else new_id("lineage"))
        references = record["reference_snapshots"]
        previous = existing[-1] if existing else None
        item = self._new_item(source, max([int(candidate.get("attempt_number", 0)) for candidate in existing] + [0]) + 1, lineage, references, prompt_override=previous.get("prompt_override") if previous else None, content_direction=previous.get("content_direction") if previous else None, background_id=previous.get("background_id") if previous else record.get("style_snapshot", {}).get("backgrounds", {}).get("default_id"))
        reused = bool(reuse_normalised and previous and previous.get("normalised_path"))
        if reused:
            item["normalised_path"] = previous["normalised_path"]; item["normalised_checksum_sha256"] = previous.get("normalised_checksum_sha256")
            item["generation_stages"] = [{"stage": "normalise", "reused_from_item_id": previous["item_id"], "output_path": previous["normalised_path"], "output_checksum_sha256": previous.get("normalised_checksum_sha256"), "result": {"reused": True, "cost_usd": 0}}]
        calls = 1 if reused else (2 if int(record.get("style_snapshot", {}).get("schema_version", 1)) == 2 else 1)
        record["items"].append(item); record["requested_paid_calls"] = int(record.get("requested_paid_calls") or 0) + calls; record["status"] = "queued"; record["updated_at"] = now_iso(); self._write(record)
        return item

    def _require_action_consent(self, record: dict[str, Any], consent: bool) -> None:
        if record.get("model_capabilities", {}).get("execution_mode") == "live" and not consent:
            raise ValueError("explicit consent is required for every live retry or additional generation attempt")

    def retry_failed(self, batch_id: str, *, consent: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._active_batch: raise ValueError("one paid generation batch is already active; wait for it to finish")
            record = self._read(batch_id)
            self._require_action_consent(record, consent)
            source_ids = [str(item["source_id"]) for item in self.latest_items(record) if item.get("status") in {"failed", "interrupted"}]
            if not source_ids: raise ValueError("this batch has no failed or interrupted sources to retry")
            for source_id in source_ids: self._append_attempt(record, source_id, reuse_normalised=True)
            record.setdefault("generation_authorization", {"required": record.get("model_capabilities", {}).get("execution_mode") == "live"})["last_action"] = {"action": "retry", "consent": bool(consent), "granted_at": now_iso() if consent else None}
            self._write(record)
            self._active_batch = batch_id; threading.Thread(target=self._work, args=(batch_id,), daemon=True, name=f"card-retry-{batch_id}").start()
            return self.payload(record)

    def try_another(self, batch_id: str, source_id: str, *, consent: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._active_batch: raise ValueError("one paid generation batch is already active; wait for it to finish")
            record = self._read(batch_id); self._require_action_consent(record, consent); self._append_attempt(record, str(source_id)); self._active_batch = batch_id
            record.setdefault("generation_authorization", {"required": record.get("model_capabilities", {}).get("execution_mode") == "live"})["last_action"] = {"action": "try-another", "consent": bool(consent), "granted_at": now_iso() if consent else None}
            self._write(record)
            threading.Thread(target=self._work, args=(batch_id,), daemon=True, name=f"card-attempt-{batch_id}").start()
            return self.payload(record)

    def accept_candidate(self, batch_id: str, item_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._read(batch_id)
            item = next((candidate for candidate in record.get("items", []) if str(candidate.get("item_id")) == item_id), None)
            if not item:
                raise ValueError("candidate attempt does not exist")
            if record.get("purpose") != "card-production" or item.get("status") != "ready":
                raise ValueError("only a ready production preview can be accepted")
            item["accepted"] = True
            item["accepted_at"] = now_iso()
            record["updated_at"] = now_iso()
            self._write(record)
            return self.payload(record)

    def rerender(self, batch_id: str, item_id: str, framing: dict[str, float] | None, palette_mode: str | None = None, background_id: str | None = None) -> dict[str, Any]:
        record = self._read(batch_id); item = next((candidate for candidate in record["items"] if candidate.get("item_id") == item_id), None)
        if not item or item.get("status") != "ready": raise ValueError("only a ready card can be reframed")
        style = record["style_snapshot"]; resolved = {**style["composition"]["default_framing"], **(framing or {})}
        approvals = self._approval_data()
        approval_key = f"{item['source_id']}:{record['style_version_id']}"
        current_approval = approvals.get("current", {}).get(approval_key)
        if current_approval and current_approval.get("attempt_id") == item_id and int(current_approval.get("render_revision", 0)) == int(item.get("render_revision", 0)):
            approvals["current"].pop(approval_key, None)
            self.store.atomic_json(self.store.root / "approvals" / "approvals.json", approvals)
        self._render_item(record, item, resolved, palette_mode, background_id); item["status"] = "ready"; item["updated_at"] = now_iso(); self._write(record)
        return self.payload(record)

    def preview_render(self, batch_id: str, item_id: str, framing: dict[str, float] | None, palette_mode: str | None = None, background_id: str | None = None) -> dict[str, Any]:
        """Render an experiment without changing the stored candidate or its revision history."""
        record = self._read(batch_id)
        item_index = next((index for index, candidate in enumerate(record["items"]) if candidate.get("item_id") == item_id), None)
        if item_index is None or record["items"][item_index].get("status") != "ready":
            raise ValueError("only a ready card can be previewed")
        preview_record = copy.deepcopy(record)
        preview_record["batch_id"] = f"{batch_id}-preview"
        preview_item = preview_record["items"][item_index]
        style = preview_record["style_snapshot"]
        resolved = {**style["composition"]["default_framing"], **(framing or {})}
        self._render_item(preview_record, preview_item, resolved, palette_mode, background_id)
        return self.payload(preview_record)["items"][item_index]

    def _approval_data(self) -> dict[str, Any]:
        return self.store.read_json(self.store.root / "approvals" / "approvals.json", {"version": 1, "history": [], "current": {}})

    def _favourite_data(self) -> dict[str, Any]:
        return self.store.read_json(self.store.root / "favorites.json", {"version": 1, "items": []})

    def favourites(self) -> list[dict[str, Any]]:
        return list(self._favourite_data().get("items", []))

    def favourite(self, batch_id: str, item_id: str) -> dict[str, Any]:
        record = self._read(batch_id)
        if record.get("purpose") != "card-production":
            raise ValueError("only candidates from saved pipelines can be favorited")
        item = next((candidate for candidate in record.get("items", []) if candidate.get("item_id") == item_id), None)
        if not item or item.get("status") != "ready":
            raise ValueError("only a ready candidate can be favorited")
        data = self._favourite_data()
        existing = next((entry for entry in data.get("items", []) if entry.get("batch_id") == batch_id and entry.get("item_id") == item_id), None)
        if existing:
            return existing
        favourite = {"favorite_id": new_id("favorite"), "batch_id": batch_id, "item_id": item_id, "favorited_at": now_iso()}
        data.setdefault("items", []).append(favourite)
        self.store.atomic_json(self.store.root / "favorites.json", data)
        return favourite

    def unfavourite(self, batch_id: str, item_id: str) -> bool:
        data = self._favourite_data()
        before = len(data.get("items", []))
        data["items"] = [entry for entry in data.get("items", []) if not (entry.get("batch_id") == batch_id and entry.get("item_id") == item_id)]
        if len(data["items"]) != before:
            self.store.atomic_json(self.store.root / "favorites.json", data)
            return True
        return False

    def remove_simulation_batches(self) -> list[str]:
        removed: list[str] = []
        for path in list((self.store.root / "production").glob("*/batch.json")):
            record = self.store.read_json(path, {})
            if record.get("style_snapshot", {}).get("generation", {}).get("execution_mode") != "simulation":
                continue
            removed.append(str(record.get("batch_id") or path.parent.name))
            shutil.rmtree(path.parent)
        existing = {path.parent.name for path in (self.store.root / "production").glob("*/batch.json")}
        data = self._favourite_data()
        data["items"] = [entry for entry in data.get("items", []) if entry.get("batch_id") in existing]
        self.store.atomic_json(self.store.root / "favorites.json", data)
        approvals = self._approval_data()
        approvals["history"] = [entry for entry in approvals.get("history", []) if entry.get("batch_id") in existing]
        approvals["current"] = {key: entry for key, entry in approvals.get("current", {}).items() if entry.get("batch_id") in existing}
        self.store.atomic_json(self.store.root / "approvals" / "approvals.json", approvals)
        for batch_id in removed:
            (self.store.root / "downloads" / f"{batch_id}-approved.zip").unlink(missing_ok=True)
        return removed

    def approve(self, batch_id: str, item_id: str) -> dict[str, Any]:
        record = self._read(batch_id); item = next((candidate for candidate in record["items"] if candidate.get("item_id") == item_id), None)
        if not item or item.get("status") != "ready": raise ValueError("only a ready final card can be approved")
        key = f"{item['source_id']}:{record['style_version_id']}"
        data = self._approval_data(); approval = {"approval_id": new_id("approval"), "source_id": item["source_id"], "attempt_id": item["item_id"], "batch_id": batch_id, "style_version_id": record["style_version_id"], "style_checksum_sha256": record["style_checksum_sha256"], "card_checksum_sha256": item["card_checksum_sha256"], "render_revision": item["render_revision"], "approved_at": now_iso()}
        data["history"].append(approval); data["current"][key] = approval; self.store.atomic_json(self.store.root / "approvals" / "approvals.json", data)
        return approval

    def approvals_for_batch(self, batch_id: str) -> list[dict[str, Any]]:
        record = self._read(batch_id); current = self._approval_data().get("current", {}); return [current[key] for key in (f"{source_id}:{record['style_version_id']}" for source_id in record["selected_source_ids"]) if key in current]

    def bundle(self, batch_id: str) -> dict[str, Any]:
        record = self._read(batch_id); approvals = {item["source_id"]: item for item in self.approvals_for_batch(batch_id)}
        if len(approvals) != len(record["selected_source_ids"]): raise ValueError("approve one current card for every selected source before downloading the bundle")
        batch_dir = self._path(batch_id).parent; output = self.store.root / "downloads" / f"{batch_id}-approved.zip"; manifest_items = []
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index, source_id in enumerate(record["selected_source_ids"], 1):
                approval = approvals[source_id]; item = next(candidate for candidate in record["items"] if candidate["item_id"] == approval["attempt_id"])
                card_path = self.store.absolute_path(str(item["card_path"])); name = f"{index:02d}-{source_id}.png"; archive.writestr(name, card_path.read_bytes())
                manifest_items.append({"order": index - 1, "source_id": source_id, "attempt_id": item["item_id"], "style_version_id": record["style_version_id"], "style_checksum_sha256": record["style_checksum_sha256"], "card_checksum_sha256": item["card_checksum_sha256"], "render_revision": item["render_revision"], "path": name})
            archive.writestr("manifest.json", json.dumps({"batch_id": batch_id, "style_version_id": record["style_version_id"], "items": manifest_items}, indent=2, sort_keys=True) + "\n")
        return {"download_url": self.store.asset_url(output.relative_to(self.store.root)), "manifest": {"batch_id": batch_id, "style_version_id": record["style_version_id"], "items": manifest_items}}
