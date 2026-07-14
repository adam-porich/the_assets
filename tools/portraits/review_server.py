from __future__ import annotations

import json
import mimetypes
import re
import shutil
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .img2img import OpenRouterBackend, load_preset, stable_seed, stylize_source
from .manifest import find_source, load_manifest, save_manifest
from .pexels import download_candidate, is_plausible_portrait, search_pexels

import os
import time
import requests


_image_models_cache: tuple[list[dict[str, Any]], float] | None = None
IMAGE_MODELS_CACHE_TTL = 3600

CHEAP_IMG2IMG_MODELS = [
    "openai/gpt-image-1-mini",
    "google/gemini-3.1-flash-lite-image",
    "google/gemini-3.1-flash-image",
    "recraft/recraft-v3",
    "recraft/recraft-v4",
    "black-forest-labs/flux.2-klein-4b",
    "sourceful/riverflow-v2-fast",
]


def fetch_image_models() -> list[dict[str, Any]]:
    global _image_models_cache
    now = time.time()
    if _image_models_cache is not None and (now - _image_models_cache[1]) < IMAGE_MODELS_CACHE_TTL:
        return _image_models_cache[0]
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.get("https://openrouter.ai/api/v1/images/models", headers=headers, timeout=15)
    response.raise_for_status()
    payload = response.json()
    models = []
    for model in payload.get("data", []):
        params = model.get("supported_parameters") or {}
        supports_img2img = "input_references" in params
        models.append({
            "id": model.get("id"),
            "name": model.get("name"),
            "description": model.get("description"),
            "supports_img2img": supports_img2img,
            "supported_parameters": list(params.keys()),
        })
    _image_models_cache = (models, now)
    return models


def fetch_cheap_img2img_models() -> list[dict[str, Any]]:
    all_models = fetch_image_models()
    cheap_set = set(CHEAP_IMG2IMG_MODELS)
    return [m for m in all_models if m["id"] in cheap_set and m["supports_img2img"]]
    _image_models_cache = (models, now)
    return models


REVIEW_PATH = Path("portrait-review/review.json")
STYLIZED_FINAL_RE = re.compile(r"^pexels-(?P<photo_id>\d+)-(?P<preset>.+)-(?P<seed>\d+)-final\.png$")
STYLIZED_RAW_RE = re.compile(r"^pexels-(?P<photo_id>\d+)-(?P<preset>.+)-(?P<seed>\d+)-raw\.png$")


def load_review(path: Path = REVIEW_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "sources": {}, "candidates": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_review(review: dict[str, Any], path: Path = REVIEW_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def asset_url(path: str | None) -> str | None:
    if not path:
        return None
    return "asset/" + path.replace("\\", "/")


def source_asset_url(local_source_filename: str | None) -> str | None:
    if not local_source_filename:
        return None
    return asset_url(f"sources/{local_source_filename}")


def candidate_url_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw_url": asset_url(candidate.get("output_path")),
        "final_url": asset_url(candidate.get("final_output_path")),
    }


def merge_stylized_candidates(entry: dict[str, Any], new_records: list[dict[str, Any]]) -> None:
    existing = {
        record.get("candidate_id"): record
        for record in entry.get("stylized_candidates", [])
        if record.get("candidate_id")
    }
    for record in new_records:
        existing[record["candidate_id"]] = record
    entry["stylized_candidates"] = sorted(existing.values(), key=lambda item: (item.get("preset", ""), item.get("seed", 0)))


def scan_disk_outputs(library_dir: Path, photo_id: str) -> list[dict[str, Any]]:
    stylized_dir = library_dir / "stylized"
    if not stylized_dir.exists():
        return []
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for path in sorted(stylized_dir.glob(f"pexels-{photo_id}-*.png")):
        final_match = STYLIZED_FINAL_RE.match(path.name)
        raw_match = STYLIZED_RAW_RE.match(path.name)
        match = final_match or raw_match
        if not match:
            continue
        preset = match.group("preset")
        seed = int(match.group("seed"))
        record = by_key.setdefault(
            (preset, seed),
            {
                "source_photo_id": int(photo_id),
                "candidate_id": f"{preset}:{seed}",
                "preset": preset,
                "seed": seed,
                "backend": "disk",
                "model": "unknown",
                "disk_only": True,
            },
        )
        field = "final_output_path" if final_match else "output_path"
        record[field] = str(path.relative_to(library_dir))
    return sorted(by_key.values(), key=lambda item: (item.get("preset", ""), item.get("seed", 0)))


def candidate_payloads(entry: dict[str, Any], library_dir: Path, review: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    photo_id = str(entry.get("pexels_photo_id"))
    manifest_candidates = {
        str(candidate.get("candidate_id")): dict(candidate)
        for candidate in entry.get("stylized_candidates", [])
        if candidate.get("candidate_id")
    }
    disk_candidates = {str(candidate["candidate_id"]): candidate for candidate in scan_disk_outputs(library_dir, photo_id)}
    all_outputs: list[dict[str, Any]] = []
    for candidate_id, candidate in sorted({**disk_candidates, **manifest_candidates}.items()):
        candidate_review = review.get("candidates", {}).get(candidate_id, {})
        payload = {
            **candidate,
            "review": candidate_review,
            **candidate_url_fields(candidate),
        }
        all_outputs.append(payload)
    candidates = [candidate for candidate in all_outputs if not candidate.get("disk_only") or candidate["candidate_id"] in manifest_candidates]
    return candidates, all_outputs


def build_library_payload(library_dir: Path, review_path: Path = REVIEW_PATH) -> dict[str, Any]:
    manifest = load_manifest(library_dir)
    review = load_review(review_path)
    sources = []
    for entry in manifest.get("sources", []):
        photo_id = str(entry.get("pexels_photo_id"))
        source_review = review.get("sources", {}).get(photo_id, {})
        selected = dict(entry.get("selected") or {})
        if source_review.get("selected_candidate"):
            selected["variant"] = source_review["selected_candidate"]
            selected["tags"] = source_review.get("tags", [])
        prep = entry.get("stylization_prep") or {}
        candidates, all_outputs = candidate_payloads(entry, library_dir, review)
        sources.append(
            {
                "photo_id": photo_id,
                "photographer": entry.get("photographer"),
                "photo_page_url": entry.get("photo_page_url"),
                "query": entry.get("query"),
                "dimensions": [entry.get("original_width"), entry.get("original_height")],
                "processing_status": entry.get("processing_status"),
                "review": source_review,
                "selected": selected,
                "source_url": source_asset_url(entry.get("local_source_filename")),
                "prepared_url": asset_url(prep.get("prepared_source_path")),
                "mask_url": asset_url(prep.get("mask_path")),
                "foreground_url": asset_url(prep.get("transparent_foreground_path")),
                "composite_url": asset_url(prep.get("composite_path")),
                "prep": prep,
                "candidates": candidates,
                "all_outputs": all_outputs,
            }
        )
    return {"sources": sources, "review": review}


def update_review_item(review: dict[str, Any], collection: str, item_id: str, status: str, note: str = "") -> dict[str, Any]:
    if collection not in {"sources", "candidates"}:
        raise ValueError("collection must be sources or candidates")
    if status == "clear":
        review.setdefault(collection, {}).pop(item_id, None)
    elif status in {"favorite", "reject", "add"}:
        review.setdefault(collection, {})[item_id] = {"status": status, "note": note}
    else:
        raise ValueError(f"unknown review status: {status}")
    return review


def select_candidate(library_dir: Path, photo_id: str, candidate_id: str, tags: list[str]) -> None:
    manifest = load_manifest(library_dir)
    for entry in manifest.get("sources", []):
        if str(entry.get("pexels_photo_id")) != str(photo_id):
            continue
        entry["selected"] = {
            "variant": candidate_id,
            "tags": sorted(set(tags)),
        }
        save_manifest(library_dir, manifest)
        return
    raise ValueError(f"unknown photo id: {photo_id}")


def select_candidate_in_review(review: dict[str, Any], photo_id: str, candidate_id: str, tags: list[str]) -> dict[str, Any]:
    source_review = review.setdefault("sources", {}).setdefault(photo_id, {})
    source_review["selected_candidate"] = candidate_id
    source_review["tags"] = sorted(set(tags))
    candidate_review = review.setdefault("candidates", {}).setdefault(candidate_id, {})
    candidate_review.setdefault("status", "favorite")
    candidate_review.setdefault("note", "")
    return review


def find_manifest_entry(manifest: dict[str, Any], photo_id: str) -> dict[str, Any]:
    for entry in manifest.get("sources", []):
        if str(entry.get("pexels_photo_id")) == str(photo_id):
            return entry
    raise ValueError(f"unknown photo id: {photo_id}")


def find_candidate(entry: dict[str, Any], library_dir: Path, candidate_id: str) -> dict[str, Any]:
    for candidate in entry.get("stylized_candidates", []):
        if str(candidate.get("candidate_id")) == str(candidate_id):
            return dict(candidate)
    for candidate in scan_disk_outputs(library_dir, str(entry.get("pexels_photo_id"))):
        if str(candidate.get("candidate_id")) == str(candidate_id):
            return dict(candidate)
    raise ValueError(f"unknown candidate id: {candidate_id}")


def safe_candidate_filename(candidate_id: str) -> str:
    if "/" in candidate_id or "\\" in candidate_id or candidate_id in {"", ".", ".."}:
        raise ValueError(f"unsafe candidate id: {candidate_id}")
    return candidate_id


def favorite_candidate(library_dir: Path, review_path: Path, photo_id: str, candidate_id: str, note: str = "") -> dict[str, Any]:
    manifest = load_manifest(library_dir)
    entry = find_manifest_entry(manifest, photo_id)
    candidate = find_candidate(entry, library_dir, candidate_id)
    final_output_path = candidate.get("final_output_path")
    if not final_output_path:
        raise ValueError(f"candidate has no final image: {candidate_id}")
    source_path = library_dir / str(final_output_path)
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"candidate final image is missing: {final_output_path}")

    dest_dir = review_path.parent / "favorites" / str(photo_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_candidate_filename(candidate_id)
    image_dest = dest_dir / f"{stem}.png"
    json_dest = dest_dir / f"{stem}.json"
    shutil.copy2(source_path, image_dest)

    prep = entry.get("stylization_prep") or {}
    sidecar = {
        "source": {
            key: entry.get(key)
            for key in (
                "source",
                "pexels_photo_id",
                "photo_page_url",
                "photographer",
                "photographer_url",
                "original_image_url",
                "selected_image_url",
                "query",
                "license_page",
                "original_width",
                "original_height",
                "local_source_filename",
                "source_checksum_sha256",
            )
        },
        "preparation": prep,
        "candidate": candidate,
        "prompt_preset": candidate.get("preset"),
        "model": candidate.get("model"),
        "seed": candidate.get("seed"),
        "backend": candidate.get("backend"),
        "timing": {"elapsed_seconds": candidate.get("elapsed_seconds"), "created_at": candidate.get("created_at")},
        "original_generated_paths": {
            "raw": candidate.get("output_path"),
            "final": candidate.get("final_output_path"),
            "input_composite": candidate.get("input_composite_path"),
        },
        "final_copied_image_path": str(image_dest),
    }
    json_dest.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    review = load_review(review_path)
    update_review_item(review, "candidates", candidate_id, "favorite", note)
    save_review(review, review_path)
    return {"image_path": str(image_dest), "metadata_path": str(json_dest), "review": review, "sidecar": sidecar}


def generate_candidate(library_dir: Path, photo_id: str, preset_name: str, model: str) -> dict[str, Any]:
    if not photo_id or not preset_name or not model:
        raise ValueError("photo_id, preset, and model are required")
    manifest = load_manifest(library_dir)
    entry = find_manifest_entry(manifest, photo_id)
    source_filename = entry.get("local_source_filename")
    if not source_filename:
        raise ValueError(f"source has no local source image: {photo_id}")
    preset = load_preset(preset_name)
    backend = OpenRouterBackend(model=model)
    source_path = library_dir / "sources" / str(source_filename)
    seed = stable_seed(int(photo_id), preset.name, len(entry.get("stylized_candidates", [])))
    prep, records = stylize_source(source_path, int(photo_id), library_dir, preset, backend, seed=seed, count=1)
    entry["stylization_prep"] = prep
    merge_stylized_candidates(entry, records)
    entry["processing_status"] = "stylized"
    entry.pop("stylization_error", None)
    save_manifest(library_dir, manifest)
    return {"prep": prep, "records": records}


def fetch_pexels_sources(library_dir: Path, query: str, count: int = 10) -> list[dict[str, Any]]:
    if not query:
        raise ValueError("query is required")
    manifest = load_manifest(library_dir)
    existing_ids = {int(entry.get("pexels_photo_id")) for entry in manifest.get("sources", []) if entry.get("pexels_photo_id")}
    candidates = search_pexels(query, count * 2)
    filtered = [item for item in candidates if is_plausible_portrait(item)]
    new_entries: list[dict[str, Any]] = []
    sources_dir = library_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    for item in filtered:
        if int(item["pexels_photo_id"]) in existing_ids:
            continue
        entry = download_candidate(item, sources_dir)
        manifest_entry = find_source(manifest, entry["pexels_photo_id"]) or {}
        manifest_entry.update(entry)
        if manifest_entry not in manifest.setdefault("sources", []):
            manifest["sources"].append(manifest_entry)
        new_entries.append(manifest_entry)
        existing_ids.add(int(item["pexels_photo_id"]))
        if len(new_entries) >= count:
            break
    save_manifest(library_dir, manifest)
    return new_entries


class ReviewHandler(BaseHTTPRequestHandler):
    library_dir = Path("portrait-library")
    review_path = REVIEW_PATH

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/library":
            self.send_json(build_library_payload(self.library_dir, self.review_path))
            return
        if parsed.path == "/api/models":
            try:
                self.send_json({"ok": True, "models": fetch_image_models()})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return
        if parsed.path == "/api/models/img2img":
            try:
                self.send_json({"ok": True, "models": fetch_cheap_img2img_models()})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return
        if parsed.path.startswith("/asset/"):
            self.serve_asset(parsed.path.removeprefix("/asset/"))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if parsed.path == "/api/review":
                review = load_review(self.review_path)
                update_review_item(
                    review,
                    str(payload["collection"]),
                    str(payload["id"]),
                    str(payload["status"]),
                    str(payload.get("note") or ""),
                )
                save_review(review, self.review_path)
                self.send_json({"ok": True, "review": review})
                return
            if parsed.path == "/api/select":
                review = load_review(self.review_path)
                select_candidate_in_review(
                    review,
                    str(payload["photo_id"]),
                    str(payload["candidate_id"]),
                    list(payload.get("tags") or []),
                )
                save_review(review, self.review_path)
                select_candidate(
                    self.library_dir,
                    str(payload["photo_id"]),
                    str(payload["candidate_id"]),
                    list(payload.get("tags") or []),
                )
                self.send_json({"ok": True})
                return
            if parsed.path == "/api/generate":
                result = generate_candidate(
                    self.library_dir,
                    str(payload["photo_id"]),
                    str(payload["preset"]),
                    str(payload["model"]),
                )
                self.send_json({"ok": True, **result, "library": build_library_payload(self.library_dir, self.review_path)})
                return
            if parsed.path == "/api/favorite-candidate":
                result = favorite_candidate(
                    self.library_dir,
                    self.review_path,
                    str(payload["photo_id"]),
                    str(payload["candidate_id"]),
                    str(payload.get("note") or ""),
                )
                self.send_json({"ok": True, **result})
                return
            if parsed.path == "/api/fetch-pexels":
                new_entries = fetch_pexels_sources(
                    self.library_dir,
                    str(payload.get("query") or ""),
                    int(payload.get("count", 10)),
                )
                self.send_json({
                    "ok": True,
                    "added": len(new_entries),
                    "library": build_library_payload(self.library_dir, self.review_path),
                })
                return
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def serve_asset(self, relative_path: str) -> None:
        safe = Path(unquote(relative_path))
        if safe.is_absolute() or ".." in safe.parts:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        path = self.library_dir / safe
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_review_server(host: str = "127.0.0.1", port: int = 8765, library_dir: Path = Path("portrait-library")) -> None:
    handler = type("ConfiguredReviewHandler", (ReviewHandler,), {"library_dir": library_dir})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Portrait review API: http://{host}:{port}")
    server.serve_forever()
