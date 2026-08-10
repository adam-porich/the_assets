from __future__ import annotations

import math
from typing import Any

from PIL import Image, ImageOps


CHROMA_KEYS = {"green": (0, 255, 0), "magenta": (255, 0, 255)}


def _distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    return math.sqrt(sum((first[channel] - second[channel]) ** 2 for channel in range(3)))


def _key_dominance(colour: tuple[int, int, int], key: tuple[int, int, int]) -> int:
    red, green, blue = colour
    return green - max(red, blue) if key[1] > 200 else min(red, blue) - green


def choose_chroma_key(source: Image.Image) -> tuple[str, tuple[int, int, int]]:
    sample = ImageOps.contain(source.convert("RGB"), (128, 128), Image.Resampling.BILINEAR)
    pixels = list(sample.getdata())
    scores = {name: sum(1 for colour in pixels if _distance(colour, key) < 90) for name, key in CHROMA_KEYS.items()}
    name = min(scores, key=scores.get)
    return name, CHROMA_KEYS[name]


def extract_foreground(image: Image.Image, key: tuple[int, int, int]) -> tuple[Image.Image, dict[str, Any]]:
    source = image.convert("RGB")
    width, height = source.size
    border = []
    step = max(1, min(width, height) // 128)
    for x in range(0, width, step): border.extend((source.getpixel((x, 0)), source.getpixel((x, height - 1))))
    for y in range(0, height, step): border.extend((source.getpixel((0, y)), source.getpixel((width - 1, y))))
    border_coverage = sum(_distance(colour, key) < 70 or _key_dominance(colour, key) > 40 for colour in border) / max(1, len(border))
    if border_coverage < 0.45:
        opaque = source.convert("RGBA")
        return opaque, {"mode": "opaque-fallback", "key": "#%02x%02x%02x" % key, "border_coverage": round(border_coverage, 6), "bbox": [0, 0, width, height]}
    output = Image.new("RGBA", source.size)
    result = []
    for red, green, blue in source.getdata():
        distance = _distance((red, green, blue), key)
        distance_alpha = max(0, min(255, round((distance - 18) / 132 * 255)))
        # Generated chroma fields are rarely the requested literal RGB value:
        # providers commonly add a gentle vignette or brightness variation.
        # Key colour dominance remains stable through that shading, so use it
        # alongside absolute distance to avoid retaining a translucent rectangle.
        dominance = _key_dominance((red, green, blue), key)
        dominance_alpha = max(0, min(255, round((72 - dominance) / 54 * 255)))
        alpha = min(distance_alpha, dominance_alpha)
        if alpha < 255:
            if key[1] > 200:
                green = min(green, max(red, blue) + 12)
            else:
                edge = green + 16
                red, blue = min(red, edge), min(blue, edge)
        result.append((red, green, blue, alpha))
    output.putdata(result)
    bbox = output.getchannel("A").getbbox() or (0, 0, width, height)
    return output, {"mode": "chroma-matte", "key": "#%02x%02x%02x" % key, "border_coverage": round(border_coverage, 6), "bbox": list(bbox)}


def _hex(value: str) -> tuple[int, int, int]:
    return tuple(bytes.fromhex(value.removeprefix("#")))  # type: ignore[return-value]


def _background(size: tuple[int, int], descriptor: dict[str, Any]) -> Image.Image:
    width, height = size
    top, bottom, glow = (_hex(str(descriptor[key])) for key in ("top", "bottom", "glow"))
    glow_strength = float(descriptor.get("glow_strength", 0.2))
    image = Image.new("RGB", size)
    pixels = []
    for y in range(height):
        vertical = y / max(1, height - 1)
        for x in range(width):
            radial = max(0.0, 1.0 - (((x - width * 0.5) / (width * 0.62)) ** 2 + ((y - height * 0.42) / (height * 0.72)) ** 2))
            base = tuple(round(top[channel] * (1 - vertical) + bottom[channel] * vertical) for channel in range(3))
            strength = glow_strength * radial
            pixels.append(tuple(round(base[channel] * (1 - strength) + glow[channel] * strength) for channel in range(3)))
    image.putdata(pixels)
    return image


def foreground_layers(foreground: Image.Image, style: dict[str, Any], background_id: str, framing: dict[str, float] | None = None) -> tuple[Image.Image, Image.Image, dict[str, Any]]:
    config = style.get("backgrounds") or {}
    presets = {str(item["id"]): item for item in config.get("presets", [])}
    descriptor = presets.get(background_id) or presets.get(str(config.get("default_id")))
    if not descriptor:
        raise ValueError(f"background preset {background_id} is not defined")
    size = tuple(int(value) for value in config.get("composite_size", [672, 552]))
    background = _background(size, descriptor)
    alpha = foreground.getchannel("A") if foreground.mode == "RGBA" else Image.new("L", foreground.size, 255)
    box = alpha.getbbox() or (0, 0, foreground.width, foreground.height)
    subject = foreground.convert("RGBA").crop(box)
    framing = framing or {}
    zoom = max(1.0, min(3.0, float(framing.get("zoom", 1.0))))
    edge_margin = max(2, round(min(foreground.size) * 0.025))
    touches_top = box[1] <= edge_margin
    touches_left = box[0] <= edge_margin
    touches_right = box[2] >= foreground.width - edge_margin
    if touches_top and not (touches_left or touches_right):
        # The vertical extent is clipped, so use the intact horizontal extent
        # and carry that crop naturally through the top of the art window.
        base_scale = size[0] * 0.94 / subject.width
    elif (touches_left or touches_right) and not touches_top:
        base_scale = size[1] * 0.94 / subject.height
    else:
        base_scale = min(size[0] * 0.9 / subject.width, size[1] * 0.94 / subject.height)
    subject = subject.resize((max(1, round(subject.width * base_scale * zoom)), max(1, round(subject.height * base_scale * zoom))), Image.Resampling.LANCZOS)
    offset_x = max(-1.0, min(1.0, float(framing.get("offset_x", 0.0))))
    offset_y = max(-1.0, min(1.0, float(framing.get("offset_y", 0.0))))
    x = round((size[0] - subject.width) / 2 + offset_x * size[0] * 0.2)
    y = round((0 if touches_top else size[1] - subject.height) + offset_y * size[1] * 0.2)
    layer = Image.new("RGBA", size)
    layer.paste(subject, (x, y), subject)
    metadata = {"background_id": descriptor["id"], "background_label": descriptor.get("label", descriptor["id"]), "descriptor": {key: descriptor[key] for key in ("top", "bottom", "glow", "glow_strength") if key in descriptor}, "subject_bbox": list(box), "touching_edges": [edge for edge, touching in (("top", touches_top), ("left", touches_left), ("right", touches_right)) if touching], "placement": [x, y, subject.width, subject.height], "composite_size": list(size), "framing": {"zoom": zoom, "offset_x": offset_x, "offset_y": offset_y}}
    return background, layer, metadata


def composite_foreground(foreground: Image.Image, style: dict[str, Any], background_id: str, framing: dict[str, float] | None = None) -> tuple[Image.Image, dict[str, Any]]:
    background, layer, metadata = foreground_layers(foreground, style, background_id, framing)
    background.paste(layer, (0, 0), layer)
    return background, metadata
