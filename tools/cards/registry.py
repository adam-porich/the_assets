from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image, ImageOps

from .amiga import render_amiga_art, render_amiga_card
from .style_pipeline import legacy_amiga_style, style_checksum


@dataclass(frozen=True)
class RenderBundle:
    logical_art: Image.Image
    art: Image.Image
    card: Image.Image
    metadata: dict[str, Any]


class RendererDriver(Protocol):
    driver_id: str
    label: str

    def render(self, style: dict[str, Any], master: Image.Image, label: str, framing: dict[str, float] | None = None) -> RenderBundle:
        ...


def _framing_transform(image: Image.Image, window: tuple[int, int], framing: dict[str, float], centering: tuple[float, float]) -> tuple[Image.Image, dict[str, Any]]:
    width, height = image.size
    window_width, window_height = window
    if width <= 0 or height <= 0:
        raise ValueError("master image dimensions must be positive")
    zoom = max(1.0, min(3.0, float(framing.get("zoom", 1.0))))
    offset_x = max(-1.0, min(1.0, float(framing.get("offset_x", 0.0))))
    offset_y = max(-1.0, min(1.0, float(framing.get("offset_y", 0.0))))
    source_ratio = width / height
    target_ratio = window_width / window_height
    if source_ratio > target_ratio:
        crop_height = height / zoom
        crop_width = crop_height * target_ratio
    else:
        crop_width = width / zoom
        crop_height = crop_width / target_ratio
    centred_left = (width - crop_width) * float(centering[0])
    centred_top = (height - crop_height) * float(centering[1])
    left = max(0.0, min(width - crop_width, centred_left + offset_x * width))
    top = max(0.0, min(height - crop_height, centred_top + offset_y * height))
    box = (round(left), round(top), round(left + crop_width), round(top + crop_height))
    cropped = image.crop(box)
    transform = {
        "zoom": round(zoom, 6), "offset_x": round(offset_x, 6), "offset_y": round(offset_y, 6),
        "source_size": [width, height], "window": [window_width, window_height], "crop_box": list(box),
        "centering": [float(centering[0]), float(centering[1])], "empty_pixels": False,
    }
    return cropped, transform


class AmigaRenderer:
    driver_id = "amiga-ocs"
    label = "Amiga OCS"

    def render(self, style: dict[str, Any], master: Image.Image, label: str, framing: dict[str, float] | None = None) -> RenderBundle:
        selected = copy.deepcopy(style)
        renderer = selected["renderer"]
        composition = selected["composition"]
        resolved_framing = {**composition["default_framing"], **(framing or {})}
        default_framing = composition["default_framing"]
        is_default = all(abs(float(resolved_framing.get(key, 0)) - float(default_framing.get(key, 0))) < 1e-9 for key in ("zoom", "offset_x", "offset_y"))
        source = ImageOps.exif_transpose(master).convert("RGB")
        if is_default:
            transformed = source
            transform = {"zoom": 1.0, "offset_x": 0.0, "offset_y": 0.0, "source_size": list(source.size), "window": list(renderer["logical_art_size"]), "crop_box": [0, 0, source.width, source.height], "centering": list(composition["centering"]), "empty_pixels": False}
        else:
            transformed, transform = _framing_transform(source, tuple(renderer["logical_art_size"]), resolved_framing, tuple(composition["centering"]))
        logical, art, metadata = render_amiga_art(transformed, centering=tuple(composition["centering"]), style=selected)
        card = render_amiga_card(logical, label, style=selected)
        metadata = {
            **metadata,
            "driver_id": self.driver_id,
            "style_version_id": selected["identity"]["style_version_id"],
            "style_checksum_sha256": selected.get("checksums", {}).get("style_sha256") or style_checksum(selected),
            "framing": {"requested": resolved_framing, "resolved": transform},
            "render_revision_input_sha256": hashlib.sha256(source.tobytes()).hexdigest(),
            "logical_card_size": list(selected["card_assembly"]["logical_card_size"]),
            "output_card_size": list(card.size),
        }
        return RenderBundle(logical, art, card, metadata)


class RendererRegistry:
    def __init__(self) -> None:
        self._drivers: dict[str, RendererDriver] = {}

    def register(self, driver: RendererDriver) -> None:
        self._drivers[driver.driver_id] = driver

    def get(self, driver_id: str) -> RendererDriver:
        try:
            return self._drivers[driver_id]
        except KeyError as exc:
            raise ValueError(f"no renderer is registered for driver {driver_id}") from exc

    def render(self, style: dict[str, Any], master: Image.Image, label: str, framing: dict[str, float] | None = None) -> RenderBundle:
        return self.get(str(style["renderer"]["driver_id"])).render(style, master, label, framing)

    def descriptors(self, driver_id: str) -> dict[str, Any]:
        driver = self.get(driver_id)
        return {"id": driver.driver_id, "label": driver.label}


registry = RendererRegistry()
registry.register(AmigaRenderer())
