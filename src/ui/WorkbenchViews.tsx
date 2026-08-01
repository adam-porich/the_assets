import { useEffect, useState, type ChangeEvent } from "react";
import { api } from "./api";
import type { Bootstrap, Framing, Model, PipelineStyle, ProductionBatch, ProductionItem, SearchResult } from "./types";

type Notice = (message: string, kind?: "success" | "error") => void;
type Shared = { bootstrap: Bootstrap; navigate: (hash: string) => void; refresh: () => Promise<void>; notify: Notice };

function formatCost(value: number | null | undefined) {
  return value == null ? "Cost returned by provider" : value === 0 ? "$0 simulation" : `$${value.toFixed(4)}`;
}
function modelCost(model: Model | undefined) { return formatCost(model?.pricing?.[0]?.cost_usd as number | undefined); }

export function SourcesView({ bootstrap, navigate, refresh, notify }: Shared) {
  const [selected, setSelected] = useState(bootstrap.selected_source_ids);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [busy, setBusy] = useState("");
  const style = bootstrap.style.active;
  const model = bootstrap.models.find((entry) => entry.id === style.generation.model_id && entry.execution_mode === style.generation.execution_mode);
  const activeBatch = bootstrap.batches.find((batch) => ["queued", "running", "processing"].includes(batch.status));
  const referenceCount = style.reference_pack.assets.filter((asset) => asset.role === "generation-reference").length;
  useEffect(() => setSelected(bootstrap.selected_source_ids), [bootstrap.selected_source_ids.join(",")]);

  async function saveSelection(next: string[]) {
    setSelected(next);
    try { await api.updateSelection(next); } catch (error) { notify((error as Error).message, "error"); }
  }
  async function search() {
    if (!query.trim()) return;
    setBusy("search");
    try { setResults((await api.searchSources(query)).results); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy("upload");
    try { await api.uploadSource(file, file.name.replace(/\.[^.]+$/, "")); await refresh(); notify("Source image uploaded"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); event.target.value = ""; }
  }
  async function makeCards() {
    if (!selected.length || !model) return;
    const live = style.generation.execution_mode === "live";
    if (live && !window.confirm(`Generate ${selected.length} neutral portrait master${selected.length === 1 ? "" : "s"} with ${model.name}? This uses ${selected.length} paid image call${selected.length === 1 ? "" : "s"}.`)) return;
    setBusy("make");
    try {
      const response = await api.createProduction(selected, style.identity.style_version_id, live);
      notify("Neutral portrait generation started");
      navigate(`#cards/${response.batch.batch_id}`);
      await refresh();
    } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  const problem = !selected.length
    ? "Select at least one source image."
    : activeBatch
      ? "A generation batch is already active."
      : style.generation.execution_mode !== "live"
        ? "This style is simulation-only and can make preview cards in Style Studio, but cannot run production."
        : !model
          ? "The active live model is not in the current capability catalogue."
          : !model.available
            ? "The selected live model is unavailable; choose an available model in Style Studio."
            : !model.credentials_configured
              ? "OPENROUTER_API_KEY is missing; configure live image generation before making cards."
              : model.max_input_references < 1 + referenceCount
                ? `The active model accepts ${model.max_input_references} references, but this style needs ${1 + referenceCount}. Reduce the ordered style references or choose another model.`
                : model.qualities.length > 0 && !model.qualities.includes(style.generation.quality)
                  ? `The active model does not support ${style.generation.quality} quality.`
                  : "";

  return <section className="page sources-page">
    <div className="page-heading">
      <div><p className="eyebrow">Sources</p><h2>Choose the images that become cards</h2><p>Select and order portrait sources. Each selected source is redrawn as a calm, neutral Amiga portrait before card assembly.</p></div>
      <span className="status-chip">{selected.length} selected</span>
    </div>
    <section className="surface source-management">
      <div className="panel-heading"><div><p className="eyebrow">Add source images</p><h3>Project library</h3></div><label className="button secondary file-button">Upload image<input aria-label="Upload source image" type="file" accept="image/*" onChange={upload} /></label></div>
      <form className="search-row" onSubmit={(event) => { event.preventDefault(); void search(); }}><input aria-label="Search source images" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search Pexels portraits" /><button className="button secondary" disabled={busy === "search"}>{busy === "search" ? "Searching…" : "Search"}</button></form>
      {results.length > 0 && <div className="search-results">{results.map((result) => <article key={result.pexels_photo_id}><img src={result.preview_url || result.selected_image_url} alt={result.label || result.photographer || "Search result"} /><div><strong>{result.photographer || "Portrait source"}</strong><button className="button secondary" onClick={() => void api.importSources([result]).then(() => refresh()).then(() => notify("Source image added")).catch((error) => notify((error as Error).message, "error"))}>Add source</button></div></article>)}</div>}
    </section>
    <section className="source-library">
      {bootstrap.sources.length === 0 ? <div className="surface empty-panel"><span className="empty-glyph">＋</span><h3>No source images yet</h3><p>Add an upload or search Pexels above. Nothing is sent to a generation provider until you make cards.</p></div> : <div className="source-grid">{bootstrap.sources.map((source) => { const order = selected.indexOf(source.id); return <article className={`surface source-tile ${order >= 0 ? "selected" : ""}`} key={source.id}><button className="source-select" aria-pressed={order >= 0} onClick={() => void saveSelection(order >= 0 ? selected.filter((id) => id !== source.id) : [...selected, source.id])}>{source.image_url && <img src={source.image_url} alt={source.label} />}<span>{source.label}</span>{order >= 0 && <b>#{order + 1}</b>}</button><button className="text-button danger" onClick={async () => { if (!window.confirm(`Delete ${source.label}?`)) return; try { await api.deleteSource(source.id); await refresh(); notify("Source removed"); } catch (error) { notify((error as Error).message, "error"); } }}>Remove</button></article>; })}</div>}
    </section>
    <section className="surface make-cards-panel">
      <div><p className="eyebrow">Active house style</p><h3>{style.identity.label}</h3><p><strong>{style.generation.execution_mode === "live" ? "Live image generation" : "Simulation preview"}</strong> · {model?.name || style.generation.model_id} · {selected.length} call{selected.length === 1 ? "" : "s"} · {modelCost(model)}</p><p className="muted">Source image first for identity evidence, then {referenceCount} ordered house-style reference{referenceCount === 1 ? "" : "s"}. The target example is review-only.</p></div>
      <button className="button primary large" disabled={Boolean(problem) || Boolean(busy) || Boolean(activeBatch)} onClick={() => void makeCards()}>{busy === "make" ? "Starting…" : `Make ${selected.length} card${selected.length === 1 ? "" : "s"} with ${style.identity.label}`}</button>
      {problem && <p className="validation-note" role="status">{problem}</p>}
    </section>
  </section>;
}

function latestItems(batch: ProductionBatch, selectedIds: string[]) {
  return selectedIds.map((sourceId) => batch.items?.filter((item) => item.source_id === sourceId).sort((a, b) => b.attempt_number - a.attempt_number)[0]).filter(Boolean).sort((a, b) => Number(b.status === "ready") - Number(a.status === "ready")) as ProductionItem[];
}
function phaseLabel(item: ProductionItem) {
  if (item.phase === "redrawing neutral portrait" || item.status === "generating") return "Redrawing neutral portrait…";
  if (item.phase === "applying Amiga rendering and assembling card" || item.status === "processing") return "Applying Amiga rendering and assembling card…";
  if (item.status === "queued") return "Queued for neutral redraw";
  if (item.status === "failed") return "Generation failed";
  if (item.status === "interrupted") return "Generation interrupted";
  return "Finished card ready for review";
}

function Provenance({ item, batch }: { item: ProductionItem; batch: ProductionBatch }) {
  const refs = item.reference_stack.filter((reference) => reference.role === "generation-reference");
  return <details>
    <summary>How this was made</summary>
    <div className="details-content">
      <p>Source identity: {item.source_url ? <a href={item.source_url}>original source</a> : "—"} · canonical master: {item.master_url ? <a href={item.master_url}>inspect master</a> : "—"}</p>
      <p>Amiga art: {item.art_url ? <a href={item.art_url}>336×276 PNG</a> : "—"} · card: {item.card_url ? <a href={item.card_url}>420×600 PNG</a> : "—"}</p>
      <p>Generation: <strong>{String(item.generation?.execution_mode || batch.model_capabilities?.execution_mode || "unknown")}</strong> · {String(item.generation?.model || batch.model?.name || batch.style_version_id)}</p>
      <p>Ordered generation references: {refs.length ? refs.map((reference, index) => <span key={String(reference.reference_id || index)}> {index ? "→ " : ""}{reference.url ? <a href={String(reference.url)}>{String(reference.label || reference.reference_id)}</a> : String(reference.label || reference.reference_id)}</span>) : "—"}</p>
      <p>Style checksum: <code>{batch.style_checksum_sha256}</code> · render revision {item.render_revision} · card checksum <code>{item.card_checksum_sha256 || "—"}</code></p>
      <p>The target example is review-only and was excluded from the provider request.</p>
    </div>
  </details>;
}

export function CardsView({ bootstrap, navigate, refresh, notify, batchId, cardId }: Shared & { batchId?: string; cardId?: string }) {
  const [batch, setBatch] = useState<ProductionBatch | undefined>();
  const [busy, setBusy] = useState("");
  const [framing, setFraming] = useState<Framing>({ zoom: 1, offset_x: 0, offset_y: 0 });
  const selectedBatch = bootstrap.batches.find((candidate) => candidate.batch_id === batchId)
    || bootstrap.batches.find((candidate) => candidate.status === "ready")
    || bootstrap.batches.find((candidate) => candidate.purpose === "card-production");
  useEffect(() => { if (selectedBatch) void api.getProduction(selectedBatch.batch_id).then((response) => setBatch(response.batch)).catch((error) => notify(error.message, "error")); }, [selectedBatch?.batch_id]);
  useEffect(() => { if (!batch || !["queued", "running", "processing"].includes(batch.status)) return; const timer = window.setInterval(() => void api.getProduction(batch.batch_id).then((response) => setBatch(response.batch)).catch(() => undefined), 800); return () => window.clearInterval(timer); }, [batch?.batch_id, batch?.status]);
  const current = batch;
  const items = current ? latestItems(current, current.selected_source_ids) : [];
  const card = items.find((item) => item.item_id === cardId);
  const live = current?.model_capabilities?.execution_mode === "live";
  async function refreshBatch() { if (!current) return; setBatch((await api.getProduction(current.batch_id)).batch); await refresh(); }
  async function approve(item: ProductionItem) { if (!current) return; setBusy(item.item_id); try { await api.approve(current.batch_id, item.item_id); notify("Card approved"); await refreshBatch(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }
  async function tryAnother(item: ProductionItem) { if (!current) return; if (live && !window.confirm("Try another makes one additional paid neutral-portrait generation attempt for this source. Continue?")) return; setBusy(item.item_id); try { await api.tryAnother(current.batch_id, item.source_id, live); notify("Another generation attempt queued"); await refreshBatch(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }
  async function render(item: ProductionItem) { if (!current) return; setBusy(`render-${item.item_id}`); try { await api.renderFraming(current.batch_id, item.item_id, framing); notify("Framing saved without a generation call"); await refreshBatch(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }
  async function bundle() { if (!current) return; setBusy("bundle"); try { const result = await api.bundle(current.batch_id); const link = document.createElement("a"); link.href = result.download_url; link.download = "approved-cards.zip"; link.click(); notify("Approved card bundle downloaded"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }
  if (!current) return <section className="page cards-page"><div className="empty-panel surface">{selectedBatch ? <><span className="spinner" /><p>Loading card production…</p></> : <><h2>No card batch yet</h2><p>Select source images and make cards to see finished candidates here.</p><button className="button primary" onClick={() => navigate("#sources")}>Choose source images</button></>}</div></section>;
  const ready = current.progress.ready_cards; const approved = current.progress.approved_cards;
  const batchLabel = current.purpose === "style-trial" ? "Live style trial" : "Production batch";
  const styleLabel = current.style_snapshot?.identity.label || current.style_version_id;
  return <section className="page cards-page"><div className="page-heading"><div><p className="eyebrow">Cards</p><h2>Review finished cards</h2><p>{batchLabel} · {styleLabel} · {formatCost(current.cost_usd)} · {current.progress.paid_calls} generation call{current.progress.paid_calls === 1 ? "" : "s"}</p></div><div className="heading-actions"><span className="status-chip">{ready} / {current.progress.selected_sources} ready</span>{current.status === "ready" && <button className="button primary" disabled={busy === "bundle" || approved !== current.progress.selected_sources} onClick={() => void bundle()}>Download approved cards</button>}</div></div><div className="batch-progress surface"><strong>{approved} / {current.progress.selected_sources} approved</strong><span className="progress-track"><i style={{ width: `${current.progress.selected_sources ? (ready / current.progress.selected_sources) * 100 : 0}%` }} /></span><small>{current.status === "ready" ? "Every source has a final card." : current.status === "ready-with-errors" ? "Some sources failed; ready cards remain reviewable." : current.items.some((item) => item.status === "processing") ? "Masters are being converted into Amiga art and cards." : `Production is ${current.status}.`}</small>{current.status === "ready-with-errors" && <button className="button secondary" onClick={async () => { if (live && !window.confirm("Retry failed sources with new paid generation calls?")) return; setBusy("retry"); try { await api.retryFailed(current.batch_id, live); notify("Failed sources queued for retry"); await refreshBatch(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }}>{busy === "retry" ? "Retrying…" : "Retry failed"}</button>}</div><div className="card-groups">{items.map((item) => <article className={`card-slot surface ${card?.item_id === item.item_id ? "focused" : ""}`} key={item.item_id}><header><div><p className="eyebrow">{item.source_label}</p><h3>Attempt {item.attempt_number}</h3></div><span className={`status-chip ${item.status}`}>{item.status}</span></header>{item.card_url ? <button className="card-image-button" onClick={() => navigate(`#cards/${current.batch_id}/${item.item_id}`)}><img className="final-card-image" src={item.card_url} alt={`${item.source_label} finished card`} /></button> : <div className="card-placeholder"><span className="spinner" />{phaseLabel(item)}{item.error && <small>{item.error}</small>}</div>}<p className="phase-label">{phaseLabel(item)}</p><div className="card-actions">{item.status === "ready" && <><button className="button primary" disabled={busy === item.item_id} onClick={() => void approve(item)}>Approve card</button><button className="button secondary" disabled={Boolean(busy)} onClick={() => void tryAnother(item)}>Try another <small>{live ? "paid" : "preview"}</small></button><button className="button secondary" disabled={Boolean(busy)} onClick={() => { setFraming(item.framing || { zoom: 1, offset_x: 0, offset_y: 0 }); navigate(`#cards/${current.batch_id}/${item.item_id}`); }}>Adjust framing <small>no generation</small></button></>}{item.error && <button className="button secondary" onClick={async () => { if (live && !window.confirm("Retry this failed source with a new paid generation call?")) return; try { await api.retryFailed(current.batch_id, live); await refreshBatch(); } catch (error) { notify((error as Error).message, "error"); } }}>Retry failed</button>}</div><Provenance item={item} batch={current} /></article>)}</div>{card && <section className="surface framing-panel"><div className="panel-heading"><div><p className="eyebrow">Framing · {card.source_label}</p><h3>Adjust the existing master</h3><p>Saving this rerenders art and card deterministically. It makes zero generation calls.</p></div><button className="button secondary" onClick={() => navigate(`#cards/${current.batch_id}`)}>Close</button></div><img className="framing-preview" src={card.card_url} alt="Live framing preview" /><div className="framing-controls"><label>Zoom<input type="range" min="1" max="3" step="0.01" value={framing.zoom} onChange={(event) => setFraming({ ...framing, zoom: Number(event.target.value) })} /></label><label>Horizontal<input type="range" min="-1" max="1" step="0.01" value={framing.offset_x} onChange={(event) => setFraming({ ...framing, offset_x: Number(event.target.value) })} /></label><label>Vertical<input type="range" min="-1" max="1" step="0.01" value={framing.offset_y} onChange={(event) => setFraming({ ...framing, offset_y: Number(event.target.value) })} /></label></div><button className="button primary" disabled={busy === `render-${card.item_id}`} onClick={() => void render(card)}>{busy === `render-${card.item_id}` ? "Saving…" : "Save framing"}</button></section>}</section>;
}

function directionText(style: PipelineStyle, field: string) { return style.generation.direction[field] || ""; }

export function StyleStudio({ bootstrap, navigate, refresh, notify }: Shared) {
  const [style, setStyle] = useState<PipelineStyle>(bootstrap.style.draft || bootstrap.style.active);
  const [cohort, setCohort] = useState<string[]>(bootstrap.selected_source_ids.slice(0, 3));
  const [trial, setTrial] = useState<ProductionBatch>();
  const [busy, setBusy] = useState("");
  const active = bootstrap.style.active;
  const draft = bootstrap.style.draft;
  const generationRefs = style.reference_pack.assets.filter((asset) => asset.role === "generation-reference");
  const target = style.reference_pack.assets.find((asset) => asset.role === "target-example");
  const models = bootstrap.models.filter((model) => model.execution_mode === style.generation.execution_mode);
  const selectedModel = bootstrap.models.find((model) => model.id === style.generation.model_id && model.execution_mode === style.generation.execution_mode);
  useEffect(() => { if (draft) setStyle(draft); }, [draft?.identity.style_version_id, draft?.checksums.style_sha256]);
  async function beginEdit() { setBusy("draft"); try { const response = await api.createDraft(); setStyle(response.style); notify("Draft style ready"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }
  async function patch(patchValue: Partial<PipelineStyle>) { try { const response = await api.updateDraft(patchValue); setStyle(response.style); await refresh(); } catch (error) { notify((error as Error).message, "error"); } }
  async function patchGeneration(next: Partial<PipelineStyle["generation"]>) { await patch({ generation: { ...style.generation, ...next } }); }
  async function changeMode(mode: PipelineStyle["generation"]["execution_mode"]) { const next = bootstrap.models.find((model) => model.execution_mode === mode && model.available) || bootstrap.models.find((model) => model.execution_mode === mode); await patchGeneration({ execution_mode: mode, model_id: next?.id || style.generation.model_id }); }
  async function runTrial() { if (!selectedModel || !cohort.length) return; const live = style.generation.execution_mode === "live"; if (live && !window.confirm(`Run ${cohort.length} live style-trial call${cohort.length === 1 ? "" : "s"} with ${selectedModel.name}?`)) return; setBusy("trial"); try { const response = await api.runTrial(cohort, live); setTrial(response.batch); notify(live ? "Live cohort trial started" : "Simulation preview trial started"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }
  useEffect(() => { if (!trial || !["queued", "running", "processing"].includes(trial.status)) return; const timer = window.setInterval(() => void api.getProduction(trial.batch_id).then((response) => setTrial(response.batch)), 800); return () => window.clearInterval(timer); }, [trial?.batch_id, trial?.status]);
  async function activate() { if (!trial) return; setBusy("activate"); try { const response = await api.activateTrial(trial.batch_id); notify("New live style version activated"); await refresh(); setStyle(response.style.active); setTrial(undefined); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }
  async function uploadReference(event: ChangeEvent<HTMLInputElement>) { const file = event.target.files?.[0]; if (!file) return; setBusy("reference"); try { const response = await api.uploadDraftReference(file); setStyle(response.style); await refresh(); notify("Generation reference added"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); event.target.value = ""; } }
  async function moveReference(index: number, delta: number) { const nextIndex = index + delta; if (nextIndex < 0 || nextIndex >= generationRefs.length) return; const ordered = [...generationRefs]; [ordered[index], ordered[nextIndex]] = [ordered[nextIndex], ordered[index]]; const targetAsset = style.reference_pack.assets.find((asset) => asset.role === "target-example"); await patch({ reference_pack: { ...style.reference_pack, assets: targetAsset ? [...ordered, targetAsset] : ordered } }); }
  return <section className="page style-page">
    <div className="page-heading"><div><p className="eyebrow">Style Studio</p><h2>{active.identity.label}</h2><p>Control live versus simulation explicitly, inspect the reference pair, then test the complete neutral-master-to-card path on a small cohort.</p></div><button className="button secondary" onClick={() => navigate("#sources")}>Back to Sources</button></div>
    <section className="style-hero surface"><div><p className="eyebrow">Active version</p><h3>{active.identity.label}</h3><p><code>{active.identity.style_version_id}</code> · checksum <code>{active.checksums.style_sha256}</code> · <strong>{active.generation.execution_mode === "live" ? "live production" : "simulation preview only"}</strong></p></div><div className="palette-strip">{active.renderer.palette.map((colour) => <i key={colour} style={{ backgroundColor: colour }} title={colour} />)}</div></section>
    <div className="reference-columns"><section className="surface"><div className="panel-heading"><h3>Ordered generation references</h3><span>{generationRefs.length} / {style.generation.reference_limit - 1}</span></div><div className="reference-strip">{generationRefs.map((asset, index) => <figure key={asset.id}><img src={asset.image_url} alt={asset.label} /><figcaption>{index + 1}. {asset.label}</figcaption>{draft && <div><button className="text-button" disabled={index === 0} onClick={() => void moveReference(index, -1)}>Earlier</button><button className="text-button" disabled={index === generationRefs.length - 1} onClick={() => void moveReference(index, 1)}>Later</button></div>}</figure>)}</div>{draft && <label className="button secondary file-button">Add generation reference<input type="file" accept="image/*" onChange={uploadReference} /></label>}<p className="muted">The identity source is always sent first, followed by these references in order.</p></section><section className="surface target-example"><h3>Generation reference → Amiga target</h3><div className="reference-pair">{generationRefs[0]?.image_url && <figure><img src={generationRefs[0].image_url} alt="High-resolution generation reference" /><figcaption>Generation reference</figcaption></figure>}{target?.image_url && <figure><img src={target.image_url} alt={target.label} /><figcaption>Rendered target example</figcaption></figure>}</div><p><strong>Review only — target is never sent to the model.</strong> The pair documents the post-render appearance expected from the deterministic driver.</p></section></div>
    {!draft ? <section className="surface edit-callout"><h3>Keep the active version clear</h3><p>Production continues using {active.identity.label}. Create a separate draft before changing anything.</p><button className="button primary" disabled={busy === "draft"} onClick={() => void beginEdit()}>Edit as new version</button></section> : <>
      <section className="surface editor"><div className="panel-heading"><div><p className="eyebrow">Draft</p><h3>Neutralisation contract</h3></div><span className="status-chip">{style.identity.style_version_id}</span></div>
        <details open><summary>Generation and provider</summary><div className="form-grid"><label>Execution mode<select value={style.generation.execution_mode} onChange={(event) => void changeMode(event.target.value as PipelineStyle["generation"]["execution_mode"])}><option value="live">Live image generation</option><option value="simulation">Simulation preview</option></select></label><label>Capability-backed model<select value={style.generation.model_id} onChange={(event) => void patchGeneration({ model_id: event.target.value })}>{models.map((model) => <option key={model.id} value={model.id}>{model.name}{!model.available ? " · unavailable" : !model.credentials_configured && model.execution_mode === "live" ? " · missing key" : ""}</option>)}</select></label><label>Quality<select value={style.generation.quality} onChange={(event) => void patchGeneration({ quality: event.target.value as PipelineStyle["generation"]["quality"] })}><option>low</option><option>medium</option><option>high</option></select></label></div><p className="muted">{style.generation.execution_mode === "live" ? `${selectedModel?.name || style.generation.model_id} · ${selectedModel?.max_input_references || 0} input references · ${modelCost(selectedModel)}` : "Simulation output is a clearly labelled preview and cannot activate a production style."}</p></details>
        {(["identity_to_retain", "composition_to_normalize", "expression_pose_to_discard", "rendering_language"] as const).map((field) => <details key={field} open={field !== "rendering_language"}><summary>{field.replace(/_/g, " ")}</summary><textarea value={directionText(style, field)} onChange={(event) => setStyle({ ...style, generation: { ...style.generation, direction: { ...style.generation.direction, [field]: event.target.value } } })} onBlur={() => void patchGeneration({ direction: style.generation.direction })} /></details>)}
        <details><summary>Avoid</summary><textarea value={style.generation.avoid} onChange={(event) => setStyle({ ...style, generation: { ...style.generation, avoid: event.target.value } })} onBlur={() => void patchGeneration({ avoid: style.generation.avoid })} /></details>
        <details><summary>Amiga processing and card</summary><div className="form-grid"><label>Dither strength<input type="number" min="0" max="1" step="0.01" value={style.renderer.dither.strength} onChange={(event) => setStyle({ ...style, renderer: { ...style.renderer, dither: { ...style.renderer.dither, strength: Number(event.target.value) } } })} onBlur={() => void patch({ renderer: style.renderer })} /></label><label>Edge threshold<input type="number" min="0" max="1" step="0.01" value={style.renderer.dither.edge_threshold} onChange={(event) => setStyle({ ...style, renderer: { ...style.renderer, dither: { ...style.renderer.dither, edge_threshold: Number(event.target.value) } } })} onBlur={() => void patch({ renderer: style.renderer })} /></label><label>Centering Y<input type="number" min="0" max="1" step="0.01" value={style.composition.centering[1]} onChange={(event) => setStyle({ ...style, composition: { ...style.composition, centering: [style.composition.centering[0], Number(event.target.value)] } })} onBlur={() => void patch({ composition: style.composition })} /></label></div><p>Pixel-native {style.card_assembly.logical_card_size.join("×")} logical · {style.card_assembly.output_scale}× output · {style.card_assembly.driver_id}</p></details>
        <div className="draft-summary"><strong>Draft checksum</strong> <code>{style.checksums.style_sha256}</code></div>
      </section>
      <section className="surface trial-panel"><div className="panel-heading"><div><p className="eyebrow">Calibration cohort</p><h3>Test complete style</h3></div><span>{cohort.length} / 3 sources</span></div><div className="cohort-picker">{bootstrap.sources.map((source) => <button key={source.id} className={cohort.includes(source.id) ? "selected" : ""} aria-pressed={cohort.includes(source.id)} onClick={() => setCohort((current) => current.includes(source.id) ? current.filter((id) => id !== source.id) : current.length < 3 ? [...current, source.id] : current)}>{source.image_url && <img src={source.image_url} alt={source.label} />}<span>{source.label}</span></button>)}</div><p>{cohort.length} generation call{cohort.length === 1 ? "" : "s"} · {modelCost(selectedModel)}. Masters are immediately processed into final cards.</p><button className="button primary" disabled={!cohort.length || !selectedModel || Boolean(busy) || Boolean(trial) || !selectedModel.available || (style.generation.execution_mode === "live" && !selectedModel.credentials_configured)} onClick={() => void runTrial()}>{busy === "trial" ? "Starting…" : style.generation.execution_mode === "live" ? "Run live cohort trial" : "Run simulation preview trial"}</button>{trial && <div className="trial-result"><span className={`status-chip ${trial.status}`}>{trial.status}</span>{trial.items.map((item) => <img key={item.item_id} src={item.card_url} alt={`${item.source_label} trial card`} />)}{trial.status === "ready" && trial.model_capabilities?.execution_mode === "live" ? <button className="button primary" disabled={busy === "activate"} onClick={() => void activate()}>{busy === "activate" ? "Activating…" : "Make this the active style"}</button> : trial.status === "ready" && <p className="validation-note">Simulation preview complete. A live cohort trial is required before activation.</p>}</div>}</section>
    </>}
  </section>;
}
