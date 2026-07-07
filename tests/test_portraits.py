from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from tools.portraits.cli import cmd_background, cmd_stylize, load_env_file, load_env_files
from tools.portraits.img2img import ExternalCommandBackend, Img2ImgRequest, Img2ImgResult, OpenRouterBackend, load_preset, raw_candidate_path, stable_seed, stylize_source
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


def test_preset_loading() -> None:
    preset = load_preset("estate-pixel-claimant-v1")
    assert preset.name == "estate-pixel-claimant-v1"
    assert preset.background_mode == "neutral-dark"
    assert preset.candidate_count == 1
    assert preset.width == 384
    assert preset.height == 384
    assert preset.steps == 6
    assert "fantasy bureaucrat" in preset.prompt
    assert stable_seed(123, preset.name) == stable_seed(123, preset.name)


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


def test_background_command_rejects_classical_mode(tmp_path: Path) -> None:
    library = tmp_path / "portrait-library"
    source_dir = library / "sources"
    source_dir.mkdir(parents=True)
    save_manifest(library, {"version": 1, "sources": []})
    args = type(
        "Args",
        (),
        {
            "input": str(source_dir),
            "output": None,
            "variants": "clean16",
            "modes": "classical",
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

    try:
        cmd_background(args)
    except SystemExit as exc:
        assert "Unknown background modes: classical" in str(exc)
    else:
        raise AssertionError("classical mode should not be accepted by the normal CLI")


class FakeImg2ImgBackend:
    name = "fake"

    def generate(self, request):
        output = raw_candidate_path(Path(request.output_dir).parent, 123, request.preset, request.seed)
        make_fixture_image(output)
        return [
            Img2ImgResult(
                image_path=str(output),
                backend=self.name,
                model="fake-model",
                seed=request.seed,
                strength=request.strength,
                steps=request.steps,
                guidance=request.guidance,
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                elapsed_seconds=0.01,
            )
        ]


def test_stylize_source_records_img2img_metadata(tmp_path: Path, monkeypatch) -> None:
    library = tmp_path / "portrait-library"
    source_dir = library / "sources"
    source_dir.mkdir(parents=True)
    source = source_dir / "pexels-123-original.jpg"
    make_fixture_image(source)
    monkeypatch.setattr("tools.portraits.img2img.model_background_mask", lambda image: Image.new("L", image.size, 255))
    preset = load_preset("estate-pixel-claimant-v1")

    prep, records = stylize_source(source, 123, library, preset, FakeImg2ImgBackend(), seed=42, count=1)

    assert prep["mask_mode"] == "rembg"
    assert prep["background_mode"] == "neutral-dark"
    assert records[0]["candidate_id"] == "estate-pixel-claimant-v1:42"
    assert records[0]["backend"] == "fake"
    assert records[0]["model"] == "fake-model"
    assert records[0]["mask_mode"] == "rembg"
    assert records[0]["input_composite_path"].endswith("neutral-dark-composite.png")
    assert (library / records[0]["output_path"]).exists()
    assert (library / records[0]["final_output_path"]).exists()


def test_external_backend_serializes_request_and_parses_result(tmp_path: Path) -> None:
    output_dir = tmp_path / "stylized"
    output_dir.mkdir()
    script = tmp_path / "fake_backend.py"
    script.write_text(
        """
import json
import sys
from pathlib import Path
from PIL import Image
request_path = Path(sys.argv[-1])
request = json.loads(request_path.read_text())
out = Path(request["output_dir"]) / f'{request["output_base"]}-raw.png'
Image.new("RGB", (32, 32), "#44352f").save(out)
print(json.dumps({"results": [{
    "image_path": str(out),
    "backend": "external-test",
    "model": "tiny-test",
    "seed": request["seed"],
    "strength": request["strength"],
    "steps": request["steps"],
    "guidance": request["guidance"],
    "prompt": request["prompt"],
    "negative_prompt": request["negative_prompt"],
    "elapsed_seconds": 0.02
}]}))
""",
        encoding="utf-8",
    )
    request = Img2ImgRequest(
        input_image_path=str(tmp_path / "input.png"),
        prompt="prompt",
        negative_prompt="negative",
        seed=7,
        strength=0.4,
        steps=6,
        guidance=5,
        width=384,
        height=384,
        preset="preset-v1",
        count=1,
        output_dir=str(output_dir),
        output_base="candidate",
    )

    results = ExternalCommandBackend(f"{sys.executable} {script}").generate(request)

    saved_request = json.loads((output_dir / "candidate-request.json").read_text(encoding="utf-8"))
    assert saved_request["width"] == 384
    assert saved_request["count"] == 1
    assert results[0].backend == "external-test"
    assert results[0].model == "tiny-test"
    assert Path(results[0].image_path).exists()


def test_openrouter_backend_sends_reference_image_and_saves_result(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "input.png"
    make_fixture_image(input_path)
    output_dir = tmp_path / "stylized"
    output_dir.mkdir()
    captured = {}

    class Response:
        ok = True
        status_code = 200
        text = ""

        def json(self):
            encoded = Image.new("RGB", (16, 16), "#44352f")
            out = tmp_path / "response.png"
            encoded.save(out)
            import base64

            return {"data": [{"b64_json": base64.b64encode(out.read_bytes()).decode("ascii")}]}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("tools.portraits.img2img.requests.post", fake_post)
    request = Img2ImgRequest(
        input_image_path=str(input_path),
        prompt="prompt",
        seed=7,
        strength=0.4,
        steps=6,
        guidance=5,
        width=384,
        height=384,
        preset="preset-v1",
        count=1,
        output_dir=str(output_dir),
        output_base="candidate",
    )

    results = OpenRouterBackend(api_key="test-key").generate(request)

    assert captured["url"] == "https://openrouter.ai/api/v1/images"
    assert captured["json"]["model"] == "openai/gpt-image-1-mini"
    assert captured["json"]["quality"] == "low"
    assert captured["json"]["input_references"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert results[0].backend == "openrouter"
    assert results[0].model == "openai/gpt-image-1-mini"
    assert Path(results[0].image_path).exists()


def test_stylize_command_errors_when_backend_unconfigured(tmp_path: Path, monkeypatch) -> None:
    library = tmp_path / "portrait-library"
    source_dir = library / "sources"
    source_dir.mkdir(parents=True)
    make_fixture_image(source_dir / "pexels-123-original.jpg")
    save_manifest(library, {"version": 1, "sources": [{"pexels_photo_id": 123, "local_source_filename": "pexels-123-original.jpg"}]})
    monkeypatch.delenv("PORTRAIT_IMG2IMG_COMMAND", raising=False)
    args = type(
        "Args",
        (),
        {
            "input": str(library),
            "preset": "estate-pixel-claimant-v1",
            "backend": "external",
            "photo_id": ["123"],
            "selected_only": False,
            "review_status": None,
            "limit": None,
            "count": 1,
            "seed": None,
            "crop_padding": 1.9,
        },
    )()

    try:
        cmd_stylize(args)
    except SystemExit as exc:
        assert "PORTRAIT_IMG2IMG_COMMAND is not configured" in str(exc)
    else:
        raise AssertionError("stylize should fail clearly without a configured backend")


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
    (library / "stylized").mkdir()
    make_fixture_image(library / "stylized" / "pexels-123-estate-pixel-claimant-v1-42-raw.png")
    make_fixture_image(library / "stylized" / "pexels-123-estate-pixel-claimant-v1-42-final.png")
    (library / "composites").mkdir()
    make_fixture_image(library / "composites" / "pexels-123-neutral-dark-composite.png")
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
                "stylization_prep": {
                    "mask_mode": "rembg",
                    "background_mode": "neutral-dark",
                    "mask_path": "masks/pexels-123-classical-mask.png",
                    "transparent_foreground_path": "foregrounds/pexels-123-classical-foreground.png",
                    "composite_path": "composites/pexels-123-neutral-dark-composite.png",
                },
                "stylized_candidates": [
                    {
                        "candidate_id": "estate-pixel-claimant-v1:42",
                        "preset": "estate-pixel-claimant-v1",
                        "backend": "fake",
                        "model": "fake-model",
                        "seed": 42,
                        "strength": 0.45,
                        "steps": 10,
                        "guidance": 6,
                        "elapsed_seconds": 0.01,
                        "background_mode": "neutral-dark",
                        "mask_mode": "rembg",
                        "output_path": "stylized/pexels-123-estate-pixel-claimant-v1-42-raw.png",
                        "final_output_path": "stylized/pexels-123-estate-pixel-claimant-v1-42-final.png",
                    }
                ],
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
    assert "uv run --extra background python -m tools.portraits stylize --input portrait-library --preset estate-pixel-claimant-v1 --backend openrouter --photo-id 123" in text
    assert "badge-favorite" in text
    assert "shortlist this" in text
    assert "Img2img Candidates" in text
    assert "fake / fake-model" in text
    assert "rembg mask" in text
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
