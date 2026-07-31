from __future__ import annotations

import base64
import hashlib
import io
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .recipes import resolve_recipe_instruction


REQUESTED_ART_RATIO = (28, 23)
REQUESTED_ART_RATIO_LABEL = "28:23"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/images/models"
SIMULATION_MODEL_ID = "fake/painterly-deterministic"
DEFAULT_LIVE_MODEL_ID = "openai/gpt-image-1-mini"


def simulation_model() -> dict[str, Any]:
    return {
        "id": SIMULATION_MODEL_ID,
        "name": "Deterministic painterly simulation",
        "description": "A local, zero-cost image-processing simulation for workflow checks. It is not generated artwork.",
        "execution_mode": "simulation",
        "available": True,
        "supported_parameters": {
            "aspect_ratio": {"type": "enum", "values": ["5:4", "4:3", "3:2"]},
            "quality": {"type": "enum", "values": ["low", "medium"]},
            "input_references": {"type": "range", "min": 0, "max": 9},
            "seed": {"type": "boolean"},
        },
        "max_input_references": 9,
        "aspect_ratios": ["5:4", "4:3", "3:2"],
        "qualities": ["low", "medium"],
        "supports_negative_prompt": False,
        "supports_reference_roles": False,
        "supports_streaming": False,
        "pricing": [{"billable": "output_image", "unit": "image", "cost_usd": 0}],
        "provider_slug": "local",
        "provider_tag": "local",
    }


def unavailable_live_model(model_id: str = DEFAULT_LIVE_MODEL_ID) -> dict[str, Any]:
    return {
        "id": model_id,
        "name": model_id,
        "description": "This saved live model is not present in the current OpenRouter image-model catalogue.",
        "execution_mode": "live",
        "available": False,
        "supported_parameters": {},
        "max_input_references": 0,
        "aspect_ratios": [],
        "qualities": [],
        "supports_negative_prompt": False,
        "supports_reference_roles": False,
        "supports_streaming": False,
        "pricing": [],
        "provider_slug": None,
        "provider_tag": None,
    }


def _descriptor_values(parameters: dict[str, Any], name: str) -> list[str]:
    descriptor = parameters.get(name)
    if not isinstance(descriptor, dict) or descriptor.get("type") != "enum":
        return []
    return [str(value) for value in descriptor.get("values") or []]


def _descriptor_max(parameters: dict[str, Any], name: str) -> int:
    descriptor = parameters.get(name)
    if not isinstance(descriptor, dict):
        return 0
    if descriptor.get("type") == "range":
        return max(0, int(descriptor.get("max") or 0))
    if descriptor.get("type") == "boolean":
        return 1
    return 0


def normalize_live_model(model: dict[str, Any], endpoint: dict[str, Any]) -> dict[str, Any]:
    """Build UI/runtime metadata from one definitive OpenRouter endpoint record."""
    parameters = dict(endpoint.get("supported_parameters") or {})
    return {
        "id": str(model.get("id") or ""),
        "name": str(model.get("name") or model.get("id") or ""),
        "description": str(model.get("description") or ""),
        "execution_mode": "live",
        "available": True,
        "architecture": dict(model.get("architecture") or {}),
        "supported_parameters": parameters,
        "max_input_references": _descriptor_max(parameters, "input_references"),
        "aspect_ratios": _descriptor_values(parameters, "aspect_ratio"),
        "qualities": _descriptor_values(parameters, "quality"),
        "supports_negative_prompt": "negative_prompt" in parameters,
        "supports_reference_roles": False,
        "supports_streaming": bool(endpoint.get("supports_streaming")),
        "pricing": list(endpoint.get("pricing") or []),
        "provider_name": endpoint.get("provider_name"),
        "provider_slug": endpoint.get("provider_slug"),
        "provider_tag": endpoint.get("provider_tag"),
        "allowed_passthrough_parameters": list(endpoint.get("allowed_passthrough_parameters") or []),
    }


def fetch_model_catalogue(timeout: float = 15) -> list[dict[str, Any]]:
    """Fetch image-to-image models and resolve each to a definitive provider endpoint."""
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"} if os.environ.get("OPENROUTER_API_KEY") else {}
    response = requests.get(OPENROUTER_MODELS_URL, headers=headers, timeout=timeout)
    response.raise_for_status()
    candidates = [
        item for item in response.json().get("data", [])
        if item.get("id") and "image" in (item.get("architecture") or {}).get("input_modalities", [])
        and "input_references" in (item.get("supported_parameters") or {})
        and item.get("endpoints")
    ]

    def resolve(model: dict[str, Any]) -> dict[str, Any] | None:
        endpoint_url = str(model["endpoints"])
        if endpoint_url.startswith("/"):
            endpoint_url = f"https://openrouter.ai{endpoint_url}"
        endpoint_response = requests.get(endpoint_url, headers=headers, timeout=timeout)
        endpoint_response.raise_for_status()
        endpoints = [
            endpoint for endpoint in endpoint_response.json().get("endpoints", [])
            if "input_references" in (endpoint.get("supported_parameters") or {})
        ]
        if not endpoints:
            return None
        # The selected endpoint is pinned in generation requests, so these descriptors
        # remain the exact runtime contract rather than a model-level capability union.
        return normalize_live_model(model, endpoints[0])

    live: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(candidates)))) as executor:
        futures = [executor.submit(resolve, model) for model in candidates]
        for future in as_completed(futures):
            try:
                resolved = future.result()
            except requests.RequestException:
                continue
            if resolved:
                live.append(resolved)
    live.sort(key=lambda item: (item["id"] != DEFAULT_LIVE_MODEL_ID, str(item["name"]).lower()))
    return [simulation_model(), *live]


@dataclass(frozen=True)
class AdapterCapabilities:
    model: str
    execution_mode: str
    available: bool
    supported_parameters: dict[str, Any]
    provider_slug: str | None
    provider_tag: str | None
    supports_streaming: bool
    pricing: list[dict[str, Any]]
    reference_roles: bool = False

    @classmethod
    def from_model(cls, model: dict[str, Any]) -> "AdapterCapabilities":
        return cls(
            model=str(model.get("id") or ""),
            execution_mode=str(model.get("execution_mode") or "live"),
            available=bool(model.get("available")),
            supported_parameters=dict(model.get("supported_parameters") or {}),
            provider_slug=model.get("provider_slug"),
            provider_tag=model.get("provider_tag"),
            supports_streaming=bool(model.get("supports_streaming")),
            pricing=list(model.get("pricing") or []),
            reference_roles=bool(model.get("supports_reference_roles")),
        )

    @property
    def max_references(self) -> int:
        return _descriptor_max(self.supported_parameters, "input_references")

    @property
    def aspect_ratios(self) -> tuple[str, ...]:
        return tuple(_descriptor_values(self.supported_parameters, "aspect_ratio"))

    @property
    def qualities(self) -> tuple[str, ...]:
        return tuple(_descriptor_values(self.supported_parameters, "quality"))

    @property
    def seed(self) -> bool:
        return "seed" in self.supported_parameters

    @property
    def negative_prompt(self) -> bool:
        return "negative_prompt" in self.supported_parameters

    def supports(self, name: str) -> bool:
        return name in self.supported_parameters

    def to_json(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "max_references": self.max_references,
            "aspect_ratios": list(self.aspect_ratios),
            "qualities": list(self.qualities),
            "seed": self.seed,
            "negative_prompt": self.negative_prompt,
        }


@dataclass(frozen=True)
class GenerationRequest:
    identity_image: Path
    style_images: list[Path]
    instruction: str
    negative_prompt: str
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
    usage: dict[str, Any]
    cost_usd: float


class GenerationAdapter(Protocol):
    capabilities: AdapterCapabilities

    def generate(self, request: GenerationRequest) -> GenerationResult:
        ...


def _ratio_value(value: str) -> float:
    left, right = value.split(":", 1)
    return float(left) / float(right)


def negotiate_aspect_ratio(supported: list[str] | tuple[str, ...]) -> str:
    candidates = [value for value in supported if value != "auto" and ":" in value]
    if not candidates:
        return "provider-default"
    return min(candidates, key=lambda candidate: abs(_ratio_value(candidate) - REQUESTED_ART_RATIO[0] / REQUESTED_ART_RATIO[1]))


def model_capabilities(model: str, models: list[dict[str, Any]] | None = None) -> AdapterCapabilities:
    entries = models or [simulation_model(), unavailable_live_model()]
    entry = next((item for item in entries if item.get("id") == model), None) or unavailable_live_model(model)
    return AdapterCapabilities.from_model(entry)


def validate_request(recipe: dict[str, Any], style_count: int, capabilities: AdapterCapabilities) -> dict[str, Any]:
    if not capabilities.available:
        raise ValueError(f"{recipe.get('model')} is unavailable; explicitly choose an available replacement")
    total = 1 + style_count
    if not capabilities.supports("input_references"):
        raise ValueError(f"{recipe.get('model')} does not support image references and cannot run this portrait workflow")
    if total > capabilities.max_references:
        raise ValueError(
            f"{recipe.get('model')} accepts at most {capabilities.max_references} input references; "
            f"the identity image plus {style_count} selected style references needs {total}. Remove {total - capabilities.max_references} reference(s)."
        )
    quality = str(recipe.get("quality") or "")
    if capabilities.qualities and quality not in capabilities.qualities:
        raise ValueError(f"{recipe.get('model')} does not support quality {quality}")
    return {
        "requested_aspect_ratio": REQUESTED_ART_RATIO_LABEL,
        "effective_aspect_ratio": negotiate_aspect_ratio(capabilities.aspect_ratios),
        "quality_mapping": "native" if capabilities.supports("quality") else "omitted-provider-default",
        "negative_prompt_mapping": "native_negative_prompt" if capabilities.negative_prompt else "explicit_avoid_instruction",
        "reference_mapping": "role_aware" if capabilities.reference_roles else "identity_first_style_after",
        "sent_parameters": [
            name for name in ("input_references", "aspect_ratio", "quality", "negative_prompt", "background", "seed", "n", "output_format")
            if capabilities.supports(name)
        ],
    }


class FakeGenerationAdapter:
    def __init__(self, capabilities: AdapterCapabilities | None = None) -> None:
        self.capabilities = capabilities or AdapterCapabilities.from_model(simulation_model())
        self.name = "simulation"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.perf_counter()
        with Image.open(request.identity_image) as original:
            source = ImageOps.exif_transpose(original).convert("RGB")
        width, height = (336, 276)
        if request.effective_aspect_ratio == "5:4":
            width, height = (320, 256)
        elif request.effective_aspect_ratio == "3:2":
            width, height = (360, 240)
        image = ImageOps.fit(source, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.44))
        image = ImageEnhance.Color(image).enhance(0.78)
        image = ImageEnhance.Contrast(image).enhance(1.08)
        image = image.filter(ImageFilter.GaussianBlur(radius=0.28))
        draw = ImageDraw.Draw(image, "RGBA")
        randomizer = random.Random(request.seed)
        palette = [(171, 133, 101, 22), (67, 82, 98, 18), (231, 197, 133, 16), (111, 75, 78, 14)]
        for _ in range(90):
            x, y = randomizer.randrange(max(1, width)), randomizer.randrange(max(1, height))
            length, color = randomizer.randrange(8, 42), randomizer.choice(palette)
            draw.line((x, y, min(width, x + length), y + randomizer.randrange(-5, 6)), fill=color, width=randomizer.choice([1, 2, 3]))
        image.save(request.output_path, format="PNG")
        return GenerationResult(
            output_path=str(request.output_path), backend=self.name, model=request.model, seed=request.seed,
            elapsed_seconds=round(time.perf_counter() - started, 3), dimensions=[width, height],
            effective_aspect_ratio=request.effective_aspect_ratio,
            usage={"images": 1, "cost": 0.0}, cost_usd=0.0,
        )


class OpenRouterGenerationAdapter:
    def __init__(self, capabilities: AdapterCapabilities, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured; live generation cannot start")
        if capabilities.execution_mode != "live":
            raise ValueError("OpenRouter adapter requires live model capabilities")
        self.capabilities = capabilities
        self.name = "openrouter"

    @staticmethod
    def _data_url(path: Path) -> str:
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{media_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        references = [{"type": "image_url", "image_url": {"url": self._data_url(request.identity_image)}}]
        references.extend({"type": "image_url", "image_url": {"url": self._data_url(path)}} for path in request.style_images)
        payload: dict[str, Any] = {"model": request.model, "prompt": request.instruction}
        if self.capabilities.supports("input_references"):
            payload["input_references"] = references
        if self.capabilities.supports("n"):
            payload["n"] = 1
        if self.capabilities.supports("aspect_ratio") and request.effective_aspect_ratio != "provider-default":
            payload["aspect_ratio"] = request.effective_aspect_ratio
        if self.capabilities.supports("quality"):
            payload["quality"] = request.quality
        if self.capabilities.supports("negative_prompt") and request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt
        if self.capabilities.supports("background"):
            payload["background"] = "opaque"
        if self.capabilities.supports("output_format"):
            payload["output_format"] = "png"
        if self.capabilities.supports("seed"):
            payload["seed"] = request.seed
        if self.capabilities.provider_tag:
            payload["provider"] = {"only": [self.capabilities.provider_tag], "allow_fallbacks": False}

        started = time.perf_counter()
        response = requests.post(
            "https://openrouter.ai/api/v1/images",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "X-Title": "Portrait Workbench"},
            json=payload,
            timeout=180,
        )
        if not response.ok:
            raise RuntimeError(f"OpenRouter image generation failed {response.status_code}: {response.text[:500]}")
        body = response.json()
        data = body.get("data") or []
        if not data or not data[0].get("b64_json"):
            raise RuntimeError("OpenRouter returned no image data")
        raw = base64.b64decode(data[0]["b64_json"])
        try:
            with Image.open(io.BytesIO(raw)) as opened:
                generated = opened.convert("RGB")
                dimensions = [int(generated.width), int(generated.height)]
                generated.save(request.output_path, format="PNG")
        except Exception as exc:
            raise RuntimeError(f"OpenRouter returned an unsupported image payload: {exc}") from exc
        usage = dict(body.get("usage") or {})
        cost = float(usage.get("cost") or 0.0)
        return GenerationResult(
            output_path=str(request.output_path), backend=self.name, model=request.model, seed=request.seed,
            elapsed_seconds=round(time.perf_counter() - started, 3), dimensions=dimensions,
            effective_aspect_ratio=request.effective_aspect_ratio, usage=usage, cost_usd=cost,
        )


def adapter_for(execution_mode: str, capabilities: AdapterCapabilities) -> GenerationAdapter:
    if execution_mode == "simulation":
        if capabilities.model != SIMULATION_MODEL_ID:
            raise ValueError("simulation runs must explicitly select the deterministic simulation model")
        return FakeGenerationAdapter(capabilities)
    if execution_mode == "live":
        return OpenRouterGenerationAdapter(capabilities)
    raise ValueError("execution_mode must be live or simulation")


def resolved_run_instruction(recipe: dict[str, Any], capabilities: AdapterCapabilities) -> str:
    if capabilities.negative_prompt:
        return resolve_recipe_instruction({**recipe, "avoid": ""})
    return resolve_recipe_instruction(recipe)


def stable_seed(item_id: str) -> int:
    return int(hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:8], 16) % (2**31)
