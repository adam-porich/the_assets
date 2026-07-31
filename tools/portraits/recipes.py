from __future__ import annotations

from typing import Any


RECIPE_FIELDS = (
    "medium_brushwork",
    "lighting",
    "background",
    "composition",
    "colour",
    "detail",
    "identity",
)

STARTER_RECIPE: dict[str, Any] = {
    "name": "Estate painterly study 01",
    "model": "openai/gpt-image-1-mini",
    "execution_mode": "live",
    "quality": "low",
    "change_note": "",
    "direction": {
        "medium_brushwork": "Opaque gouache and oil-brush modelling with visible, confident strokes and softened edges.",
        "lighting": "Quiet single-source light from upper left, with warm skin planes and cool reflected shadow.",
        "background": "A restrained atmospheric field of muted stone, paper, and dusk tones; no scenery competing with the subject.",
        "composition": "A centred head-and-shoulders portrait with breathing room around the silhouette, composed for a wide card art window.",
        "colour": "A limited estate palette of umber, ochre, dusty rose, slate blue, and parchment highlights.",
        "detail": "Resolve the eyes, hairline, collar, and distinctive clothing shapes; let peripheral texture dissolve into brushwork.",
        "identity": "Retain the source person's apparent age, facial structure, expression, hair shape, and recognizable proportions.",
    },
    "avoid": "Avoid typography, logos, watermarks, extra faces, plastic skin, photorealistic studio lighting, and decorative frames.",
    "aspect_policy": "card-window",
    "reference_ids": [],
}


def resolve_recipe_instruction(recipe: dict[str, Any]) -> str:
    direction = recipe.get("direction") or {}
    lines = []
    if str(recipe.get("change_note") or "").strip():
        lines.append(f"Requested change: {str(recipe['change_note']).strip()}")
    lines.extend(f"{label.replace('_', ' ').title()}: {direction.get(label, '').strip()}" for label in RECIPE_FIELDS if direction.get(label))
    if recipe.get("avoid"):
        lines.append(f"Avoid: {str(recipe['avoid']).strip()}")
    return "\n".join(lines)


def recipe_from_payload(payload: dict[str, Any], recipe_id: str, now: str) -> dict[str, Any]:
    direction = {field: str((payload.get("direction") or {}).get(field, "")).strip() for field in RECIPE_FIELDS}
    if not str(payload.get("name") or "").strip():
        raise ValueError("recipe name is required")
    if not str(payload.get("model") or "").strip():
        raise ValueError("recipe model is required")
    if payload.get("quality") not in {"low", "medium", "high"}:
        raise ValueError("quality must be low, medium, or high")
    execution_mode = str(payload.get("execution_mode") or "live")
    if execution_mode not in {"live", "simulation"}:
        raise ValueError("execution_mode must be live or simulation")
    return {
        "id": recipe_id,
        "name": str(payload["name"]).strip(),
        "model": str(payload["model"]).strip(),
        "execution_mode": execution_mode,
        "quality": payload["quality"],
        "change_note": str(payload.get("change_note") or "").strip(),
        "direction": direction,
        "avoid": str(payload.get("avoid") or "").strip(),
        "aspect_policy": "card-window",
        "reference_ids": [str(item) for item in payload.get("reference_ids", [])],
        "created_at": payload.get("created_at") or now,
        "updated_at": now,
    }
