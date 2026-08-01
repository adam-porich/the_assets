from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from PIL import Image


WORKSPACE_VERSION = 1
WORKSPACE_FILENAME = "workspace.json"
DEFAULT_WORKSPACE = {
  "version": WORKSPACE_VERSION,
  "sources": [],
  "benchmark_source_ids": [],
  "references": [],
}
BUNDLED_REFERENCE_DIR = Path(__file__).parent / "assets" / "estate-card-v1"
BUNDLED_REFERENCES = (
    ("reference_estate_card_v1_firelit", "Estate card · firelit hooded portrait", "9ff3c44f945f.png"),
    ("reference_estate_card_v1_armoured", "Estate card · armoured claimant", "eba013818158.png"),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _clone_default() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_WORKSPACE))


class WorkspaceError(ValueError):
    pass


class WorkspaceStore:
    """Small, locked, file-backed store for the browser workbench."""

    def __init__(self, root: Path | str = "portrait-library") -> None:
        self.root = Path(root)
        self._lock = threading.RLock()

    @property
    def workspace_path(self) -> Path:
        return self.root / WORKSPACE_FILENAME

    def ensure(self) -> None:
        with self._lock:
            for directory in ("sources", "references", "styles", "production", "approvals", "downloads"):
                (self.root / directory).mkdir(parents=True, exist_ok=True)
            if not self.workspace_path.exists():
                self._atomic_json(self.workspace_path, _clone_default())

    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict) or data.get("version") != WORKSPACE_VERSION:
            raise WorkspaceError(f"{WORKSPACE_FILENAME} must use workspace version {WORKSPACE_VERSION}")
        normalized = _clone_default()
        normalized.update(data)
        for key in ("sources", "benchmark_source_ids", "references"):
            if not isinstance(normalized.get(key), list):
                raise WorkspaceError(f"{key} must be a list")
        source_values = [str(item.get("id")) for item in normalized["sources"]]
        if len(source_values) != len(set(source_values)):
            raise WorkspaceError("sources must have unique IDs")
        source_ids = set(source_values)
        if len(normalized["benchmark_source_ids"]) != len(set(map(str, normalized["benchmark_source_ids"]))):
            raise WorkspaceError("the saved source selection contains duplicate IDs")
        if any(str(item) not in source_ids for item in normalized["benchmark_source_ids"]):
            raise WorkspaceError("the saved source selection contains an unknown source")
        reference_values = [str(item.get("id")) for item in normalized["references"]]
        if len(reference_values) != len(set(reference_values)):
            raise WorkspaceError("references must have unique IDs")
        reference_ids = set(reference_values)
        return normalized

    def read(self) -> dict[str, Any]:
        with self._lock:
            self.ensure()
            try:
                data = json.loads(self.workspace_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise WorkspaceError(f"Could not read {self.workspace_path}: {exc}") from exc
            return self._validate(data)

    def write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.ensure()
            self._atomic_json(self.workspace_path, self._validate(data))

    def mutate(self, callback: Callable[[dict[str, Any]], Any]) -> Any:
        with self._lock:
            data = self.read()
            result = callback(data)
            self._atomic_json(self.workspace_path, self._validate(data))
            return result

    @contextmanager
    def locked(self) -> Iterator[None]:
        with self._lock:
            self.ensure()
            yield

    def _atomic_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)

    def atomic_json(self, path: Path, data: Any) -> None:
        with self._lock:
            self._atomic_json(path, data)

    def read_json(self, path: Path, fallback: Any) -> Any:
        with self._lock:
            if not path.exists():
                return fallback
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise WorkspaceError(f"Could not read {path}: {exc}") from exc

    def relative_path(self, value: str | Path) -> Path:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise WorkspaceError("asset path must be relative to portrait-library")
        resolved = (self.root / candidate).resolve()
        root = self.root.resolve()
        if resolved != root and root not in resolved.parents:
            raise WorkspaceError("asset path escapes portrait-library")
        return candidate

    def absolute_path(self, value: str | Path) -> Path:
        relative = self.relative_path(value)
        return self.root / relative

    def asset_url(self, value: str | Path | None) -> str | None:
        if not value:
            return None
        relative = self.relative_path(value).as_posix()
        return f"asset/{relative}"

    def image_metadata(self, path: Path) -> tuple[list[int], str]:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                return [int(image.width), int(image.height)], (image.format or "").lower()
        except Exception as exc:
            raise WorkspaceError(f"Uploaded file is not a readable image: {exc}") from exc

    def source_payload(self, source: dict[str, Any]) -> dict[str, Any]:
        return {**source, "image_url": self.asset_url(source.get("relative_path"))}

    def reference_payload(self, reference: dict[str, Any]) -> dict[str, Any]:
        return {**reference, "image_url": self.asset_url(reference.get("relative_path"))}

    def payload(self) -> dict[str, Any]:
        data = self.read()
        return {
            "version": data["version"],
            "sources": [self.source_payload(item) for item in data["sources"]],
            "benchmark_source_ids": list(data["benchmark_source_ids"]),
            "references": [self.reference_payload(item) for item in data["references"]],
            "links": {"production": "api/production", "styles": "api/styles/bootstrap"},
        }

    def ensure_bundled_references(self) -> list[str]:
        """Copy the checked-in estate-card references into a new workspace once."""
        with self._lock:
            data = self.read()
            known = {str(item.get("id")): item for item in data["references"]}
            changed = False
            for position, (reference_id, label, filename) in enumerate(BUNDLED_REFERENCES):
                source = BUNDLED_REFERENCE_DIR / filename
                if not source.is_file():
                    raise WorkspaceError(f"bundled starter reference is missing: {source}")
                relative = Path("references") / f"{reference_id}.png"
                destination = self.absolute_path(relative)
                if reference_id not in known:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    dimensions, _ = self.image_metadata(destination)
                    data["references"].append({
                        "id": reference_id,
                        "label": label,
                        "relative_path": relative.as_posix(),
                        "dimensions": dimensions,
                        "created_at": now_iso(),
                        "original_filename": filename,
                        "checksum_sha256": checksum(destination),
                        "position": position,
                        "provenance": {
                            "kind": "bundled",
                            "style_pack": "estate-card-v1",
                            "historical_path": f"portrait-review/styles/{filename}",
                        },
                    })
                    changed = True
            if changed:
                self._atomic_json(self.workspace_path, self._validate(data))
            return [reference_id for reference_id, _, _ in BUNDLED_REFERENCES]

    def add_image_record(self, kind: str, label: str, original_name: str, content: bytes, content_type: str | None = None) -> dict[str, Any]:
        if kind not in {"source", "reference"}:
            raise WorkspaceError("image kind must be source or reference")
        if not content:
            raise WorkspaceError("image upload is empty")
        if len(content) > 20 * 1024 * 1024:
            raise WorkspaceError("image upload is larger than the 20 MB limit")
        if content_type and not content_type.startswith("image/"):
            raise WorkspaceError("upload must have an image content type")
        item_id = new_id(kind)
        suffix = Path(original_name or "upload.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
            suffix = ".png"
        directory = "sources" if kind == "source" else "references"
        relative = Path(directory) / f"{item_id}{suffix}"
        path = self.absolute_path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        try:
            dimensions, image_format = self.image_metadata(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        digest = checksum(path)
        existing = next(
            (
                item for item in self.read()["sources" if kind == "source" else "references"]
                if item.get("checksum_sha256") == digest
            ),
            None,
        )
        if existing:
            path.unlink(missing_ok=True)
            return {**existing, "deduplicated": True}
        record: dict[str, Any] = {
            "id": item_id,
            "label": label.strip() or Path(original_name or item_id).stem,
            "relative_path": relative.as_posix(),
            "dimensions": dimensions,
            "created_at": now_iso(),
            "original_filename": Path(original_name or item_id).name,
            "checksum_sha256": digest,
        }
        if kind == "source":
            record["provenance"] = {"kind": "upload", "content_type": content_type or mimetypes.guess_type(original_name)[0], "format": image_format}
        def add_record(data: dict[str, Any]) -> None:
            collection = data["sources" if kind == "source" else "references"]
            if kind == "reference":
                record["position"] = len(collection)
            collection.append(record)
        self.mutate(add_record)
        return record

    def replace_reference_image(self, reference_id: str, original_name: str, content: bytes, content_type: str | None = None) -> dict[str, Any]:
        if not content:
            raise WorkspaceError("image upload is empty")
        if len(content) > 20 * 1024 * 1024:
            raise WorkspaceError("image upload is larger than the 20 MB limit")
        if content_type and not content_type.startswith("image/"):
            raise WorkspaceError("upload must have an image content type")
        suffix = Path(original_name or "replacement.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
            suffix = ".png"
        with self._lock:
            data = self.read()
            reference = next((item for item in data["references"] if str(item.get("id")) == reference_id), None)
            if not reference:
                raise WorkspaceError(f"unknown reference {reference_id}")
            old_path = self.absolute_path(reference["relative_path"])
            relative = Path("references") / f"{reference_id}{suffix}"
            new_path = self.absolute_path(relative)
            temporary = new_path.with_name(f".{new_path.name}.{uuid.uuid4().hex}.tmp")
            temporary.write_bytes(content)
            try:
                dimensions, image_format = self.image_metadata(temporary)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            temporary.replace(new_path)
            if old_path != new_path:
                old_path.unlink(missing_ok=True)
            reference.update({
                "relative_path": relative.as_posix(),
                "dimensions": dimensions,
                "original_filename": Path(original_name or reference_id).name,
                "checksum_sha256": checksum(new_path),
                "updated_at": now_iso(),
                "provenance": {"kind": "replacement", "content_type": content_type, "format": image_format},
            })
            self._atomic_json(self.workspace_path, self._validate(data))
            return dict(reference)


def file_checksum(path: Path) -> str:
    return checksum(path)
