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


def _copy_button(label: str, command: str, css_class: str = "") -> str:
    klass = f"copy-command {css_class}".strip()
    return (
        f'<button class="{html.escape(klass)}" type="button" '
        f'data-command="{html.escape(command, quote=True)}">{html.escape(label)}</button>'
    )


def _review_command(photo_id: int | str, status: str) -> str:
    return f"uv run python -m tools.portraits {status} --photo-id {photo_id}"


def _review_status(entry: dict[str, Any]) -> str:
    return str((entry.get("review") or {}).get("status") or "unreviewed")


def _review_badge(status: str) -> str:
    return f'<span class="badge badge-{html.escape(status)}">{html.escape(status)}</span>'


def _thumbnail_nav(manifest: dict[str, Any], thumbs_dir: Path, library_dir: Path) -> str:
    items = []
    for entry in manifest.get("sources", []):
        photo_id = entry.get("pexels_photo_id")
        status = _review_status(entry)
        source_file = entry.get("local_source_filename")
        thumb = ""
        if source_file:
            source_path = library_dir / "sources" / source_file
            if source_path.exists():
                thumb_name = f"pexels-{photo_id}-source.jpg"
                shutil.copyfile(source_path, thumbs_dir / thumb_name)
                thumb = f'<img src="thumbnails/{thumb_name}" alt="source {photo_id}">'
        items.append(
            f"""
            <a class="picker-card status-{html.escape(status)}" href="#photo-{photo_id}" data-status="{html.escape(status)}">
              {thumb}
              <span>Pexels {photo_id}</span>
              {_review_badge(status)}
            </a>
            """
        )
    return f'<nav class="picker" aria-label="Portrait picker">{"".join(items)}</nav>'


def generate_lookbook(library_dir: Path) -> Path:
    import json

    manifest = json.loads((library_dir / "manifest.json").read_text(encoding="utf-8"))
    lookbook_dir = library_dir / "lookbook"
    thumbs_dir = lookbook_dir / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    picker = _thumbnail_nav(manifest, thumbs_dir, library_dir)
    rows: list[str] = []
    for entry in manifest.get("sources", []):
        photo_id = entry.get("pexels_photo_id")
        selected = entry.get("selected", {})
        selected_variant = selected.get("variant")
        review = entry.get("review") or {}
        review_status = _review_status(entry)
        review_note = review.get("note") or ""
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
        command_bar = (
            '<div class="commands" aria-label="Review commands">'
            + _copy_button("Favorite", _review_command(photo_id, "favorite"), "favorite")
            + _copy_button("Reject", _review_command(photo_id, "reject"), "reject")
            + _copy_button("Add", _review_command(photo_id, "add"), "add")
            + _copy_button("Lookbook", "uv run python -m tools.portraits lookbook --input portrait-library")
            + "</div>"
        )
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
            <section id="photo-{photo_id}" class="source status-{html.escape(review_status)} {'is-selected' if selected else ''}" data-status="{html.escape(review_status)}">
              <div class="meta">
                <h2>Pexels {photo_id} {_review_badge(review_status)}</h2>
                <p><a href="{html.escape(str(entry.get('photo_page_url') or '#'))}">source photo</a>
                by <a href="{html.escape(str(entry.get('photographer_url') or '#'))}">{html.escape(str(entry.get('photographer') or 'unknown'))}</a></p>
                <p>Query: {html.escape(str(entry.get('query') or ''))}</p>
                <p>Dimensions: {entry.get('original_width')} x {entry.get('original_height')}</p>
                <p>Status: {status}</p>
                <p>Selected: {html.escape(str(selected_variant or 'none'))} {html.escape(tags)}</p>
                <p>Review note: {html.escape(str(review_note or ''))}</p>
                {command_bar}
                {failed}
                {scores}
              </div>
              <div class="stage stage-source">
                <h3>1. Source</h3>
                <div class="images">
                  <figure>{source_img}<figcaption>original source</figcaption></figure>
                  <figure>{crop_img}<figcaption>crop</figcaption></figure>
                </div>
              </div>
              <div class="stage stage-filter">
                <h3>3. Existing Filters</h3>
                <div class="images">
                  {''.join(candidates)}
                </div>
              </div>
              <div class="benchmarks">
                <h3>2. Background Removal, Then Derived Filters</h3>
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
.toolbar {{ position: sticky; top: 0; z-index: 10; margin: 0 -24px 18px; padding: 10px 24px; background: #efe5d7; border-bottom: 1px solid #c8b9a8; box-shadow: 0 2px 6px rgb(33 28 24 / 12%); }}
.filters {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }}
button {{ font: inherit; border: 1px solid #8f7d6a; background: #fff8ee; color: #211c18; border-radius: 6px; padding: 5px 9px; cursor: pointer; }}
button:hover, button.is-active {{ background: #2f2a27; color: #fff8ee; }}
.picker {{ display: flex; gap: 10px; overflow-x: auto; padding-bottom: 6px; scroll-snap-type: x proximity; }}
.picker-card {{ flex: 0 0 124px; display: grid; gap: 4px; color: inherit; text-decoration: none; border: 1px solid #c8b9a8; background: #fff8ee; border-radius: 6px; padding: 6px; scroll-snap-align: start; }}
.picker-card img {{ width: 110px; height: 88px; object-fit: cover; image-rendering: auto; }}
.picker-card span {{ font-size: 12px; overflow-wrap: anywhere; }}
.source {{ border-top: 1px solid #c8b9a8; padding: 20px 0; display: grid; grid-template-columns: 260px 1fr; gap: 18px; }}
.source.is-selected {{ background: #fff7d6; outline: 2px solid #b38b00; padding-left: 10px; }}
.source.is-hidden {{ display: none; }}
.meta p {{ margin: 6px 0; }}
.commands {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }}
.commands .favorite {{ border-color: #997400; }}
.commands .reject {{ border-color: #9b241d; }}
.commands .add {{ border-color: #356b37; }}
.badge {{ display: inline-block; font-size: 12px; font-weight: 700; border-radius: 999px; padding: 2px 7px; background: #d8cbbd; color: #211c18; vertical-align: middle; }}
.badge-favorite {{ background: #ffe18a; }}
.badge-reject {{ background: #e7aaa2; }}
.badge-add {{ background: #bfe3bb; }}
.badge-unreviewed {{ background: #d8cbbd; }}
.status-reject {{ opacity: 0.72; }}
.images {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-start; }}
.stage h3, .benchmarks > h3 {{ margin: 0 0 8px; }}
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
<div class="toolbar">
  <div class="filters" aria-label="Review filters">
    <button type="button" class="filter is-active" data-filter="all">All</button>
    <button type="button" class="filter" data-filter="favorite">Favorites</button>
    <button type="button" class="filter" data-filter="add">Added</button>
    <button type="button" class="filter" data-filter="reject">Rejected</button>
    <button type="button" class="filter" data-filter="unreviewed">Unreviewed</button>
  </div>
  {picker}
</div>
{''.join(rows)}
<script>
const filters = document.querySelectorAll('.filter');
const sources = document.querySelectorAll('.source');
const pickerCards = document.querySelectorAll('.picker-card');
for (const button of filters) {{
  button.addEventListener('click', () => {{
    const filter = button.dataset.filter;
    for (const item of filters) item.classList.toggle('is-active', item === button);
    for (const source of sources) source.classList.toggle('is-hidden', filter !== 'all' && source.dataset.status !== filter);
    for (const card of pickerCards) card.classList.toggle('is-hidden', filter !== 'all' && card.dataset.status !== filter);
  }});
}}
for (const button of document.querySelectorAll('.copy-command')) {{
  button.addEventListener('click', async () => {{
    const command = button.dataset.command;
    try {{
      await navigator.clipboard.writeText(command);
      button.textContent = 'Copied';
      window.setTimeout(() => button.textContent = button.dataset.command.includes('favorite') ? 'Favorite' : button.dataset.command.includes('reject') ? 'Reject' : button.dataset.command.includes(' add ') ? 'Add' : 'Lookbook', 900);
    }} catch (error) {{
      window.prompt('Copy command', command);
    }}
  }});
}}
</script>
</html>
"""
    out = lookbook_dir / "index.html"
    out.write_text(html_text, encoding="utf-8")
    return out
