from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps
from tools.portraits.imaging import quantize_image


CARD_TEMPLATE_DIR = Path(__file__).parent / "templates"
STYLE_DIR = Path(__file__).parent.parent / "portraits" / "styles"
MASTER_MANIFEST = "masters.json"
CARD_MANIFEST = "cards.json"
SET_INDEX = "sets.json"
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_id(value: str, field: str) -> str:
    if not _SAFE_ID.match(value):
        raise ValueError(f"{field} must contain only lowercase letters, digits, '.', '_' or '-'")
    return value


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_masters(library_dir: Path) -> dict[str, Any]:
    return _read_json(library_dir / MASTER_MANIFEST, {"version": 1, "masters": []})


def save_masters(library_dir: Path, data: dict[str, Any]) -> None:
    _write_json(library_dir / MASTER_MANIFEST, data)


def load_cards(library_dir: Path) -> dict[str, Any]:
    return _read_json(library_dir / CARD_MANIFEST, {"version": 1, "cards": []})


def save_cards(library_dir: Path, data: dict[str, Any]) -> None:
    _write_json(library_dir / CARD_MANIFEST, data)


def load_sets(library_dir: Path) -> dict[str, Any]:
    return _read_json(library_dir / SET_INDEX, {"version": 1, "sets": []})


def save_sets(library_dir: Path, data: dict[str, Any]) -> None:
    _write_json(library_dir / SET_INDEX, data)


def load_template(template_id: str) -> dict[str, Any]:
    _safe_id(template_id, "template_id")
    path = CARD_TEMPLATE_DIR / f"{template_id}.json"
    if not path.exists():
        raise ValueError(f"unknown card template: {template_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_style(style_id: str) -> dict[str, Any]:
    _safe_id(style_id, "style_id")
    path = STYLE_DIR / f"{style_id}.json"
    if not path.exists():
        raise ValueError(f"unknown house style: {style_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def find_master(library_dir: Path, master_id: str) -> dict[str, Any]:
    for master in load_masters(library_dir).get("masters", []):
        if master.get("master_id") == master_id:
            return master
    raise ValueError(f"unknown portrait master: {master_id}")


def _find_candidate(library_dir: Path, photo_id: str, candidate_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _read_json(library_dir / "manifest.json", {"sources": []})
    for source in manifest.get("sources", []):
        if str(source.get("pexels_photo_id")) != str(photo_id):
            continue
        for candidate in source.get("stylized_candidates", []):
            if str(candidate.get("candidate_id")) == candidate_id:
                return source, candidate
    raise ValueError(f"unknown candidate {candidate_id} for source {photo_id}")


def default_composition() -> dict[str, Any]:
    return {
        "face_anchor": [0.5, 0.35],
        "head_box": [0.28, 0.12, 0.72, 0.54],
        "shoulder_line": 0.65,
        "silhouette_box": [0.12, 0.08, 0.88, 0.96],
        "preferred_archetype": "standard-bust",
    }


def candidate_source_options(candidate: dict[str, Any]) -> dict[str, str]:
    options = {
        "raw": str(candidate.get("output_path") or ""),
        "final": str(candidate.get("final_output_path") or ""),
    }
    return {kind: path for kind, path in options.items() if path}


def _prepare_master_image(source_path: Path, style: dict[str, Any], source_kind: str) -> Image.Image:
    image = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
    if source_kind == "final":
        return image
    processing = style.get("master_processing") or {}
    max_edge = int(processing.get("max_edge", 768))
    if max(image.size) > max_edge:
        scale = max_edge / max(image.size)
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    if source_kind == "clean":
        image = quantize_image(image, int(processing.get("palette_colors", 32)), False, None)
    return image


def promote_master(
    library_dir: Path,
    photo_id: str,
    candidate_id: str,
    master_id: str,
    style_id: str = "estate-card-v1",
    note: str = "",
    source_kind: str = "raw",
    rejection_reason: str = "",
) -> dict[str, Any]:
    _safe_id(master_id, "master_id")
    if source_kind not in {"raw", "clean", "final"}:
        raise ValueError("master source kind must be raw, clean, or final")
    style = load_style(style_id)
    masters = load_masters(library_dir)
    if any(item.get("master_id") == master_id for item in masters.get("masters", [])):
        raise ValueError(f"portrait master already exists: {master_id}")
    source, candidate = _find_candidate(library_dir, photo_id, candidate_id)
    source_options = candidate_source_options(candidate)
    if source_kind == "clean":
        source_kind = "clean" if "raw" in source_options else "final"
    requested_source_kind = source_kind
    selected_kind = "raw" if source_kind == "clean" else source_kind
    candidate_path = source_options.get(selected_kind)
    if not candidate_path and selected_kind == "raw" and "final" in source_options:
        selected_kind = "final"
        source_kind = "final"
        candidate_path = source_options[selected_kind]
    if not candidate_path:
        choices = ", ".join(sorted(source_options)) or "none"
        raise ValueError(f"candidate has no {source_kind} image output (available: {choices})")
    source_path = library_dir / str(candidate_path)
    if not source_path.is_file():
        raise ValueError(f"candidate image is missing: {candidate_path}")

    masters_dir = library_dir / "masters"
    masters_dir.mkdir(parents=True, exist_ok=True)
    master_path = masters_dir / f"{master_id}.png"
    master_image = _prepare_master_image(source_path, style, source_kind)
    master_image.save(master_path)
    master = {
        "master_id": master_id,
        "source_photo_id": int(photo_id),
        "candidate_id": candidate_id,
        "style_id": style["id"],
        "style_version": style["version"],
        "master_path": str(master_path.relative_to(library_dir)),
        "candidate_output_path": str(candidate_path),
        "master_source_kind": source_kind,
        "master_source_requested_kind": requested_source_kind,
        "master_source_options": source_options,
        "source_original_size": list(Image.open(source_path).size),
        "master_size": list(master_image.size),
        "source_crop_bounds": [0.0, 0.0, 1.0, 1.0],
        "composition": default_composition(),
        "note": note,
        "rejection_reason": rejection_reason,
        "created_at": now_iso(),
    }
    masters.setdefault("masters", []).append(master)
    save_masters(library_dir, masters)
    return master


def update_master_composition(library_dir: Path, master_id: str, composition: dict[str, Any]) -> dict[str, Any]:
    masters = load_masters(library_dir)
    for master in masters.get("masters", []):
        if master.get("master_id") != master_id:
            continue
        resolved_composition = {**default_composition(), **(master.get("composition") or {}), **composition}
        for key, expected_length in (("face_anchor", 2), ("head_box", 4), ("silhouette_box", 4)):
            value = resolved_composition.get(key)
            if not isinstance(value, list) or len(value) != expected_length or not all(isinstance(item, (int, float)) and 0 <= item <= 1 for item in value):
                raise ValueError(f"composition.{key} must contain {expected_length} normalized coordinates")
        head_box = resolved_composition["head_box"]
        silhouette_box = resolved_composition["silhouette_box"]
        if head_box[0] >= head_box[2] or head_box[1] >= head_box[3] or silhouette_box[0] >= silhouette_box[2] or silhouette_box[1] >= silhouette_box[3]:
            raise ValueError("composition boxes must have positive area")
        shoulder_line = resolved_composition.get("shoulder_line")
        if not isinstance(shoulder_line, (int, float)) or not 0 <= shoulder_line <= 1:
            raise ValueError("composition.shoulder_line must be normalized")
        archetype = resolved_composition.get("preferred_archetype", "standard-bust")
        if archetype not in {"standard-bust", "tall-silhouette", "wide-torso"}:
            raise ValueError("unknown preferred portrait archetype")
        master["composition"] = resolved_composition
        master["updated_at"] = now_iso()
        save_masters(library_dir, masters)
        return master
    raise ValueError(f"unknown portrait master: {master_id}")


def crop_transform(master_image: Image.Image, composition: dict[str, Any], window: tuple[int, int], archetype: dict[str, Any]) -> dict[str, Any]:
    """Calculate a deterministic composition crop without discarding master pixels."""
    image_width, image_height = master_image.size
    face_x, face_y = composition["face_anchor"]
    silhouette = composition["silhouette_box"]
    target_x, target_y = archetype.get("face_target", [0.5, 0.4])
    window_aspect = window[0] / window[1]
    scale = float(archetype.get("crop_scale", 1.0))
    desired_width = min(image_width, image_height * window_aspect) * scale
    desired_height = desired_width / window_aspect
    subject_height = max(1.0, (silhouette[3] - silhouette[1]) * image_height)
    occupancy = sum(archetype.get("safe_silhouette_occupancy", [0.5, 0.9])) / 2
    desired_height = min(desired_height, image_height, subject_height / occupancy)
    desired_width = min(desired_height * window_aspect, image_width)
    desired_height = desired_width / window_aspect
    left = (face_x * image_width) - (target_x * desired_width)
    top = (face_y * image_height) - (target_y * desired_height)
    left = max(0.0, min(left, image_width - desired_width))
    top = max(0.0, min(top, image_height - desired_height))
    return {
        "source_box": [round(left, 3), round(top, 3), round(left + desired_width, 3), round(top + desired_height, 3)],
        "source_box_normalized": [round(left / image_width, 6), round(top / image_height, 6), round((left + desired_width) / image_width, 6), round((top + desired_height) / image_height, 6)],
        "face_target": [target_x, target_y],
    }


def crop_master(master_image: Image.Image, transform: dict[str, Any], window: tuple[int, int]) -> Image.Image:
    left, top, right, bottom = transform["source_box"]
    crop = master_image.crop((round(left), round(top), round(right), round(bottom)))
    return crop.resize(window, Image.Resampling.LANCZOS)


def render_card(
    library_dir: Path,
    master_id: str,
    template_id: str = "estate-card-v1",
    archetype_id: str | None = None,
    label: str = "Experimental claimant",
) -> dict[str, Any]:
    master = find_master(library_dir, master_id)
    template = load_template(template_id)
    composition = master.get("composition") or default_composition()
    archetype_id = archetype_id or composition.get("preferred_archetype", "standard-bust")
    archetype = (template.get("archetypes") or {}).get(archetype_id)
    if not archetype:
        raise ValueError(f"template {template_id} has no archetype {archetype_id}")
    master_path = library_dir / str(master["master_path"])
    if not master_path.is_file():
        raise ValueError(f"master image is missing: {master['master_path']}")

    width, height = int(template["width"]), int(template["height"])
    left, top, right, bottom = [int(value) for value in template["art_window"]]
    colors = template["colors"]
    canvas = Image.new("RGB", (width, height), colors["card"])
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((10, 10, width - 11, height - 11), fill=colors["inner"], outline=colors["border"], width=5)
    draw.rectangle((left - 7, top - 7, right + 7, bottom + 7), fill=colors["art_matte"], outline=colors["border"], width=3)
    master_image = Image.open(master_path)
    transform = crop_transform(master_image, composition, (right - left, bottom - top), archetype)
    art = crop_master(master_image, transform, (right - left, bottom - top))
    canvas.paste(art, (left, top))
    draw.rectangle((left - 1, top - 1, right, bottom), outline=colors["border"], width=2)
    draw.rectangle((32, 382, width - 33, 426), fill=colors["card"], outline=colors["border"], width=2)
    draw.rectangle((32, 442, width - 33, 548), fill=colors["card"], outline=colors["border"], width=2)
    draw.text((44, 396), label[:40], fill=colors["title"])
    draw.text((44, 458), f"{archetype.get('label', archetype_id)} · {master['style_id']} v{master['style_version']}", fill=colors["label"])
    draw.text((44, 482), "Experimental card-context preview", fill=colors["label"])

    card_id = f"{master_id}--{template_id}--{archetype_id}"
    cards_dir = library_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    output_path = cards_dir / f"{card_id}.png"
    canvas.save(output_path)
    cards = load_cards(library_dir)
    record = {
        "card_id": card_id,
        "master_id": master_id,
        "style_id": master["style_id"],
        "style_version": master["style_version"],
        "template_id": template["id"],
        "template_version": template["version"],
        "archetype_id": archetype_id,
        "label": label,
        "output_path": str(output_path.relative_to(library_dir)),
        "crop_transform": transform,
        "created_at": now_iso(),
    }
    cards_by_id = {item.get("card_id"): item for item in cards.get("cards", [])}
    cards_by_id[card_id] = record
    cards["cards"] = sorted(cards_by_id.values(), key=lambda item: item["card_id"])
    save_cards(library_dir, cards)
    return record


def card_payloads(library_dir: Path, review: dict[str, Any]) -> list[dict[str, Any]]:
    masters = {item.get("master_id"): item for item in load_masters(library_dir).get("masters", [])}
    sources = {str(item.get("pexels_photo_id")): item for item in _read_json(library_dir / "manifest.json", {"sources": []}).get("sources", [])}
    payloads = []
    for card in load_cards(library_dir).get("cards", []):
        master = masters.get(card.get("master_id"), {})
        source = sources.get(str(master.get("source_photo_id")), {})
        candidate = next((item for item in source.get("stylized_candidates", []) if item.get("candidate_id") == master.get("candidate_id")), {})
        payloads.append({
            **card,
            "review": review.get("cards", {}).get(str(card.get("card_id")), {}),
            "card_url": "asset/" + str(card.get("output_path", "")),
            "master_url": "asset/" + str(master.get("master_path", "")),
            "composition": master.get("composition"),
            "master_review": review.get("masters", {}).get(str(master.get("master_id")), {}),
            "candidate_id": master.get("candidate_id"),
            "candidate_url": ("asset/" + str(candidate.get("final_output_path") or candidate.get("output_path"))) if (candidate.get("final_output_path") or candidate.get("output_path")) else None,
            "source_url": ("asset/sources/" + str(source.get("local_source_filename"))) if source.get("local_source_filename") else None,
        })
    return payloads


def master_payloads(library_dir: Path, review: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    review = review or {}
    cards_by_master: dict[str, list[dict[str, Any]]] = {}
    for card in load_cards(library_dir).get("cards", []):
        cards_by_master.setdefault(str(card.get("master_id")), []).append(card)
    payloads = []
    for master in load_masters(library_dir).get("masters", []):
        payloads.append({
            **master,
            "master_url": "asset/" + str(master.get("master_path", "")),
            "review": review.get("masters", {}).get(str(master.get("master_id")), {}),
            "renders": sorted(cards_by_master.get(str(master.get("master_id")), []), key=lambda card: str(card.get("card_id"))),
        })
    return payloads


def list_templates() -> list[dict[str, Any]]:
    templates = []
    for path in sorted(CARD_TEMPLATE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        templates.append({
            "id": data["id"],
            "version": data["version"],
            "width": data["width"],
            "height": data["height"],
            "archetypes": data.get("archetypes", {}),
        })
    return templates


def _approved_card_ids(library_dir: Path, review: dict[str, Any]) -> set[str]:
    masters = {item.get("master_id"): item for item in load_masters(library_dir).get("masters", [])}
    approved = set()
    for card in load_cards(library_dir).get("cards", []):
        card_id = str(card.get("card_id"))
        master_id = str(card.get("master_id"))
        if review.get("cards", {}).get(card_id, {}).get("status") == "approved" and review.get("masters", {}).get(master_id, {}).get("status") == "approved" and master_id in masters:
            approved.add(card_id)
    return approved


def _contact_sheet(library_dir: Path, set_id: str, cards: list[dict[str, Any]]) -> str:
    thumb_width, thumb_height, columns, gap = 168, 240, 4, 12
    rows = max(1, (len(cards) + columns - 1) // columns)
    sheet = Image.new("RGB", (columns * thumb_width + (columns + 1) * gap, rows * thumb_height + (rows + 1) * gap), "#201916")
    for index, card in enumerate(sorted(cards, key=lambda item: str(item["card_id"]))):
        image = Image.open(library_dir / str(card["output_path"])).convert("RGB")
        image.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        x = gap + (index % columns) * (thumb_width + gap)
        y = gap + (index // columns) * (thumb_height + gap)
        sheet.paste(image, (x + (thumb_width - image.width) // 2, y + (thumb_height - image.height) // 2))
    output = library_dir / "sets" / f"{set_id}-contact-sheet.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return str(output.relative_to(library_dir))


def create_set(library_dir: Path, review: dict[str, Any], set_id: str, label: str, card_ids: list[str]) -> dict[str, Any]:
    _safe_id(set_id, "set_id")
    if not card_ids:
        raise ValueError("a set needs at least one approved card")
    sets = load_sets(library_dir)
    if any(item.get("set_id") == set_id for item in sets.get("sets", [])):
        raise ValueError(f"set already exists: {set_id}")
    approved = _approved_card_ids(library_dir, review)
    requested = set(card_ids)
    unapproved = sorted(requested - approved)
    if unapproved:
        raise ValueError(f"only approved card renders with approved masters can enter a set: {', '.join(unapproved)}")
    cards = [card for card in load_cards(library_dir).get("cards", []) if card.get("card_id") in requested]
    record = {
        "set_id": set_id,
        "label": label or set_id,
        "version": 1,
        "card_ids": sorted(requested),
        "contact_sheet_path": _contact_sheet(library_dir, set_id, cards),
        "created_at": now_iso(),
    }
    _write_json(library_dir / "sets" / f"{set_id}.json", record)
    sets.setdefault("sets", []).append(record)
    save_sets(library_dir, sets)
    return record


def set_payloads(library_dir: Path) -> list[dict[str, Any]]:
    return [{**record, "contact_sheet_url": "asset/" + str(record.get("contact_sheet_path", ""))} for record in load_sets(library_dir).get("sets", [])]


def validate_cards(library_dir: Path, card_ids: list[str] | None = None) -> dict[str, Any]:
    """Return explainable integrity and composition warnings for a small card batch."""
    all_cards = load_cards(library_dir).get("cards", [])
    selected = [card for card in all_cards if card_ids is None or card.get("card_id") in set(card_ids)]
    masters = {item.get("master_id"): item for item in load_masters(library_dir).get("masters", [])}
    issues: list[dict[str, str]] = []
    if not selected:
        issues.append({"level": "error", "message": "No card renders selected."})
    styles = {(card.get("style_id"), card.get("style_version")) for card in selected}
    templates = {(card.get("template_id"), card.get("template_version")) for card in selected}
    if len(styles) > 1:
        issues.append({"level": "warning", "message": "Batch contains more than one house-style version."})
    if len(templates) > 1:
        issues.append({"level": "warning", "message": "Batch contains more than one card-template version."})
    for card in selected:
        card_id = str(card.get("card_id", "unknown"))
        output_path = library_dir / str(card.get("output_path", ""))
        master = masters.get(card.get("master_id"))
        if not output_path.is_file():
            issues.append({"level": "error", "card_id": card_id, "message": "Rendered card image is missing."})
            continue
        try:
            template = load_template(str(card.get("template_id")))
            if Image.open(output_path).size != (int(template["width"]), int(template["height"])):
                issues.append({"level": "error", "card_id": card_id, "message": "Rendered card dimensions do not match its template."})
        except ValueError as exc:
            issues.append({"level": "error", "card_id": card_id, "message": str(exc)})
        if not master:
            issues.append({"level": "error", "card_id": card_id, "message": "Referenced portrait master is missing."})
            continue
        composition = master.get("composition") or {}
        face = composition.get("face_anchor")
        if not isinstance(face, list) or len(face) != 2:
            issues.append({"level": "warning", "card_id": card_id, "message": "Master has no approved face anchor."})
        elif not (0.1 <= float(face[0]) <= 0.9 and 0.08 <= float(face[1]) <= 0.7):
            issues.append({"level": "warning", "card_id": card_id, "message": "Face anchor is outside the initial safe review range."})
        archetype = template.get("archetypes", {}).get(card.get("archetype_id"), {})
        transform = card.get("crop_transform") or {}
        crop = transform.get("source_box_normalized")
        if isinstance(crop, list) and len(crop) == 4 and isinstance(face, list) and len(face) == 2:
            face_in_card = [(float(face[0]) - crop[0]) / (crop[2] - crop[0]), (float(face[1]) - crop[1]) / (crop[3] - crop[1])]
            for index, key in enumerate(("safe_face_x", "safe_face_y")):
                bounds = archetype.get(key)
                if bounds and not float(bounds[0]) <= face_in_card[index] <= float(bounds[1]):
                    issues.append({"level": "warning", "card_id": card_id, "message": f"Face {('x', 'y')[index]} is outside the {card.get('archetype_id')} safe range."})
            silhouette = composition.get("silhouette_box") or []
            if len(silhouette) == 4:
                occupancy = (float(silhouette[3]) - float(silhouette[1])) / (crop[3] - crop[1])
                bounds = archetype.get("safe_silhouette_occupancy")
                if bounds and not float(bounds[0]) <= occupancy <= float(bounds[1]):
                    issues.append({"level": "warning", "card_id": card_id, "message": f"Silhouette occupancy is outside the {card.get('archetype_id')} safe range."})
    return {
        "version": 1,
        "validated_at": now_iso(),
        "card_count": len(selected),
        "styles": sorted(f"{style}@{version}" for style, version in styles),
        "templates": sorted(f"{template}@{version}" for template, version in templates),
        "issues": issues,
        "ok": not any(issue["level"] == "error" for issue in issues),
    }


def write_validation_report(library_dir: Path, card_ids: list[str] | None = None) -> dict[str, Any]:
    report = validate_cards(library_dir, card_ids)
    _write_json(library_dir / "cards" / "validation.json", report)
    return report


def validate_set(library_dir: Path, set_id: str) -> dict[str, Any]:
    record = next((item for item in load_sets(library_dir).get("sets", []) if item.get("set_id") == set_id), None)
    if not record:
        raise ValueError(f"unknown set: {set_id}")
    report = validate_cards(library_dir, list(record.get("card_ids") or []))
    report["set_id"] = set_id
    _write_json(library_dir / "sets" / f"{set_id}-validation.json", report)
    return report
