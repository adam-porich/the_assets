from __future__ import annotations

import base64
import hashlib
import os
import random
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Protocol

import requests
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw

from .recipes import resolve_recipe_instruction
from .workspace import now_iso


REQUESTED_ART_RATIO = (28, 23)
REQUESTED_ART_RATIO_LABEL = "28:23"
FALLBACK_MODELS: list[dict[str, Any]] = [
    {
        "id": "fake/painterly-deterministic",
        "name": "Deterministic painterly preview",
        "description": "Local fake adapter for smoke tests and interface work.",
        "max_input_references": 9,
        "aspect_ratios": ["5:4", "4:3", "3:2"],
        "qualities": ["low", "medium"],
        "supports_negative_prompt": True,
        "supports_reference_roles": True,
    },
    {
        "id": "openai/gpt-image-1-mini",
        "name": "GPT Image 1 mini",
        "description": "OpenRouter image model; requires OPENROUTER_API_KEY.",
        "max_input_references": 5,
        "aspect_ratios": ["5:4", "4:3", "3:2"],
        "qualities": ["low", "medium", "high"],
        "supports_negative_prompt": False,
        "supports_reference_roles": False,
    },
    {
        "id": "google/gemini-3.1-flash-image",
        "name": "Gemini Flash Image",
        "description": "OpenRouter image model; requires OPENROUTER_API_KEY.",
        "max_input_references": 5,
        "aspect_ratios": ["5:4", "4:3", "3:2"],
        "qualities": ["low", "medium", "high"],
        "supports_negative_prompt": False,
        "supports_reference_roles": False,
    },
]


@dataclass(frozen=True)
class AdapterCapabilities:
    model: str
    reference_roles: bool
    max_references: int
    seed: bool
    aspect_ratios: tuple[str, ...]
    qualities: tuple[str, ...]
    negative_prompt: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "reference_roles": self.reference_roles,
            "max_references": self.max_references,
            "seed": self.seed,
            "aspect_ratios": list(self.aspect_ratios),
            "qualities": list(self.qualities),
            "negative_prompt": self.negative_prompt,
        }


@dataclass(frozen=True)
class GenerationRequest:
    identity_image: Path
    style_images: list[Path]
    instruction: str
    model: str
    quality: str
    seed: int
    effective_aspect_ratio: str
    output_path: Path


@dataclass(frozen=True)
class GenerationResult:
    output_path: str
    backend: str
    model: str
    seed: int
    elapsed_seconds: float
    dimensions: list[int]
    effective_aspect_ratio: str


class GenerationAdapter(Protocol):
    capabilities: AdapterCapabilities

    def generate(self, request: GenerationRequest) -> GenerationResult:
        ...


def _ratio_value(value: str) -> float:
    left, right = value.split(":", 1)
    return float(left) / float(right)


def negotiate_aspect_ratio(supported: list[str] | tuple[str, ...]) -> str:
    if not supported:
        raise ValueError("selected model does not expose any supported aspect ratios")
    return min(supported, key=lambda candidate: abs(_ratio_value(candidate) - REQUESTED_ART_RATIO[0] / REQUESTED_ART_RATIO[1]))


def model_capabilities(model: str, models: list[dict[str, Any]] | None = None) -> AdapterCapabilities:
    entry = next((item for item in (models or FALLBACK_MODELS) if item.get("id") == model), None)
    entry = entry or next((item for item in FALLBACK_MODELS if item.get("id") == model), None)
    if entry is None:
        entry = {
            "max_input_references": 5,
            "aspect_ratios": ["5:4", "4:3", "3:2"],
            "qualities": ["low", "medium", "high"],
            "supports_negative_prompt": False,
            "supports_reference_roles": False,
        }
    return AdapterCapabilities(
        model=model,
        reference_roles=bool(entry.get("supports_reference_roles")),
        max_references=int(entry.get("max_input_references") or 0),
        seed=True,
        aspect_ratios=tuple(str(value) for value in entry.get("aspect_ratios") or ["4:3"]),
        qualities=tuple(str(value) for value in entry.get("qualities") or ["low"]),
        negative_prompt=bool(entry.get("supports_negative_prompt")),
    )


def validate_request(recipe: dict[str, Any], style_count: int, capabilities: AdapterCapabilities) -> dict[str, Any]:
    total = 1 + style_count
    if total > capabilities.max_references:
        raise ValueError(
            f"{recipe.get('model')} accepts at most {capabilities.max_references} input references; "
            f"the identity image plus {style_count} selected style references needs {total}. Remove {total - capabilities.max_references} reference(s)."
        )
    if recipe.get("quality") not in capabilities.qualities:
        raise ValueError(f"{recipe.get('model')} does not support quality {recipe.get('quality')}")
    return {
        "requested_aspect_ratio": REQUESTED_ART_RATIO_LABEL,
        "effective_aspect_ratio": negotiate_aspect_ratio(capabilities.aspect_ratios),
        "negative_prompt_mapping": "explicit_avoid_instruction" if not capabilities.negative_prompt else "native_negative_prompt",
        "reference_mapping": "role_aware" if capabilities.reference_roles else "identity_first_style_after",
    }


class FakeGenerationAdapter:
    def __init__(self, model: str = "fake/painterly-deterministic") -> None:
        self.capabilities = model_capabilities(model)
        self.name = "fake"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.perf_counter()
        with Image.open(request.identity_image) as original:
            source = ImageOps.exif_transpose(original).convert("RGB")
        width, height = (336, 276)
        if request.effective_aspect_ratio == "5:4":
            width, height = 320, 256
        elif request.effective_aspect_ratio == "3:2":
            width, height = 360, 240
        image = ImageOps.fit(source, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.44))
        image = ImageEnhance.Color(image).enhance(0.78)
        image = ImageEnhance.Contrast(image).enhance(1.08)
        image = image.filter(ImageFilter.GaussianBlur(radius=0.28))
        draw = ImageDraw.Draw(image, "RGBA")
        randomizer = random.Random(request.seed)
        palette = [(171, 133, 101, 22), (67, 82, 98, 18), (231, 197, 133, 16), (111, 75, 78, 14)]
        for _ in range(90):
            x = randomizer.randrange(max(1, width))
            y = randomizer.randrange(max(1, height))
            length = randomizer.randrange(8, 42)
            color = randomizer.choice(palette)
            draw.line((x, y, min(width, x + length), y + randomizer.randrange(-5, 6)), fill=color, width=randomizer.choice([1, 2, 3]))
        image.save(request.output_path, format="PNG")
        return GenerationResult(
            output_path=str(request.output_path),
            backend=self.name,
            model=request.model,
            seed=request.seed,
            elapsed_seconds=round(time.perf_counter() - started, 3),
            dimensions=[width, height],
            effective_aspect_ratio=request.effective_aspect_ratio,
        )


class OpenRouterGenerationAdapter:
    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured; choose the deterministic preview model or add a key")
        self.capabilities = model_capabilities(model)
        self.name = "openrouter"

    @staticmethod
    def _data_url(path: Path) -> str:
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{media_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        references = [{"type": "image_url", "image_url": {"url": self._data_url(request.identity_image)}}]
        references.extend({"type": "image_url", "image_url": {"url": self._data_url(path)}} for path in request.style_images)
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": request.instruction,
            "n": 1,
            "aspect_ratio": request.effective_aspect_ratio,
            "output_format": "png",
            "input_references": references,
            "seed": request.seed,
        }
        if request.model.startswith("openai/"):
            payload["quality"] = request.quality
            payload["background"] = "opaque"
        response = requests.post(
            "https://openrouter.ai/api/v1/images",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "X-Title": "Portrait Workbench"},
            json=payload,
            timeout=180,
        )
        if not response.ok:
            raise RuntimeError(f"OpenRouter image generation failed {response.status_code}: {response.text[:500]}")
        data = response.json().get("data") or []
        if not data or not data[0].get("b64_json"):
            raise RuntimeError("OpenRouter returned no image data")
        request.output_path.write_bytes(base64.b64decode(data[0]["b64_json"]))
        with Image.open(request.output_path) as image:
            dimensions = [int(image.width), int(image.height)]
        return GenerationResult(
            output_path=str(request.output_path), backend=self.name, model=request.model, seed=request.seed,
            elapsed_seconds=round(time.perf_counter() - started, 3), dimensions=dimensions,
            effective_aspect_ratio=request.effective_aspect_ratio,
        )


def adapter_for(model: str) -> GenerationAdapter:
    if model.startswith("fake/") or os.environ.get("PORTRAIT_WORKBENCH_FAKE_GENERATION") == "1":
        return FakeGenerationAdapter(model if model.startswith("fake/") else "fake/painterly-deterministic")
    return OpenRouterGenerationAdapter(model)


def resolved_run_instruction(recipe: dict[str, Any], capabilities: AdapterCapabilities) -> str:
    instruction = resolve_recipe_instruction(recipe)
    if not capabilities.negative_prompt and recipe.get("avoid"):
        return instruction
    return instruction

