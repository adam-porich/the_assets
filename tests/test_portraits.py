from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw

from tools.portraits.cli import cmd_background, load_env_file, load_env_files
from tools.portraits.imaging import (
    benchmark_background_source,
    classical_background_mask,
    palette_color_count,
    process_source,
    square_crop_box,
)
from tools.portraits.lookbook import generate_lookbook
from tools.portraits.manifest import (
    CandidateSettings,
    deterministic_candidate_filename,
    deterministic_source_filename,
    load_manifest,
    save_manifest,
    update_review_status,
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


def test_review_status_updates_and_clears(tmp_path: Path) -> None:
    manifest = {"version": 1, "sources": [{"pexels_photo_id": 123}]}
    update_review_status(manifest, 123, "favorite", "strong candidate")
    assert manifest["sources"][0]["review"]["status"] == "favorite"
    assert manifest["sources"][0]["review"]["note"] == "strong candidate"

    update_review_status(manifest, 123, "clear")

    assert "review" not in manifest["sources"][0]


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


def test_classical_background_benchmark_outputs_masks_and_candidates(tmp_path: Path) -> None:
    library = tmp_path / "portrait-library"
    source_dir = library / "sources"
    source_dir.mkdir(parents=True)
    source = source_dir / "pexels-123-original.jpg"
    make_fixture_image(source)
    settings = CandidateSettings(size=48, review_scale=2)

    results, face_box = benchmark_background_source(source, 123, library, settings, ["none", "classical"], ["clean16"])

    assert face_box is None
    assert [result.mode for result in results] == ["none", "classical"]
    assert results[0].error is None
    assert results[1].error is None
    assert (library / str(results[1].mask)).exists()
    assert (library / str(results[1].transparent_foreground)).exists()
    assert (library / str(results[1].neutral_background)).exists()
    assert (library / "candidates" / "pexels-123-classical-clean16-48.png").exists()
    assert palette_color_count(library / "candidates" / "pexels-123-classical-clean16-48.png") <= 16


def test_classical_mask_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "fixture.jpg"
    make_fixture_image(source)
    image = Image.open(source).convert("RGB")

    first = classical_background_mask(image)
    second = classical_background_mask(image)

    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    first.save(first_path)
    second.save(second_path)
    assert digest(first_path) == digest(second_path)


def test_background_command_merges_existing_modes(tmp_path: Path) -> None:
    library = tmp_path / "portrait-library"
    source_dir = library / "sources"
    source_dir.mkdir(parents=True)
    make_fixture_image(source_dir / "pexels-123-original.jpg")
    save_manifest(
        library,
        {
            "version": 1,
            "sources": [
                {
                    "pexels_photo_id": 123,
                    "local_source_filename": "pexels-123-original.jpg",
                    "background_benchmarks": [{"mode": "classical", "elapsed_seconds": 0.1}],
                }
            ],
        },
    )
    args = type(
        "Args",
        (),
        {
            "input": str(source_dir),
            "output": None,
            "variants": "clean16",
            "modes": "none",
            "size": 48,
            "review_scale": 2,
            "contrast": 1.08,
            "saturation": 0.95,
            "sharpness": 1.05,
            "crop_padding": 1.9,
            "palette": None,
            "photo_id": [],
        },
    )()

    cmd_background(args)

    entry = load_manifest(library)["sources"][0]
    assert [benchmark["mode"] for benchmark in entry["background_benchmarks"]] == ["classical", "none"]


def test_lookbook_generation_includes_failed_and_selected_entries(tmp_path: Path) -> None:
    library = tmp_path / "portrait-library"
    (library / "sources").mkdir(parents=True)
    (library / "crops").mkdir()
    (library / "candidates").mkdir()
    (library / "masks").mkdir()
    (library / "foregrounds").mkdir()
    (library / "backgrounds").mkdir()
    make_fixture_image(library / "sources" / "pexels-123-original.jpg")
    make_fixture_image(library / "crops" / "pexels-123-crop.png")
    make_fixture_image(library / "candidates" / "pexels-123-edge24-64.png")
    make_fixture_image(library / "candidates" / "pexels-123-classical-clean16-64.png")
    make_fixture_image(library / "backgrounds" / "pexels-123-classical-neutral.png")
    make_fixture_image(library / "foregrounds" / "pexels-123-classical-foreground.png")
    Image.new("L", (160, 220), 255).save(library / "masks" / "pexels-123-classical-mask.png")
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
                "review": {"status": "favorite", "note": "shortlist this"},
                "candidates": [
                    {
                        "variant": "edge24",
                        "filename": "candidates/pexels-123-edge24-64.png",
                        "logical_size": 64,
                        "colors": 24,
                    }
                ],
                "background_benchmarks": [
                    {
                        "mode": "classical",
                        "elapsed_seconds": 0.123,
                        "crop": "crops/pexels-123-benchmark-crop.png",
                        "mask": "masks/pexels-123-classical-mask.png",
                        "transparent_foreground": "foregrounds/pexels-123-classical-foreground.png",
                        "neutral_background": "backgrounds/pexels-123-classical-neutral.png",
                        "candidates": [
                            {
                                "background_mode": "classical",
                                "variant": "clean16",
                                "filename": "candidates/pexels-123-classical-clean16-64.png",
                                "logical_size": 64,
                                "colors": 16,
                            }
                        ],
                    }
                ],
                "scores": {
                    "classical/clean16": {
                        "likeness": 4,
                        "silhouette": 3,
                        "pixel_art_quality": 4,
                        "game_fit": 5,
                        "manual_cleanup_needed": "minor",
                        "notes": "good hat",
                    }
                },
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
    assert "Portrait picker" in text
    assert "data-filter=\"favorite\"" in text
    assert "uv run python -m tools.portraits favorite --photo-id 123" in text
    assert "badge-favorite" in text
    assert "shortlist this" in text
    assert "edge24" in text
    assert "audit" in text
    assert "Failed: bad image" in text
    assert "classical background removal" in text
    assert "Duration: 0.123s" in text
    assert "classical/clean16" in text
    assert "good hat" in text


def test_env_loader_does_not_override_exported_values(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('PEXELS_API_KEY="from-file"\nOTHER=value\n', encoding="utf-8")
    monkeypatch.setenv("PEXELS_API_KEY", "from-shell")
    os.environ.pop("OTHER", None)

    load_env_file(env_file, protected_keys={"PEXELS_API_KEY"})

    assert os.environ["PEXELS_API_KEY"] == "from-shell"
    assert os.environ["OTHER"] == "value"


def test_repo_env_overrides_home_env_but_not_shell(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    home.mkdir()
    repo.mkdir()
    (home / ".env").write_text("PEXELS_API_KEY=from-home\nOTHER=home\n", encoding="utf-8")
    (repo / ".env").write_text("PEXELS_API_KEY=from-repo\nOTHER=repo\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(repo)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.setenv("OTHER", "from-shell")

    load_env_files()

    assert os.environ["PEXELS_API_KEY"] == "from-repo"
    assert os.environ["OTHER"] == "from-shell"
