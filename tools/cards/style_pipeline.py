from __future__ import annotations

import copy
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from tools.portraits.workspace import WorkspaceError, WorkspaceStore, checksum, now_iso


STYLE_DEFINITION_PATH = Path(__file__).parent / "styles" / "amiga-ocs-portrait-v1.json"
ASSET_ROOT = Path(__file__).parent / "assets" / "amiga-ocs-portrait-v1"
STYLE_FAMILY_ID = "amiga-ocs-portrait"
FACE_FREE_PIPELINE_ID = "face-free-style-board"
PORTRAIT_REFERENCE_PIPELINE_ID = "portrait-style-reference"
PIPELINE_IDS = {FACE_FREE_PIPELINE_ID, PORTRAIT_REFERENCE_PIPELINE_ID}
PIPELINE_LABELS = {
    FACE_FREE_PIPELINE_ID: "Amiga Style Transfer",
    PORTRAIT_REFERENCE_PIPELINE_ID: "Portrait Style Reference",
}
PIPELINE_DESCRIPTIONS = {
    FACE_FREE_PIPELINE_ID: "Generates a matted foreground, then applies a deterministic renderer-owned background.",
    PORTRAIT_REFERENCE_PIPELINE_ID: "Uses the original portrait reference from historical Pipelines 01/02.",
}
FACE_FREE_REFERENCE_CHECKSUM = "b898df7ab12666bc6f409fddd45fbdd39847c754c02f57c20e1419eae2bc9354"
FACE_FREE_REFERENCE_CHECKSUMS = {FACE_FREE_REFERENCE_CHECKSUM, "6d4dbdd6d031678d83468122d6b8201266b5e2f3272f8628ebfd3af0dd871823", "ad0a1277a27a61dee615652f6fd81fa163a6dd44d5db378d9ed745faae39085c"}
PORTRAIT_REFERENCE_CHECKSUM = "68ca995a8d308963278a2047863886b382adc8cd1230d05952c017b659838efe"
LEGACY_SIMULATION_MODEL_ID = "fake/painterly-deterministic"
SIMULATION_MODEL_IDS = {LEGACY_SIMULATION_MODEL_ID, "fake/amiga-ocs-deterministic"}
ART_LOGICAL_SIZE = [168, 99]
ART_OUTPUT_SIZE = [336, 198]
ART_RATIO_LABEL = "56:33"


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _hex_colour(value: str) -> str:
    text = str(value).strip().lower()
    if not text.startswith("#") or len(text) != 7:
        raise ValueError(f"invalid palette colour: {value}")
    try:
        channels = tuple(int(text[offset:offset + 2], 16) for offset in (1, 3, 5))
    except ValueError as exc:
        raise ValueError(f"invalid palette colour: {value}") from exc
    if any(channel % 17 for channel in channels):
        raise ValueError("Amiga OCS colours must use 4-bit channels expanded to 8-bit")
    return text


def _rgb_colour(value: str) -> str:
    text = str(value).strip().lower()
    if not text.startswith("#") or len(text) != 7:
        raise ValueError(f"invalid RGB colour: {value}")
    try:
        bytes.fromhex(text[1:])
    except ValueError as exc:
        raise ValueError(f"invalid RGB colour: {value}") from exc
    return text


def _without_checksums(style: dict[str, Any]) -> dict[str, Any]:
    result = _json_copy(style)
    result.pop("checksums", None)
    result.pop("provenance", None)
    identity = result.get("identity")
    if isinstance(identity, dict):
        identity.pop("state", None)
    for asset in result.get("reference_pack", {}).get("assets", []):
        if isinstance(asset, dict):
            asset.pop("relative_path", None)
            asset.pop("input_path", None)
            asset.pop("image_url", None)
    return result


def canonical_style(style: dict[str, Any]) -> str:
    return json.dumps(_without_checksums(style), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def style_checksum(style: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_style(style).encode("utf-8")).hexdigest()


def validate_style(style: dict[str, Any], *, require_locked: bool = False) -> dict[str, Any]:
    schema_version = int(style.get("schema_version", 0)) if isinstance(style, dict) else 0
    if schema_version not in {1, 2, 3}:
        raise ValueError("style pipeline schema_version 1, 2, or 3 is required")
    identity = style.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("style identity is required")
    for field in ("family_id", "style_version_id", "label"):
        if not str(identity.get(field) or "").strip():
            raise ValueError(f"style identity.{field} is required")
    if identity["family_id"] != STYLE_FAMILY_ID:
        raise ValueError("only the amiga-ocs-portrait style family is registered")
    if identity.get("pipeline_id") and identity["pipeline_id"] not in PIPELINE_IDS:
        raise ValueError("style identity.pipeline_id is not a registered pipeline")
    state = str(identity.get("state") or "")
    if state not in {"draft", "locked"}:
        raise ValueError("style state must be draft or locked")
    if require_locked and state != "locked":
        raise ValueError("a locked style version is required")
    generation = style.get("generation")
    if not isinstance(generation, dict):
        raise ValueError("style generation section is required")
    if str(generation.get("execution_mode")) not in {"simulation", "live"}:
        raise ValueError("generation.execution_mode must be simulation or live")
    if not str(generation.get("model_id") or "").strip():
        raise ValueError("generation.model_id is required")
    if str(generation.get("quality") or "") not in {"low", "medium", "high"}:
        raise ValueError("generation.quality must be low, medium, or high")
    if not isinstance(generation.get("reference_limit"), int) or generation["reference_limit"] < 2:
        raise ValueError("generation.reference_limit must allow an identity image and at least one style reference")
    if not str(generation.get("requested_aspect_policy") or "").strip():
        raise ValueError("generation.requested_aspect_policy is required")
    if schema_version == 1:
        direction = generation.get("direction")
        if not isinstance(direction, dict) or not any(str(value).strip() for value in direction.values()):
            raise ValueError("generation.direction must contain text")
    elif schema_version == 2:
        stages = generation.get("stages")
        if not isinstance(stages, dict) or any(not str((stages.get(name) or {}).get("prompt") or "").strip() for name in ("normalise", "stylise")):
            raise ValueError("generation.stages must contain normalise and stylise prompts")
    elif not str(generation.get("prompt") or "").strip():
        raise ValueError("generation.prompt is required")
    references = style.get("reference_pack", {}).get("assets")
    if not isinstance(references, list) or not references:
        raise ValueError("style reference_pack.assets is required")
    seen_roles: set[str] = set()
    seen_ids: set[str] = set()
    for asset in references:
        if not isinstance(asset, dict) or not str(asset.get("id") or "").strip():
            raise ValueError("each style reference needs an id")
        if asset["id"] in seen_ids:
            raise ValueError("style reference IDs must be unique")
        seen_ids.add(asset["id"])
        role = str(asset.get("role") or "")
        if role not in {"generation-reference", "target-example"}:
            raise ValueError("style references must use generation-reference or target-example roles")
        if role in seen_roles and role == "target-example":
            raise ValueError("a style can contain at most one target-example")
        seen_roles.add(role)
        if not str(asset.get("checksum_sha256") or "").strip():
            raise ValueError(f"reference {asset['id']} is missing its checksum")
    generation_count = sum(1 for asset in references if asset.get("role") == "generation-reference")
    if generation_count < 1:
        raise ValueError("at least one generation-reference is required")
    if generation_count + 1 > int(generation["reference_limit"]):
        raise ValueError("the style reference pack exceeds generation.reference_limit")
    composition = style.get("composition")
    renderer = style.get("renderer")
    if not isinstance(composition, dict) or not isinstance(renderer, dict):
        raise ValueError("composition and renderer sections are required")
    composition["logical_art_size"] = list(ART_LOGICAL_SIZE)
    composition["requested_art_ratio"] = ART_RATIO_LABEL
    renderer["logical_art_size"] = list(ART_LOGICAL_SIZE)
    generation["requested_aspect_policy"] = ART_RATIO_LABEL
    if isinstance(style.get("backgrounds"), dict):
        style["backgrounds"]["composite_size"] = list(ART_OUTPUT_SIZE)
    for section, key in ((composition, "logical_art_size"), (renderer, "logical_art_size")):
        dimensions = section.get(key)
        if not isinstance(dimensions, list) or len(dimensions) != 2 or any(not isinstance(value, int) or value <= 0 or value > 4096 for value in dimensions):
            raise ValueError(f"{key} must contain two positive integer dimensions")
    if composition["logical_art_size"] != renderer["logical_art_size"]:
        raise ValueError("composition and renderer logical art sizes must match")
    scale = renderer.get("output_scale")
    if not isinstance(scale, int) or scale < 1 or scale > 8:
        raise ValueError("renderer.output_scale must be an integer from 1 to 8")
    centering = composition.get("centering")
    if not isinstance(centering, list) or len(centering) != 2 or any(not isinstance(value, (int, float)) or not 0 <= float(value) <= 1 for value in centering):
        raise ValueError("composition.centering values must be normalized between 0 and 1")
    framing = composition.get("default_framing")
    if not isinstance(framing, dict) or float(framing.get("zoom", 0)) < 1 or any(abs(float(framing.get(key, 0))) > 1 for key in ("offset_x", "offset_y")):
        raise ValueError("composition.default_framing is invalid")
    if int(renderer.get("driver_version", 1)) >= 3:
        backgrounds = style.get("backgrounds") or {}
        presets = backgrounds.get("presets") if isinstance(backgrounds, dict) else None
        if not isinstance(presets, list) or not presets or str(backgrounds.get("default_id") or "") not in {str(item.get("id")) for item in presets if isinstance(item, dict)}:
            raise ValueError("backgrounds must define presets and a valid default_id")
        for preset in presets:
            if not isinstance(preset, dict) or not str(preset.get("id") or "") or any(not isinstance(preset.get(key), str) for key in ("top", "bottom", "glow")):
                raise ValueError("each background preset requires id, top, bottom, and glow")
            for key in ("top", "bottom", "glow"):
                preset[key] = _rgb_colour(preset[key])
    palette = renderer.get("palette")
    if renderer.get("palette_mode", "fixed-house") not in {"fixed-house", "adaptive-hybrid"}:
        raise ValueError("renderer.palette_mode must be fixed-house or adaptive-hybrid")
    if not isinstance(palette, list) or len(palette) != 32:
        raise ValueError("the Amiga OCS renderer requires exactly 32 palette colours")
    renderer["palette"] = [_hex_colour(value) for value in palette]
    dither = renderer.get("dither")
    if not isinstance(dither, dict) or dither.get("matrix") != "bayer-4x4" or not 0 <= float(dither.get("strength", -1)) <= 1 or not 0 <= float(dither.get("edge_threshold", -1)) <= 1:
        raise ValueError("renderer.dither must define bayer-4x4 strength and edge_threshold from 0 to 1")
    if renderer.get("driver_id") != "amiga-ocs":
        raise ValueError("the registered Amiga pipeline requires the amiga-ocs driver")
    normalized = _json_copy(style)
    normalized["checksums"] = {**dict(normalized.get("checksums") or {}), "style_sha256": style_checksum(normalized)}
    return normalized


def load_checked_in_style() -> dict[str, Any]:
    return validate_style(json.loads(STYLE_DEFINITION_PATH.read_text(encoding="utf-8")))


def pipeline_id_for_style(style: dict[str, Any]) -> str:
    explicit = str(style.get("identity", {}).get("pipeline_id") or "")
    if explicit in PIPELINE_IDS:
        return explicit
    generation_assets = [asset for asset in style.get("reference_pack", {}).get("assets", []) if asset.get("role") == "generation-reference"]
    if any(str(asset.get("checksum_sha256")) in FACE_FREE_REFERENCE_CHECKSUMS for asset in generation_assets):
        return FACE_FREE_PIPELINE_ID
    return PORTRAIT_REFERENCE_PIPELINE_ID


def legacy_amiga_style(style: dict[str, Any]) -> dict[str, Any]:
    """Adapt the validated snapshot to the proven Amiga implementation."""
    renderer = style["renderer"]
    preprocess = renderer.get("preprocess") or {}
    return {
        "id": style["identity"]["family_id"],
        "version": style["identity"].get("version", 1),
        "label": style["identity"]["label"],
        "logical_art_size": list(renderer["logical_art_size"]),
        "logical_card_size": [210, 300],
        "output_scale": renderer["output_scale"],
        "palette_space": renderer["palette_space"],
        "palette": list(renderer["palette"]),
        "dither": dict(renderer["dither"]),
        "preprocess": {"color": float(preprocess.get("color", 1.0)), "contrast": float(preprocess.get("contrast", 1.02)), "unsharp_radius": float(preprocess.get("unsharp_radius", 0.8)), "unsharp_percent": int(preprocess.get("unsharp_percent", 90)), "unsharp_threshold": int(preprocess.get("unsharp_threshold", 5))},
    }


class StyleStore:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
        self.store.ensure()
        (self.store.root / "styles" / "versions").mkdir(parents=True, exist_ok=True)

    @property
    def index_path(self) -> Path:
        return self.store.root / "styles" / "index.json"

    def _index(self) -> dict[str, Any]:
        return self.store.read_json(self.index_path, {"version": 1, "active_version_id": None, "versions": [], "draft": None})

    def _write_index(self, index: dict[str, Any]) -> None:
        self.store.atomic_json(self.index_path, index)

    def _style_path(self, version_id: str) -> Path:
        if not version_id or "/" in version_id or "\\" in version_id or ".." in version_id:
            raise WorkspaceError("unsafe style version ID")
        return self.store.root / "styles" / "versions" / version_id / "style.json"

    def _asset_path(self, asset: dict[str, Any]) -> Path:
        return self.store.absolute_path(str(asset.get("relative_path") or ""))

    def _ensure_default(self) -> dict[str, Any]:
        index = self._index()
        active_id = index.get("active_version_id")
        if active_id and self._style_path(str(active_id)).is_file():
            active = self.raw_version(str(active_id))
            checked_in = load_checked_in_style()
            active_reference_checksums = {asset.get("checksum_sha256") for asset in active.get("reference_pack", {}).get("assets", [])}
            if active.get("schema_version") == 3 and active.get("identity", {}).get("pipeline_id") == FACE_FREE_PIPELINE_ID and FACE_FREE_REFERENCE_CHECKSUM in active_reference_checksums and int(active.get("renderer", {}).get("driver_version", 1)) >= 3 and active["generation"].get("model_id") not in SIMULATION_MODEL_IDS and active["generation"].get("execution_mode") != "simulation":
                return self.payload(active)
            expected_checksum = style_checksum(checked_in)
            matching_version = next((entry for entry in index.get("versions", []) if entry.get("checksum_sha256") == expected_checksum and str(entry.get("style_version_id")) != str(active_id)), None)
            if matching_version:
                index["active_version_id"] = str(matching_version["style_version_id"])
                self._write_index(index)
                return self.get_version(str(matching_version["style_version_id"]))
            next_version = max([int(self.raw_version(str(entry["style_version_id"])).get("identity", {}).get("version", 0)) for entry in index.get("versions", [])] + [0]) + 1
            checked_in["identity"] = {**checked_in["identity"], "state": "locked", "version": next_version, "style_version_id": f"style_{STYLE_FAMILY_ID.replace('-', '_')}_v{next_version}_{uuid.uuid4().hex[:10]}"}
            checked_in["provenance"] = {"derived_from": active["identity"]["style_version_id"], "materialized_at": now_iso(), "source": "checked-in-migration"}
            if index.get("draft"):
                draft_path = self.store.root / "styles" / "draft.json"
                if draft_path.is_file():
                    archive = self.store.root / "styles" / "archive" / f"{index['draft']}.json"
                    archive.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(draft_path, archive)
                    draft_path.unlink()
                index["draft"] = None
            return self._materialize_locked(checked_in, index, activate=True)
        style = load_checked_in_style()
        return self._materialize_locked(style, index, activate=True)

    def _ensure_portrait_reference(self) -> dict[str, Any]:
        index = self._index()
        matching: list[str] = []
        for entry in index.get("versions", []):
            try:
                style = self.raw_version(str(entry["style_version_id"]))
            except ValueError:
                continue
            if style["generation"].get("execution_mode") == "live" and style.get("identity", {}).get("pipeline_id") == PORTRAIT_REFERENCE_PIPELINE_ID:
                matching.append(str(entry["style_version_id"]))
        if matching:
            return self.get_version(matching[-1])

        base = self.raw_version(str(index.get("active_version_id")))
        portrait = _json_copy(base)
        portrait["identity"] = {
            **portrait["identity"],
            "pipeline_id": PORTRAIT_REFERENCE_PIPELINE_ID,
            "style_version_id": f"style_portrait_reference_v1_{uuid.uuid4().hex[:10]}",
            "version": 1,
            "state": "locked",
            "label": PIPELINE_LABELS[PORTRAIT_REFERENCE_PIPELINE_ID],
        }
        target_assets = [asset for asset in portrait["reference_pack"]["assets"] if asset.get("role") == "target-example"]
        portrait["reference_pack"] = {
            **portrait["reference_pack"],
            "id": "portrait-style-reference-pack",
            "version": 1,
            "assets": [{
                "id": "generation-reference-01",
                "asset_key": "generation-reference-01.png",
                "role": "generation-reference",
                "label": "Original portrait style reference",
                "checksum_sha256": PORTRAIT_REFERENCE_CHECKSUM,
            }, *target_assets],
        }
        portrait["provenance"] = {
            "source": "seeded-pipeline",
            "derived_from": base["identity"]["style_version_id"],
            "reference_lineage": "historical-pipelines-01-02",
        }
        portrait["checksums"] = {"style_sha256": style_checksum(portrait)}
        return self._materialize_locked(portrait, index, activate=False)

    def ensure_initial(self) -> dict[str, Any]:
        active = self._ensure_default()
        return active

    def _materialize_locked(self, style: dict[str, Any], index: dict[str, Any], *, activate: bool) -> dict[str, Any]:
        version_id = str(style["identity"]["style_version_id"])
        version_dir = self._style_path(version_id).parent
        version_dir.mkdir(parents=True, exist_ok=True)
        for asset in style["reference_pack"]["assets"]:
            source = ASSET_ROOT / str(asset["asset_key"])
            if not source.is_file():
                raise WorkspaceError(f"checked-in style asset is missing: {source}")
            destination = version_dir / "references" / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if checksum(destination) != asset["checksum_sha256"]:
                raise WorkspaceError(f"checked-in asset checksum mismatch: {asset['asset_key']}")
            asset["relative_path"] = destination.relative_to(self.store.root).as_posix()
        style["provenance"] = {**style.get("provenance", {}), "materialized_at": now_iso(), "source": style.get("provenance", {}).get("source", "checked-in")}
        style["checksums"] = {"style_sha256": style_checksum(style), "assets": {asset["id"]: asset["checksum_sha256"] for asset in style["reference_pack"]["assets"]}}
        self.store.atomic_json(self._style_path(version_id), style)
        versions = [entry for entry in index.get("versions", []) if entry.get("style_version_id") != version_id]
        versions.append({"style_version_id": version_id, "checksum_sha256": style["checksums"]["style_sha256"], "created_at": now_iso()})
        index["version"] = 1
        index["versions"] = versions
        index.setdefault("draft", None)
        if activate:
            index["active_version_id"] = version_id
        self._write_index(index)
        return self.get_version(version_id)

    def get_version(self, version_id: str) -> dict[str, Any]:
        style = self.store.read_json(self._style_path(version_id), None)
        if not isinstance(style, dict):
            raise ValueError(f"style version {version_id} does not exist")
        return self.payload(validate_style(style, require_locked=True))

    def raw_version(self, version_id: str) -> dict[str, Any]:
        style = self.store.read_json(self._style_path(version_id), None)
        if not isinstance(style, dict):
            raise ValueError(f"style version {version_id} does not exist")
        return validate_style(style, require_locked=True)

    def active_id(self) -> str | None:
        value = self._index().get("active_version_id")
        if value:
            return str(value)
        self.ensure_initial()
        value = self._index().get("active_version_id")
        return str(value) if value else None

    def active(self) -> dict[str, Any]:
        self.ensure_initial()
        active_id = self.active_id()
        if not active_id:
            raise ValueError("no active locked style version exists")
        return self.get_version(str(active_id))

    def versions(self) -> list[dict[str, Any]]:
        self.ensure_initial()
        result = []
        for entry in self._index().get("versions", []):
            try:
                style = self.get_version(str(entry["style_version_id"]))
                result.append({
                    "pipeline_id": pipeline_id_for_style(style),
                    "style_version_id": style["identity"]["style_version_id"],
                    "label": style["identity"]["label"],
                    "version": style["identity"].get("version"),
                    "checksum_sha256": style["checksums"]["style_sha256"],
                    "active": style["identity"]["style_version_id"] == self.active_id(),
                    "created_at": entry.get("created_at"),
                    "execution_mode": style["generation"]["execution_mode"],
                    "model_id": style["generation"]["model_id"],
                    "quality": style["generation"]["quality"],
                    "reference_count": len([asset for asset in style["reference_pack"]["assets"] if asset.get("role") == "generation-reference"]),
                    "renderer_id": style["renderer"]["driver_id"],
                })
            except ValueError:
                continue
        return result

    def pipelines(self) -> list[dict[str, Any]]:
        self.ensure_initial()
        index = self._index()
        result: list[dict[str, Any]] = []
        for pipeline_id in (FACE_FREE_PIPELINE_ID,):
            revisions: list[dict[str, Any]] = []
            for entry in index.get("versions", []):
                try:
                    raw = self.raw_version(str(entry["style_version_id"]))
                except ValueError:
                    continue
                if raw["generation"].get("execution_mode") != "live" or pipeline_id_for_style(raw) != pipeline_id:
                    continue
                revisions.append({
                    "style_version_id": raw["identity"]["style_version_id"],
                    "checksum_sha256": raw["checksums"]["style_sha256"],
                    "created_at": entry.get("created_at"),
                })
            if not revisions:
                continue
            current_id = str(revisions[-1]["style_version_id"])
            style = self.get_version(current_id)
            result.append({
                "pipeline_id": pipeline_id,
                "label": PIPELINE_LABELS[pipeline_id],
                "description": PIPELINE_DESCRIPTIONS[pipeline_id],
                "active": current_id == self.active_id(),
                "current_version_id": current_id,
                "revision_count": len(revisions),
                "revisions": revisions,
                "style": style,
            })
        return result

    def active_pipeline_id(self) -> str:
        return pipeline_id_for_style(self.raw_version(str(self.active_id())))

    def raw_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        pipeline = next((item for item in self.pipelines() if item["pipeline_id"] == pipeline_id), None)
        if not pipeline:
            raise ValueError(f"pipeline {pipeline_id} does not exist")
        return self.raw_version(str(pipeline["current_version_id"]))

    def activate_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        style = self.raw_pipeline(pipeline_id)
        return self.activate(str(style["identity"]["style_version_id"]))

    def draft(self) -> dict[str, Any] | None:
        draft_id = self._index().get("draft")
        if not draft_id:
            return None
        path = self.store.root / "styles" / "draft.json"
        if not path.is_file():
            return None
        return self.payload(validate_style(self.store.read_json(path, {})))

    def raw_draft(self) -> dict[str, Any] | None:
        path = self.store.root / "styles" / "draft.json"
        if not path.is_file():
            return None
        return validate_style(self.store.read_json(path, {}))

    def create_or_resume_draft(self, pipeline_id: str | None = None) -> dict[str, Any]:
        current = self.draft()
        if current:
            requested = pipeline_id or self.active_pipeline_id()
            if pipeline_id_for_style(current) != requested:
                raise ValueError("finish the existing working pipeline before editing another pipeline")
            return current
        requested = pipeline_id or self.active_pipeline_id()
        base = self.raw_pipeline(requested)
        draft = _json_copy(base)
        draft["identity"] = {**draft["identity"], "pipeline_id": requested, "label": PIPELINE_LABELS[requested], "state": "draft", "style_version_id": f"draft_{uuid.uuid4().hex[:16]}"}
        draft["provenance"] = {"derived_from": base["identity"]["style_version_id"], "created_at": now_iso()}
        draft["checksums"] = {"style_sha256": style_checksum(draft), "base_style_version_id": base["identity"]["style_version_id"]}
        self.store.atomic_json(self.store.root / "styles" / "draft.json", draft)
        index = self._index(); index["draft"] = draft["identity"]["style_version_id"]; self._write_index(index)
        return self.payload(draft)

    def update_draft(self, patch: dict[str, Any]) -> dict[str, Any]:
        draft = self.draft() or self.create_or_resume_draft()
        raw = self.store.read_json(self.store.root / "styles" / "draft.json", {})
        if not isinstance(patch, dict):
            raise ValueError("draft patch must be an object")
        candidate = copy.deepcopy(raw)
        for section in ("generation", "composition", "renderer"):
            if isinstance(patch.get(section), dict):
                candidate[section] = {**candidate.get(section, {}), **patch[section]}
        if "reference_pack" in patch:
            candidate["reference_pack"] = patch["reference_pack"]
            original_targets = {str(asset["id"]) for asset in raw.get("reference_pack", {}).get("assets", []) if asset.get("role") == "target-example"}
            candidate_targets = {str(asset.get("id")) for asset in candidate.get("reference_pack", {}).get("assets", []) if asset.get("role") == "target-example"}
            if original_targets != candidate_targets:
                raise ValueError("target examples are review-only and cannot be moved into generation references")
            for asset in candidate.get("reference_pack", {}).get("assets", []):
                if str(asset.get("id")) in original_targets and asset.get("role") != "target-example":
                    raise ValueError("target examples are review-only and cannot be moved into generation references")
        candidate["checksums"] = {"style_sha256": style_checksum(candidate), "base_style_version_id": raw.get("provenance", {}).get("derived_from")}
        normalized = validate_style(candidate)
        self.store.atomic_json(self.store.root / "styles" / "draft.json", normalized)
        return self.payload(normalized)

    def add_draft_reference(self, label: str, original_name: str, content: bytes, content_type: str | None = None) -> dict[str, Any]:
        draft = self.draft() or self.create_or_resume_draft()
        record = self.store.add_image_record("reference", label, original_name, content, content_type)
        raw = self.store.read_json(self.store.root / "styles" / "draft.json", {})
        asset = {"id": f"draft-reference-{uuid.uuid4().hex[:12]}", "label": record["label"], "role": "generation-reference", "relative_path": record["relative_path"], "checksum_sha256": record["checksum_sha256"], "provenance": {"kind": "draft-upload", "created_at": now_iso()}}
        assets = [*raw["reference_pack"]["assets"], asset]
        return self.update_draft({"reference_pack": {**raw["reference_pack"], "assets": assets}})

    def lock_draft(self) -> dict[str, Any]:
        draft_path = self.store.root / "styles" / "draft.json"
        draft = validate_style(self.store.read_json(draft_path, {}))
        if draft["generation"].get("execution_mode") != "live":
            raise ValueError("simulation-only styles are previews and cannot be locked for production")
        for asset in draft["reference_pack"]["assets"]:
            path = self._asset_path(asset)
            if not path.is_file() or checksum(path) != asset["checksum_sha256"]:
                raise ValueError("style draft reference assets changed; refresh the draft before locking")
        index = self._index()
        next_version = max([int(self.get_version(str(item["style_version_id"])).get("identity", {}).get("version", 0)) for item in index.get("versions", [])] + [0]) + 1
        pipeline_id = pipeline_id_for_style(draft)
        version_id = f"style_{pipeline_id.replace('-', '_')}_v{next_version}_{uuid.uuid4().hex[:10]}"
        locked = _json_copy(draft)
        locked["identity"] = {**locked["identity"], "pipeline_id": pipeline_id, "label": PIPELINE_LABELS[pipeline_id], "state": "locked", "version": next_version, "style_version_id": version_id}
        locked["provenance"] = {"derived_from_draft": draft["identity"]["style_version_id"], "created_at": now_iso()}
        version_dir = self._style_path(version_id).parent
        for asset in locked["reference_pack"]["assets"]:
            source = self._asset_path(asset)
            destination = version_dir / "references" / f"{asset['id']}{source.suffix.lower() or '.png'}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
            shutil.copy2(source, temporary)
            temporary.replace(destination)
            asset["relative_path"] = destination.relative_to(self.store.root).as_posix()
        locked["checksums"] = {"style_sha256": style_checksum(locked), "assets": {asset["id"]: asset["checksum_sha256"] for asset in locked["reference_pack"]["assets"]}}
        self.store.atomic_json(self._style_path(version_id), locked)
        index["versions"].append({"style_version_id": version_id, "checksum_sha256": locked["checksums"]["style_sha256"], "created_at": now_iso()})
        index["draft"] = None
        self._write_index(index)
        draft_path.unlink(missing_ok=True)
        return self.get_version(version_id)

    def activate(self, version_id: str) -> dict[str, Any]:
        style = self.raw_version(version_id)
        index = self._index(); index["active_version_id"] = style["identity"]["style_version_id"]; self._write_index(index)
        return self.get_version(version_id)

    def remove_simulation_versions(self) -> list[str]:
        self.ensure_initial()
        index = self._index()
        removed: list[str] = []
        retained: list[dict[str, Any]] = []
        for entry in index.get("versions", []):
            version_id = str(entry.get("style_version_id") or "")
            try:
                style = self.raw_version(version_id)
            except ValueError:
                continue
            if style["generation"].get("execution_mode") == "simulation":
                if version_id == index.get("active_version_id"):
                    raise ValueError("cannot remove the active pipeline version")
                shutil.rmtree(self._style_path(version_id).parent)
                removed.append(version_id)
            else:
                retained.append(entry)
        index["versions"] = retained
        self._write_index(index)
        return removed

    def remove_superseded_legacy_versions(self, protected_version_ids: set[str] | None = None) -> list[str]:
        """Remove unreferenced pre-pipeline live versions after the two pipelines are seeded."""
        self.ensure_initial()
        index = self._index()
        removed: list[str] = []
        retained: list[dict[str, Any]] = []
        active_id = str(index.get("active_version_id") or "")
        protected = protected_version_ids or set()
        for entry in index.get("versions", []):
            version_id = str(entry.get("style_version_id") or "")
            try:
                style = self.raw_version(version_id)
            except ValueError:
                continue
            legacy_nonactive = style["generation"].get("execution_mode") == "live" and not style.get("identity", {}).get("pipeline_id") and version_id != active_id and version_id not in protected
            if legacy_nonactive:
                shutil.rmtree(self._style_path(version_id).parent)
                removed.append(version_id)
            else:
                retained.append(entry)
        index["versions"] = retained
        self._write_index(index)
        return removed

    def payload(self, style: dict[str, Any]) -> dict[str, Any]:
        result = _json_copy(style)
        for asset in result.get("reference_pack", {}).get("assets", []):
            if asset.get("relative_path"):
                asset["image_url"] = self.store.asset_url(asset["relative_path"])
        return result

    def bootstrap(self) -> dict[str, Any]:
        active = self.active()
        return {"active": active, "active_pipeline_id": self.active_pipeline_id(), "pipelines": self.pipelines(), "draft": self.draft(), "versions": self.versions(), "driver": {"id": "amiga-ocs", "label": "Amiga OCS", "output": "336×276 rendered artwork"}}
