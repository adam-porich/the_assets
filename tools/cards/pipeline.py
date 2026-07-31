from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from tools.portraits.workspace import WorkspaceStore, checksum, now_iso


TEMPLATE_DIR = Path(__file__).parent / "templates"
ART_WINDOW = (336, 276)
PIXEL_LOGICAL_SIZE = (112, 92)
PIXEL_PALETTE_COLOURS = 32
TREATMENTS = {"painterly", "estate-pixel-v1"}
TREATMENT_VERSIONS = {"painterly": "painterly-source-v1", "estate-pixel-v1": "estate-pixel-v1"}
PREVIEW_SCHEMA_VERSION = 1
FRAME_PRESETS: dict[str, dict[str, float | str]] = {
    "bust": {"label": "Bust", "zoom": 1.0, "offset_x": 0.0, "offset_y": 0.02},
    "tall": {"label": "Tall", "zoom": 1.16, "offset_x": 0.0, "offset_y": -0.06},
    "torso": {"label": "Torso", "zoom": 1.28, "offset_x": 0.0, "offset_y": 0.08},
}


def load_template(template_id: str = "estate-card-v1") -> dict[str, Any]:
    path = TEMPLATE_DIR / f"{template_id}.json"
    if not path.exists():
        raise ValueError(f"unknown card template: {template_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def framing_preset(name: str) -> dict[str, float | str]:
    if name not in FRAME_PRESETS:
        raise ValueError(f"unknown framing preset: {name}; choose bust, tall, or torso")
    return dict(FRAME_PRESETS[name])


def calculate_cover_transform(
    image_size: tuple[int, int] | list[int],
    window_size: tuple[int, int] = ART_WINDOW,
    zoom: float = 1.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> dict[str, Any]:
    image_width, image_height = (float(image_size[0]), float(image_size[1]))
    window_width, window_height = (float(window_size[0]), float(window_size[1]))
    if image_width <= 0 or image_height <= 0 or window_width <= 0 or window_height <= 0:
        raise ValueError("image and art window dimensions must be positive")
    zoom = max(1.0, min(float(zoom), 3.0))
    base_scale = max(window_width / image_width, window_height / image_height)
    scale = base_scale * zoom
    scaled_width, scaled_height = image_width * scale, image_height * scale
    centred_left = (window_width - scaled_width) / 2
    centred_top = (window_height - scaled_height) / 2
    requested_left = centred_left + float(offset_x) * window_width
    requested_top = centred_top + float(offset_y) * window_height
    left = min(0.0, max(window_width - scaled_width, requested_left))
    top = min(0.0, max(window_height - scaled_height, requested_top))
    return {
        "base_scale": round(base_scale, 8),
        "scale": round(scale, 8),
        "left": round(left, 4),
        "top": round(top, 4),
        "scaled_width": round(scaled_width, 4),
        "scaled_height": round(scaled_height, 4),
        "offset_x": round((left - centred_left) / window_width, 6),
        "offset_y": round((top - centred_top) / window_height, 6),
        "window": [int(window_width), int(window_height)],
        "image_bounds": [round(left, 4), round(top, 4), round(left + scaled_width, 4), round(top + scaled_height, 4)],
    }


def apply_estate_pixel_treatment(art: Image.Image) -> Image.Image:
    """Apply the deterministic estate-pixel-v1 treatment to a framed 336×276 crop."""
    logical = art.convert("RGB").resize(PIXEL_LOGICAL_SIZE, Image.Resampling.LANCZOS)
    quantized = logical.quantize(
        colors=PIXEL_PALETTE_COLOURS,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    ).convert("RGB")
    return quantized.resize(ART_WINDOW, Image.Resampling.NEAREST)


def _render_image(
    source_path: Path,
    output_path: Path,
    art_output_path: Path,
    label: str,
    framing: dict[str, Any],
    template: dict[str, Any],
    treatment: str,
) -> dict[str, Any]:
    if treatment not in TREATMENTS:
        raise ValueError("treatment must be painterly or estate-pixel-v1")
    width, height = int(template["width"]), int(template["height"])
    left, top, right, bottom = [int(value) for value in template["art_window"]]
    colors = template["colors"]
    with Image.open(source_path) as opened:
        source = ImageOps.exif_transpose(opened).convert("RGB")
    transform = calculate_cover_transform(source.size, (right - left, bottom - top), **{key: framing[key] for key in ("zoom", "offset_x", "offset_y")})
    scaled = source.resize((round(transform["scaled_width"]), round(transform["scaled_height"])), Image.Resampling.LANCZOS)
    crop_left = max(0, round(-transform["left"]))
    crop_top = max(0, round(-transform["top"]))
    art = scaled.crop((crop_left, crop_top, crop_left + (right - left), crop_top + (bottom - top)))
    if treatment == "estate-pixel-v1":
        art = apply_estate_pixel_treatment(art)
    art_output_path.parent.mkdir(parents=True, exist_ok=True)
    art_temporary = art_output_path.with_name(f".{art_output_path.name}.{uuid.uuid4().hex}.tmp")
    art.save(art_temporary, format="PNG")
    art_temporary.replace(art_output_path)
    canvas = Image.new("RGB", (width, height), colors["card"])
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((10, 10, width - 11, height - 11), fill=colors["inner"], outline=colors["border"], width=5)
    draw.rectangle((left - 7, top - 7, right + 7, bottom + 7), fill=colors["art_matte"], outline=colors["border"], width=3)
    canvas.paste(art, (left, top))
    draw.rectangle((left - 1, top - 1, right, bottom), outline=colors["border"], width=2)
    draw.rectangle((32, 382, width - 33, 426), fill=colors["card"], outline=colors["border"], width=2)
    draw.rectangle((32, 442, width - 33, 548), fill=colors["card"], outline=colors["border"], width=2)
    font = ImageFont.load_default()
    draw.text((44, 396), label[:40], fill=colors["title"], font=font)
    draw.text((44, 458), "Experimental card-context preview", fill=colors["label"], font=font)
    draw.text((44, 482), "Framing remains freely adjustable", fill=colors["label"], font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    canvas.save(temporary, format="PNG")
    temporary.replace(output_path)
    palette_colours = len(art.resize(PIXEL_LOGICAL_SIZE, Image.Resampling.NEAREST).getcolors(maxcolors=PIXEL_LOGICAL_SIZE[0] * PIXEL_LOGICAL_SIZE[1]) or []) if treatment == "estate-pixel-v1" else None
    return {
        "dimensions": [width, height], "transform": transform,
        "render_metadata": {
            "treatment": treatment,
            "treatment_version": TREATMENT_VERSIONS[treatment],
            "template_id": template["id"],
            "template_version": template["version"],
            "art_window": list(ART_WINDOW),
            "logical_size": list(PIXEL_LOGICAL_SIZE) if treatment == "estate-pixel-v1" else list(ART_WINDOW),
            "palette_limit": PIXEL_PALETTE_COLOURS if treatment == "estate-pixel-v1" else None,
            "palette_colours": palette_colours,
            "dither": False if treatment == "estate-pixel-v1" else None,
            "resampling": "nearest-3x" if treatment == "estate-pixel-v1" else "painterly-framed-crop",
            "art_checksum_sha256": checksum(art_output_path),
            "render_checksum_sha256": checksum(output_path),
        },
    }


def _cards_path(store: WorkspaceStore) -> Path:
    return store.root / "cards" / "cards.json"


def load_cards(store: WorkspaceStore) -> dict[str, Any]:
    return store.read_json(_cards_path(store), {"version": 1, "cards": []})


def _save_cards(store: WorkspaceStore, data: dict[str, Any]) -> None:
    store.atomic_json(_cards_path(store), data)


def _find_run_item(store: WorkspaceStore, run_id: str, item_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    run_dir = store.root / "runs" / run_id
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise ValueError(f"run {run_id} does not exist")
    run = store.read_json(run_path, {})
    item = next((item for item in run.get("items", []) if item.get("item_id") == item_id), None)
    if not item:
        raise ValueError(f"run item {item_id} does not exist")
    if item.get("status") != "complete" or not item.get("output_path"):
        raise ValueError("only a completed run item can become a card")
    source_path = store.absolute_path(item["output_path"])
    if not source_path.is_file():
        raise ValueError(f"run item image is missing: {item['output_path']}")
    return run, {**item, "_source_path": source_path}


def _payload(store: WorkspaceStore, card: dict[str, Any]) -> dict[str, Any]:
    return {
        **card,
        "archetype": card.get("archetype", "bust"),
        "framing": card.get("framing") or {key: framing_preset("bust")[key] for key in ("zoom", "offset_x", "offset_y")},
        "decision": card.get("decision", "working"),
        "treatment": card.get("treatment", "painterly"),
        "treatment_version": card.get("treatment_version", TREATMENT_VERSIONS[card.get("treatment", "painterly")]),
        "render_url": store.asset_url(card.get("render_path")),
        "art_url": store.asset_url(card.get("art_render_path")),
        "source_url": store.asset_url(card.get("source_output_path")),
    }


def create_card_draft(
    store: WorkspaceStore,
    run_id: str,
    item_id: str,
    label: str = "Experimental claimant",
    preset: str = "bust",
    treatment: str = "painterly",
) -> dict[str, Any]:
    store.ensure()
    run, item = _find_run_item(store, run_id, item_id)
    existing = next(
        (
            candidate for candidate in load_cards(store).get("cards", [])
            if candidate.get("run_id") == run_id
            and candidate.get("run_item_id") == item_id
            and candidate.get("decision", "working") in {"working", "keep"}
        ),
        None,
    )
    if existing:
        return _payload(store, existing)
    framing = framing_preset(preset)
    card_id = f"card_{uuid.uuid4().hex[:12]}"
    record = {
        "card_id": card_id,
        "run_id": run_id,
        "run_item_id": item_id,
        "label": label.strip() or "Experimental claimant",
        "template_id": "estate-card-v1",
        "archetype": preset,
        "framing": {key: framing[key] for key in ("zoom", "offset_x", "offset_y")},
        "decision": "working",
        "treatment": treatment,
        "treatment_version": TREATMENT_VERSIONS[treatment],
        "render_path": f"cards/{card_id}.png",
        "art_render_path": f"cards/{card_id}-art.png",
        "source_output_path": item["output_path"],
        "source_dimensions": item.get("dimensions"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "source_run_provenance": {
            "run_id": run_id,
            "run_item_id": item_id,
            "execution_mode": run.get("execution_mode"),
            "model": run.get("model"),
            "recipe_id": run.get("recipe_id"),
            "recipe_name": run.get("recipe_name"),
            "change_note": (run.get("recipe_snapshot") or {}).get("change_note", ""),
            "source_label": item.get("source_label"),
            "source_output_checksum_sha256": checksum(item["_source_path"]),
        },
    }
    rendered = _render_image(
        item["_source_path"], store.absolute_path(record["render_path"]), store.absolute_path(record["art_render_path"]),
        record["label"], record["framing"], load_template(), treatment,
    )
    record["render_dimensions"] = rendered["dimensions"]
    record["transform"] = rendered["transform"]
    record["render_metadata"] = rendered["render_metadata"]
    data = load_cards(store)
    data.setdefault("cards", []).insert(0, record)
    _save_cards(store, data)
    return _payload(store, record)


def _preview_cache_key(card: dict[str, Any], source_path: Path, template: dict[str, Any]) -> str:
    payload = {
        "schema": PREVIEW_SCHEMA_VERSION,
        "source_checksum_sha256": checksum(source_path),
        "template_id": template["id"],
        "template_version": template["version"],
        "frame_presets": FRAME_PRESETS,
        "treatment_versions": TREATMENT_VERSIONS,
        "label": card.get("label", "Experimental claimant"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:20]


def card_previews(store: WorkspaceStore, card_id: str) -> list[dict[str, Any]]:
    """Return the six exact, cached preset/treatment renders for a card draft."""
    data = load_cards(store)
    record = next((item for item in data.get("cards", []) if item.get("card_id") == card_id), None)
    if not record:
        raise ValueError(f"card {card_id} does not exist")
    _, item = _find_run_item(store, str(record["run_id"]), str(record["run_item_id"]))
    template = load_template(str(record.get("template_id") or "estate-card-v1"))
    cache_key = _preview_cache_key(record, item["_source_path"], template)
    cache_relative = Path("cards") / "previews" / card_id
    cache_dir = store.absolute_path(cache_relative)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for stale in cache_dir.iterdir():
        if stale.is_file() and not stale.name.startswith(f"{cache_key}-"):
            stale.unlink()

    previews: list[dict[str, Any]] = []
    for preset in FRAME_PRESETS:
        framing = framing_preset(preset)
        frame = {key: framing[key] for key in ("zoom", "offset_x", "offset_y")}
        for treatment in ("painterly", "estate-pixel-v1"):
            stem = f"{cache_key}-{preset}-{treatment}"
            render_relative = cache_relative / f"{stem}.png"
            art_relative = cache_relative / f"{stem}-art.png"
            metadata_relative = cache_relative / f"{stem}.json"
            render_path = store.absolute_path(render_relative)
            art_path = store.absolute_path(art_relative)
            metadata_path = store.absolute_path(metadata_relative)
            cached = store.read_json(metadata_path, {}) if metadata_path.exists() else {}
            if not render_path.is_file() or not art_path.is_file() or not cached:
                rendered = _render_image(
                    item["_source_path"], render_path, art_path,
                    str(record.get("label") or "Experimental claimant"), frame, template, treatment,
                )
                cached = {
                    "dimensions": rendered["dimensions"],
                    "transform": rendered["transform"],
                    "render_metadata": {
                        **rendered["render_metadata"],
                        "preview_schema_version": PREVIEW_SCHEMA_VERSION,
                        "preview_cache_key": cache_key,
                    },
                }
                store.atomic_json(metadata_path, cached)
            previews.append({
                "option_id": f"{cache_key}:{preset}:{treatment}",
                "preset": preset,
                "preset_label": str(framing["label"]),
                "treatment": treatment,
                "treatment_label": "Estate Pixel" if treatment == "estate-pixel-v1" else "Painterly",
                "framing": frame,
                "render_path": render_relative.as_posix(),
                "render_url": store.asset_url(render_relative),
                "art_render_path": art_relative.as_posix(),
                "art_url": store.asset_url(art_relative),
                "render_dimensions": cached["dimensions"],
                "render_metadata": cached["render_metadata"],
            })
    return previews


def _copy_preview(store: WorkspaceStore, source_relative: str, destination_relative: str) -> None:
    source = store.absolute_path(source_relative)
    destination = store.absolute_path(destination_relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    shutil.copy2(source, temporary)
    temporary.replace(destination)


def update_card_draft(store: WorkspaceStore, card_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    data = load_cards(store)
    record = next((item for item in data.get("cards", []) if item.get("card_id") == card_id), None)
    if not record:
        raise ValueError(f"card {card_id} does not exist")
    if patch.get("preview_id"):
        preview = next((item for item in card_previews(store, card_id) if item["option_id"] == patch["preview_id"]), None)
        if not preview:
            raise ValueError("preview_id is stale or unknown; reload the frame previews")
        decision = str(patch.get("decision", record.get("decision", "working")))
        if decision not in {"working", "keep", "discard"}:
            raise ValueError("decision must be working, keep, or discard")
        _copy_preview(store, preview["render_path"], str(record["render_path"]))
        art_render_path = str(record.get("art_render_path") or f"cards/{card_id}-art.png")
        _copy_preview(store, preview["art_render_path"], art_render_path)
        updated = {
            **record,
            "archetype": preview["preset"],
            "framing": preview["framing"],
            "treatment": preview["treatment"],
            "treatment_version": TREATMENT_VERSIONS[preview["treatment"]],
            "decision": decision,
            "art_render_path": art_render_path,
            "selected_preview_id": preview["option_id"],
            "updated_at": now_iso(),
            "render_dimensions": preview["render_dimensions"],
            "transform": calculate_cover_transform(
                record.get("source_dimensions") or [336, 276], ART_WINDOW, **preview["framing"]
            ),
            "render_metadata": preview["render_metadata"],
        }
        data["cards"] = [updated if item.get("card_id") == card_id else item for item in data.get("cards", [])]
        _save_cards(store, data)
        return _payload(store, updated)
    run, item = _find_run_item(store, str(record["run_id"]), str(record["run_item_id"]))
    framing = dict(record.get("framing") or {})
    incoming = patch.get("framing") or {}
    for key in ("zoom", "offset_x", "offset_y"):
        if key in incoming:
            framing[key] = float(incoming[key])
    framing["zoom"] = max(1.0, min(framing.get("zoom", 1.0), 3.0))
    label = str(patch.get("label", record.get("label")) or "Experimental claimant").strip()[:80]
    decision = str(patch.get("decision", record.get("decision", "working")))
    if decision not in {"working", "keep", "discard"}:
        raise ValueError("decision must be working, keep, or discard")
    treatment = str(patch.get("treatment", record.get("treatment", "painterly")))
    if treatment not in TREATMENTS:
        raise ValueError("treatment must be painterly or estate-pixel-v1")
    art_render_path = str(record.get("art_render_path") or f"cards/{card_id}-art.png")
    rendered = _render_image(
        item["_source_path"], store.absolute_path(record["render_path"]), store.absolute_path(art_render_path),
        label, framing, load_template(), treatment,
    )
    updated = {
        **record, "label": label, "framing": framing, "decision": decision,
        "archetype": patch.get("archetype", record.get("archetype", "bust")),
        "treatment": treatment,
        "treatment_version": TREATMENT_VERSIONS[treatment],
        "art_render_path": art_render_path,
        "updated_at": now_iso(), "render_dimensions": rendered["dimensions"],
        "transform": rendered["transform"], "render_metadata": rendered["render_metadata"],
    }
    data["cards"] = [updated if item.get("card_id") == card_id else item for item in data.get("cards", [])]
    _save_cards(store, data)
    return _payload(store, updated)


def list_card_drafts(store: WorkspaceStore, include_discarded: bool = False) -> list[dict[str, Any]]:
    cards = load_cards(store).get("cards", [])
    if not include_discarded:
        cards = [item for item in cards if item.get("decision") != "discard"]
    return [_payload(store, item) for item in cards]


def card_detail(store: WorkspaceStore, card_id: str) -> dict[str, Any]:
    card = next((item for item in load_cards(store).get("cards", []) if item.get("card_id") == card_id), None)
    if not card:
        raise ValueError(f"card {card_id} does not exist")
    return _payload(store, card)


def list_templates() -> list[dict[str, Any]]:
    template = load_template()
    return [{"id": template["id"], "version": template["version"], "art_window": template["art_window"], "frame_presets": FRAME_PRESETS}]
