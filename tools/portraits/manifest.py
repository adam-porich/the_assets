from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LICENSE_PAGE = "https://www.pexels.com/license/"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_manifest(library_dir: Path) -> dict[str, Any]:
    path = library_dir / "manifest.json"
    if not path.exists():
        return {"version": 1, "sources": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(library_dir: Path, manifest: dict[str, Any]) -> None:
    library_dir.mkdir(parents=True, exist_ok=True)
    path = library_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def source_id(photo_id: int | str) -> str:
    return f"pexels-{photo_id}"


def deterministic_source_filename(photo_id: int | str, suffix: str = ".jpg") -> str:
    return f"{source_id(photo_id)}-original{suffix}"


def deterministic_crop_filename(photo_id: int | str) -> str:
    return f"{source_id(photo_id)}-crop.png"


def deterministic_candidate_filename(photo_id: int | str, variant: str, size: int) -> str:
    return f"{source_id(photo_id)}-{variant}-{size}.png"


def deterministic_background_filename(photo_id: int | str, mode: str, kind: str, suffix: str = ".png") -> str:
    return f"{source_id(photo_id)}-{mode}-{kind}{suffix}"


def deterministic_background_candidate_filename(photo_id: int | str, mode: str, variant: str, size: int) -> str:
    return f"{source_id(photo_id)}-{mode}-{variant}-{size}.png"


def find_source(manifest: dict[str, Any], photo_id: int | str) -> dict[str, Any] | None:
    wanted = int(photo_id)
    for entry in manifest.get("sources", []):
        if int(entry.get("pexels_photo_id")) == wanted:
            return entry
    return None


def upsert_source(manifest: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    existing = find_source(manifest, entry["pexels_photo_id"])
    if existing is None:
        manifest.setdefault("sources", []).append(entry)
        return entry
    existing.update(entry)
    return existing


def update_selection(
    manifest: dict[str, Any],
    photo_id: int | str,
    variant: str,
    tags: list[str],
) -> dict[str, Any]:
    entry = find_source(manifest, photo_id)
    if entry is None:
        raise ValueError(f"No source with Pexels photo id {photo_id}")
    selected = entry.setdefault("selected", {})
    selected["variant"] = variant
    selected["tags"] = sorted(set(selected.get("tags", []) + tags))
    selected["selected_at"] = utc_now_iso()
    return entry


def update_review_status(
    manifest: dict[str, Any],
    photo_id: int | str,
    status: str | None,
    note: str = "",
) -> dict[str, Any]:
    entry = find_source(manifest, photo_id)
    if entry is None:
        raise ValueError(f"No source with Pexels photo id {photo_id}")
    if status is None or status == "clear":
        entry.pop("review", None)
        return entry
    if status not in {"favorite", "reject", "add"}:
        raise ValueError(f"Unknown review status: {status}")
    entry["review"] = {
        "status": status,
        "note": note,
        "updated_at": utc_now_iso(),
    }
    return entry


@dataclass(frozen=True)
class CandidateSettings:
    size: int = 64
    review_scale: int = 4
    contrast: float = 1.08
    saturation: float = 0.95
    sharpness: float = 1.05
    crop_padding: float = 1.9
    background: str = "keep"
    palette: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "review_scale": self.review_scale,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "sharpness": self.sharpness,
            "crop_padding": self.crop_padding,
            "background": self.background,
            "palette": self.palette,
        }


@dataclass(frozen=True)
class VariantConfig:
    name: str
    colors: int
    dither: bool = False
    edge: bool = False
    pre_blur: float = 0.0


DEFAULT_VARIANTS = {
    "clean16": VariantConfig("clean16", 16),
    "clean24": VariantConfig("clean24", 24),
    "dither24": VariantConfig("dither24", 24, dither=True),
    "edge24": VariantConfig("edge24", 24, edge=True, pre_blur=0.35),
}


@dataclass
class ProcessResult:
    crop: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    face_box: list[int] | None = None


@dataclass
class BackgroundResult:
    mode: str
    elapsed_seconds: float
    crop: str
    mask: str | None = None
    transparent_foreground: str | None = None
    neutral_background: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
