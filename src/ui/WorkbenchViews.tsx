import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { api } from "./api";
import type { Bootstrap, Framing, Model, PipelineStyle, PipelineVersion, ProducedCard, ProductionBatch, SearchResult, Source } from "./types";

type Notice = (message: string, kind?: "success" | "error") => void;
type Shared = { bootstrap: Bootstrap; navigate: (hash: string) => void; refresh: () => Promise<void>; notify: Notice };

function formatCost(value: number | null | undefined) {
  return value == null ? "provider-priced" : value === 0 ? "$0 simulation" : `$${value.toFixed(4)}`;
}
function modelCost(model: Model | undefined) { return formatCost(model?.pricing?.[0]?.cost_usd as number | undefined); }
function isActive(status: string) { return ["queued", "running", "processing"].includes(status); }
function versionName(version: number | null | undefined) { return version ? `Pipeline ${String(version).padStart(2, "0")}` : "Working pipeline"; }
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
      const response = await api.createProduction(selected, pipeline.identity.style_version_id, pipeline.generation.execution_mode === "live");
      notify(`${selected.length}-source pipeline run started`);
      navigate(`#cards/${response.batch.batch_id}`);
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
      <div className="launcher-flow"><div><p className="eyebrow">Current source set</p><strong>{selected.length} identities</strong></div><i>→</i><button className="pipeline-token" onClick={() => navigate("#pipelines")}><small>Active pipeline · v{pipeline.identity.version}</small><strong>{pipeline.identity.label}</strong><span>{model?.name || pipeline.generation.model_id} · {referenceCount} refs</span></button><i>→</i><div><p className="eyebrow">Expected output</p><strong>{selected.length} cards</strong></div></div>
      <div className="launcher-action"><p>{selected.length} generation call{selected.length === 1 ? "" : "s"} · {modelCost(model)} each. Runs start immediately so comparison sets stay easy to replenish.</p><button className="button primary large" disabled={Boolean(problem) || Boolean(busy)} onClick={() => void runPipeline()}>{busy === "run" ? "Starting pipeline…" : `Run ${selected.length} source${selected.length === 1 ? "" : "s"}`}</button>{problem && <p className="validation-note" role="status">{problem}</p>}</div>
    </section>
  </section>;
}

type PipelineCard = PipelineVersion & { outputCount: number; samples: ProducedCard[] };

function pipelineResults(cards: ProducedCard[], styleId: string, checksum?: string) {
  return cards.filter((card) => card.style_version_id === styleId && (!checksum || card.style_checksum_sha256 === checksum));
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
  const selectedId = pipelineId || draft?.identity.style_version_id || active.identity.style_version_id;
  const selectedStyle = selectedId === draft?.identity.style_version_id ? draft : selectedId === active.identity.style_version_id ? active : undefined;
  const selectedVersion = bootstrap.style.versions.find((version) => version.style_version_id === selectedId);
  const selectedChecksum = selectedStyle?.checksums.style_sha256 || selectedVersion?.checksum_sha256;
  const selectedCards = pipelineResults(bootstrap.cards, selectedId, selectedChecksum);
  const pipelineCards: PipelineCard[] = bootstrap.style.versions.slice().reverse().map((version) => {
    const outputs = pipelineResults(bootstrap.cards, version.style_version_id, version.checksum_sha256);
    return { ...version, outputCount: new Set(outputs.map((card) => card.source_id)).size, samples: outputs.slice(0, 3) };
  });
  const generationRefs = style.reference_pack.assets.filter((asset) => asset.role === "generation-reference");
  const target = style.reference_pack.assets.find((asset) => asset.role === "target-example");
  const models = bootstrap.models.filter((model) => model.execution_mode === style.generation.execution_mode);
  const selectedModel = bootstrap.models.find((model) => model.id === style.generation.model_id && model.execution_mode === style.generation.execution_mode);
  const activeBatch = bootstrap.batches.find((batch) => isActive(batch.status));
  const previewCards = trial?.items.filter((item) => item.status === "ready") || (draft ? pipelineResults(bootstrap.cards, draft.identity.style_version_id, draft.checksums.style_sha256) : []);
  useEffect(() => { if (draft) setStyle(draft); else setStyle(active); }, [draft?.identity.style_version_id, draft?.checksums.style_sha256, active.identity.style_version_id]);

  async function beginEdit() {
    setBusy("draft");
    try { const response = await api.createDraft(); setStyle(response.style); navigate(`#pipelines/${response.style.identity.style_version_id}`); await refresh(); notify("Working pipeline created"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
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
  async function activate() { if (!trial) return; setBusy("activate"); try { const response = await api.activateTrial(trial.batch_id); notify("Pipeline saved and made active"); await refresh(); setStyle(response.style.active); navigate(`#pipelines/${response.style.active.identity.style_version_id}`); setTrial(undefined); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); } }
  async function uploadReference(event: ChangeEvent<HTMLInputElement>) { const file = event.target.files?.[0]; if (!file) return; setBusy("reference"); try { const response = await api.uploadDraftReference(file); setStyle(response.style); await refresh(); notify("Pipeline reference added"); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); event.target.value = ""; } }
  async function moveReference(index: number, delta: number) { const nextIndex = index + delta; if (nextIndex < 0 || nextIndex >= generationRefs.length) return; const ordered = [...generationRefs]; [ordered[index], ordered[nextIndex]] = [ordered[nextIndex], ordered[index]]; const targetAsset = style.reference_pack.assets.find((asset) => asset.role === "target-example"); await patch({ reference_pack: { ...style.reference_pack, assets: targetAsset ? [...ordered, targetAsset] : ordered } }); }

  return <section className="page pipelines-page">
    <div className="page-heading"><div><p className="eyebrow">Pipelines</p><h2>The recipe is an asset too</h2><p>Each pipeline records the model direction, ordered references, renderer, card assembly, and the cards it produced.</p></div><button className="button secondary" onClick={() => navigate("#cards")}>Compare all results</button></div>
    <section className="pipeline-collection" aria-label="Saved pipelines">
      {draft && <button className={`surface pipeline-card draft ${selectedId === draft.identity.style_version_id ? "selected" : ""}`} onClick={() => navigate(`#pipelines/${draft.identity.style_version_id}`)}><div><span className="status-chip working">working</span><small>{shortChecksum(draft.checksums.style_sha256)}</small></div><strong>Working pipeline</strong><p>{draft.generation.model_id} · {draft.reference_pack.assets.filter((asset) => asset.role === "generation-reference").length} refs</p><div className="pipeline-samples">{pipelineResults(bootstrap.cards, draft.identity.style_version_id, draft.checksums.style_sha256).slice(0, 3).map((card) => <img key={card.item_id} src={card.card_url} alt="Working pipeline result" />)}<span>＋</span></div></button>}
      {pipelineCards.map((pipeline) => <button className={`surface pipeline-card ${pipeline.active ? "active" : ""} ${selectedId === pipeline.style_version_id ? "selected" : ""}`} key={pipeline.style_version_id} onClick={() => navigate(`#pipelines/${pipeline.style_version_id}`)}><div>{pipeline.active ? <span className="status-chip">active</span> : <span>{versionName(pipeline.version)}</span>}<small>{shortChecksum(pipeline.checksum_sha256)}</small></div><strong>{pipeline.label}</strong><p>{pipeline.model_id} · {pipeline.reference_count} refs</p><div className="pipeline-samples">{pipeline.samples.map((card) => <img key={card.item_id} src={card.card_url} alt={`${pipeline.label} result`} />)}<span>{pipeline.outputCount || "＋"}</span></div></button>)}
    </section>
    <PipelineDiagram style={selectedStyle} cards={selectedCards} sources={selectedSources(bootstrap)} />
    <section className="surface pipeline-meta"><div><p className="eyebrow">{selectedId === draft?.identity.style_version_id ? "Working pipeline" : selectedVersion?.active ? "Active pipeline" : versionName(selectedVersion?.version)}</p><h3>{selectedStyle?.identity.label || selectedVersion?.label || selectedId}</h3><p><code>{selectedId}</code> · checksum <code>{shortChecksum(selectedChecksum || "")}</code></p></div><div className="palette-strip">{selectedStyle?.renderer.palette.map((colour) => <i key={colour} style={{ backgroundColor: colour }} title={colour} />)}</div>{!draft && <button className="button primary" disabled={busy === "draft"} onClick={() => void beginEdit()}>{busy === "draft" ? "Creating…" : "Branch active pipeline"}</button>}{draft && selectedId !== draft.identity.style_version_id && <button className="button primary" onClick={() => navigate(`#pipelines/${draft.identity.style_version_id}`)}>Open working pipeline</button>}</section>
    {draft && selectedId === draft.identity.style_version_id && <>
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

type StrategyGroup = { id: string; label: string; description: string; cards: ProducedCard[]; configurations: string[]; active: boolean };

function cardStrategy(card: ProducedCard) {
  if (card.strategy_id) return { id: card.strategy_id, label: card.strategy_label, description: card.strategy_description };
  const interpretive = card.generation?.execution_mode === "live" || !String(card.generation?.model || "").startsWith("fake/");
  return interpretive
    ? { id: "interpretive-redraw", label: "Interpretive redraw", description: "Image-model redraw followed by Amiga rendering" }
    : { id: "direct-render", label: "Direct render", description: "Source-led deterministic rendering baseline" };
}

function strategyGroups(bootstrap: Bootstrap): StrategyGroup[] {
  const groups = new Map<string, StrategyGroup>();
  const active = bootstrap.style.active;
  [...bootstrap.cards].sort((a, b) => b.batch_created_at.localeCompare(a.batch_created_at) || b.attempt_number - a.attempt_number).forEach((card) => {
    const strategy = cardStrategy(card);
    const configuration = `${card.style_version_id}:${card.style_checksum_sha256}`;
    const group = groups.get(strategy.id) || { ...strategy, cards: [], configurations: [], active: false };
    group.cards.push(card);
    if (!group.configurations.includes(configuration)) group.configurations.push(configuration);
    if (card.style_version_id === active.identity.style_version_id && card.style_checksum_sha256 === active.checksums.style_sha256) group.active = true;
    groups.set(strategy.id, group);
  });
  return [...groups.values()].sort((a, b) => Number(b.id === "interpretive-redraw") - Number(a.id === "interpretive-redraw"));
}

function generationOrigin(card: ProducedCard) {
  const pipeline = card.style_version_id.startsWith("draft_") ? `experiment ${shortChecksum(card.style_checksum_sha256)}` : versionName(card.pipeline_version);
  return `${pipeline} · attempt ${card.attempt_number}`;
}

function ResultProvenance({ card }: { card: ProducedCard }) {
  const refs = card.reference_stack.filter((reference) => reference.role === "generation-reference");
  return <details><summary>Run details</summary><div className="details-content"><p>Pipeline <code>{card.style_version_id}</code> · configuration <code>{shortChecksum(card.style_checksum_sha256)}</code></p><p>Generation: <strong>{String(card.generation?.execution_mode || "unknown")}</strong> · {String(card.generation?.model || "model unavailable")}</p><p>Ordered references: {refs.length ? refs.map((reference, index) => <span key={String(reference.reference_id || index)}> {index ? "→ " : ""}{String(reference.label || reference.reference_id)}</span>) : "—"}</p><p>Render revision {card.render_revision} · card checksum <code>{card.card_checksum_sha256 || "—"}</code></p></div></details>;
}

export function CardsView({ bootstrap, navigate, refresh, notify, batchId, cardId }: Shared & { batchId?: string; cardId?: string }) {
  const groups = useMemo(() => strategyGroups(bootstrap), [bootstrap.cards, bootstrap.style.active.identity.style_version_id]);
  const sources = selectedSources(bootstrap);
  const [busy, setBusy] = useState("");
  const selectedCard = bootstrap.cards.find((card) => card.item_id === cardId && (!batchId || card.batch_id === batchId));
  const [framing, setFraming] = useState<Framing>(selectedCard?.framing || { zoom: 1, offset_x: 0, offset_y: 0 });
  const activePipeline = bootstrap.style.active;
  const model = bootstrap.models.find((entry) => entry.id === activePipeline.generation.model_id && entry.execution_mode === activePipeline.generation.execution_mode);
  const activeBatch = bootstrap.batches.find((batch) => isActive(batch.status));
  useEffect(() => { if (selectedCard) setFraming(selectedCard.framing || { zoom: 1, offset_x: 0, offset_y: 0 }); }, [selectedCard?.item_id]);

  async function generate(sourceIds = bootstrap.selected_source_ids) {
    if (!sourceIds.length) return;
    setBusy("generate");
    try { await api.createProduction(sourceIds, activePipeline.identity.style_version_id, activePipeline.generation.execution_mode === "live"); notify(`${sourceIds.length}-source pipeline run started`); await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function tryAnother(card: ProducedCard) {
    setBusy(card.item_id);
    try { await api.tryAnother(card.batch_id, card.source_id, card.generation?.execution_mode === "live"); notify("Another result queued"); await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function render(card: ProducedCard) {
    setBusy(`render-${card.item_id}`);
    try { await api.renderFraming(card.batch_id, card.item_id, framing); notify("Framing rerendered"); await refresh(); } catch (error) { notify((error as Error).message, "error"); } finally { setBusy(""); }
  }

  if (!groups.length) return <section className="page cards-page"><div className="page-heading"><div><p className="eyebrow">Cards</p><h2>Produced assets appear here</h2><p>Run a source set through the active pipeline to start a visual history.</p></div></div><div className="empty-panel surface"><span className="empty-glyph">→</span><h3>No pipeline results yet</h3><button className="button primary" onClick={() => navigate("#sources")}>Choose sources</button></div></section>;

  return <section className="page cards-page">
    <div className="page-heading"><div><p className="eyebrow">Cards · strategy comparison</p><h2>Two strategies, every generation</h2><p>Rows hold identity constant. Each strategy keeps every generated candidate, with pipeline details tucked underneath.</p></div><div className="heading-actions"><span className="status-chip">{groups.length} {groups.length === 1 ? "strategy" : "strategies"} · {bootstrap.cards.length} generations</span><small className="run-cost">{sources.length} calls · {modelCost(model)} each</small><button className="button primary" disabled={Boolean(activeBatch) || Boolean(busy) || !sources.length || !model?.available || !model.credentials_configured} onClick={() => void generate()}>{activeBatch ? "Pipeline running…" : `Run active pipeline · ${sources.length}`}</button></div></div>
    {activeBatch && <div className="surface running-banner"><span className="spinner" /><div><strong>Producing new generations</strong><small>{activeBatch.progress.ready_cards} / {activeBatch.progress.selected_sources} cards ready</small></div></div>}
    <div className="results-matrix surface" style={{ "--pipeline-count": groups.length } as React.CSSProperties}>
      <div className="matrix-corner"><small>Source identity</small><strong>{sources.length} pinned</strong></div>
      {groups.map((group) => <div className={`matrix-pipeline ${group.active ? "active" : ""}`} key={group.id}><span>{group.active ? "active strategy" : "baseline strategy"}</span><strong>{group.label}</strong><small>{group.description} · {group.configurations.length} configuration{group.configurations.length === 1 ? "" : "s"}</small></div>)}
      {sources.map((source) => <div className="matrix-row" key={source.id}>
        <div className="matrix-source">{source.image_url && <img src={source.image_url} alt={source.label} />}<div><small>source</small><strong>{source.label}</strong></div></div>
        {groups.map((group) => { const cards = group.cards.filter((candidate) => candidate.source_id === source.id); const latest = cards[0]; return <article className={`matrix-result ${cards.length ? "produced" : "missing"}`} key={group.id}>{cards.length ? <><div className="generation-gallery">{cards.map((card, index) => <button className={`generation-card ${selectedCard?.item_id === card.item_id ? "selected" : ""}`} key={`${card.batch_id}:${card.item_id}`} onClick={() => navigate(`#cards/${card.batch_id}/${card.item_id}`)}><img src={card.card_url} alt={`${source.label} ${group.label} generation ${index + 1}`} /><span><strong>Gen {String(index + 1).padStart(2, "0")}</strong><small>{generationOrigin(card)}</small></span></button>)}</div><div className="strategy-result-footer"><span>{cards.length} generation{cards.length === 1 ? "" : "s"}</span><button disabled={Boolean(busy) || Boolean(activeBatch)} onClick={() => void tryAnother(latest)}>Generate again</button></div></> : <><span className="empty-glyph">＋</span><small>No {group.label.toLowerCase()} result</small>{group.active && <button className="text-button" disabled={Boolean(activeBatch) || Boolean(busy)} onClick={() => void generate([source.id])}>Generate</button>}</>}</article>; })}
      </div>)}
    </div>
    {selectedCard && <section className="surface result-inspector"><div className="panel-heading"><div><p className="eyebrow">{selectedCard.strategy_label} · {selectedCard.source_label}</p><h3>{selectedCard.pipeline_label}</h3><p>Inspect every stage or rerender the existing master. This candidate remains part of its strategy gallery.</p></div><button className="button secondary" onClick={() => navigate("#cards")}>Close</button></div><div className="asset-stages"><figure><img src={selectedCard.source_url} alt="Source" /><figcaption>Source</figcaption></figure><span>→</span><figure><img src={selectedCard.master_url} alt="Generated master" /><figcaption>Generated master</figcaption></figure><span>→</span><figure><img className="pixelated" src={selectedCard.art_url} alt="Amiga art" /><figcaption>Rendered art</figcaption></figure><span>→</span><figure className="final-stage"><img className="pixelated" src={selectedCard.card_url} alt="Final card" /><figcaption>Card</figcaption></figure></div><div className="framing-controls"><label>Zoom<input type="range" min="1" max="3" step="0.01" value={framing.zoom} onChange={(event) => setFraming({ ...framing, zoom: Number(event.target.value) })} /></label><label>Horizontal<input type="range" min="-1" max="1" step="0.01" value={framing.offset_x} onChange={(event) => setFraming({ ...framing, offset_x: Number(event.target.value) })} /></label><label>Vertical<input type="range" min="-1" max="1" step="0.01" value={framing.offset_y} onChange={(event) => setFraming({ ...framing, offset_y: Number(event.target.value) })} /></label></div><div className="inspector-actions"><button className="button primary" disabled={Boolean(busy)} onClick={() => void tryAnother(selectedCard)}>Generate another result</button><button className="button secondary" disabled={Boolean(busy)} onClick={() => void render(selectedCard)}>{busy === `render-${selectedCard.item_id}` ? "Rerendering…" : "Save framing · no generation"}</button></div><ResultProvenance card={selectedCard} /></section>}
  </section>;
}
