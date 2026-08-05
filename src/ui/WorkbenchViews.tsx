import { useEffect, useState, type ChangeEvent } from "react";
import { api } from "./api";
import type { Bootstrap, Framing, InputAsset, Model, PipelineRecord, PipelineStyle, ProducedCard, ProductionBatch, SearchResult } from "./types";

type Notice = (message: string, kind?: "success" | "error") => void;
type Shared = { bootstrap: Bootstrap; navigate: (hash: string) => void; refresh: () => Promise<void>; notify: Notice };

function formatCost(value: number | null | undefined) {
  return value == null ? "provider-priced" : value === 0 ? "$0 simulation" : `$${value.toFixed(4)}`;
}
function modelCost(model: Model | undefined) { return formatCost(model?.pricing?.[0]?.cost_usd as number | undefined); }
function isActive(status: string) { return ["queued", "running", "processing"].includes(status); }
function shortChecksum(value: string) { return value.slice(0, 8); }
function selectedSources(bootstrap: Bootstrap) { return bootstrap.inputs; }

export function InputsView({ bootstrap, refresh, notify }: Shared) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState<InputAsset>();
  const [prompt, setPrompt] = useState(bootstrap.normalisation.default_prompt);
  const [quality, setQuality] = useState<"low" | "medium" | "high">(bootstrap.normalisation.default_quality);
  const pipeline = bootstrap.style.active;
  const model = bootstrap.models.find((entry) => entry.id === pipeline.generation.model_id && entry.execution_mode === pipeline.generation.execution_mode);
  const latest = editing?.normalisation_attempts?.slice(-1)[0];
  useEffect(() => {
    if (!editing || !latest || !isActive(latest.status)) return;
    const timer = window.setInterval(() => void api.getInput(editing.id).then(({ input }) => setEditing(input)).catch((error) => notify((error as Error).message, "error")), 800);
    return () => window.clearInterval(timer);
  }, [editing?.id, latest?.status]);
  function open(item: InputAsset) { setEditing(item); setPrompt(item.accepted_normalisation?.prompt || bootstrap.normalisation.default_prompt); setQuality(item.accepted_normalisation?.quality || bootstrap.normalisation.default_quality); }
  async function search() {
    if (!query.trim()) return;
    setBusy("search");
    try { setResults((await api.searchInputs(query)).results); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy("upload");
    try { const response = await api.uploadInput(file, file.name.replace(/\.[^.]+$/, "")); open(response.input); notify("Prepare this image before adding it to Inputs"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); event.target.value = ""; }
  }
  async function chooseResult(result: SearchResult) {
    setBusy(`import-${result.id}`);
    try { const response = await api.importInput(result); open(response.input); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function normalise() {
    if (!editing) return;
    setBusy("normalise");
    try { setEditing((await api.normaliseInput(editing.id, prompt, quality, pipeline.generation.execution_mode === "live")).input); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function accept() {
    if (!editing || latest?.status !== "ready") return;
    setBusy("accept");
    try { await api.acceptInput(editing.id, latest.id); await refresh(); setEditing(undefined); notify("Input accepted and ready for generation"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function close() {
    if (!editing) return;
    if (editing.status === "pending") { try { await api.deleteInput(editing.id); } catch (error) { notify((error as Error).message, "error"); return; } }
    setEditing(undefined);
  }

  return <section className="page inputs-page">
    <div className="page-heading">
      <div><p className="eyebrow">Prepared assets</p><h2>Inputs</h2><p>Normalize each image once, inspect the result, then reuse that stable Input in every later pipeline.</p></div>
      <span className="status-chip">{bootstrap.inputs.length} ready</span>
    </div>
    <section className="surface source-management">
      <div className="panel-heading"><div><p className="eyebrow">Add an Input</p><h3>Choose an original image</h3></div><label className="button secondary file-button">Upload image<input aria-label="Upload input image" type="file" accept="image/*" onChange={upload} /></label></div>
      <form className="search-row" onSubmit={(event) => { event.preventDefault(); void search(); }}><input aria-label="Search input images" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search Pexels" /><button className="button secondary" disabled={busy === "search"}>{busy === "search" ? "Searching…" : "Search"}</button></form>
      {results.length > 0 && <div className="search-results">{results.map((result) => <article key={result.pexels_photo_id || result.id}><img src={result.preview_url || result.selected_image_url} alt={result.label || result.photographer || "Search result"} /><div><strong>{result.photographer || "Image source"}</strong><button type="button" className="button secondary" disabled={Boolean(busy)} onClick={() => void chooseResult(result)}>Prepare</button></div></article>)}</div>}
    </section>
    <section className="source-library">
      {bootstrap.inputs.length === 0 ? <div className="surface empty-panel"><span className="empty-glyph">＋</span><h3>No Inputs yet</h3><p>Upload or search for an original, normalize it, then accept the preview.</p></div> : <div className="source-grid">{bootstrap.inputs.map((item) => <article className="surface source-tile selected" key={item.id}><button className="source-select" onClick={() => open(item)}>{item.image_url && <img src={item.image_url} alt={item.label} />}<span>{item.label}</span><b>Ready</b></button><button className="text-button danger" onClick={async () => { if (!window.confirm(`Delete ${item.label}?`)) return; try { await api.deleteInput(item.id); await refresh(); notify("Input removed"); } catch (error) { notify((error as Error).message, "error"); } }}>Remove</button></article>)}</div>}
    </section>
    {editing && <div className="dialog-backdrop" role="presentation"><section className="surface input-dialog" role="dialog" aria-modal="true" aria-labelledby="input-dialog-title"><div className="panel-heading"><div><p className="eyebrow">Prepare Input</p><h3 id="input-dialog-title">{editing.label}</h3></div><button className="button secondary" disabled={isActive(latest?.status || "") || busy === "accept"} onClick={() => void close()}>Cancel</button></div><div className="normalisation-preview"><figure>{editing.original_url && <img src={editing.original_url} alt="Original" />}<figcaption>Original</figcaption></figure><span>→</span><figure>{latest?.preview_url ? <img src={latest.preview_url} alt="Normalized preview" /> : editing.image_url ? <img src={editing.image_url} alt="Accepted Input" /> : <div className="preview-placeholder">{isActive(latest?.status || "") ? <span className="spinner" /> : "Preview"}</div>}<figcaption>{latest?.status === "failed" ? "Preview failed" : "Normalized Input"}</figcaption></figure></div>{latest?.error && <p className="validation-note" role="alert">{latest.error}</p>}<label className="prompt-field">Normalization prompt<textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label><div className="dialog-controls"><label>Quality<select value={quality} onChange={(event) => setQuality(event.target.value as typeof quality)}>{(["low", "medium", "high"] as const).map((value) => <option key={value} value={value} disabled={Boolean(model?.qualities.length) && !model?.qualities.includes(value)}>{value}</option>)}</select></label><div><small>{model?.name || pipeline.generation.model_id} · {modelCost(model)} per preview</small><button className="button secondary" disabled={!model?.available || isActive(latest?.status || "") || Boolean(busy)} onClick={() => void normalise()}>{isActive(latest?.status || "") ? "Normalizing…" : latest?.status === "ready" ? "Rerun normalization" : "Normalize preview"}</button><button className="button primary" disabled={latest?.status !== "ready" || Boolean(busy)} onClick={() => void accept()}>{busy === "accept" ? "Adding…" : "OK · Add to Inputs"}</button></div></div></section></div>}
  </section>;
}

type PipelineCard = PipelineRecord & { outputCount: number; samples: ProducedCard[] };

function pipelineResults(cards: ProducedCard[], pipelineId: string, styleId?: string) {
  return cards.filter((card) => card.pipeline_id === pipelineId && (!styleId || card.style_version_id === styleId));
}

function PipelineDiagram({ style, cards, sources }: { style?: PipelineStyle; cards: ProducedCard[]; sources: InputAsset[] }) {
  const example = cards[0];
  const reference = style?.reference_pack.assets.find((asset) => asset.role === "generation-reference");
  const recordedReference = example?.reference_stack.find((asset) => asset.role === "generation-reference");
  const referenceUrl = reference?.image_url || String(recordedReference?.url || "");
  const referenceLabel = reference?.label || String(recordedReference?.label || "Style reference");
  const model = style?.generation.model_id || String(example?.generation?.model || "image model");
  const renderer = style?.renderer.driver_id || "Amiga renderer";
  const sourceUrl = example?.source_url || sources[0]?.image_url;
  return <section className="surface pipeline-diagram">
    <div className="diagram-heading"><div><p className="eyebrow">Pipeline anatomy</p><h3>Prepared Input in. Card out.</h3></div><span>{cards.length} produced result{cards.length === 1 ? "" : "s"}</span></div>
    <div className="diagram-track">
      <figure>{sourceUrl ? <img src={sourceUrl} alt="Prepared Input" /> : <span className="diagram-empty">＋</span>}<figcaption><small>Prepared</small><strong>Input</strong></figcaption></figure>
      <span className="diagram-plus">+</span>
      <figure>{referenceUrl ? <img src={referenceUrl} alt={referenceLabel} /> : <span className="diagram-empty">ref</span>}<figcaption><small>Style only</small><strong>Style board</strong></figcaption></figure>
      <div className="diagram-step"><span>→</span><small>{model}</small></div>
      <figure>{example?.master_url ? <img src={example.master_url} alt="Styled master" /> : <span className="diagram-empty">master</span>}<figcaption><small>Generated</small><strong>Styled master</strong></figcaption></figure>
      <div className="diagram-step"><span>→</span><small>{renderer}</small></div>
      <figure>{example?.art_url ? <img className="pixelated" src={example.art_url} alt="Rendered asset art" /> : <span className="diagram-empty">art</span>}<figcaption><small>Rendered</small><strong>Amiga art</strong></figcaption></figure>
      <div className="diagram-step"><span>→</span><small>card assembly</small></div>
      <figure className="diagram-card">{example?.card_url ? <img className="pixelated" src={example.card_url} alt="Produced card" /> : <span className="diagram-empty">card</span>}<figcaption><small>Output</small><strong>Produced card</strong></figcaption></figure>
    </div>
  </section>;
}

export function PipelinesView({ bootstrap, navigate, refresh, notify, pipelineId }: Shared & { pipelineId?: string }) {
  const [style, setStyle] = useState<PipelineStyle>(bootstrap.style.draft || bootstrap.style.active);
  const [cohort, setCohort] = useState<string[]>(bootstrap.inputs.slice(0, 3).map((item) => item.id));
  const [trial, setTrial] = useState<ProductionBatch>();
  const [busy, setBusy] = useState("");
  const active = bootstrap.style.active;
  const draft = bootstrap.style.draft;
  const draftPipelineId = draft ? bootstrap.style.pipelines.find((item) => item.current_version_id === draft.provenance?.derived_from || item.pipeline_id === draft.identity.pipeline_id)?.pipeline_id || draft.identity.pipeline_id : undefined;
  const selectedPipeline = bootstrap.style.pipelines.find((item) => item.pipeline_id === pipelineId) || bootstrap.style.pipelines.find((item) => item.pipeline_id === draftPipelineId) || bootstrap.style.pipelines.find((item) => item.active) || bootstrap.style.pipelines[0];
  const selectedId = selectedPipeline?.pipeline_id;
  const selectedStyle = draft && draftPipelineId === selectedId ? draft : selectedPipeline?.style;
  const selectedChecksum = selectedStyle?.checksums.style_sha256;
  const selectedCards = selectedId ? pipelineResults(bootstrap.cards, selectedId) : [];
  const pipelineCards: PipelineCard[] = bootstrap.style.pipelines.map((pipeline) => {
    const outputs = pipelineResults(bootstrap.cards, pipeline.pipeline_id);
    return { ...pipeline, outputCount: new Set(outputs.map((card) => card.source_id)).size, samples: outputs.slice(0, 3) };
  });
  const generationRefs = style.reference_pack.assets.filter((asset) => asset.role === "generation-reference");
  const target = style.reference_pack.assets.find((asset) => asset.role === "target-example");
  const models = bootstrap.models.filter((model) => model.execution_mode === style.generation.execution_mode);
  const selectedModel = bootstrap.models.find((model) => model.id === style.generation.model_id && model.execution_mode === style.generation.execution_mode);
  const activeBatch = bootstrap.batches.find((batch) => isActive(batch.status));
  const previewCards = trial?.items.filter((item) => item.status === "ready") || [];
  useEffect(() => { setStyle(selectedStyle || active); }, [selectedStyle?.identity.style_version_id, selectedStyle?.checksums.style_sha256, active.identity.style_version_id]);

  async function beginEdit() {
    setBusy("draft");
    if (!selectedId) return;
    try { const response = await api.createDraft(selectedId); setStyle(response.style); navigate(`#pipelines/${selectedId}`); await refresh(); notify("Working pipeline created"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function patch(patchValue: Partial<PipelineStyle>) { try { const response = await api.updateDraft(patchValue); setStyle(response.style); await refresh(); } catch (error) { notify((error as Error).message, "error"); } }
  async function patchGeneration(next: Partial<PipelineStyle["generation"]>) { await patch({ generation: { ...style.generation, ...next } }); }
  async function changeMode(mode: PipelineStyle["generation"]["execution_mode"]) { const next = bootstrap.models.find((model) => model.execution_mode === mode && model.available) || bootstrap.models.find((model) => model.execution_mode === mode); await patchGeneration({ execution_mode: mode, model_id: next?.id || style.generation.model_id }); }
  async function runTrial() {
    if (!selectedModel || !cohort.length) return;
    setBusy("trial");
    try { const response = await api.runTrial(cohort, style.generation.execution_mode === "live"); setTrial(response.batch); notify(`${cohort.length}-source comparison run started`); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  useEffect(() => { if (!trial || !isActive(trial.status)) return; const timer = window.setInterval(() => void api.getProduction(trial.batch_id).then((response) => setTrial(response.batch)).then(() => refresh()), 800); return () => window.clearInterval(timer); }, [trial?.batch_id, trial?.status]);
  async function activate() { if (!trial) return; setBusy("activate"); try { const response = await api.activateTrial(trial.batch_id); notify("Pipeline saved and made active"); await refresh(); setStyle(response.style.active); navigate(`#pipelines/${response.style.active.identity.pipeline_id || response.style.active_pipeline_id}`); setTrial(undefined); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }
  async function makeActive() { if (!selectedId) return; setBusy("active"); try { await api.activatePipeline(selectedId); await refresh(); notify(`${selectedPipeline?.label || "Pipeline"} is now the active default`); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }
  async function uploadReference(event: ChangeEvent<HTMLInputElement>) { const file = event.target.files?.[0]; if (!file) return; setBusy("reference"); try { const response = await api.uploadDraftReference(file); setStyle(response.style); await refresh(); notify("Pipeline reference added"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); event.target.value = ""; } }
  async function moveReference(index: number, delta: number) { const nextIndex = index + delta; if (nextIndex < 0 || nextIndex >= generationRefs.length) return; const ordered = [...generationRefs]; [ordered[index], ordered[nextIndex]] = [ordered[nextIndex], ordered[index]]; const targetAsset = style.reference_pack.assets.find((asset) => asset.role === "target-example"); await patch({ reference_pack: { ...style.reference_pack, assets: targetAsset ? [...ordered, targetAsset] : ordered } }); }

  return <section className="page pipelines-page">
    <div className="page-heading"><div><p className="eyebrow">Pipeline</p><h2>Style a prepared Input</h2><p>Inputs are normalized during ingest. A pipeline now contains only the style transformation and renderer.</p></div><button className="button secondary" onClick={() => navigate("#candidates")}>Open candidates</button></div>
    <section className="pipeline-collection" aria-label="Saved pipelines">
      {pipelineCards.map((pipeline) => <button className={`surface pipeline-card ${pipeline.active ? "active" : ""} ${selectedId === pipeline.pipeline_id ? "selected" : ""}`} key={pipeline.pipeline_id} onClick={() => navigate(`#pipelines/${pipeline.pipeline_id}`)}><div>{pipeline.active ? <span className="status-chip">active default</span> : <span>runnable</span>}<small>rev {pipeline.revision_count}</small></div><strong>{pipeline.label}</strong><p>{pipeline.description}</p><div className="pipeline-samples">{pipeline.samples.map((card) => <img key={`${card.batch_id}:${card.item_id}`} src={card.card_url} alt={`${pipeline.label} result`} />)}<span>{pipeline.outputCount || "＋"}</span></div></button>)}
    </section>
    <PipelineDiagram style={selectedStyle} cards={selectedCards} sources={selectedSources(bootstrap)} />
    <section className="surface pipeline-meta"><div><p className="eyebrow">{draft && draftPipelineId === selectedId ? "Working revision" : selectedPipeline?.active ? "Active default" : "Runnable pipeline"}</p><h3>{selectedPipeline?.label || selectedId}</h3><p><code>{selectedPipeline?.current_version_id}</code> · checksum <code>{shortChecksum(selectedChecksum || "")}</code></p></div><div className="palette-strip">{selectedStyle?.renderer.palette.map((colour) => <i key={colour} style={{ backgroundColor: colour }} title={colour} />)}</div>{!draft && <button className="button secondary" disabled={busy === "draft"} onClick={() => void beginEdit()}>{busy === "draft" ? "Creating…" : "Edit pipeline"}</button>}{selectedPipeline && !selectedPipeline.active && <button className="button primary" disabled={busy === "active"} onClick={() => void makeActive()}>{busy === "active" ? "Switching…" : "Make active default"}</button>}</section>
    {selectedPipeline && <details className="surface pipeline-history"><summary>{selectedPipeline.revision_count} saved revision{selectedPipeline.revision_count === 1 ? "" : "s"}</summary><div className="details-content">{selectedPipeline.revisions.slice().reverse().map((revision, index) => <p key={revision.style_version_id}>Revision {selectedPipeline.revision_count - index} · <code>{shortChecksum(revision.checksum_sha256)}</code>{revision.created_at ? ` · ${revision.created_at}` : ""}</p>)}</div></details>}
    {draft && draftPipelineId === selectedId && <>
      <div className="reference-columns"><section className="surface"><div className="panel-heading"><div><p className="eyebrow">Inputs</p><h3>Ordered generation references</h3></div><span>{generationRefs.length} / {style.generation.reference_limit - 1}</span></div><div className="reference-strip">{generationRefs.map((asset, index) => <figure key={asset.id}><img src={asset.image_url} alt={asset.label} /><figcaption>{index + 1}. {asset.label}</figcaption><div><button className="text-button" disabled={index === 0} onClick={() => void moveReference(index, -1)}>Earlier</button><button className="text-button" disabled={index === generationRefs.length - 1} onClick={() => void moveReference(index, 1)}>Later</button></div></figure>)}</div><label className="button secondary file-button">Add reference<input type="file" accept="image/*" onChange={uploadReference} /></label><p className="muted">The identity source is always first; these pipeline references follow in order.</p></section><section className="surface target-example"><p className="eyebrow">Renderer proof</p><h3>Reference → target</h3><div className="reference-pair">{generationRefs[0]?.image_url && <figure><img src={generationRefs[0].image_url} alt="High-resolution generation reference" /><figcaption>Model reference</figcaption></figure>}{target?.image_url && <figure><img src={target.image_url} alt={target.label} /><figcaption>Rendered target</figcaption></figure>}</div><p>Target is documentation for the renderer and is never sent to the model.</p></section></div>
      <section className="surface editor"><div className="panel-heading"><div><p className="eyebrow">Transform</p><h3>Edit working pipeline</h3></div><span className="status-chip working">unsaved version</span></div>
        <details open><summary>Generation model</summary><div className="form-grid"><label>Execution mode<select value={style.generation.execution_mode} onChange={(event) => void changeMode(event.target.value as PipelineStyle["generation"]["execution_mode"])}><option value="live">Live image generation</option><option value="simulation">Simulation preview</option></select></label><label>Model<select value={style.generation.model_id} onChange={(event) => void patchGeneration({ model_id: event.target.value })}>{models.map((model) => <option key={model.id} value={model.id}>{model.name}{!model.available ? " · unavailable" : !model.credentials_configured && model.execution_mode === "live" ? " · missing key" : ""}</option>)}</select></label><label>Quality<select value={style.generation.quality} onChange={(event) => void patchGeneration({ quality: event.target.value as PipelineStyle["generation"]["quality"] })}><option>low</option><option>medium</option><option>high</option></select></label></div><p className="muted">{selectedModel?.name || style.generation.model_id} · {selectedModel?.max_input_references || 0} inputs · {modelCost(selectedModel)} per result</p></details>
        <details open><summary>Style prompt</summary><textarea value={style.generation.prompt || ""} onChange={(event) => setStyle({ ...style, generation: { ...style.generation, prompt: event.target.value } })} onBlur={() => void patchGeneration({ prompt: style.generation.prompt })} /></details>
        <details><summary>Amiga renderer and card assembly</summary><div className="form-grid"><label>Dither strength<input type="number" min="0" max="1" step="0.01" value={style.renderer.dither.strength} onChange={(event) => setStyle({ ...style, renderer: { ...style.renderer, dither: { ...style.renderer.dither, strength: Number(event.target.value) } } })} onBlur={() => void patch({ renderer: style.renderer })} /></label><label>Edge threshold<input type="number" min="0" max="1" step="0.01" value={style.renderer.dither.edge_threshold} onChange={(event) => setStyle({ ...style, renderer: { ...style.renderer, dither: { ...style.renderer.dither, edge_threshold: Number(event.target.value) } } })} onBlur={() => void patch({ renderer: style.renderer })} /></label><label>Centering Y<input type="number" min="0" max="1" step="0.01" value={style.composition.centering[1]} onChange={(event) => setStyle({ ...style, composition: { ...style.composition, centering: [style.composition.centering[0], Number(event.target.value)] } })} onBlur={() => void patch({ composition: style.composition })} /></label></div></details>
        <div className="draft-summary"><strong>Current configuration</strong> <code>{shortChecksum(style.checksums.style_sha256)}</code></div>
      </section>
      <section className="surface trial-panel"><div className="panel-heading"><div><p className="eyebrow">Output</p><h3>Run a constant comparison set</h3></div><span>{cohort.length} / 3 Inputs</span></div><div className="cohort-picker">{bootstrap.inputs.map((source) => <button key={source.id} className={cohort.includes(source.id) ? "selected" : ""} aria-pressed={cohort.includes(source.id)} onClick={() => setCohort((current) => current.includes(source.id) ? current.filter((id) => id !== source.id) : current.length < 3 ? [...current, source.id] : current)}>{source.image_url && <img src={source.image_url} alt={source.label} />}<span>{source.label}</span></button>)}</div><div className="trial-actions"><p>Every run produces complete cards immediately. {cohort.length} call{cohort.length === 1 ? "" : "s"} · {modelCost(selectedModel)} each.</p><button className="button primary" disabled={!cohort.length || !selectedModel || Boolean(busy) || Boolean(activeBatch) || !selectedModel.available || (style.generation.execution_mode === "live" && !selectedModel.credentials_configured)} onClick={() => void runTrial()}>{busy === "trial" ? "Starting…" : previewCards.length ? "Run this configuration again" : "Run comparison set"}</button></div>{(trial || previewCards.length > 0) && <div className="trial-result"><span className={`status-chip ${trial?.status || "ready"}`}>{trial?.status || "ready"}</span>{previewCards.map((item) => item.card_url && <img key={item.item_id} src={item.card_url} alt={`${item.source_label} pipeline result`} />)}{trial?.status === "ready" && trial.model_capabilities?.execution_mode === "live" && <button className="button primary" disabled={busy === "activate"} onClick={() => void activate()}>{busy === "activate" ? "Saving…" : "Save as pipeline & make active"}</button>}</div>}</section>
    </>}
  </section>;
}

function generationOrigin(card: ProducedCard) {
  return `revision ${card.pipeline_version || "—"} · attempt ${card.attempt_number}`;
}

function ResultProvenance({ card }: { card: ProducedCard }) {
  const refs = card.reference_stack.filter((reference) => reference.role === "generation-reference");
  return <details><summary>Run details</summary><div className="details-content"><p>Pipeline <code>{card.style_version_id}</code> · configuration <code>{shortChecksum(card.style_checksum_sha256)}</code></p><p>Generation: <strong>{String(card.generation?.execution_mode || "unknown")}</strong> · {String(card.generation?.model || "model unavailable")}</p><p>Ordered references: {refs.length ? refs.map((reference, index) => <span key={String(reference.reference_id || index)}> {index ? "→ " : ""}{String(reference.label || reference.reference_id)}</span>) : "—"}</p><p>Render revision {card.render_revision} · card checksum <code>{card.card_checksum_sha256 || "—"}</code></p></div></details>;
}

export function CandidatesView({ bootstrap, navigate, refresh, notify, batchId, cardId }: Shared & { batchId?: string; cardId?: string }) {
  const pipelines = bootstrap.style.pipelines;
  const sources = selectedSources(bootstrap).sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")));
  const [busy, setBusy] = useState("");
  const selectedCard = bootstrap.cards.find((card) => card.item_id === cardId && (!batchId || card.batch_id === batchId));
  const [framing, setFraming] = useState<Framing>(selectedCard?.framing || { zoom: 1, offset_x: 0, offset_y: 0 });
  const activeBatch = bootstrap.batches.find((batch) => isActive(batch.status));
  useEffect(() => { if (selectedCard) setFraming(selectedCard.framing || { zoom: 1, offset_x: 0, offset_y: 0 }); }, [selectedCard?.item_id]);

  async function generate(sourceIds: string[], selectedId = bootstrap.style.active_pipeline_id) {
    if (!sourceIds.length || !selectedId) return;
    setBusy(`generate-${sourceIds[0]}`);
    const pipeline = pipelines.find((item) => item.pipeline_id === selectedId);
    try { await api.createProduction(sourceIds, selectedId, pipeline?.style.generation.execution_mode === "live"); notify("New two-stage candidate started"); await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function tryAnother(card: ProducedCard) {
    setBusy(card.item_id);
    try { await api.tryAnother(card.batch_id, card.source_id, card.generation?.execution_mode === "live"); notify("Another result queued"); await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function render(card: ProducedCard) {
    setBusy(`render-${card.item_id}`);
    try { await api.renderFraming(card.batch_id, card.item_id, framing); notify("Framing rerendered"); await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function toggleFavorite(card: ProducedCard) {
    setBusy(`favorite-${card.item_id}`);
    try { if (card.favorite) { await api.unfavorite(card.batch_id, card.item_id); notify("Removed from Collection"); } else { await api.favorite(card.batch_id, card.item_id); notify("Saved to Collection"); } await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }

  return <section className="page candidates-page">
    <div className="page-heading"><div><p className="eyebrow">Candidate packs</p><h2>Next. Next. Ooh, a good one.</h2><p>Each Input keeps its three newest cards in view. Generation applies the chosen style pipeline in one call.</p></div><span className="status-chip">3 cards per Input</span></div>
    {!sources.length ? <div className="empty-panel surface"><span className="empty-glyph">→</span><h3>Prepare an Input first</h3><button className="button primary" onClick={() => navigate("#inputs")}>Open Inputs</button></div> : <div className="candidate-packs">{sources.map((source) => {
      const allCards = bootstrap.cards.filter((candidate) => candidate.source_id === source.id);
      const cards = allCards.slice(0, 3);
      const isGenerating = activeBatch?.purpose === "card-production" && activeBatch.selected_source_ids?.includes(source.id) === true;
      const sourceCount = `${cards.length} in view${allCards.length > 3 ? ` · ${allCards.length - 3} older stored` : ""}`;
      return <section className="surface candidate-pack" key={source.id}>
        <div className="pack-cards">{isGenerating && <div className="generation-card pending-card" role="status" aria-label={`Generating a new card for ${source.label}`}><span className="spinner" /></div>}{cards.length ? cards.map((card, index) => <div className={`generation-card ${selectedCard?.item_id === card.item_id ? "selected" : ""}`} key={`${card.batch_id}:${card.item_id}`}><button className="candidate-open" onClick={() => navigate(`#candidates/${card.batch_id}/${card.item_id}`)}><img src={card.card_url} alt={`${source.label} ${card.pipeline_label} candidate ${index + 1}`} /><span><strong>{index === 0 ? "Newest card" : `Previous ${index}`}</strong><small>{card.pipeline_label}</small><small>{generationOrigin(card)}</small></span></button><button className={`favorite-button ${card.favorite ? "saved" : ""}`} aria-label={card.favorite ? "Remove from Collection" : "Save to Collection"} disabled={Boolean(busy)} onClick={() => void toggleFavorite(card)}>{card.favorite ? "★" : "☆"}</button></div>) : !isGenerating && <div className="pack-empty"><span>◇</span><strong>No cards yet</strong><small>Open your first one.</small></div>}</div>
        <aside className="pack-generate">
          <button className="source-peek" aria-label={`Input: ${source.label}. ${sourceCount}`}><span>Input</span><i aria-hidden="true">ⓘ</i><span className="source-popover" aria-hidden="true">{source.image_url && <img src={source.image_url} alt="" />}<span><small>prepared Input</small><strong>{source.label}</strong><em>{sourceCount}</em></span></span></button>
          <div className="pack-action"><button className="generate-card" disabled={Boolean(activeBatch) || Boolean(busy)} onClick={() => void generate([source.id])}><span>＋</span><strong>Generate new</strong><small>style · 1 call</small></button></div>
        </aside>
      </section>;
    })}</div>}
    {selectedCard && <section className="surface result-inspector"><div className="panel-heading"><div><p className="eyebrow">{selectedCard.pipeline_label} · {selectedCard.source_label}</p><h3>Candidate details</h3><p>Inspect the style and render stages, adjust framing, or save this candidate to Collection.</p></div><button className="button secondary" onClick={() => navigate("#candidates")}>Close</button></div><div className="asset-stages"><figure><img src={selectedCard.source_url} alt="Prepared Input" /><figcaption>Input</figcaption></figure><span>→</span><figure><img src={selectedCard.master_url} alt="Styled master" /><figcaption>Styled master</figcaption></figure><span>→</span><figure><img className="pixelated" src={selectedCard.art_url} alt="Amiga art" /><figcaption>Rendered art</figcaption></figure><span>→</span><figure className="final-stage"><img className="pixelated" src={selectedCard.card_url} alt="Final card" /><figcaption>Candidate card</figcaption></figure></div><div className="framing-controls"><label>Zoom<input type="range" min="1" max="3" step="0.01" value={framing.zoom} onChange={(event) => setFraming({ ...framing, zoom: Number(event.target.value) })} /></label><label>Horizontal<input type="range" min="-1" max="1" step="0.01" value={framing.offset_x} onChange={(event) => setFraming({ ...framing, offset_x: Number(event.target.value) })} /></label><label>Vertical<input type="range" min="-1" max="1" step="0.01" value={framing.offset_y} onChange={(event) => setFraming({ ...framing, offset_y: Number(event.target.value) })} /></label></div><div className="inspector-actions"><button className="button primary" disabled={Boolean(busy)} onClick={() => void toggleFavorite(selectedCard)}>{selectedCard.favorite ? "★ Saved to Collection" : "☆ Save to Collection"}</button><button className="button secondary" disabled={Boolean(busy)} onClick={() => void tryAnother(selectedCard)}>Generate another result</button><button className="button secondary" disabled={Boolean(busy)} onClick={() => void render(selectedCard)}>{busy === `render-${selectedCard.item_id}` ? "Rerendering…" : "Save framing · no generation"}</button></div><ResultProvenance card={selectedCard} /></section>}
  </section>;
}

export function CollectionView({ bootstrap, navigate, refresh, notify }: Shared) {
  const [busy, setBusy] = useState("");
  async function remove(card: ProducedCard) {
    setBusy(card.item_id);
    try { await api.unfavorite(card.batch_id, card.item_id); await refresh(); notify("Removed from Collection"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  return <section className="page collection-page"><div className="page-heading"><div><p className="eyebrow">Collection</p><h2>Your saved candidate cards</h2><p>Favorites from any source or pipeline stay here until you remove them. The original generation and provenance remain intact.</p></div><span className="status-chip">{bootstrap.favorites.length} saved</span></div>{bootstrap.favorites.length === 0 ? <div className="empty-panel surface"><span className="empty-glyph">☆</span><h3>No saved candidates yet</h3><p>Favorite candidates while comparing pipeline results.</p><button className="button primary" onClick={() => navigate("#candidates")}>Open Candidates</button></div> : <div className="collection-grid">{bootstrap.favorites.map((card) => <article className="surface collection-card" key={`${card.batch_id}:${card.item_id}`}><button className="collection-open" onClick={() => navigate(`#candidates/${card.batch_id}/${card.item_id}`)}><img src={card.card_url} alt={`${card.source_label} from ${card.pipeline_label}`} /><span><strong>{card.source_label}</strong><small>{card.pipeline_label} · {generationOrigin(card)}</small></span></button><button className="text-button danger" disabled={busy === card.item_id} onClick={() => void remove(card)}>Remove from Collection</button></article>)}</div>}</section>;
}
