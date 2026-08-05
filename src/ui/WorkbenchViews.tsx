import { useEffect, useState, type ChangeEvent } from "react";
import { api } from "./api";
import type { Bootstrap, Framing, Model, PipelineRecord, PipelineStyle, ProducedCard, ProductionBatch, SearchResult, Source } from "./types";

type Notice = (message: string, kind?: "success" | "error") => void;
type Shared = { bootstrap: Bootstrap; navigate: (hash: string) => void; refresh: () => Promise<void>; notify: Notice };

function formatCost(value: number | null | undefined) {
  return value == null ? "provider-priced" : value === 0 ? "$0 simulation" : `$${value.toFixed(4)}`;
}
function modelCost(model: Model | undefined) { return formatCost(model?.pricing?.[0]?.cost_usd as number | undefined); }
function isActive(status: string) { return ["queued", "running", "processing"].includes(status); }
function shortChecksum(value: string) { return value.slice(0, 8); }
function selectedSources(bootstrap: Bootstrap) {
  return bootstrap.selected_source_ids.map((id) => bootstrap.sources.find((source) => source.id === id)).filter(Boolean) as Source[];
}

export function SourcesView({ bootstrap, navigate, refresh, notify }: Shared) {
  const [selected, setSelected] = useState(bootstrap.selected_source_ids);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [busy, setBusy] = useState("");
  const pipeline = bootstrap.style.active;
  const model = bootstrap.models.find((entry) => entry.id === pipeline.generation.model_id && entry.execution_mode === pipeline.generation.execution_mode);
  const activeBatch = bootstrap.batches.find((batch) => isActive(batch.status));
  const referenceCount = pipeline.reference_pack.assets.filter((asset) => asset.role === "generation-reference").length;
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
  async function runPipeline() {
    if (!selected.length || !model) return;
    setBusy("run");
    try {
      const response = await api.createProduction(selected, bootstrap.style.active_pipeline_id, pipeline.generation.execution_mode === "live");
      notify(`${selected.length}-source pipeline run started`);
      navigate(`#candidates/${response.batch.batch_id}`);
      await refresh();
    } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  const problem = !selected.length
    ? "Select at least one source image."
    : activeBatch
      ? "A pipeline run is already active."
      : pipeline.generation.execution_mode !== "live"
        ? "The active pipeline is simulation-only. Open Pipelines to switch it back to live generation."
        : !model
          ? "The active pipeline model is not in the current capability catalogue."
          : !model.available
            ? "The active pipeline model is unavailable; choose another model in Pipelines."
            : !model.credentials_configured
              ? "OPENROUTER_API_KEY is missing; configure live image generation before running this set."
              : model.max_input_references < 1 + referenceCount
                ? `The active model accepts ${model.max_input_references} references, but this pipeline needs ${1 + referenceCount}.`
                : model.qualities.length > 0 && !model.qualities.includes(pipeline.generation.quality)
                  ? `The active model does not support ${pipeline.generation.quality} quality.`
                  : "";

  return <section className="page sources-page">
    <div className="page-heading">
      <div><p className="eyebrow">Source library</p><h2>Choose the identity inputs</h2><p>Keep a broad library, then pin the same source set while you compare pipeline changes.</p></div>
      <span className="status-chip">{selected.length} in current set</span>
    </div>
    <section className="surface source-management">
      <div className="panel-heading"><div><p className="eyebrow">Add sources</p><h3>Project library</h3></div><label className="button secondary file-button">Upload image<input aria-label="Upload source image" type="file" accept="image/*" onChange={upload} /></label></div>
      <form className="search-row" onSubmit={(event) => { event.preventDefault(); void search(); }}><input aria-label="Search source images" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search Pexels portraits" /><button className="button secondary" disabled={busy === "search"}>{busy === "search" ? "Searching…" : "Search"}</button></form>
      {results.length > 0 && <div className="search-results">{results.map((result) => <article key={result.pexels_photo_id}><img src={result.preview_url || result.selected_image_url} alt={result.label || result.photographer || "Search result"} /><div><strong>{result.photographer || "Portrait source"}</strong><button type="button" className="button secondary" onClick={() => void api.importSources([result]).then(() => refresh()).then(() => notify("Source image added")).catch((error) => notify((error as Error).message, "error"))}>Add source</button></div></article>)}</div>}
    </section>
    <section className="source-library">
      {bootstrap.sources.length === 0 ? <div className="surface empty-panel"><span className="empty-glyph">＋</span><h3>No source images yet</h3><p>Add an upload or search Pexels above.</p></div> : <div className="source-grid">{bootstrap.sources.map((source) => { const order = selected.indexOf(source.id); return <article className={`surface source-tile ${order >= 0 ? "selected" : ""}`} key={source.id}><button className="source-select" aria-pressed={order >= 0} onClick={() => void saveSelection(order >= 0 ? selected.filter((id) => id !== source.id) : [...selected, source.id])}>{source.image_url && <img src={source.image_url} alt={source.label} />}<span>{source.label}</span>{order >= 0 && <b>{String(order + 1).padStart(2, "0")}</b>}</button><button className="text-button danger" onClick={async () => { if (!window.confirm(`Delete ${source.label}?`)) return; try { await api.deleteSource(source.id); await refresh(); notify("Source removed"); } catch (error) { notify((error as Error).message, "error"); } }}>Remove</button></article>; })}</div>}
    </section>
    <section className="surface pipeline-launcher">
      <div className="launcher-flow"><div><p className="eyebrow">Current source set</p><strong>{selected.length} identities</strong></div><i>→</i><button className="pipeline-token" onClick={() => navigate("#pipelines")}><small>Active pipeline · revision {bootstrap.style.pipelines.find((item) => item.active)?.revision_count || 1}</small><strong>{bootstrap.style.pipelines.find((item) => item.active)?.label || pipeline.identity.label}</strong><span>{model?.name || pipeline.generation.model_id} · {referenceCount} refs</span></button><i>→</i><div><p className="eyebrow">Expected output</p><strong>{selected.length} candidates</strong></div></div>
      <div className="launcher-action"><p>{selected.length} generation call{selected.length === 1 ? "" : "s"} · {modelCost(model)} each. Runs start immediately so comparison sets stay easy to replenish.</p><button className="button primary large" disabled={Boolean(problem) || Boolean(busy)} onClick={() => void runPipeline()}>{busy === "run" ? "Starting pipeline…" : `Run ${selected.length} source${selected.length === 1 ? "" : "s"}`}</button>{problem && <p className="validation-note" role="status">{problem}</p>}</div>
    </section>
  </section>;
}

type PipelineCard = PipelineRecord & { outputCount: number; samples: ProducedCard[] };

function pipelineResults(cards: ProducedCard[], pipelineId: string, styleId?: string) {
  return cards.filter((card) => card.pipeline_id === pipelineId && (!styleId || card.style_version_id === styleId));
}

function PipelineDiagram({ style, cards, sources }: { style?: PipelineStyle; cards: ProducedCard[]; sources: Source[] }) {
  const example = cards[0];
  const reference = style?.reference_pack.assets.find((asset) => asset.role === "generation-reference");
  const recordedReference = example?.reference_stack.find((asset) => asset.role === "generation-reference");
  const referenceUrl = reference?.image_url || String(recordedReference?.url || "");
  const referenceLabel = reference?.label || String(recordedReference?.label || "Style reference");
  const model = style?.generation.model_id || String(example?.generation?.model || "image model");
  const renderer = style?.renderer.driver_id || "Amiga renderer";
  const sourceUrl = example?.source_url || sources[0]?.image_url;
  return <section className="surface pipeline-diagram">
    <div className="diagram-heading"><div><p className="eyebrow">Pipeline anatomy</p><h3>Identity in. Card out.</h3></div><span>{cards.length} produced result{cards.length === 1 ? "" : "s"}</span></div>
    <div className="diagram-track">
      <figure>{sourceUrl ? <img src={sourceUrl} alt="Source identity input" /> : <span className="diagram-empty">＋</span>}<figcaption><small>Input 01</small><strong>Source identity</strong></figcaption></figure>
      <span className="diagram-plus">+</span>
      <figure>{referenceUrl ? <img src={referenceUrl} alt={referenceLabel} /> : <span className="diagram-empty">ref</span>}<figcaption><small>Input 02</small><strong>Style reference</strong></figcaption></figure>
      <div className="diagram-step"><span>→</span><small>{model}</small></div>
      <figure>{example?.master_url ? <img src={example.master_url} alt="Generated portrait master" /> : <span className="diagram-empty">master</span>}<figcaption><small>Generated</small><strong>Portrait master</strong></figcaption></figure>
      <div className="diagram-step"><span>→</span><small>{renderer}</small></div>
      <figure>{example?.art_url ? <img className="pixelated" src={example.art_url} alt="Rendered portrait art" /> : <span className="diagram-empty">art</span>}<figcaption><small>Rendered</small><strong>Amiga art</strong></figcaption></figure>
      <div className="diagram-step"><span>→</span><small>card assembly</small></div>
      <figure className="diagram-card">{example?.card_url ? <img className="pixelated" src={example.card_url} alt="Produced card" /> : <span className="diagram-empty">card</span>}<figcaption><small>Output</small><strong>Produced card</strong></figcaption></figure>
    </div>
  </section>;
}

function directionText(style: PipelineStyle, field: string) { return style.generation.direction[field] || ""; }

export function PipelinesView({ bootstrap, navigate, refresh, notify, pipelineId }: Shared & { pipelineId?: string }) {
  const [style, setStyle] = useState<PipelineStyle>(bootstrap.style.draft || bootstrap.style.active);
  const [cohort, setCohort] = useState<string[]>(bootstrap.selected_source_ids.slice(0, 3));
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
    <div className="page-heading"><div><p className="eyebrow">Pipelines</p><h2>Two real ways to make candidates</h2><p>Each saved pipeline is runnable. Active means it is the default from Sources; it does not make the other pipeline less real.</p></div><button className="button secondary" onClick={() => navigate("#candidates")}>Open candidates</button></div>
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
        {(["identity_to_retain", "composition_to_normalize", "expression_pose_to_discard", "rendering_language"] as const).map((field) => <details key={field} open={field !== "rendering_language"}><summary>{field.replace(/_/g, " ")}</summary><textarea value={directionText(style, field)} onChange={(event) => setStyle({ ...style, generation: { ...style.generation, direction: { ...style.generation.direction, [field]: event.target.value } } })} onBlur={() => void patchGeneration({ direction: style.generation.direction })} /></details>)}
        <details><summary>Avoid</summary><textarea value={style.generation.avoid} onChange={(event) => setStyle({ ...style, generation: { ...style.generation, avoid: event.target.value } })} onBlur={() => void patchGeneration({ avoid: style.generation.avoid })} /></details>
        <details><summary>Amiga renderer and card assembly</summary><div className="form-grid"><label>Dither strength<input type="number" min="0" max="1" step="0.01" value={style.renderer.dither.strength} onChange={(event) => setStyle({ ...style, renderer: { ...style.renderer, dither: { ...style.renderer.dither, strength: Number(event.target.value) } } })} onBlur={() => void patch({ renderer: style.renderer })} /></label><label>Edge threshold<input type="number" min="0" max="1" step="0.01" value={style.renderer.dither.edge_threshold} onChange={(event) => setStyle({ ...style, renderer: { ...style.renderer, dither: { ...style.renderer.dither, edge_threshold: Number(event.target.value) } } })} onBlur={() => void patch({ renderer: style.renderer })} /></label><label>Centering Y<input type="number" min="0" max="1" step="0.01" value={style.composition.centering[1]} onChange={(event) => setStyle({ ...style, composition: { ...style.composition, centering: [style.composition.centering[0], Number(event.target.value)] } })} onBlur={() => void patch({ composition: style.composition })} /></label></div></details>
        <div className="draft-summary"><strong>Current configuration</strong> <code>{shortChecksum(style.checksums.style_sha256)}</code></div>
      </section>
      <section className="surface trial-panel"><div className="panel-heading"><div><p className="eyebrow">Output</p><h3>Run a constant comparison set</h3></div><span>{cohort.length} / 3 sources</span></div><div className="cohort-picker">{bootstrap.sources.map((source) => <button key={source.id} className={cohort.includes(source.id) ? "selected" : ""} aria-pressed={cohort.includes(source.id)} onClick={() => setCohort((current) => current.includes(source.id) ? current.filter((id) => id !== source.id) : current.length < 3 ? [...current, source.id] : current)}>{source.image_url && <img src={source.image_url} alt={source.label} />}<span>{source.label}</span></button>)}</div><div className="trial-actions"><p>Every run produces complete cards immediately. {cohort.length} calls · {modelCost(selectedModel)} each.</p><button className="button primary" disabled={!cohort.length || !selectedModel || Boolean(busy) || Boolean(activeBatch) || !selectedModel.available || (style.generation.execution_mode === "live" && !selectedModel.credentials_configured)} onClick={() => void runTrial()}>{busy === "trial" ? "Starting…" : previewCards.length ? "Run this configuration again" : "Run comparison set"}</button></div>{(trial || previewCards.length > 0) && <div className="trial-result"><span className={`status-chip ${trial?.status || "ready"}`}>{trial?.status || "ready"}</span>{previewCards.map((item) => item.card_url && <img key={item.item_id} src={item.card_url} alt={`${item.source_label} pipeline result`} />)}{trial?.status === "ready" && trial.model_capabilities?.execution_mode === "live" && <button className="button primary" disabled={busy === "activate"} onClick={() => void activate()}>{busy === "activate" ? "Saving…" : "Save as pipeline & make active"}</button>}</div>}</section>
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
  const sources = selectedSources(bootstrap);
  const [busy, setBusy] = useState("");
  const [pipelineId, setPipelineId] = useState(bootstrap.style.active_pipeline_id);
  const selectedCard = bootstrap.cards.find((card) => card.item_id === cardId && (!batchId || card.batch_id === batchId));
  const [framing, setFraming] = useState<Framing>(selectedCard?.framing || { zoom: 1, offset_x: 0, offset_y: 0 });
  const selectedPipeline = pipelines.find((pipeline) => pipeline.pipeline_id === pipelineId) || pipelines[0];
  const model = bootstrap.models.find((entry) => entry.id === selectedPipeline?.style.generation.model_id && entry.execution_mode === selectedPipeline?.style.generation.execution_mode);
  const activeBatch = bootstrap.batches.find((batch) => isActive(batch.status));
  useEffect(() => { if (selectedCard) setFraming(selectedCard.framing || { zoom: 1, offset_x: 0, offset_y: 0 }); }, [selectedCard?.item_id]);

  async function generate(sourceIds = bootstrap.selected_source_ids, selectedId = pipelineId) {
    if (!sourceIds.length || !selectedId) return;
    setBusy("generate");
    const pipeline = pipelines.find((item) => item.pipeline_id === selectedId);
    try { await api.createProduction(sourceIds, selectedId, pipeline?.style.generation.execution_mode === "live"); notify(`${sourceIds.length}-source ${pipeline?.label || "pipeline"} run started`); await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
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
    <div className="page-heading"><div><p className="eyebrow">Candidate generation</p><h2>Generate, compare, and keep the good ones</h2><p>Rows keep the source identity constant. Columns show the real pipeline that produced each candidate.</p></div><div className="heading-actions"><label className="pipeline-picker">Pipeline<select aria-label="Pipeline to run" value={pipelineId} onChange={(event) => setPipelineId(event.target.value)}>{pipelines.map((pipeline) => <option key={pipeline.pipeline_id} value={pipeline.pipeline_id}>{pipeline.label}{pipeline.active ? " · active default" : ""}</option>)}</select></label><small className="run-cost">{sources.length} calls · {modelCost(model)} each</small><button className="button primary" disabled={Boolean(activeBatch) || Boolean(busy) || !sources.length || !model?.available || !model.credentials_configured} onClick={() => void generate()}>{activeBatch ? "Pipeline running…" : `Generate ${sources.length} candidate${sources.length === 1 ? "" : "s"}`}</button></div></div>
    {activeBatch && <div className="surface running-banner"><span className="spinner" /><div><strong>Producing new generations</strong><small>{activeBatch.progress.ready_cards} / {activeBatch.progress.selected_sources} cards ready</small></div></div>}
    {!sources.length ? <div className="empty-panel surface"><span className="empty-glyph">→</span><h3>Choose at least one source first</h3><button className="button primary" onClick={() => navigate("#sources")}>Choose sources</button></div> : <div className="results-matrix surface" style={{ "--pipeline-count": pipelines.length } as React.CSSProperties}>
      <div className="matrix-corner"><small>Source identity</small><strong>{sources.length} pinned</strong></div>
      {pipelines.map((pipeline) => <div className={`matrix-pipeline ${pipeline.active ? "active" : ""}`} key={pipeline.pipeline_id}><span>{pipeline.active ? "active default" : "runnable pipeline"}</span><strong>{pipeline.label}</strong><small>{pipeline.description}</small></div>)}
      {sources.map((source) => <div className="matrix-row" key={source.id}>
        <div className="matrix-source">{source.image_url && <img src={source.image_url} alt={source.label} />}<div><small>source</small><strong>{source.label}</strong></div></div>
        {pipelines.map((pipeline) => { const cards = bootstrap.cards.filter((candidate) => candidate.pipeline_id === pipeline.pipeline_id && candidate.source_id === source.id); const latest = cards[0]; return <article className={`matrix-result ${cards.length ? "produced" : "missing"}`} key={pipeline.pipeline_id}>{cards.length ? <><div className="generation-gallery">{cards.map((card, index) => <div className={`generation-card ${selectedCard?.item_id === card.item_id ? "selected" : ""}`} key={`${card.batch_id}:${card.item_id}`}><button className="candidate-open" onClick={() => navigate(`#candidates/${card.batch_id}/${card.item_id}`)}><img src={card.card_url} alt={`${source.label} ${pipeline.label} candidate ${index + 1}`} /><span><strong>Candidate {String(index + 1).padStart(2, "0")}</strong><small>{generationOrigin(card)}</small></span></button><button className={`favorite-button ${card.favorite ? "saved" : ""}`} aria-label={card.favorite ? "Remove from Collection" : "Save to Collection"} disabled={Boolean(busy)} onClick={() => void toggleFavorite(card)}>{card.favorite ? "★" : "☆"}</button></div>)}</div><div className="candidate-result-footer"><span>{cards.length} candidate{cards.length === 1 ? "" : "s"}</span><button disabled={Boolean(busy) || Boolean(activeBatch)} onClick={() => void tryAnother(latest)}>Generate again</button></div></> : <><span className="empty-glyph">＋</span><small>No candidates yet</small><button className="text-button" disabled={Boolean(activeBatch) || Boolean(busy)} onClick={() => void generate([source.id], pipeline.pipeline_id)}>Generate</button></>}</article>; })}
      </div>)}
    </div>}
    {selectedCard && <section className="surface result-inspector"><div className="panel-heading"><div><p className="eyebrow">{selectedCard.pipeline_label} · {selectedCard.source_label}</p><h3>Candidate details</h3><p>Inspect every stage, adjust the framing, or save this candidate to Collection.</p></div><button className="button secondary" onClick={() => navigate("#candidates")}>Close</button></div><div className="asset-stages"><figure><img src={selectedCard.source_url} alt="Source" /><figcaption>Source</figcaption></figure><span>→</span><figure><img src={selectedCard.master_url} alt="Generated master" /><figcaption>Generated master</figcaption></figure><span>→</span><figure><img className="pixelated" src={selectedCard.art_url} alt="Amiga art" /><figcaption>Rendered art</figcaption></figure><span>→</span><figure className="final-stage"><img className="pixelated" src={selectedCard.card_url} alt="Final card" /><figcaption>Candidate card</figcaption></figure></div><div className="framing-controls"><label>Zoom<input type="range" min="1" max="3" step="0.01" value={framing.zoom} onChange={(event) => setFraming({ ...framing, zoom: Number(event.target.value) })} /></label><label>Horizontal<input type="range" min="-1" max="1" step="0.01" value={framing.offset_x} onChange={(event) => setFraming({ ...framing, offset_x: Number(event.target.value) })} /></label><label>Vertical<input type="range" min="-1" max="1" step="0.01" value={framing.offset_y} onChange={(event) => setFraming({ ...framing, offset_y: Number(event.target.value) })} /></label></div><div className="inspector-actions"><button className="button primary" disabled={Boolean(busy)} onClick={() => void toggleFavorite(selectedCard)}>{selectedCard.favorite ? "★ Saved to Collection" : "☆ Save to Collection"}</button><button className="button secondary" disabled={Boolean(busy)} onClick={() => void tryAnother(selectedCard)}>Generate another result</button><button className="button secondary" disabled={Boolean(busy)} onClick={() => void render(selectedCard)}>{busy === `render-${selectedCard.item_id}` ? "Rerendering…" : "Save framing · no generation"}</button></div><ResultProvenance card={selectedCard} /></section>}
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
