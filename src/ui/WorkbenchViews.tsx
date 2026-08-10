import { useEffect, useState, type ChangeEvent } from "react";
import { api } from "./api";
import type { Bootstrap, InputAsset, Model, PipelineRecord, PipelineStyle, ProducedCard, ProductionBatch, ProductionItem, SearchResult } from "./types";

type Notice = (message: string, kind?: "success" | "error") => void;
type Shared = { bootstrap: Bootstrap; navigate: (hash: string) => void; refresh: () => Promise<void>; notify: Notice };

function formatCost(value: number | null | undefined) {
  return value == null ? "provider-priced" : value === 0 ? "$0 simulation" : `$${value.toFixed(4)}`;
}
function modelCost(model: Model | undefined) { return formatCost(model?.pricing?.[0]?.cost_usd as number | undefined); }
function isActive(status: string) { return ["queued", "running", "processing"].includes(status); }
function shortChecksum(value: string) { return value.slice(0, 8); }
function selectedSources(bootstrap: Bootstrap) { return bootstrap.inputs; }
function backgroundConfig(style?: PipelineStyle) { return style?.backgrounds || { default_id: "warm-parchment", composite_size: [336, 276] as [number, number], presets: [{ id: "warm-parchment", label: "Warm parchment", top: "#d3be8e", bottom: "#674d34", glow: "#ecd6a5", glow_strength: .22 }] }; }

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
      <div><p className="eyebrow">Prepared assets</p><h2>Inputs</h2><p>Prepare each image once, inspect the result, then reuse that stable Input in every later pipeline.</p></div>
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
    {editing && <div className="dialog-backdrop" role="presentation"><section className="surface input-dialog" role="dialog" aria-modal="true" aria-labelledby="input-dialog-title"><div className="panel-heading"><div><p className="eyebrow">Prepare Input</p><h3 id="input-dialog-title">{editing.label}</h3></div><button className="button secondary" disabled={isActive(latest?.status || "") || busy === "accept"} onClick={() => void close()}>Cancel</button></div><div className="normalisation-preview"><figure>{editing.original_url && <img src={editing.original_url} alt="Original" />}<figcaption>Original</figcaption></figure><span>→</span><figure>{latest?.preview_url ? <img src={latest.preview_url} alt="Generated preview" /> : editing.image_url ? <img src={editing.image_url} alt="Accepted Input" /> : <div className="preview-placeholder">{isActive(latest?.status || "") ? <span className="spinner" /> : "Preview"}</div>}<figcaption>{latest?.status === "failed" ? "Preview failed" : "Prepared Input"}</figcaption></figure></div>{latest?.error && <p className="validation-note" role="alert">{latest.error}</p>}<label className="prompt-field">Preparation prompt<textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label><div className="dialog-controls"><label>Quality<select value={quality} onChange={(event) => setQuality(event.target.value as typeof quality)}>{(["low", "medium", "high"] as const).map((value) => <option key={value} value={value} disabled={Boolean(model?.qualities.length) && !model?.qualities.includes(value)}>{value}</option>)}</select></label><div><small>{model?.name || pipeline.generation.model_id} · {modelCost(model)} per preview</small><button className="button secondary" disabled={!model?.available || isActive(latest?.status || "") || Boolean(busy)} onClick={() => void normalise()}>{isActive(latest?.status || "") ? "Preparing…" : latest?.status === "ready" ? "Rerun preparation" : "Generate preview"}</button><button className="button primary" disabled={latest?.status !== "ready" || Boolean(busy)} onClick={() => void accept()}>{busy === "accept" ? "Adding…" : "OK · Add to Inputs"}</button></div></div></section></div>}
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
      <figure>{example?.foreground_url ? <img src={example.foreground_url} alt="Isolated foreground" /> : <span className="diagram-empty">subject</span>}<figcaption><small>Generated + matted</small><strong>Foreground</strong></figcaption></figure>
      <div className="diagram-step"><span>→</span><small>renderer background</small></div>
      <figure>{example?.master_url ? <img src={example.master_url} alt="Background composite" /> : <span className="diagram-empty">composite</span>}<figcaption><small>{example?.background_id || style?.backgrounds.default_id}</small><strong>Composite</strong></figcaption></figure>
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
  function updateBackgroundPreset(id: string, key: "top" | "bottom" | "glow", value: string) { setStyle({ ...style, backgrounds: { ...style.backgrounds, presets: style.backgrounds.presets.map((preset) => preset.id === id ? { ...preset, [key]: value } : preset) } }); }
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
    <div className="page-heading"><div><p className="eyebrow">Pipeline</p><h2>Style a prepared Input</h2><p>Inputs are normalized during ingest. A pipeline now contains only the style transformation and renderer.</p></div><button className="button secondary" onClick={() => navigate("#cards")}>Open Cards</button></div>
    <section className="pipeline-collection" aria-label="Saved pipelines">
      {pipelineCards.map((pipeline) => <button className={`surface pipeline-card ${pipeline.active ? "active" : ""} ${selectedId === pipeline.pipeline_id ? "selected" : ""}`} key={pipeline.pipeline_id} onClick={() => navigate(`#pipelines/${pipeline.pipeline_id}`)}><div>{pipeline.active ? <span className="status-chip">active default</span> : <span>runnable</span>}<small>rev {pipeline.revision_count}</small></div><strong>{pipeline.label}</strong><p>{pipeline.description}</p><div className="pipeline-samples">{pipeline.samples.map((card) => <img key={`${card.batch_id}:${card.item_id}`} src={card.card_url} alt={`${pipeline.label} result`} />)}<span>{pipeline.outputCount || "＋"}</span></div></button>)}
    </section>
    <PipelineDiagram style={selectedStyle} cards={selectedCards} sources={selectedSources(bootstrap)} />
    <section className="surface pipeline-meta"><div><p className="eyebrow">{draft && draftPipelineId === selectedId ? "Working revision" : selectedPipeline?.active ? "Active default" : "Runnable pipeline"}</p><h3>{selectedPipeline?.label || selectedId}</h3><p><code>{selectedPipeline?.current_version_id}</code> · checksum <code>{shortChecksum(selectedChecksum || "")}</code> · {selectedStyle?.renderer.palette_mode === "adaptive-hybrid" ? "adaptive OCS palette" : "fixed house palette"}</p></div><div className="palette-strip">{selectedStyle?.renderer.palette.map((colour) => <i key={colour} style={{ backgroundColor: colour }} title={colour} />)}</div>{!draft && <button className="button secondary" disabled={busy === "draft"} onClick={() => void beginEdit()}>{busy === "draft" ? "Creating…" : "Edit pipeline"}</button>}{selectedPipeline && !selectedPipeline.active && <button className="button primary" disabled={busy === "active"} onClick={() => void makeActive()}>{busy === "active" ? "Switching…" : "Make active default"}</button>}</section>
    {selectedPipeline && <details className="surface pipeline-history"><summary>{selectedPipeline.revision_count} saved revision{selectedPipeline.revision_count === 1 ? "" : "s"}</summary><div className="details-content">{selectedPipeline.revisions.slice().reverse().map((revision, index) => <p key={revision.style_version_id}>Revision {selectedPipeline.revision_count - index} · <code>{shortChecksum(revision.checksum_sha256)}</code>{revision.created_at ? ` · ${revision.created_at}` : ""}</p>)}</div></details>}
    {draft && draftPipelineId === selectedId && <>
      <div className="reference-columns"><section className="surface"><div className="panel-heading"><div><p className="eyebrow">Inputs</p><h3>Ordered generation references</h3></div><span>{generationRefs.length} / {style.generation.reference_limit - 1}</span></div><div className="reference-strip">{generationRefs.map((asset, index) => <figure key={asset.id}><img src={asset.image_url} alt={asset.label} /><figcaption>{index + 1}. {asset.label}</figcaption><div><button className="text-button" disabled={index === 0} onClick={() => void moveReference(index, -1)}>Earlier</button><button className="text-button" disabled={index === generationRefs.length - 1} onClick={() => void moveReference(index, 1)}>Later</button></div></figure>)}</div><label className="button secondary file-button">Add reference<input type="file" accept="image/*" onChange={uploadReference} /></label><p className="muted">The identity source is always first; these pipeline references follow in order.</p></section><section className="surface target-example"><p className="eyebrow">Renderer proof</p><h3>Reference → target</h3><div className="reference-pair">{generationRefs[0]?.image_url && <figure><img src={generationRefs[0].image_url} alt="High-resolution generation reference" /><figcaption>Model reference</figcaption></figure>}{target?.image_url && <figure><img src={target.image_url} alt={target.label} /><figcaption>Rendered target</figcaption></figure>}</div><p>Target is documentation for the renderer and is never sent to the model.</p></section></div>
      <section className="surface editor"><div className="panel-heading"><div><p className="eyebrow">Transform</p><h3>Edit working pipeline</h3></div><span className="status-chip working">unsaved version</span></div>
        <details open><summary>Generation model</summary><div className="form-grid"><label>Execution mode<select value={style.generation.execution_mode} onChange={(event) => void changeMode(event.target.value as PipelineStyle["generation"]["execution_mode"])}><option value="live">Live image generation</option><option value="simulation">Simulation preview</option></select></label><label>Model<select value={style.generation.model_id} onChange={(event) => void patchGeneration({ model_id: event.target.value })}>{models.map((model) => <option key={model.id} value={model.id}>{model.name}{!model.available ? " · unavailable" : !model.credentials_configured && model.execution_mode === "live" ? " · missing key" : ""}</option>)}</select></label><label>Quality<select value={style.generation.quality} onChange={(event) => void patchGeneration({ quality: event.target.value as PipelineStyle["generation"]["quality"] })}><option>low</option><option>medium</option><option>high</option></select></label></div><p className="muted">{selectedModel?.name || style.generation.model_id} · {selectedModel?.max_input_references || 0} inputs · {modelCost(selectedModel)} per result</p></details>
        <details open><summary>Style prompt</summary><textarea value={style.generation.prompt || ""} onChange={(event) => setStyle({ ...style, generation: { ...style.generation, prompt: event.target.value } })} onBlur={() => void patchGeneration({ prompt: style.generation.prompt })} /></details>
        <details open><summary>Card backgrounds</summary><div className="form-grid"><label>Default background<select value={style.backgrounds.default_id} onChange={(event) => void patch({ backgrounds: { ...style.backgrounds, default_id: event.target.value } })}>{style.backgrounds.presets.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}</select></label></div><div className="background-presets">{style.backgrounds.presets.map((preset) => <fieldset key={preset.id}><legend>{preset.label}</legend>{(["top", "bottom", "glow"] as const).map((key) => <label key={key}>{key}<input type="color" value={preset[key]} onChange={(event) => updateBackgroundPreset(preset.id, key, event.target.value)} onBlur={() => void patch({ backgrounds: style.backgrounds })} /></label>)}</fieldset>)}</div><p className="muted">These colours are composed after generation; they are never sent to the image model.</p></details>
        <details><summary>Amiga renderer and card assembly</summary><div className="form-grid"><label>Palette mode<select value={style.renderer.palette_mode || "fixed-house"} onChange={(event) => void patch({ renderer: { ...style.renderer, palette_mode: event.target.value as "fixed-house" | "adaptive-hybrid" } })}><option value="adaptive-hybrid">Adaptive OCS · image + house anchors</option><option value="fixed-house">Fixed house · same 32 colours</option></select></label><label>Dither strength<input type="number" min="0" max="1" step="0.01" value={style.renderer.dither.strength} onChange={(event) => setStyle({ ...style, renderer: { ...style.renderer, dither: { ...style.renderer.dither, strength: Number(event.target.value) } } })} onBlur={() => void patch({ renderer: style.renderer })} /></label><label>Edge threshold<input type="number" min="0" max="1" step="0.01" value={style.renderer.dither.edge_threshold} onChange={(event) => setStyle({ ...style, renderer: { ...style.renderer, dither: { ...style.renderer.dither, edge_threshold: Number(event.target.value) } } })} onBlur={() => void patch({ renderer: style.renderer })} /></label><label>Centering Y<input type="number" min="0" max="1" step="0.01" value={style.composition.centering[1]} onChange={(event) => setStyle({ ...style, composition: { ...style.composition, centering: [style.composition.centering[0], Number(event.target.value)] } })} onBlur={() => void patch({ composition: style.composition })} /></label></div></details>
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
  return <details><summary>Run details</summary><div className="details-content">{card.source_original_url && <p>Source trail: <a href={card.source_original_url} target="_blank" rel="noreferrer">original</a> → prepared Input → generated foreground → background composite → OCS render</p>}<p>Pipeline <code>{card.style_version_id}</code> · configuration <code>{shortChecksum(card.style_checksum_sha256)}</code></p><p>Generation: <strong>{String(card.generation?.execution_mode || "unknown")}</strong> · {String(card.generation?.model || "model unavailable")}</p>{card.chroma_key && <p>Foreground matte: {card.chroma_key.name} key {card.chroma_key.hex} · {String(card.matte_metadata?.mode || "unknown")}</p>}{card.background_id && <p>Renderer background: <strong>{card.background_id}</strong></p>}{card.content_direction && <p>Content direction: {card.content_direction}</p>}{card.prompt_override && <p>Legacy style override: {card.prompt_override}</p>}<p>Ordered references: {refs.length ? refs.map((reference, index) => <span key={String(reference.reference_id || index)}> {index ? "→ " : ""}{String(reference.label || reference.reference_id)}</span>) : "—"}</p><p>Render revision {card.render_revision} · card checksum <code>{card.card_checksum_sha256 || "—"}</code></p></div></details>;
}

export function CardsView({ bootstrap, navigate, refresh, notify, batchId, cardId }: Shared & { batchId?: string; cardId?: string }) {
  const pipelines = bootstrap.style.pipelines;
  const sources = selectedSources(bootstrap).sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")));
  const [busy, setBusy] = useState("");
  const [filter, setFilter] = useState<"all" | "favorites" | "trash">("all");
  const [choosingInput, setChoosingInput] = useState(false);
  const [generationSource, setGenerationSource] = useState<InputAsset>();
  const [generationPipelineId, setGenerationPipelineId] = useState(bootstrap.style.active_pipeline_id);
  const [contentDirection, setContentDirection] = useState("");
  const [generationBackgroundId, setGenerationBackgroundId] = useState(backgroundConfig(bootstrap.style.active).default_id);
  const [previewBatch, setPreviewBatch] = useState<ProductionBatch>();
  const selectedCard = bootstrap.cards.find((card) => card.item_id === cardId && (!batchId || card.batch_id === batchId));
  const selectedCardStyle = pipelines.find((pipeline) => pipeline.pipeline_id === selectedCard?.pipeline_id)?.style || bootstrap.style.active;
  const [paletteMode, setPaletteMode] = useState<"fixed-house" | "adaptive-hybrid">(selectedCard?.palette_mode || "fixed-house");
  const [backgroundId, setBackgroundId] = useState(selectedCard?.background_id || backgroundConfig(bootstrap.style.active).default_id);
  const [renderPreview, setRenderPreview] = useState<ProductionItem>();
  const activeBatch = bootstrap.batches.find((batch) => isActive(batch.status));
  useEffect(() => { if (selectedCard) { setPaletteMode(selectedCard.palette_mode || (selectedCard.render_metadata?.palette_mode === "adaptive-hybrid" ? "adaptive-hybrid" : "fixed-house")); setBackgroundId(selectedCard.background_id || backgroundConfig(bootstrap.style.active).default_id); setRenderPreview(undefined); } }, [selectedCard?.item_id]);
  useEffect(() => {
    if (!previewBatch || !isActive(previewBatch.status)) return;
    const timer = window.setInterval(() => void api.getProduction(previewBatch.batch_id).then(({ batch }) => setPreviewBatch(batch)).catch((error) => notify((error as Error).message, "error")), 800);
    return () => window.clearInterval(timer);
  }, [previewBatch?.batch_id, previewBatch?.status]);

  function openGeneration(source: InputAsset, pipelineId = bootstrap.style.active_pipeline_id, direction?: string | null, selectedBackground?: string | null) {
    const pipeline = pipelines.find((item) => item.pipeline_id === pipelineId) || pipelines[0];
    setGenerationSource(source); setGenerationPipelineId(pipeline?.pipeline_id || ""); setContentDirection(direction || ""); setGenerationBackgroundId(selectedBackground || backgroundConfig(pipeline?.style).default_id); setPreviewBatch(undefined);
  }

  async function generate() {
    if (!generationSource || !generationPipelineId) return;
    setBusy(`generate-${generationSource.id}`);
    const pipeline = pipelines.find((item) => item.pipeline_id === generationPipelineId);
    try { const response = await api.createProduction([generationSource.id], generationPipelineId, pipeline?.style.generation.execution_mode === "live", contentDirection, generationBackgroundId); setPreviewBatch(response.batch); notify("Candidate preview started"); await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function tryAnother(card: ProducedCard) {
    const source = sources.find((item) => item.id === card.source_id);
    if (source) { navigate("#cards"); openGeneration(source, card.pipeline_id, card.content_direction || card.prompt_override, card.background_id); }
  }
  const previewItem = previewBatch?.items?.slice(-1)[0];
  async function render(card: ProducedCard) {
    setBusy(`render-${card.item_id}`);
    try { await api.renderFraming(card.batch_id, card.item_id, card.framing || selectedCardStyle.composition.default_framing, paletteMode, backgroundId); setRenderPreview(undefined); notify("Background and palette saved"); await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function previewRender(card: ProducedCard) {
    setBusy(`preview-${card.item_id}`);
    try { setRenderPreview((await api.previewFraming(card.batch_id, card.item_id, card.framing || selectedCardStyle.composition.default_framing, paletteMode, backgroundId)).preview); notify("Preview updated · candidate not saved"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function toggleFavorite(card: ProducedCard) {
    setBusy(`favorite-${card.item_id}`);
    try { if (card.favorite) { await api.unfavorite(card.batch_id, card.item_id); notify("Favorite removed"); } else { await api.favorite(card.batch_id, card.item_id); notify("Card favorited"); } await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }

  async function toggleHidden(card: ProducedCard) {
    setBusy(`trash-${card.item_id}`);
    try { if (card.hidden) { await api.restoreCard(card.batch_id, card.item_id); notify("Card restored"); } else { await api.hideCard(card.batch_id, card.item_id); notify("Card moved to Trash"); } await refresh(); navigate("#cards"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }

  const visibleCards = bootstrap.cards.filter((card) => filter === "trash" ? card.hidden : !card.hidden && (filter !== "favorites" || card.favorite));

  return <section className="page cards-page">
    <div className="page-heading"><div><p className="eyebrow">Generation archive</p><h2>Cards</h2><p>Every run stays available for comparison, post-processing, and forking.</p></div><span className="status-chip">{bootstrap.cards.length} attempts</span></div>
    <div className="cards-toolbar"><button className="button primary" disabled={Boolean(activeBatch)} onClick={() => setChoosingInput(true)}>＋ Generate</button><div className="card-filters" aria-label="Card filters">{(["all", "favorites", "trash"] as const).map((value) => <button key={value} className={filter === value ? "active" : ""} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}</div></div>
    {!visibleCards.length ? <div className="empty-panel surface"><span className="empty-glyph">◇</span><h3>No {filter === "all" ? "cards" : filter} here</h3><p>{filter === "all" ? "Generate a card from one of your prepared Inputs." : "Change the filter to browse other cards."}</p></div> : <div className="raw-results-grid">{visibleCards.map((card) => <article className="surface raw-result-card" key={`${card.batch_id}:${card.item_id}`}><button className={`card-corner favorite-corner ${card.favorite ? "saved" : ""}`} aria-label={card.favorite ? "Remove favorite" : "Favorite card"} disabled={Boolean(busy) || card.status !== "ready"} onClick={() => void toggleFavorite(card)}>{card.favorite ? "★" : "☆"}</button><button className="card-corner trash-corner" aria-label={card.hidden ? "Restore card" : "Move card to Trash"} disabled={Boolean(busy)} onClick={() => void toggleHidden(card)}>{card.hidden ? "↶" : "⌫"}</button><button className="raw-result" onClick={() => navigate(`#cards/${card.batch_id}/${card.item_id}`)}>{card.card_url || card.art_url || card.foreground_url || card.raw_foreground_url ? <img className={card.card_url ? "pixelated card-result" : ""} src={card.card_url || card.art_url || card.foreground_url || card.raw_foreground_url} alt={`${card.source_label} result`} /> : <span className="preview-placeholder">{card.status === "failed" || card.status === "interrupted" ? "Generation failed" : "No image yet"}</span>}<span className="raw-result-copy"><span><strong>{card.source_label || "Untitled"}</strong><span className={`status-chip ${card.status}`}>{card.status}</span></span><small>{card.batch_id}</small><small>{card.pipeline_label} · attempt {card.attempt_number} · {card.batch_created_at}</small></span></button></article>)}</div>}
    {choosingInput && !generationSource && <div className="dialog-backdrop" role="presentation"><section className="surface input-dialog input-picker" role="dialog" aria-modal="true" aria-labelledby="choose-input-title"><div className="panel-heading"><div><p className="eyebrow">Generate</p><h3 id="choose-input-title">Choose an Input</h3></div><button className="button secondary" onClick={() => setChoosingInput(false)}>Cancel</button></div>{sources.length ? <div className="source-grid">{sources.map((source) => <button className="surface source-select" key={source.id} onClick={() => { setChoosingInput(false); openGeneration(source); }}>{source.image_url && <img src={source.image_url} alt={source.label} />}<span>{source.label}</span></button>)}</div> : <div className="empty-panel"><p>Prepare an Input before generating.</p><button className="button primary" onClick={() => navigate("#inputs")}>Open Inputs</button></div>}</section></div>}
    {generationSource && <div className="dialog-backdrop" role="presentation"><section className="surface input-dialog candidate-dialog" role="dialog" aria-modal="true" aria-labelledby="candidate-dialog-title"><div className="panel-heading"><div><p className="eyebrow">Generate candidate</p><h3 id="candidate-dialog-title">{generationSource.label}</h3></div><button className="button secondary" disabled={isActive(previewBatch?.status || "")} onClick={() => { setGenerationSource(undefined); setPreviewBatch(undefined); }}>Cancel</button></div><div className="candidate-preview foreground-flow"><figure>{generationSource.image_url && <img src={generationSource.image_url} alt="Prepared Input" />}<figcaption>Input</figcaption></figure><span>→</span><figure>{previewItem?.foreground_url ? <img src={previewItem.foreground_url} alt="Isolated foreground" /> : <div className="preview-placeholder">{isActive(previewBatch?.status || "") ? <span className="spinner" /> : "Foreground"}</div>}<figcaption>Foreground</figcaption></figure><span>→</span><figure>{previewItem?.master_url ? <img src={previewItem.master_url} alt="Composited master" /> : <div className="preview-placeholder">Composite</div>}<figcaption>Background composite</figcaption></figure><span>→</span><figure className="candidate-preview-card">{previewItem?.card_url ? <img className="pixelated" src={previewItem.card_url} alt="Candidate preview" /> : <div className="preview-placeholder">Card</div>}<figcaption>Candidate card</figcaption></figure></div>{previewItem?.error && <p className="validation-note" role="alert">{previewItem.error}</p>}<label className="prompt-field">Pipeline<select value={generationPipelineId} disabled={Boolean(previewBatch)} onChange={(event) => { const pipeline = pipelines.find((item) => item.pipeline_id === event.target.value); setGenerationPipelineId(event.target.value); setGenerationBackgroundId(pipeline?.style.backgrounds.default_id || "warm-parchment"); }}>{pipelines.map((pipeline) => <option key={pipeline.pipeline_id} value={pipeline.pipeline_id}>{pipeline.label}</option>)}</select></label><label className="prompt-field">Card background<select value={generationBackgroundId} disabled={Boolean(previewBatch)} onChange={(event) => setGenerationBackgroundId(event.target.value)}>{(pipelines.find((item) => item.pipeline_id === generationPipelineId)?.style.backgrounds.presets || []).map((background) => <option key={background.id} value={background.id}>{background.label}</option>)}</select></label><label className="prompt-field">Content direction <small>optional</small><textarea value={contentDirection} placeholder="For example: make the smile unsettling, keep everything else unchanged." onChange={(event) => setContentDirection(event.target.value)} /></label><p className="validation-note">The generated foreground and deterministic card background remain separate.</p><div className="candidate-dialog-actions"><small>{pipelines.find((item) => item.pipeline_id === generationPipelineId)?.style.generation.quality || "low"} quality · {modelCost(bootstrap.models.find((model) => model.id === pipelines.find((item) => item.pipeline_id === generationPipelineId)?.style.generation.model_id))} per result</small><button className="button primary" disabled={isActive(previewBatch?.status || "") || Boolean(busy) || Boolean(activeBatch && activeBatch.batch_id !== previewBatch?.batch_id)} onClick={() => void generate()}>{isActive(previewBatch?.status || "") ? "Generating…" : previewItem ? "Generate another" : "Generate"}</button><button className="button secondary" disabled={isActive(previewBatch?.status || "")} onClick={() => { setGenerationSource(undefined); setPreviewBatch(undefined); void refresh(); }}>Done</button></div></section></div>}
    {selectedCard && !generationSource && <div className="dialog-backdrop" role="presentation"><section className="surface input-dialog candidate-dialog result-inspector" role="dialog" aria-modal="true" aria-labelledby="candidate-details-title">
      <div className="panel-heading"><div><p className="eyebrow">{selectedCard.pipeline_label} · {selectedCard.source_label}</p><h3 id="candidate-details-title">Candidate details</h3><p>Inspect the foreground and composite, then experiment with the background or palette without regenerating.</p></div><button className="button secondary" onClick={() => navigate("#cards")}>Close</button></div>
      {selectedCard.error && <p className="validation-note" role="alert">{selectedCard.error}</p>}
      <div className="candidate-preview foreground-flow"><figure>{selectedCard.source_url ? <img src={selectedCard.source_url} alt="Prepared Input" /> : <div className="preview-placeholder">Input unavailable</div>}<figcaption>Input</figcaption></figure><span>→</span><figure>{selectedCard.foreground_url ? <img src={selectedCard.foreground_url} alt="Isolated foreground" /> : <div className="preview-placeholder">Foreground unavailable</div>}<figcaption>Foreground</figcaption></figure><span>→</span><figure>{(renderPreview?.master_url || selectedCard.master_url) ? <img src={renderPreview?.master_url || selectedCard.master_url} alt="Background composite" /> : <div className="preview-placeholder">Composite unavailable</div>}<figcaption>{renderPreview ? "Preview composite" : "Background composite"}</figcaption></figure><span>→</span><figure className="candidate-preview-card">{(renderPreview?.card_url || selectedCard.card_url) ? <img className="pixelated" src={renderPreview?.card_url || selectedCard.card_url} alt="Candidate card" /> : <div className="preview-placeholder">Card unavailable</div>}<figcaption>{renderPreview ? "Preview card · unsaved" : "Candidate card"}</figcaption></figure></div>
      {selectedCard.status === "ready" && <><div className="candidate-edit-controls">{selectedCard.foreground_url && <label>Background<select value={backgroundId} onChange={(event) => { setBackgroundId(event.target.value); setRenderPreview(undefined); }}>{backgroundConfig(selectedCardStyle).presets.map((background) => <option key={background.id} value={background.id}>{background.label}</option>)}</select></label>}<label>Palette<select value={paletteMode} onChange={(event) => { setPaletteMode(event.target.value as "fixed-house" | "adaptive-hybrid"); setRenderPreview(undefined); }}><option value="adaptive-hybrid">Adaptive · 10 anchors + 22 image colours</option><option value="fixed-house">Fixed · original house 32</option></select></label></div>
      </>}<div className="inspector-actions"><button className="button secondary" disabled={Boolean(busy) || selectedCard.status !== "ready" || Boolean(renderPreview)} onClick={() => void toggleFavorite(selectedCard)}>{selectedCard.favorite ? "★ Favorite" : "☆ Favorite"}</button><button className="button secondary" disabled={Boolean(busy)} onClick={() => void tryAnother(selectedCard)}>Fork</button>{selectedCard.status === "ready" && <><button className="button primary" disabled={Boolean(busy)} onClick={() => void previewRender(selectedCard)}>{busy === `preview-${selectedCard.item_id}` ? "Previewing…" : "Preview changes"}</button><button className="button secondary" disabled={Boolean(busy)} onClick={() => void render(selectedCard)}>{busy === `render-${selectedCard.item_id}` ? "Saving…" : "Save changes"}</button></>}</div><ResultProvenance card={selectedCard} />
    </section></div>}
  </section>;
}
