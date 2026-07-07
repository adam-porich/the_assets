from __future__ import annotations

import html
import shutil
from pathlib import Path
from typing import Any


def _rel(path: str) -> str:
    return "../" + path.replace("\\", "/")


def _figure(path: str | None, caption: str, css_class: str = "") -> str:
    if not path:
        return ""
    klass = f' class="{css_class}"' if css_class else ""
    return f'<figure{klass}><img src="{html.escape(_rel(path))}" alt="{html.escape(caption)}"><figcaption>{html.escape(caption)}<br>{html.escape(path)}</figcaption></figure>'


def _score_table(scores: dict) -> str:
    if not scores:
        return ""
    rows = []
    for name, score in scores.items():
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(name))}</td>"
            f"<td>{score.get('likeness', '')}</td>"
            f"<td>{score.get('silhouette', '')}</td>"
            f"<td>{score.get('pixel_art_quality', '')}</td>"
            f"<td>{score.get('game_fit', '')}</td>"
            f"<td>{html.escape(str(score.get('manual_cleanup_needed', '')))}</td>"
            f"<td>{html.escape(str(score.get('notes', '')))}</td>"
            "</tr>"
        )
    return (
        '<table class="scores"><thead><tr><th>Pipeline</th><th>Likeness</th><th>Silhouette</th>'
        "<th>Pixel</th><th>Fit</th><th>Cleanup</th><th>Notes</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def generate_lookbook(library_dir: Path) -> Path:
    import json

    manifest = json.loads((library_dir / "manifest.json").read_text(encoding="utf-8"))
    lookbook_dir = library_dir / "lookbook"
    thumbs_dir = lookbook_dir / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    for entry in manifest.get("sources", []):
        photo_id = entry.get("pexels_photo_id")
        selected = entry.get("selected", {})
        selected_variant = selected.get("variant")
        status = html.escape(str(entry.get("processing_status", "unknown")))
        source_file = entry.get("local_source_filename")
        source_img = ""
        if source_file:
            source_path = library_dir / "sources" / source_file
            if source_path.exists():
                thumb_name = f"pexels-{photo_id}-source.jpg"
                shutil.copyfile(source_path, thumbs_dir / thumb_name)
                source_img = f'<img src="thumbnails/{thumb_name}" alt="source {photo_id}">'
        crop = entry.get("crop_filename")
        crop_img = f'<img src="{html.escape(_rel(crop))}" alt="crop {photo_id}">' if crop else ""
        candidates = []
        for candidate in entry.get("candidates", []):
            variant = candidate["variant"]
            klass = "candidate selected" if variant == selected_variant else "candidate"
            candidates.append(
                f'<figure class="{klass}"><img src="{html.escape(_rel(candidate["filename"]))}" '
                f'alt="{html.escape(variant)}"><figcaption>{html.escape(variant)}<br>'
                f'{candidate.get("logical_size")}px / {candidate.get("colors")} colours<br>'
                f'{html.escape(candidate["filename"])}</figcaption></figure>'
            )
        tags = ", ".join(selected.get("tags", []))
        failed = ""
        if entry.get("processing_error"):
            failed = f'<p class="error">Failed: {html.escape(str(entry["processing_error"]))}</p>'
        benchmarks = []
        for benchmark in entry.get("background_benchmarks", []):
            mode = benchmark.get("mode")
            bench_candidates = []
            for candidate in benchmark.get("candidates", []):
                label = f"{mode} {candidate.get('variant')}"
                klass = "candidate selected" if candidate.get("variant") == selected_variant else "candidate"
                bench_candidates.append(_figure(candidate.get("filename"), label, klass))
            error = f'<p class="error">Failed: {html.escape(str(benchmark.get("error")))}</p>' if benchmark.get("error") else ""
            benchmarks.append(
                f"""
                <div class="benchmark">
                  <h3>{html.escape(str(mode))} background removal</h3>
                  <p>Duration: {benchmark.get('elapsed_seconds', '')}s</p>
                  {error}
                  <div class="images">
                    {_figure(benchmark.get('mask'), f'{mode} mask', 'mask')}
                    {_figure(benchmark.get('transparent_foreground'), f'{mode} transparent')}
                    {_figure(benchmark.get('neutral_background'), f'{mode} neutral')}
                    {''.join(bench_candidates)}
                  </div>
                </div>
                """
            )
        scores = _score_table(entry.get("scores", {}))
        rows.append(
            f"""
            <section class="source {'is-selected' if selected else ''}">
              <div class="meta">
                <h2>Pexels {photo_id}</h2>
                <p><a href="{html.escape(str(entry.get('photo_page_url') or '#'))}">source photo</a>
                by <a href="{html.escape(str(entry.get('photographer_url') or '#'))}">{html.escape(str(entry.get('photographer') or 'unknown'))}</a></p>
                <p>Query: {html.escape(str(entry.get('query') or ''))}</p>
                <p>Dimensions: {entry.get('original_width')} x {entry.get('original_height')}</p>
                <p>Status: {status}</p>
                <p>Selected: {html.escape(str(selected_variant or 'none'))} {html.escape(tags)}</p>
                {failed}
                {scores}
              </div>
              <div class="images">
                <figure>{source_img}<figcaption>source</figcaption></figure>
                <figure>{crop_img}<figcaption>crop</figcaption></figure>
                {''.join(candidates)}
              </div>
              <div class="benchmarks">
                {''.join(benchmarks)}
              </div>
            </section>
            """
        )
    html_text = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Portrait Candidate Lookbook</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; background: #f6f1e8; color: #211c18; }}
h1 {{ margin-bottom: 8px; }}
.note {{ color: #64594f; }}
.source {{ border-top: 1px solid #c8b9a8; padding: 20px 0; display: grid; grid-template-columns: 260px 1fr; gap: 18px; }}
.source.is-selected {{ background: #fff7d6; outline: 2px solid #b38b00; padding-left: 10px; }}
.meta p {{ margin: 6px 0; }}
.images {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-start; }}
.benchmarks {{ grid-column: 1 / -1; }}
.benchmark {{ margin-top: 14px; padding-top: 10px; border-top: 1px dashed #c8b9a8; }}
.benchmark h3 {{ margin: 0 0 4px; }}
figure {{ margin: 0; max-width: 280px; }}
img {{ image-rendering: pixelated; max-width: 256px; max-height: 256px; object-fit: contain; background: #ddd0c0; }}
.mask img {{ image-rendering: auto; }}
figcaption {{ font-size: 12px; color: #64594f; overflow-wrap: anywhere; }}
.candidate.selected img {{ outline: 4px solid #b38b00; }}
.error {{ color: #9b241d; font-weight: 700; }}
.scores {{ border-collapse: collapse; margin-top: 10px; font-size: 12px; }}
.scores th, .scores td {{ border: 1px solid #c8b9a8; padding: 3px 5px; text-align: left; }}
@media (max-width: 800px) {{ .source {{ grid-template-columns: 1fr; }} }}
</style>
<h1>Portrait Candidate Lookbook</h1>
<p class="note">Experimental provenance-only review. Do not treat metadata as permanent licensing proof.</p>
{''.join(rows)}
</html>
"""
    out = lookbook_dir / "index.html"
    out.write_text(html_text, encoding="utf-8")
    return out
