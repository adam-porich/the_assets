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
    "Place the complete subject centrally on a plain off-white background. Do not turn objects into people "
    "or invent faces, limbs, clothing, props, symbols, or decorative details."
)
NORMALISATION_MODES = {"preserve", "reconstruct"}


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

    def start(self, input_id: str, prompt: str, quality: str, model: dict[str, Any], *, consent: bool, mode: str = "reconstruct") -> dict[str, Any]:
        prompt = prompt.strip()
        if mode not in NORMALISATION_MODES:
            raise ValueError("normalisation mode must be preserve or reconstruct")
        if mode == "reconstruct" and not prompt:
            raise ValueError("normalisation prompt is required")
        if quality not in {"low", "medium", "high"}:
            raise ValueError("normalisation quality must be low, medium, or high")
        capabilities = AdapterCapabilities.from_model(model)
        if mode == "reconstruct" and capabilities.execution_mode == "live" and not consent:
            raise ValueError("explicit consent is required before paid normalisation")
        mapping = validate_request({"model": model["id"], "quality": quality, "execution_mode": capabilities.execution_mode}, 0, capabilities)
        with self._lock:
            if self._active_attempt:
                raise ValueError("one image generation is already active; wait for it to finish")
            item = self._find(input_id)
            attempt_id = new_id("normalisation")
            attempt = {
                "id": attempt_id, "status": "queued", "created_at": now_iso(), "prompt": prompt, "mode": mode,
                "quality": quality, "model_id": model["id"] if mode == "reconstruct" else "deterministic/preserve", "execution_mode": capabilities.execution_mode if mode == "reconstruct" else "deterministic",
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
            if attempt.get("mode") == "preserve":
                with Image.open(self.store.absolute_path(item["original_path"])) as opened:
                    source = ImageOps.exif_transpose(opened).convert("RGB")
                    fitted = ImageOps.contain(source, (1024, 1024), Image.Resampling.LANCZOS)
                    canvas = Image.new("RGB", (1024, 1024), (246, 243, 237))
                    canvas.paste(fitted, ((1024 - fitted.width) // 2, (1024 - fitted.height) // 2))
                    canvas.save(output, format="PNG")
                self._update(input_id, attempt_id, {
                    "status": "ready", "finished_at": now_iso(), "relative_path": relative.as_posix(),
                    "checksum_sha256": checksum(output), "dimensions": [1024, 1024], "usage": {},
                    "cost_usd": 0, "elapsed_seconds": 0, "backend": "deterministic-preserve", "effective_aspect_ratio": "1:1",
                })
                return
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
