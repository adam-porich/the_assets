from __future__ import annotations

import json
import math
import time
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .manifest import (
    BackgroundResult,
    DEFAULT_VARIANTS,
    CandidateSettings,
    ProcessResult,
    VariantConfig,
    deterministic_background_candidate_filename,
    deterministic_background_filename,
    deterministic_candidate_filename,
    deterministic_crop_filename,
)


def load_fixed_palette(path: Path | None, color_limit: int) -> Image.Image | None:
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    colors = data.get("colors", [])[:color_limit]
    palette_values: list[int] = []
    for value in colors:
        value = value.lstrip("#")
        palette_values.extend([int(value[i : i + 2], 16) for i in (0, 2, 4)])
    palette_values.extend([0] * (768 - len(palette_values)))
    palette = Image.new("P", (1, 1))
    palette.putpalette(palette_values)
    return palette


def clamp_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    left = max(0, min(left, width - 1))
    top = max(0, min(top, height - 1))
    right = max(left + 1, min(right, width))
    bottom = max(top + 1, min(bottom, height))
    return left, top, right, bottom


def square_crop_box(
    width: int,
    height: int,
    face_box: list[int] | None = None,
    padding: float = 1.9,
) -> tuple[int, int, int, int]:
    if face_box:
        x, y, w, h = face_box
        cx = x + w / 2
        cy = y + h * 0.58
        side = max(w, h) * padding
    else:
        cx = width / 2
        cy = height * 0.43
        side = min(width, height) * 0.82
    side = max(1, min(side, width, height))
    left = int(round(cx - side / 2))
    top = int(round(cy - side * 0.45))
    right = int(round(left + side))
    bottom = int(round(top + side))
    if left < 0:
        right -= left
        left = 0
    if top < 0:
        bottom -= top
        top = 0
    if right > width:
        left -= right - width
        right = width
    if bottom > height:
        top -= bottom - height
        bottom = height
    return clamp_box((left, top, right, bottom), width, height)


def detect_largest_face(path: Path) -> list[int] | None:
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    image = cv2.imread(str(path))
    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
    return [int(x), int(y), int(w), int(h)]


def apply_background(image: Image.Image, mode: str) -> Image.Image:
    if mode == "keep":
        return image
    if mode == "vignette":
        base = image.copy()
        width, height = base.size
        mask = Image.new("L", base.size, 0)
        px = mask.load()
        cx, cy = width / 2, height / 2
        max_dist = math.hypot(cx, cy)
        for y in range(height):
            for x in range(width):
                dist = math.hypot(x - cx, y - cy) / max_dist
                px[x, y] = int(max(0, min(110, (dist - 0.35) * 220)))
        shadow = ImageEnhance.Brightness(base).enhance(0.55)
        return Image.composite(shadow, base, mask)
    if mode == "flatten":
        small = image.resize((1, 1), Image.Resampling.BOX)
        bg = Image.new("RGB", image.size, small.getpixel((0, 0)))
        soft_mask = Image.new("L", image.size, 0)
        width, height = image.size
        px = soft_mask.load()
        for y in range(height):
            for x in range(width):
                nx = abs((x / max(width - 1, 1)) - 0.5) * 2
                ny = abs((y / max(height - 1, 1)) - 0.5) * 2
                px[x, y] = int(max(nx, ny) ** 2 * 150)
        return Image.composite(bg, image, soft_mask)
    raise ValueError(f"Unknown background mode: {mode}")


def prepare_crop(source_path: Path, crop_path: Path, settings: CandidateSettings) -> tuple[Image.Image, list[int] | None]:
    image = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
    face_box = detect_largest_face(source_path)
    box = square_crop_box(image.width, image.height, face_box, settings.crop_padding)
    crop = image.crop(box)
    crop = apply_background(crop, settings.background)
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(crop_path)
    return crop, face_box


def prepare_raw_crop(source_path: Path, crop_path: Path, settings: CandidateSettings) -> tuple[Image.Image, list[int] | None]:
    image = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
    face_box = detect_largest_face(source_path)
    box = square_crop_box(image.width, image.height, face_box, settings.crop_padding)
    crop = image.crop(box)
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(crop_path)
    return crop, face_box


def neutral_background(size: tuple[int, int]) -> Image.Image:
    return Image.new("RGB", size, "#b8afa3")


def transparent_from_mask(image: Image.Image, mask: Image.Image) -> Image.Image:
    foreground = image.convert("RGBA")
    foreground.putalpha(mask)
    return foreground


def composite_on_neutral(image: Image.Image, mask: Image.Image) -> Image.Image:
    return Image.composite(image.convert("RGB"), neutral_background(image.size), mask)


def no_removal_mask(image: Image.Image) -> Image.Image:
    return Image.new("L", image.size, 255)


def corner_average(image: Image.Image, sample: int = 12) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    points: list[tuple[int, int, int]] = []
    for x0, y0 in ((0, 0), (max(0, width - sample), 0), (0, max(0, height - sample)), (max(0, width - sample), max(0, height - sample))):
        region = rgb.crop((x0, y0, min(width, x0 + sample), min(height, y0 + sample)))
        region_px = region.load()
        for y in range(region.height):
            for x in range(region.width):
                points.append(region_px[x, y])
    count = max(1, len(points))
    return (
        sum(pixel[0] for pixel in points) // count,
        sum(pixel[1] for pixel in points) // count,
        sum(pixel[2] for pixel in points) // count,
    )


def color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def classical_background_mask(image: Image.Image, threshold: int = 48) -> Image.Image:
    rgb = image.convert("RGB")
    width, height = rgb.size
    bg = corner_average(rgb)
    pixels = rgb.load()
    visited = set()
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    background = Image.new("L", rgb.size, 0)
    bg_px = background.load()
    while queue:
        x, y = queue.popleft()
        if (x, y) in visited or x < 0 or y < 0 or x >= width or y >= height:
            continue
        visited.add((x, y))
        if color_distance(pixels[x, y], bg) > threshold:
            continue
        bg_px[x, y] = 255
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    foreground = ImageOps.invert(background)
    foreground = foreground.filter(ImageFilter.MaxFilter(5))
    foreground = foreground.filter(ImageFilter.MinFilter(3))
    return foreground.filter(ImageFilter.GaussianBlur(1.2))


def model_background_mask(image: Image.Image) -> Image.Image:
    try:
        from rembg import remove  # type: ignore
    except Exception as exc:
        raise RuntimeError("Model background mode requires `uv sync --extra background`") from exc
    result = remove(image.convert("RGBA"))
    if not isinstance(result, Image.Image):
        result = Image.open(result)
    return result.convert("RGBA").getchannel("A")


def make_background_mask(image: Image.Image, mode: str) -> Image.Image:
    if mode == "none":
        return no_removal_mask(image)
    if mode == "classical":
        return classical_background_mask(image)
    if mode == "model":
        return model_background_mask(image)
    raise ValueError(f"Unknown background benchmark mode: {mode}")


def normalize(image: Image.Image, settings: CandidateSettings) -> Image.Image:
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(settings.contrast)
    image = ImageEnhance.Color(image).enhance(settings.saturation)
    image = ImageEnhance.Sharpness(image).enhance(settings.sharpness)
    return image


def quantize_image(
    image: Image.Image,
    colors: int,
    dither: bool,
    fixed_palette: Image.Image | None,
) -> Image.Image:
    dither_mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    if fixed_palette is not None:
        return image.quantize(palette=fixed_palette, dither=dither_mode).convert("RGB")
    return image.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=dither_mode).convert("RGB")


def add_restrained_edges(image: Image.Image, quantized: Image.Image) -> Image.Image:
    gray = image.convert("L").filter(ImageFilter.FIND_EDGES)
    gray = ImageOps.autocontrast(gray)
    edges = gray.point(lambda value: 255 if value > 108 else 0).filter(ImageFilter.MinFilter(3))
    dark = ImageEnhance.Brightness(quantized).enhance(0.45)
    return Image.composite(dark, quantized, edges.point(lambda value: 70 if value else 0))


def make_variant(
    crop: Image.Image,
    variant: VariantConfig,
    settings: CandidateSettings,
    fixed_palette: Image.Image | None = None,
) -> Image.Image:
    image = normalize(crop, settings)
    if variant.pre_blur:
        image = image.filter(ImageFilter.GaussianBlur(variant.pre_blur))
    logical = image.resize((settings.size, settings.size), Image.Resampling.LANCZOS)
    quantized = quantize_image(logical, variant.colors, variant.dither, fixed_palette)
    if variant.edge:
        quantized = add_restrained_edges(logical, quantized)
    return quantized.resize(
        (settings.size * settings.review_scale, settings.size * settings.review_scale),
        Image.Resampling.NEAREST,
    )


def palette_color_count(path: Path) -> int:
    image = Image.open(path).convert("RGB")
    return len(image.getcolors(maxcolors=256 * 256) or [])


def process_source(
    source_path: Path,
    photo_id: int,
    library_dir: Path,
    settings: CandidateSettings,
    variants: list[str],
    palette_path: Path | None = None,
) -> ProcessResult:
    crop_path = library_dir / "crops" / deterministic_crop_filename(photo_id)
    crop, face_box = prepare_crop(source_path, crop_path, settings)
    fixed_palette = load_fixed_palette(palette_path, max(DEFAULT_VARIANTS[name].colors for name in variants))
    result = ProcessResult(crop=str(crop_path.relative_to(library_dir)), face_box=face_box)
    out_dir = library_dir / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in variants:
        variant = DEFAULT_VARIANTS[name]
        candidate = make_variant(crop, variant, settings, fixed_palette)
        filename = deterministic_candidate_filename(photo_id, name, settings.size)
        out_path = out_dir / filename
        candidate.save(out_path)
        result.candidates.append(
            {
                "variant": name,
                "filename": str(out_path.relative_to(library_dir)),
                "logical_size": settings.size,
                "review_scale": settings.review_scale,
                "colors": variant.colors,
                "dither": variant.dither,
                "edge": variant.edge,
                "settings": settings.to_json(),
            }
        )
    return result


def benchmark_background_source(
    source_path: Path,
    photo_id: int,
    library_dir: Path,
    settings: CandidateSettings,
    modes: list[str],
    variants: list[str],
    palette_path: Path | None = None,
) -> tuple[list[BackgroundResult], list[int] | None]:
    crop_dir = library_dir / "crops"
    mask_dir = library_dir / "masks"
    foreground_dir = library_dir / "foregrounds"
    background_dir = library_dir / "backgrounds"
    candidate_dir = library_dir / "candidates"
    for directory in (crop_dir, mask_dir, foreground_dir, background_dir, candidate_dir):
        directory.mkdir(parents=True, exist_ok=True)

    crop_path = crop_dir / deterministic_background_filename(photo_id, "benchmark", "crop")
    crop, face_box = prepare_raw_crop(source_path, crop_path, settings)
    fixed_palette = load_fixed_palette(palette_path, max(DEFAULT_VARIANTS[name].colors for name in variants))
    results: list[BackgroundResult] = []
    for mode in modes:
        started = time.perf_counter()
        result = BackgroundResult(
            mode=mode,
            elapsed_seconds=0.0,
            crop=str(crop_path.relative_to(library_dir)),
        )
        try:
            mask = make_background_mask(crop, mode)
            foreground = transparent_from_mask(crop, mask)
            neutral = composite_on_neutral(crop, mask)

            mask_path = mask_dir / deterministic_background_filename(photo_id, mode, "mask")
            foreground_path = foreground_dir / deterministic_background_filename(photo_id, mode, "foreground")
            neutral_path = background_dir / deterministic_background_filename(photo_id, mode, "neutral")
            mask.save(mask_path)
            foreground.save(foreground_path)
            neutral.save(neutral_path)
            result.mask = str(mask_path.relative_to(library_dir))
            result.transparent_foreground = str(foreground_path.relative_to(library_dir))
            result.neutral_background = str(neutral_path.relative_to(library_dir))

            for name in variants:
                variant = DEFAULT_VARIANTS[name]
                candidate = make_variant(neutral, variant, settings, fixed_palette)
                filename = deterministic_background_candidate_filename(photo_id, mode, name, settings.size)
                out_path = candidate_dir / filename
                candidate.save(out_path)
                result.candidates.append(
                    {
                        "background_mode": mode,
                        "variant": name,
                        "filename": str(out_path.relative_to(library_dir)),
                        "logical_size": settings.size,
                        "review_scale": settings.review_scale,
                        "colors": variant.colors,
                        "dither": variant.dither,
                        "edge": variant.edge,
                        "settings": settings.to_json(),
                    }
                )
        except Exception as exc:
            result.error = str(exc)
        finally:
            result.elapsed_seconds = round(time.perf_counter() - started, 3)
        results.append(result)
    return results, face_box
