from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


STYLE_PATH = Path(__file__).parent / "styles" / "amiga-ocs-portrait-v1.json"
BAYER_4X4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


@dataclass(frozen=True)
class AmigaRender:
    logical_art: Image.Image
    art: Image.Image
    card: Image.Image
    metadata: dict[str, Any]


@lru_cache(maxsize=1)
def load_amiga_style() -> dict[str, Any]:
    return json.loads(STYLE_PATH.read_text(encoding="utf-8"))


def amiga_palette(style: dict[str, Any] | None = None) -> tuple[tuple[int, int, int], ...]:
    selected = style or load_amiga_style()
    if "renderer" in selected:
        selected = selected["renderer"]
    return tuple(tuple(bytes.fromhex(value.removeprefix("#"))) for value in selected["palette"])  # type: ignore[return-value]


def _linear(value: int) -> float:
    channel = value / 255.0
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _oklab(colour: tuple[int, int, int]) -> tuple[float, float, float]:
    red, green, blue = (_linear(channel) for channel in colour)
    light = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    light, medium, short = (value ** (1 / 3) for value in (light, medium, short))
    return (
        0.2104542553 * light + 0.7936177850 * medium - 0.0040720468 * short,
        1.9779984951 * light - 2.4285922050 * medium + 0.4505937099 * short,
        0.0259040371 * light + 0.7827717662 * medium - 0.8086757660 * short,
    )


def _distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    # Chroma is slightly restrained so the limited warm/cool value ramps remain
    # useful across varied skin tones instead of snapping to accent colours.
    return (
        (first[0] - second[0]) ** 2
        + 0.82 * (first[1] - second[1]) ** 2
        + 0.82 * (first[2] - second[2]) ** 2
    )


def _luminance(colour: tuple[int, int, int]) -> float:
    red, green, blue = (_linear(channel) for channel in colour)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _prepare_master(master: Image.Image, logical_size: tuple[int, int], centering: tuple[float, float], style: dict[str, Any] | None = None) -> Image.Image:
    source = ImageOps.exif_transpose(master).convert("RGB")
    source = ImageOps.fit(source, logical_size, method=Image.Resampling.LANCZOS, centering=centering)
    selected = (style or load_amiga_style())
    selected = selected.get("renderer", selected)
    preprocess = selected.get("preprocess") or {}
    source = ImageEnhance.Color(source).enhance(float(preprocess.get("color", 0.88)))
    source = ImageEnhance.Contrast(source).enhance(float(preprocess.get("contrast", 1.08)))
    return source.filter(ImageFilter.UnsharpMask(radius=float(preprocess.get("unsharp_radius", 0.8)), percent=int(preprocess.get("unsharp_percent", 90)), threshold=int(preprocess.get("unsharp_threshold", 5))))


def _two_nearest(
    colour: tuple[int, int, int],
    palette_lab: tuple[tuple[float, float, float], ...],
) -> tuple[int, float, int, float]:
    target = _oklab(colour)
    first, second = -1, -1
    first_distance, second_distance = math.inf, math.inf
    for index, candidate in enumerate(palette_lab):
        distance = _distance(target, candidate)
        if distance < first_distance:
            second, second_distance = first, first_distance
            first, first_distance = index, distance
        elif distance < second_distance:
            second, second_distance = index, distance
    return first, first_distance, second, second_distance


def _edge_strength(luminance: list[float], width: int, height: int, x: int, y: int) -> float:
    centre = luminance[y * width + x]
    differences = []
    if x:
        differences.append(abs(centre - luminance[y * width + x - 1]))
    if x + 1 < width:
        differences.append(abs(centre - luminance[y * width + x + 1]))
    if y:
        differences.append(abs(centre - luminance[(y - 1) * width + x]))
    if y + 1 < height:
        differences.append(abs(centre - luminance[(y + 1) * width + x]))
    return max(differences, default=0.0)


def quantize_amiga(
    image: Image.Image,
    palette: tuple[tuple[int, int, int], ...] | None = None,
    *,
    dither_strength: float | None = None,
    edge_threshold: float | None = None,
    style: dict[str, Any] | None = None,
) -> Image.Image:
    """Map a logical-size master to the fixed OCS palette with edge-aware ordered dither."""
    selected_style = style or load_amiga_style()
    selected_renderer = selected_style.get("renderer", selected_style)
    selected_palette = palette or amiga_palette(selected_style)
    strength = float(selected_renderer["dither"]["strength"] if dither_strength is None else dither_strength)
    threshold = float(selected_renderer["dither"]["edge_threshold"] if edge_threshold is None else edge_threshold)
    source = image.convert("RGB")
    width, height = source.size
    raw = source.tobytes()
    pixels = list(zip(raw[0::3], raw[1::3], raw[2::3]))
    luminance = [_luminance(pixel) for pixel in pixels]
    palette_lab = tuple(_oklab(colour) for colour in selected_palette)
    nearest_cache: dict[tuple[int, int, int], tuple[int, float, int, float]] = {}
    output: list[tuple[int, int, int]] = []
    for y in range(height):
        for x in range(width):
            index = y * width + x
            colour = pixels[index]
            nearest = nearest_cache.get(colour)
            if nearest is None:
                nearest = _two_nearest(colour, palette_lab)
                nearest_cache[colour] = nearest
            first, first_distance, second, second_distance = nearest
            selected = first
            if first_distance > 1e-8 and _edge_strength(luminance, width, height, x, y) < threshold:
                first_root, second_root = math.sqrt(first_distance), math.sqrt(second_distance)
                second_share = min(0.48, strength * first_root / max(1e-8, first_root + second_root))
                ordered_threshold = (BAYER_4X4[y % 4][x % 4] + 0.5) / 16.0
                if ordered_threshold < second_share:
                    selected = second
            output.append(selected_palette[selected])
    result = Image.new("RGB", source.size)
    result.putdata(output)
    return result


def render_amiga_art(
    master: Image.Image,
    *,
    centering: tuple[float, float] = (0.5, 0.44),
    style: dict[str, Any] | None = None,
) -> tuple[Image.Image, Image.Image, dict[str, Any]]:
    selected = style or load_amiga_style()
    renderer = selected.get("renderer", selected)
    composition = selected.get("composition", {})
    logical_size = tuple(int(value) for value in renderer["logical_art_size"])
    scale = int(renderer["output_scale"])
    effective_centering = tuple(float(value) for value in composition.get("centering", centering)) if composition else centering
    prepared = _prepare_master(master, logical_size, effective_centering, selected)
    logical = quantize_amiga(prepared, amiga_palette(selected), style=selected)
    art = logical.resize((logical.width * scale, logical.height * scale), Image.Resampling.NEAREST)
    colours = logical.getcolors(maxcolors=logical.width * logical.height) or []
    metadata = {
        "style_id": selected.get("identity", {}).get("family_id", selected.get("id")),
        "style_version": selected.get("identity", {}).get("version", selected.get("version")),
        "logical_art_size": list(logical.size),
        "output_art_size": list(art.size),
        "output_scale": scale,
        "palette_space": renderer["palette_space"],
        "palette_limit": len(renderer["palette"]),
        "palette_colours_used": len(colours),
        "palette_sha256": hashlib.sha256("\n".join(renderer["palette"]).encode("ascii")).hexdigest(),
        "dither": dict(renderer["dither"]),
        "centering": list(effective_centering),
    }
    return logical, art, metadata


def _pixel_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, colour: tuple[int, int, int]) -> None:
    draw.text(xy, text.upper(), fill=colour, font=ImageFont.load_default())


def render_amiga_card(
    logical_art: Image.Image,
    label: str,
    *,
    style: dict[str, Any] | None = None,
) -> Image.Image:
    """Compose the complete card on the same logical pixel grid as its art."""
    selected = style or load_amiga_style()
    renderer = selected.get("renderer", selected)
    card_config = selected.get("card_assembly", selected)
    card_width, card_height = (int(value) for value in card_config["logical_card_size"])
    scale = int(card_config.get("output_scale", renderer["output_scale"]))
    palette = amiga_palette(selected)
    ink, deep_brown, slate, brown, umber = palette[0], palette[1], palette[3], palette[6], palette[7]
    border, title, copy, accent = palette[19], palette[16], palette[20], palette[22]
    canvas = Image.new("RGB", (card_width, card_height), deep_brown)
    draw = ImageDraw.Draw(canvas)

    draw.rectangle((4, 4, card_width - 5, card_height - 5), fill=brown, outline=border, width=2)
    draw.rectangle((7, 7, card_width - 8, card_height - 8), outline=umber, width=1)
    for x, y in ((7, 7), (card_width - 12, 7), (7, card_height - 12), (card_width - 12, card_height - 12)):
        draw.rectangle((x, y, x + 4, y + 4), fill=accent)

    draw.rectangle((17, 10, 192, 31), fill=deep_brown, outline=border, width=1)
    draw.line((20, 28, 189, 28), fill=umber, width=1)
    _pixel_text(draw, (23, 16), str((card_config.get("text") or {}).get("title", "Portrait Workbench")), title)

    art = logical_art.convert("RGB")
    if art.size != tuple(renderer["logical_art_size"]):
        art = art.resize(tuple(renderer["logical_art_size"]), Image.Resampling.NEAREST)
    draw.rectangle((18, 36, 192, 180), fill=ink, outline=border, width=2)
    canvas.paste(art, (21, 39))
    draw.rectangle((20, 38, 189, 177), outline=copy, width=1)

    draw.rectangle((16, 191, 194, 213), fill=deep_brown, outline=border, width=1)
    _pixel_text(draw, (22, 198), label[:28], title)
    draw.rectangle((16, 221, 194, 274), fill=deep_brown, outline=border, width=1)
    card_text = card_config.get("text") or {}
    _pixel_text(draw, (22, 229), str(card_text.get("subtitle", "Amiga OCS / 32 colours")), copy)
    _pixel_text(draw, (22, 241), str(card_text.get("version", "House style v1")), copy)
    draw.line((22, 256, 188, 256), fill=slate, width=1)
    _pixel_text(draw, (22, 261), str(card_text.get("identity", "Identity retained")), border)
    # Pillow rasterises even its bitmap font through an antialiased mask. Snap
    # the complete logical card back to the same hardware palette before the
    # nearest-neighbour presentation scale is applied.
    canvas = quantize_amiga(canvas, palette, dither_strength=0.0)
    return canvas.resize((card_width * scale, card_height * scale), Image.Resampling.NEAREST)


def render_amiga(master: Image.Image, label: str, *, centering: tuple[float, float] = (0.5, 0.44)) -> AmigaRender:
    selected = load_amiga_style()
    logical, art, metadata = render_amiga_art(master, centering=centering, style=selected)
    card = render_amiga_card(logical, label, style=selected)
    card_config = selected.get("card_assembly", selected)
    metadata = {**metadata, "logical_card_size": card_config["logical_card_size"], "output_card_size": list(card.size)}
    return AmigaRender(logical, art, card, metadata)


def palette_is_ocs_12_bit(palette: Iterable[tuple[int, int, int]]) -> bool:
    return all(channel % 17 == 0 for colour in palette for channel in colour)
