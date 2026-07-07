from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .manifest import load_manifest, save_manifest


REVIEW_PATH = Path("portrait-review/review.json")


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
        candidates = []
        for candidate in entry.get("stylized_candidates", []):
            candidate_id = str(candidate.get("candidate_id"))
            candidate_review = review.get("candidates", {}).get(candidate_id, {})
            candidates.append(
                {
                    **candidate,
                    "review": candidate_review,
                    "raw_url": asset_url(candidate.get("output_path")),
                    "final_url": asset_url(candidate.get("final_output_path")),
                }
            )
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
