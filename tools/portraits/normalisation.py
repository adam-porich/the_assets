from __future__ import annotations

import copy
import shutil
import threading
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps

from .generation import AdapterCapabilities, GenerationRequest, adapter_for, stable_seed, validate_request
from .workspace import WorkspaceStore, checksum, new_id, now_iso


DEFAULT_NORMALISATION_PROMPT = (
    "Create a clean, neutral studio representation of the exact subject in the input image. "
    "Preserve its category, identity, proportions, materials, colours, markings, and important details. "
    "Remove the original scene, lighting effects, text overlays, and photographic clutter. "
    "Place the complete subject centrally on a plain off-white background with at least 8% clear space above and on both sides. "
    "Never crop hats, hair, ears, shoulders, or props. Do not turn objects into people "
    "or invent faces, limbs, clothing, props, symbols, or decorative details."
)
class InputNormalisationManager:
    def __init__(self, store: WorkspaceStore, adapter_factory: Callable[[str, AdapterCapabilities], Any] | None = None) -> None:
        self.store = store
        self.adapter_factory = adapter_factory or adapter_for
        self._lock = threading.RLock()
        self._active_attempt: str | None = None

    @property
    def is_active(self) -> bool:
        return self._active_attempt is not None

    def _find(self, input_id: str) -> dict[str, Any]:
        item = next((entry for entry in self.store.read().get("inputs", []) if str(entry.get("id")) == input_id), None)
        if not item:
            raise ValueError(f"input {input_id} does not exist")
        return item

    def payload(self, item: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(item)
        result["original_url"] = self.store.asset_url(result.get("original_path"))
        accepted = result.get("accepted_normalisation") or {}
        result["image_url"] = self.store.asset_url(accepted.get("relative_path"))
        for attempt in result.get("normalisation_attempts", []):
            attempt["preview_url"] = self.store.asset_url(attempt.get("relative_path"))
        return result

    def get(self, input_id: str) -> dict[str, Any]:
        return self.payload(self._find(input_id))

    def start(self, input_id: str, prompt: str, quality: str, model: dict[str, Any], *, consent: bool) -> dict[str, Any]:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("normalisation prompt is required")
        if quality not in {"low", "medium", "high"}:
            raise ValueError("normalisation quality must be low, medium, or high")
        capabilities = AdapterCapabilities.from_model(model)
        if capabilities.execution_mode == "live" and not consent:
            raise ValueError("explicit consent is required before paid normalisation")
        mapping = validate_request({"model": model["id"], "quality": quality, "execution_mode": capabilities.execution_mode}, 0, capabilities)
        with self._lock:
            if self._active_attempt:
                raise ValueError("one image generation is already active; wait for it to finish")
            item = self._find(input_id)
            attempt_id = new_id("normalisation")
            attempt = {
                "id": attempt_id, "status": "queued", "created_at": now_iso(), "prompt": prompt,
                "quality": quality, "model_id": model["id"], "execution_mode": capabilities.execution_mode,
                "cost_usd": None, "usage": {}, "error": None, "relative_path": None,
            }
            self.store.mutate(lambda data: next(entry for entry in data["inputs"] if entry["id"] == input_id)["normalisation_attempts"].append(attempt))
            self._active_attempt = attempt_id
            threading.Thread(target=self._work, args=(input_id, attempt_id, model, str(mapping["effective_aspect_ratio"])), daemon=True, name=f"normalise-{attempt_id}").start()
            return self.get(input_id)

    def _work(self, input_id: str, attempt_id: str, model: dict[str, Any], effective_aspect_ratio: str) -> None:
        try:
            item = self._find(input_id)
            attempt = next(entry for entry in item["normalisation_attempts"] if entry["id"] == attempt_id)
            self._update(input_id, attempt_id, {"status": "running", "started_at": now_iso()})
            relative = Path("staging") / input_id / f"{attempt_id}.png"
            output = self.store.absolute_path(relative)
            output.parent.mkdir(parents=True, exist_ok=True)
            capabilities = AdapterCapabilities.from_model(model)
            request = GenerationRequest(
                identity_image=self.store.absolute_path(item["original_path"]), style_images=[],
                instruction=attempt["prompt"], negative_prompt="", model=attempt["model_id"], quality=attempt["quality"],
                seed=stable_seed(attempt_id), effective_aspect_ratio=effective_aspect_ratio, output_path=output, reference_roles=(),
            )
            result = self.adapter_factory(capabilities.execution_mode, capabilities).generate(request)
            self._update(input_id, attempt_id, {
                "status": "ready", "finished_at": now_iso(), "relative_path": relative.as_posix(),
                "checksum_sha256": checksum(output), "dimensions": result.dimensions, "usage": result.usage,
                "cost_usd": result.cost_usd, "elapsed_seconds": result.elapsed_seconds, "seed": result.seed,
                "backend": result.backend, "effective_aspect_ratio": result.effective_aspect_ratio,
            })
        except Exception as exc:
            self._update(input_id, attempt_id, {"status": "failed", "finished_at": now_iso(), "error": str(exc)})
        finally:
            with self._lock:
                if self._active_attempt == attempt_id:
                    self._active_attempt = None

    def _update(self, input_id: str, attempt_id: str, patch: dict[str, Any]) -> None:
        def mutate(data: dict[str, Any]) -> None:
            item = next(entry for entry in data["inputs"] if entry["id"] == input_id)
            attempt = next(entry for entry in item["normalisation_attempts"] if entry["id"] == attempt_id)
            attempt.update(patch)
        self.store.mutate(mutate)

    def accept(self, input_id: str, attempt_id: str) -> dict[str, Any]:
        item = self._find(input_id)
        attempt = next((entry for entry in item.get("normalisation_attempts", []) if entry.get("id") == attempt_id), None)
        if not attempt or attempt.get("status") != "ready" or not attempt.get("relative_path"):
            raise ValueError("choose a completed normalisation preview before accepting this input")
        source = self.store.absolute_path(attempt["relative_path"])
        if attempt.get("execution_mode") == "live":
            with Image.open(source) as opened:
                preview = ImageOps.contain(opened.convert("RGB"), (256, 256), Image.Resampling.BILINEAR)
            corners = [preview.getpixel(point) for point in ((0, 0), (preview.width - 1, 0), (0, preview.height - 1), (preview.width - 1, preview.height - 1))]
            background = tuple(round(sum(colour[channel] for colour in corners) / len(corners)) for channel in range(3))
            mask = Image.new("L", preview.size)
            mask.putdata([255 if sum((colour[channel] - background[channel]) ** 2 for channel in range(3)) ** 0.5 >= 32 else 0 for colour in preview.getdata()])
            box = mask.getbbox()
            margin = max(3, round(min(preview.size) * 0.025))
            if box and (box[0] <= margin or box[1] <= margin or box[2] >= preview.width - margin):
                raise ValueError("the prepared subject touches the top or side edge; rerun preparation with the complete silhouette and clear padding")
        original = self.store.absolute_path(item["original_path"])
        directory = self.store.root / "inputs" / input_id
        directory.mkdir(parents=True, exist_ok=True)
        accepted_path = directory / f"normalised-{attempt_id}.png"
        original_path = directory / f"original{original.suffix.lower() or '.png'}"
        shutil.copy2(source, accepted_path)
        if original.resolve() != original_path.resolve():
            shutil.copy2(original, original_path)
        accepted = {**attempt, "relative_path": accepted_path.relative_to(self.store.root).as_posix(), "accepted_at": now_iso()}
        def mutate(data: dict[str, Any]) -> None:
            stored = next(entry for entry in data["inputs"] if entry["id"] == input_id)
            stored.update({"status": "ready", "original_path": original_path.relative_to(self.store.root).as_posix(), "accepted_normalisation": accepted})
            next(entry for entry in stored["normalisation_attempts"] if entry["id"] == attempt_id)["relative_path"] = accepted["relative_path"]
        self.store.mutate(mutate)
        staging = self.store.root / "staging" / input_id
        if staging.exists():
            shutil.rmtree(staging)
        return self.get(input_id)

    def delete(self, input_id: str) -> None:
        item = self._find(input_id)
        self.store.mutate(lambda data: data.update({"inputs": [entry for entry in data["inputs"] if entry["id"] != input_id]}))
        for key in ("original_path",):
            path = self.store.absolute_path(item[key])
            if path.is_file():
                path.unlink()
        for directory in (self.store.root / "staging" / input_id, self.store.root / "inputs" / input_id):
            if directory.exists():
                shutil.rmtree(directory)
