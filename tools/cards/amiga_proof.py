from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .amiga import amiga_palette, load_amiga_style, render_amiga


def _slug(value: str) -> str:
    return "-".join(part for part in "".join(character.lower() if character.isalnum() else " " for character in value).split() if part) or "portrait"


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(resolved)


def build_proof(inputs: list[tuple[str, Path]], output_dir: Path) -> dict:
    style = load_amiga_style()
    style_label = style.get("identity", {}).get("label", style.get("label", "Amiga OCS Portrait"))
    records = []
    renders = []
    for label, path in inputs:
        with Image.open(path) as opened:
            master = ImageOps.exif_transpose(opened).convert("RGB")
        rendered = render_amiga(master, label)
        stem = _slug(label)
        logical_path = output_dir / f"{stem}-logical.png"
        art_path = output_dir / f"{stem}-art-2x.png"
        card_path = output_dir / f"{stem}-card-2x.png"
        _save(rendered.logical_art, logical_path)
        _save(rendered.art, art_path)
        _save(rendered.card, card_path)
        records.append({
            "label": label,
            "master_path": _portable_path(path),
            "master_checksum_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "logical_path": logical_path.name,
            "art_path": art_path.name,
            "card_path": card_path.name,
            "metadata": rendered.metadata,
        })
        renders.append((label, master, rendered.art, rendered.card))

    sheet_width = 1120
    row_height = 430
    header_height = 112
    sheet = Image.new("RGB", (sheet_width, header_height + row_height * len(renders)), "#111111")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text((30, 24), str(style_label).upper(), fill="#eeddcc", font=font)
    draw.text((30, 42), "IMG2IMG MASTER  >  FIXED OCS ART  >  PIXEL-NATIVE CARD", fill="#cc9933", font=font)
    draw.text((30, 60), "168x138 LOGICAL ART / SHARED 32-COLOUR 12-BIT PALETTE / ORDERED DITHER / 2X NEAREST", fill="#aabbcc", font=font)
    palette = amiga_palette(style)
    for index, colour in enumerate(palette):
        x = 30 + index * 29
        draw.rectangle((x, 82, x + 26, 101), fill=colour)

    for row, (label, master, art, card) in enumerate(renders):
        top = header_height + row * row_height
        draw.rectangle((18, top + 10, sheet_width - 18, top + row_height - 10), outline="#443322", width=2)
        draw.text((30, top + 24), label.upper(), fill="#eeddcc", font=font)
        draw.text((30, top + 42), "MASTER", fill="#778899", font=font)
        master_preview = ImageOps.fit(master, (300, 300), method=Image.Resampling.LANCZOS, centering=(0.5, 0.44))
        sheet.paste(master_preview, (30, top + 66))
        draw.text((370, top + 42), "FINAL ART / 2X", fill="#778899", font=font)
        sheet.paste(art, (370, top + 66))
        draw.text((746, top + 42), "FINAL CARD / LOGICAL PREVIEW", fill="#778899", font=font)
        card_preview = card.resize((280, 400), Image.Resampling.NEAREST)
        sheet.paste(card_preview, (746, top + 20))

    sheet_path = output_dir / "amiga-ocs-v1-pipeline-sheet.png"
    _save(sheet, sheet_path)

    card_columns = min(4, len(renders))
    card_rows = (len(renders) + card_columns - 1) // card_columns
    card_sheet = Image.new("RGB", (card_columns * 440 + 20, card_rows * 620 + 94), "#111111")
    card_draw = ImageDraw.Draw(card_sheet)
    card_draw.text((20, 20), "AMIGA OCS PORTRAIT V1 / FINAL SET", fill="#eeddcc", font=font)
    card_draw.text((20, 38), "ONE LOGICAL GRID / ONE 32-COLOUR PALETTE / ONE CARD SYSTEM", fill="#cc9933", font=font)
    for index, (_, _, _, card) in enumerate(renders):
        left = 20 + (index % card_columns) * 440
        top = 72 + (index // card_columns) * 620
        card_sheet.paste(card, (left, top))
    card_sheet_path = output_dir / "amiga-ocs-v1-card-set.png"
    _save(card_sheet, card_sheet_path)

    manifest = {
        "style": style,
        "items": records,
        "pipeline_review_sheet": sheet_path.name,
        "card_set_review_sheet": card_sheet_path.name,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"sheet": sheet_path, "card_sheet": card_sheet_path, "manifest": manifest_path, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an Amiga OCS house-style proof sheet from portrait masters.")
    parser.add_argument("--input", action="append", required=True, metavar="LABEL=PATH")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inputs = []
    for value in args.input:
        label, separator, path = value.partition("=")
        if not separator or not label.strip() or not path.strip():
            parser.error("--input must use LABEL=PATH")
        inputs.append((label.strip(), Path(path).resolve()))
    result = build_proof(inputs, args.output_dir.resolve())
    print(result["sheet"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
