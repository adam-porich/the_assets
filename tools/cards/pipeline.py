from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps


CARD_TEMPLATE_DIR = Path(__file__).parent / "templates"
STYLE_DIR = Path(__file__).parent.parent / "portraits" / "styles"
MASTER_MANIFEST = "masters.json"
CARD_MANIFEST = "cards.json"
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


def promote_master(
    library_dir: Path,
    photo_id: str,
    candidate_id: str,
    master_id: str,
    style_id: str = "estate-card-v1",
    note: str = "",
) -> dict[str, Any]:
    _safe_id(master_id, "master_id")
    style = load_style(style_id)
    masters = load_masters(library_dir)
    if any(item.get("master_id") == master_id for item in masters.get("masters", [])):
        raise ValueError(f"portrait master already exists: {master_id}")
    source, candidate = _find_candidate(library_dir, photo_id, candidate_id)
    candidate_path = candidate.get("final_output_path") or candidate.get("output_path")
    if not candidate_path:
        raise ValueError(f"candidate has no image output: {candidate_id}")
    source_path = library_dir / str(candidate_path)
    if not source_path.is_file():
        raise ValueError(f"candidate image is missing: {candidate_path}")

    masters_dir = library_dir / "masters"
    masters_dir.mkdir(parents=True, exist_ok=True)
    master_path = masters_dir / f"{master_id}.png"
    ImageOps.exif_transpose(Image.open(source_path)).convert("RGB").save(master_path)
    master = {
        "master_id": master_id,
        "source_photo_id": int(photo_id),
        "candidate_id": candidate_id,
        "style_id": style["id"],
        "style_version": style["version"],
        "master_path": str(master_path.relative_to(library_dir)),
        "candidate_output_path": str(candidate_path),
        "composition": default_composition(),
        "note": note,
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
        face = composition.get("face_anchor")
        if not isinstance(face, list) or len(face) != 2 or not all(isinstance(value, (int, float)) and 0 <= value <= 1 for value in face):
            raise ValueError("composition.face_anchor must be two normalized coordinates")
        archetype = composition.get("preferred_archetype", "standard-bust")
        if archetype not in {"standard-bust", "tall-silhouette", "wide-torso"}:
            raise ValueError("unknown preferred portrait archetype")
        master["composition"] = {**default_composition(), **composition}
        master["updated_at"] = now_iso()
        save_masters(library_dir, masters)
        return master
    raise ValueError(f"unknown portrait master: {master_id}")


def _fit_master(master_image: Image.Image, composition: dict[str, Any], window: tuple[int, int], face_y_bias: float) -> Image.Image:
    face_x, face_y = composition.get("face_anchor", [0.5, 0.35])
    centering = (max(0.0, min(1.0, float(face_x))), max(0.0, min(1.0, float(face_y) + face_y_bias)))
    return ImageOps.fit(master_image.convert("RGB"), window, method=Image.Resampling.LANCZOS, centering=centering)


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
    art = _fit_master(Image.open(master_path), composition, (right - left, bottom - top), float(archetype.get("face_y_bias", 0)))
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
        "created_at": now_iso(),
    }
    cards_by_id = {item.get("card_id"): item for item in cards.get("cards", [])}
    cards_by_id[card_id] = record
    cards["cards"] = sorted(cards_by_id.values(), key=lambda item: item["card_id"])
    save_cards(library_dir, cards)
    return record


def card_payloads(library_dir: Path, review: dict[str, Any]) -> list[dict[str, Any]]:
    masters = {item.get("master_id"): item for item in load_masters(library_dir).get("masters", [])}
    payloads = []
    for card in load_cards(library_dir).get("cards", []):
        master = masters.get(card.get("master_id"), {})
        payloads.append({
            **card,
            "review": review.get("cards", {}).get(str(card.get("card_id")), {}),
            "card_url": "asset/" + str(card.get("output_path", "")),
            "master_url": "asset/" + str(master.get("master_path", "")),
            "composition": master.get("composition"),
        })
    return payloads


def master_payloads(library_dir: Path) -> list[dict[str, Any]]:
    cards_by_master: dict[str, list[dict[str, Any]]] = {}
    for card in load_cards(library_dir).get("cards", []):
        cards_by_master.setdefault(str(card.get("master_id")), []).append(card)
    payloads = []
    for master in load_masters(library_dir).get("masters", []):
        payloads.append({
            **master,
            "master_url": "asset/" + str(master.get("master_path", "")),
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
