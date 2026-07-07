from __future__ import annotations

import argparse
import os
from dataclasses import asdict
from pathlib import Path

from .img2img import ExternalCommandBackend, load_preset, stylize_source
from .imaging import benchmark_background_source, process_source
from .lookbook import generate_lookbook
from .manifest import (
    DEFAULT_VARIANTS,
    CandidateSettings,
    find_source,
    load_manifest,
    save_manifest,
    update_review_status,
    update_selection,
)
from .pexels import download_candidate, is_plausible_portrait, search_pexels


def load_env_file(path: Path, protected_keys: set[str] | None = None, override: bool = False) -> None:
    if not path.exists():
        return
    protected_keys = protected_keys or set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in protected_keys and (override or key not in os.environ):
            os.environ[key] = value


def load_env_files() -> None:
    protected_keys = set(os.environ)
    load_env_file(Path.home() / ".env", protected_keys=protected_keys)
    load_env_file(Path(".env"), protected_keys=protected_keys, override=True)


def library_dirs(root: Path) -> None:
    for name in ("sources", "crops", "candidates", "lookbook", "masks", "foregrounds", "backgrounds", "composites", "stylized"):
        (root / name).mkdir(parents=True, exist_ok=True)


def cmd_fetch(args: argparse.Namespace) -> int:
    out = Path(args.output)
    library_dirs(out)
    candidates = search_pexels(args.query, args.count, args.orientation, args.page, args.per_page)
    filtered = [item for item in candidates if is_plausible_portrait(item)]
    if args.dry_run:
        for item in filtered:
            print(f"{item['pexels_photo_id']}: {item['photographer']} {item['photo_page_url']}")
        return 0
    manifest = load_manifest(out)
    for item in filtered:
        entry = download_candidate(item, out / "sources")
        manifest_entry = find_source(manifest, entry["pexels_photo_id"]) or {}
        manifest_entry.update(entry)
        if manifest_entry not in manifest.get("sources", []):
            manifest.setdefault("sources", []).append(manifest_entry)
    save_manifest(out, manifest)
    print(f"Downloaded {len(filtered)} source images into {out / 'sources'}")
    return 0


def source_entries(manifest: dict, input_path: Path, library_dir: Path) -> list[tuple[dict, Path]]:
    if input_path.is_dir() and input_path.name == "sources":
        entries = []
        for entry in manifest.get("sources", []):
            filename = entry.get("local_source_filename")
            if filename:
                entries.append((entry, input_path / filename))
        return entries
    if input_path.is_dir():
        return [(entry, library_dir / "sources" / entry["local_source_filename"]) for entry in manifest.get("sources", []) if entry.get("local_source_filename")]
    raise ValueError("--input must be the library directory or its sources directory")


def cmd_process(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    library_dir = Path(args.output) if args.output else (input_path.parent if input_path.name == "sources" else input_path)
    library_dirs(library_dir)
    manifest = load_manifest(library_dir)
    variants = [name.strip() for name in args.variants.split(",") if name.strip()]
    unknown = [name for name in variants if name not in DEFAULT_VARIANTS]
    if unknown:
        raise SystemExit(f"Unknown variants: {', '.join(unknown)}")
    settings = CandidateSettings(
        size=args.size,
        review_scale=args.review_scale,
        contrast=args.contrast,
        saturation=args.saturation,
        sharpness=args.sharpness,
        crop_padding=args.crop_padding,
        background=args.background,
        palette=args.palette,
    )
    for entry, source_path in source_entries(manifest, input_path, library_dir):
        try:
            result = process_source(source_path, int(entry["pexels_photo_id"]), library_dir, settings, variants, Path(args.palette) if args.palette else None)
            entry["crop_filename"] = result.crop
            entry["candidates"] = result.candidates
            entry["detected_face_box"] = result.face_box
            entry["processing_status"] = "processed"
            entry.pop("processing_error", None)
        except Exception as exc:  # keep processing the rest for review.
            entry["processing_status"] = "failed"
            entry["processing_error"] = str(exc)
    save_manifest(library_dir, manifest)
    print(f"Processed sources into {library_dir / 'candidates'}")
    return 0


def parse_variants(value: str) -> list[str]:
    variants = [name.strip() for name in value.split(",") if name.strip()]
    unknown = [name for name in variants if name not in DEFAULT_VARIANTS]
    if unknown:
        raise SystemExit(f"Unknown variants: {', '.join(unknown)}")
    return variants


def cmd_background(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    library_dir = Path(args.output) if args.output else (input_path.parent if input_path.name == "sources" else input_path)
    library_dirs(library_dir)
    manifest = load_manifest(library_dir)
    variants = parse_variants(args.variants)
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    unknown_modes = [mode for mode in modes if mode not in {"none", "model"}]
    if unknown_modes:
        raise SystemExit(f"Unknown background modes: {', '.join(unknown_modes)}")
    settings = CandidateSettings(
        size=args.size,
        review_scale=args.review_scale,
        contrast=args.contrast,
        saturation=args.saturation,
        sharpness=args.sharpness,
        crop_padding=args.crop_padding,
        background="none",
        palette=args.palette,
    )
    only_ids = {int(photo_id) for photo_id in args.photo_id} if args.photo_id else None
    for entry, source_path in source_entries(manifest, input_path, library_dir):
        photo_id = int(entry["pexels_photo_id"])
        if only_ids is not None and photo_id not in only_ids:
            continue
        results, face_box = benchmark_background_source(
            source_path,
            photo_id,
            library_dir,
            settings,
            modes,
            variants,
            Path(args.palette) if args.palette else None,
        )
        entry["detected_face_box"] = face_box
        existing = {
            benchmark.get("mode"): benchmark
            for benchmark in entry.get("background_benchmarks", [])
            if benchmark.get("mode")
        }
        for result in results:
            existing[result.mode] = asdict(result)
        entry["background_benchmarks"] = [existing[mode] for mode in sorted(existing)]
        entry["processing_status"] = "background-benchmarked"
    save_manifest(library_dir, manifest)
    print(f"Generated background benchmark artifacts in {library_dir}")
    return 0


def should_stylize_entry(entry: dict, args: argparse.Namespace) -> bool:
    if args.photo_id and int(entry.get("pexels_photo_id")) not in {int(photo_id) for photo_id in args.photo_id}:
        return False
    if args.selected_only and not entry.get("selected"):
        return False
    if args.review_status:
        status = (entry.get("review") or {}).get("status")
        if args.review_status == "unreviewed":
            return status is None
        if status != args.review_status:
            return False
    return True


def merge_stylized_candidates(entry: dict, new_records: list[dict]) -> None:
    existing = {
        record.get("candidate_id"): record
        for record in entry.get("stylized_candidates", [])
        if record.get("candidate_id")
    }
    for record in new_records:
        existing[record["candidate_id"]] = record
    entry["stylized_candidates"] = sorted(existing.values(), key=lambda item: (item.get("preset", ""), item.get("seed", 0)))


def cmd_stylize(args: argparse.Namespace) -> int:
    library_dir = Path(args.input)
    library_dirs(library_dir)
    manifest = load_manifest(library_dir)
    preset = load_preset(args.preset)
    if args.backend != "external":
        raise SystemExit(f"Unknown img2img backend: {args.backend}")
    try:
        backend = ExternalCommandBackend()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    processed = 0
    for entry, source_path in source_entries(manifest, library_dir, library_dir):
        if not should_stylize_entry(entry, args):
            continue
        if args.limit is not None and processed >= args.limit:
            break
        photo_id = int(entry["pexels_photo_id"])
        try:
            prep, records = stylize_source(
                source_path,
                photo_id,
                library_dir,
                preset,
                backend,
                crop_padding=args.crop_padding,
                seed=args.seed,
                count=args.count,
            )
            entry["stylization_prep"] = prep
            merge_stylized_candidates(entry, records)
            entry["processing_status"] = "stylized"
            entry.pop("stylization_error", None)
            processed += 1
        except Exception as exc:
            entry["processing_status"] = "stylize-failed"
            entry["stylization_error"] = str(exc)
    save_manifest(library_dir, manifest)
    print(f"Stylized {processed} source images")
    return 0


def cmd_lookbook(args: argparse.Namespace) -> int:
    out = generate_lookbook(Path(args.input))
    print(out)
    print(f'Open in Windows: explorer.exe "$(wslpath -w {out})"')
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    library_dir = Path(args.input)
    manifest = load_manifest(library_dir)
    update_selection(manifest, args.photo_id, args.variant, args.tag or [])
    save_manifest(library_dir, manifest)
    print(f"Selected Pexels {args.photo_id} variant {args.variant}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    library_dir = Path(args.input)
    manifest = load_manifest(library_dir)
    entry = find_source(manifest, args.photo_id)
    if entry is None:
        raise SystemExit(f"No source with Pexels photo id {args.photo_id}")
    scores = entry.setdefault("scores", {})
    scores[args.pipeline] = {
        "likeness": args.likeness,
        "silhouette": args.silhouette,
        "pixel_art_quality": args.pixel_art_quality,
        "game_fit": args.game_fit,
        "manual_cleanup_needed": args.manual_cleanup_needed,
        "notes": args.notes or "",
    }
    save_manifest(library_dir, manifest)
    print(f"Scored Pexels {args.photo_id} pipeline {args.pipeline}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    library_dir = Path(args.input)
    manifest = load_manifest(library_dir)
    update_review_status(manifest, args.photo_id, args.status, args.note or "")
    save_manifest(library_dir, manifest)
    print(f"Marked Pexels {args.photo_id} as {args.status}")
    return 0


def cmd_harvest(args: argparse.Namespace) -> int:
    cmd_fetch(args)
    if args.process:
        process_args = argparse.Namespace(**vars(args))
        process_args.input = str(Path(args.output) / "sources")
        process_args.variants = args.variants
        cmd_process(process_args)
    if args.lookbook:
        cmd_lookbook(argparse.Namespace(input=args.output))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.portraits")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_fetch_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--query", required=True)
        p.add_argument("--count", type=int, default=20)
        p.add_argument("--orientation", choices=["portrait", "landscape", "square"], default="portrait")
        p.add_argument("--page", type=int, default=1)
        p.add_argument("--per-page", type=int)
        p.add_argument("--output", default="portrait-library")
        p.add_argument("--dry-run", action="store_true")

    fetch = sub.add_parser("fetch")
    add_fetch_options(fetch)
    fetch.set_defaults(func=cmd_fetch)

    process = sub.add_parser("process")
    process.add_argument("--input", required=True)
    process.add_argument("--output")
    process.add_argument("--size", type=int, choices=[48, 64, 96], default=64)
    process.add_argument("--variants", default="clean16,clean24,dither24,edge24")
    process.add_argument("--review-scale", type=int, default=4)
    process.add_argument("--contrast", type=float, default=1.08)
    process.add_argument("--saturation", type=float, default=0.95)
    process.add_argument("--sharpness", type=float, default=1.05)
    process.add_argument("--crop-padding", type=float, default=1.9)
    process.add_argument("--background", choices=["keep", "flatten", "vignette"], default="keep")
    process.add_argument("--palette")
    process.set_defaults(func=cmd_process)

    background = sub.add_parser("background")
    background.add_argument("--input", required=True)
    background.add_argument("--output")
    background.add_argument("--photo-id", action="append", default=[])
    background.add_argument("--modes", default="model")
    background.add_argument("--size", type=int, choices=[48, 64, 96], default=64)
    background.add_argument("--variants", default="clean16,clean24,dither24,edge24")
    background.add_argument("--review-scale", type=int, default=4)
    background.add_argument("--contrast", type=float, default=1.08)
    background.add_argument("--saturation", type=float, default=0.95)
    background.add_argument("--sharpness", type=float, default=1.05)
    background.add_argument("--crop-padding", type=float, default=1.9)
    background.add_argument("--palette")
    background.set_defaults(func=cmd_background)

    stylize = sub.add_parser("stylize")
    stylize.add_argument("--input", default="portrait-library")
    stylize.add_argument("--preset", required=True)
    stylize.add_argument("--backend", default="external")
    stylize.add_argument("--photo-id", action="append", default=[])
    stylize.add_argument("--selected-only", action="store_true")
    stylize.add_argument("--review-status", choices=["favorite", "add", "reject", "unreviewed"])
    stylize.add_argument("--limit", type=int, default=3)
    stylize.add_argument("--count", type=int)
    stylize.add_argument("--seed", type=int)
    stylize.add_argument("--crop-padding", type=float, default=1.9)
    stylize.set_defaults(func=cmd_stylize)

    lookbook = sub.add_parser("lookbook")
    lookbook.add_argument("--input", default="portrait-library")
    lookbook.set_defaults(func=cmd_lookbook)

    select = sub.add_parser("select")
    select.add_argument("--input", default="portrait-library")
    select.add_argument("--photo-id", required=True)
    select.add_argument("--variant", required=True)
    select.add_argument("--tag", action="append")
    select.set_defaults(func=cmd_select)

    score = sub.add_parser("score")
    score.add_argument("--input", default="portrait-library")
    score.add_argument("--photo-id", required=True)
    score.add_argument("--pipeline", required=True, help="Candidate or pipeline label, e.g. estate-pixel-claimant-v1:12345")
    score.add_argument("--likeness", type=int, choices=range(1, 6), required=True)
    score.add_argument("--silhouette", type=int, choices=range(1, 6), required=True)
    score.add_argument("--pixel-art-quality", type=int, choices=range(1, 6), required=True)
    score.add_argument("--game-fit", type=int, choices=range(1, 6), required=True)
    score.add_argument("--manual-cleanup-needed", choices=["none", "minor", "major"], required=True)
    score.add_argument("--notes")
    score.set_defaults(func=cmd_score)

    review = sub.add_parser("review")
    review.add_argument("--input", default="portrait-library")
    review.add_argument("--photo-id", required=True)
    review.add_argument("--status", choices=["favorite", "reject", "add", "clear"], required=True)
    review.add_argument("--note")
    review.set_defaults(func=cmd_review)

    for status in ("favorite", "reject", "add"):
        alias = sub.add_parser(status)
        alias.add_argument("--input", default="portrait-library")
        alias.add_argument("--photo-id", required=True)
        alias.add_argument("--note")
        alias.set_defaults(func=cmd_review, status=status)

    harvest = sub.add_parser("harvest")
    add_fetch_options(harvest)
    harvest.add_argument("--process", action="store_true")
    harvest.add_argument("--lookbook", action="store_true")
    harvest.add_argument("--size", type=int, choices=[48, 64, 96], default=64)
    harvest.add_argument("--variants", default="clean16,clean24,dither24,edge24")
    harvest.add_argument("--review-scale", type=int, default=4)
    harvest.add_argument("--contrast", type=float, default=1.08)
    harvest.add_argument("--saturation", type=float, default=0.95)
    harvest.add_argument("--sharpness", type=float, default=1.05)
    harvest.add_argument("--crop-padding", type=float, default=1.9)
    harvest.add_argument("--background", choices=["keep", "flatten", "vignette"], default="keep")
    harvest.add_argument("--palette")
    harvest.set_defaults(func=cmd_harvest)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env_files()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
