from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from tools.portraits.imaging import palette_color_count, process_source, square_crop_box
from tools.portraits.lookbook import generate_lookbook
from tools.portraits.manifest import (
    CandidateSettings,
    deterministic_candidate_filename,
    deterministic_source_filename,
    load_manifest,
    save_manifest,
    update_selection,
)
from tools.portraits.pexels import parse_search_response


def make_fixture_image(path: Path) -> None:
    image = Image.new("RGB", (160, 220), "#c8b09a")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 160, 90), fill="#59646d")
    draw.ellipse((48, 50, 112, 122), fill="#d8a070")
    draw.rectangle((60, 115, 100, 180), fill="#44352f")
    draw.rectangle((40, 28, 120, 58), fill="#2b211f")
    draw.ellipse((64, 78, 70, 84), fill="#1a1512")
    draw.ellipse((90, 78, 96, 84), fill="#1a1512")
    draw.line((70, 102, 92, 102), fill="#8a423b", width=2)
    image.save(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_parse_pexels_response_preserves_provenance_fields() -> None:
    payload = {
        "photos": [
            {
                "id": 123,
                "width": 1200,
                "height": 1600,
                "url": "https://www.pexels.com/photo/example-123/",
                "photographer": "A Photographer",
                "photographer_url": "https://www.pexels.com/@a",
                "src": {
                    "original": "https://images.pexels.com/photos/123/original.jpg",
                    "large2x": "https://images.pexels.com/photos/123/large2x.jpg",
                },
            }
        ]
    }
    parsed = parse_search_response(payload, "eccentric portrait")
    assert parsed == [
        {
            "source": "pexels",
            "pexels_photo_id": 123,
            "photo_page_url": "https://www.pexels.com/photo/example-123/",
            "photographer": "A Photographer",
            "photographer_url": "https://www.pexels.com/@a",
            "original_image_url": "https://images.pexels.com/photos/123/original.jpg",
            "selected_image_url": "https://images.pexels.com/photos/123/large2x.jpg",
            "query": "eccentric portrait",
            "license_page": "https://www.pexels.com/license/",
            "original_width": 1200,
            "original_height": 1600,
        }
    ]


def test_deterministic_filenames() -> None:
    assert deterministic_source_filename(123) == "pexels-123-original.jpg"
    assert deterministic_candidate_filename(123, "edge24", 64) == "pexels-123-edge24-64.png"


def test_manifest_serialization_and_selection(tmp_path: Path) -> None:
    manifest = {
        "version": 1,
        "sources": [
            {
                "source": "pexels",
                "pexels_photo_id": 123,
                "photo_page_url": "https://example.test/photo",
                "photographer": "Tester",
                "photographer_url": "https://example.test/person",
                "original_image_url": "https://example.test/image.jpg",
                "selected_image_url": "https://example.test/large.jpg",
                "query": "test",
                "license_page": "https://www.pexels.com/license/",
                "original_width": 160,
                "original_height": 220,
                "local_source_filename": "pexels-123-original.jpg",
                "source_checksum_sha256": "abc",
                "processing_status": "downloaded",
            }
        ],
    }
    save_manifest(tmp_path, manifest)
    loaded = load_manifest(tmp_path)
    update_selection(loaded, 123, "edge24", ["audit", "claimant", "audit"])
    save_manifest(tmp_path, loaded)
    selected = load_manifest(tmp_path)["sources"][0]["selected"]
    assert selected["variant"] == "edge24"
    assert selected["tags"] == ["audit", "claimant"]


def test_crop_bounds_are_square_and_inside_image() -> None:
    box = square_crop_box(160, 220, [50, 60, 70, 80], padding=2.0)
    left, top, right, bottom = box
    assert right - left == bottom - top
    assert 0 <= left < right <= 160
    assert 0 <= top < bottom <= 220


def test_processing_is_deterministic_and_palette_limited(tmp_path: Path) -> None:
    library = tmp_path / "portrait-library"
    source_dir = library / "sources"
    source_dir.mkdir(parents=True)
    source = source_dir / "pexels-123-original.jpg"
    make_fixture_image(source)
    settings = CandidateSettings(size=48, review_scale=2)

    process_source(source, 123, library, settings, ["clean16", "clean24", "dither24", "edge24"])
    first = digest(library / "candidates" / "pexels-123-clean16-48.png")
    process_source(source, 123, library, settings, ["clean16", "clean24", "dither24", "edge24"])
    second = digest(library / "candidates" / "pexels-123-clean16-48.png")

    assert first == second
    assert palette_color_count(library / "candidates" / "pexels-123-clean16-48.png") <= 16
    assert palette_color_count(library / "candidates" / "pexels-123-clean24-48.png") <= 24
    assert (library / "crops" / "pexels-123-crop.png").exists()


def test_lookbook_generation_includes_failed_and_selected_entries(tmp_path: Path) -> None:
    library = tmp_path / "portrait-library"
    (library / "sources").mkdir(parents=True)
    (library / "crops").mkdir()
    (library / "candidates").mkdir()
    make_fixture_image(library / "sources" / "pexels-123-original.jpg")
    make_fixture_image(library / "crops" / "pexels-123-crop.png")
    make_fixture_image(library / "candidates" / "pexels-123-edge24-64.png")
    manifest = {
        "version": 1,
        "sources": [
            {
                "pexels_photo_id": 123,
                "photo_page_url": "https://www.pexels.com/photo/example-123/",
                "photographer": "Tester",
                "photographer_url": "https://example.test/person",
                "query": "hat",
                "original_width": 160,
                "original_height": 220,
                "local_source_filename": "pexels-123-original.jpg",
                "crop_filename": "crops/pexels-123-crop.png",
                "processing_status": "processed",
                "selected": {"variant": "edge24", "tags": ["audit"]},
                "candidates": [
                    {
                        "variant": "edge24",
                        "filename": "candidates/pexels-123-edge24-64.png",
                        "logical_size": 64,
                        "colors": 24,
                    }
                ],
            },
            {
                "pexels_photo_id": 456,
                "photographer": "Failed",
                "query": "stern",
                "original_width": 160,
                "original_height": 220,
                "processing_status": "failed",
                "processing_error": "bad image",
            },
        ],
    }
    (library / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    out = generate_lookbook(library)
    text = out.read_text(encoding="utf-8")
    assert "Pexels 123" in text
    assert "edge24" in text
    assert "audit" in text
    assert "Failed: bad image" in text

