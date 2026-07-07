from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import requests

from .manifest import LICENSE_PAGE, deterministic_source_filename, utc_now_iso


API_URL = "https://api.pexels.com/v1/search"


def parse_photo(photo: dict[str, Any], query: str) -> dict[str, Any]:
    src = photo.get("src") or {}
    original_url = src.get("original") or src.get("large2x") or src.get("large")
    selected_url = src.get("large2x") or src.get("large") or original_url
    if not selected_url:
        raise ValueError(f"Pexels photo {photo.get('id')} has no downloadable image URL")
    return {
        "source": "pexels",
        "pexels_photo_id": int(photo["id"]),
        "photo_page_url": photo.get("url"),
        "photographer": photo.get("photographer"),
        "photographer_url": photo.get("photographer_url"),
        "original_image_url": original_url,
        "selected_image_url": selected_url,
        "query": query,
        "license_page": LICENSE_PAGE,
        "original_width": photo.get("width"),
        "original_height": photo.get("height"),
    }


def parse_search_response(payload: dict[str, Any], query: str) -> list[dict[str, Any]]:
    return [parse_photo(photo, query) for photo in payload.get("photos", [])]


def search_pexels(
    query: str,
    count: int,
    orientation: str | None = None,
    page: int = 1,
    per_page: int | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    key = api_key or os.environ.get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY is not set")
    params: dict[str, Any] = {
        "query": query,
        "page": page,
        "per_page": per_page or min(max(count, 1), 80),
    }
    if orientation:
        params["orientation"] = orientation
    response = requests.get(API_URL, headers={"Authorization": key}, params=params, timeout=30)
    response.raise_for_status()
    return parse_search_response(response.json(), query)[:count]


def is_plausible_portrait(candidate: dict[str, Any]) -> bool:
    width = int(candidate.get("original_width") or 0)
    height = int(candidate.get("original_height") or 0)
    if width < 400 or height < 400:
        return False
    ratio = width / height
    return 0.55 <= ratio <= 1.35


def checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_candidate(candidate: dict[str, Any], source_dir: Path) -> dict[str, Any]:
    source_dir.mkdir(parents=True, exist_ok=True)
    photo_id = candidate["pexels_photo_id"]
    filename = deterministic_source_filename(photo_id)
    path = source_dir / filename
    response = requests.get(candidate["selected_image_url"], timeout=60)
    response.raise_for_status()
    path.write_bytes(response.content)
    enriched = dict(candidate)
    enriched.update(
        {
            "downloaded_at": utc_now_iso(),
            "local_source_filename": filename,
            "source_checksum_sha256": checksum_file(path),
            "processing_status": "downloaded",
        }
    )
    return enriched

