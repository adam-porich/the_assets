from __future__ import annotations

import argparse
from pathlib import Path

from .imaging import process_source
from .lookbook import generate_lookbook
from .manifest import (
    DEFAULT_VARIANTS,
    CandidateSettings,
    find_source,
    load_manifest,
    save_manifest,
    update_selection,
)
from .pexels import download_candidate, is_plausible_portrait, search_pexels


def library_dirs(root: Path) -> None:
    for name in ("sources", "crops", "candidates", "lookbook"):
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

    lookbook = sub.add_parser("lookbook")
    lookbook.add_argument("--input", default="portrait-library")
    lookbook.set_defaults(func=cmd_lookbook)

    select = sub.add_parser("select")
    select.add_argument("--input", default="portrait-library")
    select.add_argument("--photo-id", required=True)
    select.add_argument("--variant", required=True)
    select.add_argument("--tag", action="append")
    select.set_defaults(func=cmd_select)

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
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

