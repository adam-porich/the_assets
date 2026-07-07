from __future__ import annotations

import base64
import hashlib
import json
import os
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import requests
from PIL import Image, ImageOps

from .imaging import model_background_mask, quantize_image, transparent_from_mask
from .manifest import deterministic_background_filename, utc_now_iso


PRESET_DIR = Path(__file__).parent / "presets"


@dataclass(frozen=True)
class Img2ImgPreset:
    name: str
    prompt: str
    negative_prompt: str = ""
    strength: float = 0.45
    steps: int = 10
    guidance: float | None = 6.0
    width: int = 512
    height: int = 512
    background_mode: str = "neutral-dark"
    candidate_count: int = 3
    department_tint: str | None = None
    post_processing: dict[str, Any] | None = None


@dataclass(frozen=True)
class PreparationSettings:
    max_edge: int = 768

    def to_json(self) -> dict[str, Any]:
        return {"max_edge": self.max_edge}


@dataclass(frozen=True)
class Img2ImgRequest:
    input_image_path: str
    prompt: str
    negative_prompt: str = ""
    seed: int | None = None
    strength: float = 0.45
    steps: int = 10
    guidance: float | None = None
    width: int = 512
    height: int = 512
    preset: str = ""
    count: int = 1
    output_dir: str = ""
    output_base: str = ""


@dataclass(frozen=True)
class Img2ImgResult:
    image_path: str
    backend: str
    model: str
    seed: int
    strength: float
    steps: int
    guidance: float | None
    prompt: str
    negative_prompt: str
    elapsed_seconds: float


class Img2ImgBackend(Protocol):
    name: str

    def generate(self, request: Img2ImgRequest) -> list[Img2ImgResult]:
        ...


def load_preset(name: str, preset_dir: Path = PRESET_DIR) -> Img2ImgPreset:
    path = preset_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown portrait stylization preset: {name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Img2ImgPreset(**data)


def stable_seed(photo_id: int, preset: str, index: int = 0) -> int:
    digest = hashlib.sha256(f"{photo_id}:{preset}:{index}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


class ExternalCommandBackend:
    name = "external"

    def __init__(self, command: str | None = None) -> None:
        self.command = command or os.environ.get("PORTRAIT_IMG2IMG_COMMAND")
        if not self.command:
            raise RuntimeError("PORTRAIT_IMG2IMG_COMMAND is not configured")

    def generate(self, request: Img2ImgRequest) -> list[Img2ImgResult]:
        request_dir = Path(request.output_dir)
        request_dir.mkdir(parents=True, exist_ok=True)
        request_path = request_dir / f"{request.output_base}-request.json"
        request_path.write_text(json.dumps(asdict(request), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        command = [part.format(request=str(request_path), output_dir=request.output_dir) for part in shlex.split(self.command)]
        started = time.perf_counter()
        completed = subprocess.run(command + [str(request_path)], check=True, capture_output=True, text=True)
        elapsed = round(time.perf_counter() - started, 3)
        payload = json.loads(completed.stdout or "[]")
        raw_results = payload.get("results", payload) if isinstance(payload, dict) else payload
        results = []
        for item in raw_results:
            item = dict(item)
            item.setdefault("backend", self.name)
            item.setdefault("model", "external")
            item.setdefault("strength", request.strength)
            item.setdefault("steps", request.steps)
            item.setdefault("guidance", request.guidance)
            item.setdefault("prompt", request.prompt)
            item.setdefault("negative_prompt", request.negative_prompt)
            item.setdefault("elapsed_seconds", elapsed)
            if "seed" not in item or item["seed"] is None:
                item["seed"] = request.seed or 0
            results.append(Img2ImgResult(**item))
        return results


class OpenRouterBackend:
    name = "openrouter"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        quality: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        self.model = model or os.environ.get("OPENROUTER_IMAGE_MODEL") or "openai/gpt-image-1-mini"
        self.quality = quality or os.environ.get("OPENROUTER_IMAGE_QUALITY") or "low"

    def generate(self, request: Img2ImgRequest) -> list[Img2ImgResult]:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": request.prompt,
            "n": request.count,
            "aspect_ratio": "1:1",
            "output_format": "png",
            "input_references": [
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url(Path(request.input_image_path))},
                }
            ],
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if self.model.startswith("openai/"):
            payload["quality"] = self.quality
            payload["background"] = "opaque"
        else:
            payload["resolution"] = "1K"

        started = time.perf_counter()
        response = requests.post(
            "https://openrouter.ai/api/v1/images",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/adam-porich/the_assets",
                "X-Title": "the_assets portrait pipeline",
            },
            json=payload,
            timeout=180,
        )
        elapsed = round(time.perf_counter() - started, 3)
        if not response.ok:
            raise RuntimeError(f"OpenRouter image generation failed {response.status_code}: {response.text[:500]}")

        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for index, item in enumerate(response.json().get("data", [])):
            seed = (request.seed or 0) + index
            media_type = item.get("media_type") or "image/png"
            suffix = ".svg" if media_type == "image/svg+xml" else ".png"
            output_path = output_dir / f"{request.output_base}-{seed}-openrouter{suffix}"
            output_path.write_bytes(base64.b64decode(item["b64_json"]))
            results.append(
                Img2ImgResult(
                    image_path=str(output_path),
                    backend=self.name,
                    model=self.model,
                    seed=seed,
                    strength=request.strength,
                    steps=request.steps,
                    guidance=request.guidance,
                    prompt=request.prompt,
                    negative_prompt=request.negative_prompt,
                    elapsed_seconds=elapsed,
                )
            )
        return results


def image_data_url(path: Path) -> str:
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def controlled_background(size: tuple[int, int], mode: str, department_tint: str | None = None) -> Image.Image:
    colors = {
        "neutral-light": "#c8beb0",
        "neutral-dark": "#403936",
        "department-tint": department_tint or "#4f3d57",
    }
    if mode not in colors:
        raise ValueError(f"Unknown stylization background mode: {mode}")
    return Image.new("RGB", size, colors[mode])


def composite_on_controlled_background(image: Image.Image, mask: Image.Image, mode: str, department_tint: str | None = None) -> Image.Image:
    background = controlled_background(image.size, mode, department_tint)
    return Image.composite(image.convert("RGB"), background, mask)


def resize_full_source(image: Image.Image, max_edge: int) -> Image.Image:
    if max_edge <= 0:
        raise ValueError("preparation max_edge must be positive")
    largest = max(image.size)
    if largest <= max_edge:
        return image.copy()
    scale = max_edge / largest
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def prepare_rembg_composite(
    source_path: Path,
    photo_id: int,
    library_dir: Path,
    preset: Img2ImgPreset,
    preparation: PreparationSettings | None = None,
) -> dict[str, Any]:
    preparation = preparation or PreparationSettings()
    prep_dir = library_dir / "prepared"
    mask_dir = library_dir / "masks"
    foreground_dir = library_dir / "foregrounds"
    composite_dir = library_dir / "composites"
    for directory in (prep_dir, mask_dir, foreground_dir, composite_dir):
        directory.mkdir(parents=True, exist_ok=True)

    original = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
    source = resize_full_source(original, preparation.max_edge)
    prepared_path = prep_dir / deterministic_background_filename(photo_id, "stylize", "source")
    source.save(prepared_path)
    mask = model_background_mask(source)
    foreground = transparent_from_mask(source, mask)
    composite = composite_on_controlled_background(source, mask, preset.background_mode, preset.department_tint)

    mask_path = mask_dir / deterministic_background_filename(photo_id, "rembg", "mask")
    foreground_path = foreground_dir / deterministic_background_filename(photo_id, "rembg", "foreground")
    composite_path = composite_dir / deterministic_background_filename(photo_id, preset.background_mode, "composite")
    mask.save(mask_path)
    foreground.save(foreground_path)
    composite.save(composite_path)
    return {
        "prepared_source_path": str(prepared_path.relative_to(library_dir)),
        "mask_path": str(mask_path.relative_to(library_dir)),
        "transparent_foreground_path": str(foreground_path.relative_to(library_dir)),
        "composite_path": str(composite_path.relative_to(library_dir)),
        "mask_mode": "rembg",
        "background_mode": preset.background_mode,
        "framing": "full-source",
        "preparation": preparation.to_json(),
        "original_size": list(original.size),
        "prepared_size": list(source.size),
    }


def final_candidate_path(library_dir: Path, photo_id: int, preset_name: str, seed: int) -> Path:
    return library_dir / "stylized" / f"pexels-{photo_id}-{preset_name}-{seed}-final.png"


def raw_candidate_path(library_dir: Path, photo_id: int, preset_name: str, seed: int) -> Path:
    return library_dir / "stylized" / f"pexels-{photo_id}-{preset_name}-{seed}-raw.png"


def finish_stylized_candidate(raw_path: Path, final_path: Path, post_processing: dict[str, Any] | None) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    if not post_processing or not post_processing.get("enabled", True):
        ImageOps.exif_transpose(Image.open(raw_path)).convert("RGB").save(final_path)
        return
    logical_size = int(post_processing.get("logical_size", 64))
    review_scale = int(post_processing.get("review_scale", 4))
    palette_colors = int(post_processing.get("palette_colors", 32))
    image = ImageOps.exif_transpose(Image.open(raw_path)).convert("RGB")
    image = ImageOps.fit(image, (logical_size, logical_size), method=Image.Resampling.LANCZOS, centering=(0.5, 0.42))
    image = quantize_image(image, palette_colors, False, None)
    image = image.resize((logical_size * review_scale, logical_size * review_scale), Image.Resampling.NEAREST)
    image.save(final_path)


def stylize_source(
    source_path: Path,
    photo_id: int,
    library_dir: Path,
    preset: Img2ImgPreset,
    backend: Img2ImgBackend,
    seed: int | None = None,
    count: int | None = None,
    preparation: PreparationSettings | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prep = prepare_rembg_composite(source_path, photo_id, library_dir, preset, preparation)
    output_dir = library_dir / "stylized"
    output_dir.mkdir(parents=True, exist_ok=True)
    base_seed = seed if seed is not None else stable_seed(photo_id, preset.name)
    request = Img2ImgRequest(
        input_image_path=str(library_dir / prep["composite_path"]),
        prompt=preset.prompt,
        negative_prompt=preset.negative_prompt,
        seed=base_seed,
        strength=preset.strength,
        steps=preset.steps,
        guidance=preset.guidance,
        width=preset.width,
        height=preset.height,
        preset=preset.name,
        count=count or preset.candidate_count,
        output_dir=str(output_dir),
        output_base=f"pexels-{photo_id}-{preset.name}-{base_seed}",
    )
    results = backend.generate(request)
    records = []
    for index, result in enumerate(results):
        raw_path = Path(result.image_path)
        result_seed = int(result.seed)
        if raw_path.exists() and raw_path.resolve() != raw_candidate_path(library_dir, photo_id, preset.name, result_seed).resolve():
            canonical_raw = raw_candidate_path(library_dir, photo_id, preset.name, result_seed)
            canonical_raw.parent.mkdir(parents=True, exist_ok=True)
            ImageOps.exif_transpose(Image.open(raw_path)).convert("RGB").save(canonical_raw)
            raw_path = canonical_raw
        final_path = final_candidate_path(library_dir, photo_id, preset.name, result_seed)
        finish_stylized_candidate(raw_path, final_path, preset.post_processing)
        records.append(
            {
                "source_photo_id": photo_id,
                "candidate_id": f"{preset.name}:{result_seed}",
                "background_mode": prep["background_mode"],
                "mask_mode": prep["mask_mode"],
                "preset": preset.name,
                "backend": result.backend,
                "model": result.model,
                "prompt": result.prompt,
                "negative_prompt": result.negative_prompt,
                "seed": result_seed,
                "strength": result.strength,
                "steps": result.steps,
                "guidance": result.guidance,
                "elapsed_seconds": result.elapsed_seconds,
                "created_at": utc_now_iso(),
                "input_composite_path": prep["composite_path"],
                "output_path": str(raw_path.relative_to(library_dir)),
                "final_output_path": str(final_path.relative_to(library_dir)),
                "index": index,
            }
        )
    return prep, records
