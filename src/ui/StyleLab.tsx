import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { Model, Recipe, Run, RunSummary, SearchResult, Source, Workspace } from "./types";

const directionLabels: Array<[keyof Recipe["direction"], string, string]> = [
  ["medium_brushwork", "Medium & brushwork", "What the paint should feel like."],
  ["lighting", "Lighting", "Set the light source and temperature."],
  ["background", "Background", "Describe the quiet field behind the subject."],
  ["composition", "Composition", "Control the portrait's shape in the card window."],
  ["colour", "Colour", "Choose the palette relationships."],
  ["detail", "Detail", "Say what earns crisp attention."],
  ["identity", "Identity retention", "Describe what must remain recognizable."],
];

function formatTime(value: string) { return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); }

type Props = {
  workspace: Workspace;
  models: Model[];
  runs: RunSummary[];
  activeRun?: Run;
  onWorkspace: (workspace: Workspace) => void;
  onRefresh: () => Promise<void>;
  onNavigate: (hash: string) => void;
  onMessage: (message: string, kind?: "success" | "error") => void;
};

export function StyleLab({ workspace, models, runs, activeRun, onWorkspace, onRefresh, onNavigate, onMessage }: Props) {
  const activeRecipe = workspace.recipes.find((recipe) => recipe.id === workspace.active_recipe_id) || workspace.recipes[0];
  const [recipe, setRecipe] = useState<Recipe | undefined>(activeRecipe);
  const [sourcePanel, setSourcePanel] = useState(false);
  const [referencePanel, setReferencePanel] = useState(false);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [busy, setBusy] = useState("");
  const [uploadLabel, setUploadLabel] = useState("");
  const [runOutputs, setRunOutputs] = useState(1);
  const [runLaunching, setRunLaunching] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState("");

  useEffect(() => setRecipe(workspace.recipes.find((item) => item.id === workspace.active_recipe_id) || workspace.recipes[0]), [workspace]);
  const benchmark = useMemo(() => workspace.benchmark_source_ids.map((id) => workspace.sources.find((source) => source.id === id)).filter(Boolean) as Source[], [workspace]);
  const unselected = workspace.sources.filter((source) => !workspace.benchmark_source_ids.includes(source.id));
  const references = workspace.references;

  function patchRecipe(patch: Partial<Recipe>) { setRecipe((current) => current ? { ...current, ...patch } : current); }
  function patchDirection(key: keyof Recipe["direction"], value: string) { setRecipe((current) => current ? { ...current, direction: { ...current.direction, [key]: value } } : current); }
  async function updateBenchmark(ids: string[]) {
    setBusy("benchmark");
    try { const result = await api.updateBenchmark(ids); onWorkspace(result.workspace); onMessage("Benchmark order saved", "success"); } catch (error) { onMessage((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function addSource(id: string) { await updateBenchmark([...workspace.benchmark_source_ids, id]); }
  async function removeSource(id: string) { await updateBenchmark(workspace.benchmark_source_ids.filter((candidate) => candidate !== id)); }
  async function moveSource(index: number, direction: -1 | 1) {
    const next = [...workspace.benchmark_source_ids]; const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]]; await updateBenchmark(next);
  }
  async function search() {
    setBusy("search");
    try { setSearchResults((await api.searchSources(query)).results); } catch (error) { onMessage((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function upload(kind: "sources" | "references", event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file) return;
    setBusy(`upload-${kind}`);
    try { const result = await api.upload(kind, file, uploadLabel); onWorkspace(result.workspace); setUploadLabel(""); onMessage(`${kind === "sources" ? "Source" : "Reference"} added`, "success"); } catch (error) { onMessage((error as Error).message, "error"); } finally { setBusy(""); event.target.value = ""; }
  }
  async function importSearchResult(result: SearchResult) {
    setBusy(`import-${result.pexels_photo_id}`);
    try { const response = await api.importSource(result); onWorkspace(response.workspace); onMessage("Source downloaded into the workspace", "success"); } catch (error) { onMessage((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function deleteSource(source: Source) {
    const token = `source:${source.id}`;
    if (confirmDelete !== token) { setConfirmDelete(token); return; }
    try { onWorkspace((await api.deleteSource(source.id)).workspace); setConfirmDelete(""); } catch (error) { onMessage((error as Error).message, "error"); }
  }
  async function deleteReference(id: string) {
    const token = `reference:${id}`;
    if (confirmDelete !== token) { setConfirmDelete(token); return; }
    try { onWorkspace((await api.deleteReference(id)).workspace); setConfirmDelete(""); } catch (error) { onMessage((error as Error).message, "error"); }
  }
  async function saveRecipe() {
    if (!recipe) return;
    setBusy("recipe");
    try { const response = await api.updateRecipe(recipe.id, recipe); onWorkspace(response.workspace); onMessage("Recipe saved", "success"); } catch (error) { onMessage((error as Error).message, "error"); } finally { setBusy(""); }
  }
  async function duplicateRecipe() {
    if (!recipe) return;
    try { const response = await api.duplicateRecipe(recipe.id); const selected = await api.selectRecipe(response.recipe.id); onWorkspace(selected.workspace); onMessage("Recipe duplicated; edit the copy to change one variable", "success"); } catch (error) { onMessage((error as Error).message, "error"); }
  }
  async function createRecipe() {
    if (!recipe) return;
    try { const response = await api.createRecipe({ ...recipe, name: `${recipe.name} · new variable`, reference_ids: [] }); const selected = await api.selectRecipe(response.recipe.id); onWorkspace(selected.workspace); onMessage("New recipe created", "success"); } catch (error) { onMessage((error as Error).message, "error"); }
  }
  async function selectRecipe(id: string) {
    try { onWorkspace((await api.selectRecipe(id)).workspace); } catch (error) { onMessage((error as Error).message, "error"); }
  }
  async function launchRun() {
    if (!recipe) return;
    setRunLaunching(true);
    try { const response = await api.startRun(recipe.id, runOutputs); onNavigate(`#run/${response.run.run_id}`); onMessage("Benchmark queued", "success"); } catch (error) { onMessage((error as Error).message, "error"); } finally { setRunLaunching(false); }
  }
  async function reviewRun(verdict: string) {
    if (!activeRun) return;
    try { onNavigate(`#run/${activeRun.run_id}`); await api.reviewRun(activeRun.run_id, verdict, activeRun.note || ""); await onRefresh(); onMessage("Sheet verdict saved", "success"); } catch (error) { onMessage((error as Error).message, "error"); }
  }
  async function usePortrait(itemId: string) {
    if (!activeRun) return;
    try { const response = await api.createCard(activeRun.run_id, itemId, "Experimental claimant", "bust"); onNavigate(`#card/${response.card.card_id}`); } catch (error) { onMessage((error as Error).message, "error"); }
  }

  if (activeRun) return <RunSheet run={activeRun} runs={runs} onReview={reviewRun} onUsePortrait={usePortrait} onNavigate={onNavigate} onRefresh={onRefresh} onMessage={onMessage} />;

  return <div className="lab-layout">
    {(workspace.sources.length === 0 || workspace.references.length === 0) && <div className="empty-setup surface"><div className="empty-glyph">◇</div><div><p className="eyebrow">Start here</p><h2>Build an experiment in three small pieces</h2><p>Add source portraits to the benchmark, curate a few consistent style references, then edit the seeded recipe below. The controls stay on this page; you can run a one-source smoke test at any time.</p></div><button className="button primary" onClick={() => setSourcePanel(true)}>Open source controls</button></div>}
    <section className="benchmark-strip surface">
      <div className="section-heading"><div><p className="eyebrow">01 / Input set</p><h2>Benchmark portraits</h2></div><span className="recommendation">6–10 recommended · {benchmark.length} selected</span><button className="button secondary" onClick={() => setSourcePanel((value) => !value)}>{sourcePanel ? "Close source finder" : "Find or upload"}</button></div>
      <p className="section-help">Keep the people and order fixed while you compare recipes. A one-source smoke test is fine.</p>
      {sourcePanel && <div className="setup-drawer source-drawer">
      <div className="drawer-column"><label className="field-label">Search Pexels<input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && search()} placeholder="e.g. eccentric portrait hat" /></label><button className="button primary" onClick={search} disabled={busy === "search"}>{busy === "search" ? "Searching…" : "Search visually"}</button><div className="search-results">{searchResults.map((result) => <article className="search-result" key={result.pexels_photo_id}><img src={result.preview_url} alt="" /><div><strong>Pexels {result.pexels_photo_id}</strong><small>{result.photographer || "Pexels"}</small><button className="text-button" onClick={() => importSearchResult(result)} disabled={busy === `import-${result.pexels_photo_id}`}>{busy === `import-${result.pexels_photo_id}` ? "Adding…" : "Add source"}</button></div></article>)}</div></div>
        <div className="drawer-column upload-column"><p className="field-label">Local upload</p><p className="muted">Use a local image when Pexels is unavailable. Original filenames remain provenance only.</p><input className="text-input" value={uploadLabel} onChange={(event) => setUploadLabel(event.target.value)} placeholder="Optional source label" /><label className="file-button button secondary">{busy === "upload-sources" ? "Uploading…" : "Choose image"}<input type="file" accept="image/*" onChange={(event) => upload("sources", event)} disabled={Boolean(busy)} /></label></div>
      </div>}
      <div className="benchmark-row">{benchmark.map((source, index) => <article className="benchmark-card" key={source.id}><img src={source.image_url} alt={source.label} /><div className="benchmark-card-body"><span className="order-number">{String(index + 1).padStart(2, "0")}</span><strong>{source.label}</strong><small>{source.provenance.kind === "pexels" ? `Pexels · ${String(source.provenance.photographer || "")}` : "Local upload"}</small><div className="card-actions"><button className="icon-button" onClick={() => moveSource(index, -1)} disabled={index === 0} aria-label="Move left">←</button><button className="icon-button" onClick={() => moveSource(index, 1)} disabled={index === benchmark.length - 1} aria-label="Move right">→</button><button className="text-button danger-text" onClick={() => removeSource(source.id)}>Remove</button></div></div></article>)}{benchmark.length === 0 && <div className="empty-strip">No benchmark portraits yet. Add a local image or search Pexels to begin.</div>}</div>
      {unselected.length > 0 && <div className="available-sources"><span>Imported, not in benchmark:</span>{unselected.map((source) => <button className="source-chip" key={source.id} onClick={() => addSource(source.id)}><img src={source.image_url} alt="" />{source.label}<b>+</b></button>)}</div>}
      {workspace.sources.length > 0 && <details className="secondary-list"><summary>All imported sources ({workspace.sources.length})</summary><div>{workspace.sources.map((source) => <span key={source.id}>{source.label} <button className="text-button danger-text" onClick={() => deleteSource(source)}>{confirmDelete === `source:${source.id}` ? "Confirm delete" : "Delete"}</button></span>)}</div></details>}
    </section>

    <div className="lab-columns">
      <section className="recipe-panel surface"><div className="section-heading"><div><p className="eyebrow">02 / Recipe</p><h2>Art direction</h2></div><div className="recipe-actions"><button className="button secondary" onClick={createRecipe} disabled={!recipe}>New</button><button className="button secondary" onClick={duplicateRecipe} disabled={!recipe}>Duplicate</button></div></div>
        {workspace.recipes.length > 1 && <label className="field-label">Recipe version<select value={recipe?.id || ""} onChange={(event) => selectRecipe(event.target.value)}>{workspace.recipes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        {recipe ? <><label className="field-label">Name<input value={recipe.name} onChange={(event) => patchRecipe({ name: event.target.value })} /></label><div className="form-grid"><label className="field-label">Model<select value={recipe.model} onChange={(event) => patchRecipe({ model: event.target.value })}>{models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label><label className="field-label">Quality<select value={recipe.quality} onChange={(event) => patchRecipe({ quality: event.target.value as Recipe["quality"] })}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label></div>{directionLabels.map(([key, label, help]) => <label className="field-label" key={key}>{label}<span className="field-help">{help}</span><textarea rows={2} value={recipe.direction[key]} onChange={(event) => patchDirection(key, event.target.value)} /></label>)}<label className="field-label">Avoid<span className="field-help">The resolver shows this as an explicit instruction when a backend lacks negative prompts.</span><textarea rows={2} value={recipe.avoid} onChange={(event) => patchRecipe({ avoid: event.target.value })} /></label><div className="reference-pack"><div className="pack-heading"><span>Style reference pack</span><button className="text-button" onClick={() => setReferencePanel((value) => !value)}>{referencePanel ? "Close" : "Manage"}</button></div><p className="muted">{recipe.reference_ids.length} selected · 4–6 recommended</p><div className="reference-thumbs">{recipe.reference_ids.map((id) => { const reference = references.find((item) => item.id === id); return reference ? <img key={id} src={reference.image_url} title={reference.label} alt={reference.label} /> : null; })}</div>{referencePanel && <ReferenceManager workspace={workspace} recipe={recipe} onWorkspace={onWorkspace} onRecipe={setRecipe} onUpload={upload} onDelete={deleteReference} confirmDelete={confirmDelete} onMessage={onMessage} uploadBusy={busy === "upload-references"} />}</div><div className="instruction-preview"><span className="eyebrow">Resolved instruction preview</span><pre>{resolveInstruction(recipe)}</pre></div><button className="button primary full-width" onClick={saveRecipe} disabled={busy === "recipe"}>{busy === "recipe" ? "Saving…" : "Save recipe"}</button></> : <div className="empty-panel">Your starter recipe is being prepared. Refresh the workspace to continue.</div>}
      </section>
      <section className="experiment-panel surface"><div className="section-heading"><div><p className="eyebrow">03 / Experiment</p><h2>Whole-sheet run</h2></div><span className="quiet-status">{recipe ? `${recipe.model} · ${recipe.quality}` : "Setup needed"}</span></div><div className="experiment-intro"><div className="experiment-mark">✳</div><div><h3>Make the recipe empirical</h3><p>Run the same ordered portraits through one recipe, then judge the sheet as a set. The requested card window is 28:23; the backend records its closest supported landscape ratio.</p></div></div>{recipe && <div className="run-preflight"><div><span>Source calls</span><strong>{benchmark.length} portraits</strong></div><div><span>Reference pack</span><strong>{recipe.reference_ids.length} images</strong></div><div><span>Outputs / source</span><select value={runOutputs} onChange={(event) => setRunOutputs(Number(event.target.value))}><option value={1}>1</option><option value={2}>2</option></select></div><div><span>Total image calls</span><strong>{benchmark.length * runOutputs}</strong></div><button className="button primary large-button" onClick={launchRun} disabled={runLaunching || benchmark.length === 0}>{runLaunching ? "Starting…" : "Run benchmark"}</button></div>}{benchmark.length === 0 && <div className="setup-guidance"><strong>Add at least one source to unlock a smoke run.</strong><span>Six to ten fixed portraits will make style differences easier to see.</span></div>}<RunHistory runs={runs} onNavigate={onNavigate} /></section>
    </div>
  </div>;
}

function resolveInstruction(recipe: Recipe) { return Object.entries(recipe.direction).filter(([, value]) => value).map(([key, value]) => `${key.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase())}: ${value}`).concat(recipe.avoid ? [`Avoid: ${recipe.avoid}`] : []).join("\n"); }

function ReferenceManager({ workspace, recipe, onWorkspace, onRecipe, onUpload, onDelete, confirmDelete, onMessage, uploadBusy }: { workspace: Workspace; recipe: Recipe; onWorkspace: (workspace: Workspace) => void; onRecipe: (recipe: Recipe) => void; onUpload: (kind: "sources" | "references", event: React.ChangeEvent<HTMLInputElement>) => void; onDelete: (id: string) => void; confirmDelete: string; onMessage: (message: string, kind?: "success" | "error") => void; uploadBusy: boolean }) {
  async function toggle(id: string) { const next = recipe.reference_ids.includes(id) ? recipe.reference_ids.filter((value) => value !== id) : [...recipe.reference_ids, id]; try { const response = await api.updateRecipe(recipe.id, { ...recipe, reference_ids: next }); onWorkspace(response.workspace); onRecipe(response.workspace.recipes.find((item) => item.id === recipe.id) || recipe); } catch (error) { onMessage((error as Error).message, "error"); } }
  async function updateReference(id: string, patch: { label?: string; position?: number }) { try { const response = await api.updateReference(id, patch); onWorkspace(response.workspace); } catch (error) { onMessage((error as Error).message, "error"); } }
  return <div className="reference-manager"><label className="file-button button secondary">{uploadBusy ? "Uploading…" : "Upload reference"}<input type="file" accept="image/*" onChange={(event) => onUpload("references", event)} disabled={uploadBusy} /></label>{workspace.references.length === 0 && <p className="muted">Add consistent painterly references here. Do not generate them in this flow.</p>}{workspace.references.map((reference, index) => <div className="reference-row" key={reference.id}><img src={reference.image_url} alt="" /><button className={`reference-select ${recipe.reference_ids.includes(reference.id) ? "selected" : ""}`} onClick={() => toggle(reference.id)}>{recipe.reference_ids.includes(reference.id) ? "Included" : "Include"}</button><input className="reference-label" value={reference.label} onChange={(event) => onWorkspace({ ...workspace, references: workspace.references.map((item) => item.id === reference.id ? { ...item, label: event.target.value } : item) })} onBlur={(event) => void updateReference(reference.id, { label: event.target.value })} /><button className="icon-button" disabled={index === 0} onClick={() => void updateReference(reference.id, { position: index - 1 })}>↑</button><button className="icon-button" disabled={index === workspace.references.length - 1} onClick={() => void updateReference(reference.id, { position: index + 1 })}>↓</button><button className="text-button danger-text" onClick={() => onDelete(reference.id)}>{confirmDelete === `reference:${reference.id}` ? "Confirm delete" : "Delete"}</button></div>)}</div>;
}

function RunHistory({ runs, onNavigate }: { runs: RunSummary[]; onNavigate: (hash: string) => void }) { return <div className="run-history"><div className="history-heading"><h3>Run history</h3><span>Newest first</span></div>{runs.length === 0 ? <p className="muted">Completed sheets will appear here for refreshable comparison.</p> : runs.map((run) => <button className="history-row" key={run.run_id} onClick={() => onNavigate(`#run/${run.run_id}`)}><span className={`status-dot ${run.status}`} /><span className="history-main"><strong>{run.recipe_name}</strong><small>{formatTime(run.created_at)} · {run.source_count} sources · {run.completed_calls}/{run.total_calls} calls</small></span><span className="verdict-pill">{run.verdict}</span><span>→</span></button>)}</div>; }

function RunSheet({ run, runs, onReview, onUsePortrait, onNavigate, onRefresh, onMessage }: { run: Run; runs: RunSummary[]; onReview: (verdict: string) => void; onUsePortrait: (itemId: string) => void; onNavigate: (hash: string) => void; onRefresh: () => Promise<void>; onMessage: (message: string, kind?: "success" | "error") => void }) {
  const [selectedItem, setSelectedItem] = useState<Run["items"][number]>();
  useEffect(() => { if (["queued", "running"].includes(run.status)) { const timer = window.setInterval(() => void onRefresh(), 1500); return () => window.clearInterval(timer); } }, [run.status, onRefresh]);
  const done = run.completed_calls === run.total_calls;
  async function duplicate() { try { await api.duplicateRecipeFromRun(run.run_id); onMessage("Recipe duplicated from the immutable run snapshot", "success"); } catch (error) { onMessage((error as Error).message, "error"); } }
  async function rerun() { try { const response = await api.startRun(run.recipe_id, run.outputs_per_source); onNavigate(`#run/${response.run.run_id}`); onMessage("Run queued again from the current recipe", "success"); } catch (error) { onMessage((error as Error).message, "error"); } }
  return <section className="run-view"><div className="run-toolbar"><button className="back-link" onClick={() => onNavigate("#lab")}>← Back to Style Lab</button><div><p className="eyebrow">Run sheet</p><h2>{run.recipe_snapshot.name}</h2><p className="muted">{run.status} · {run.completed_calls}/{run.total_calls} calls · requested {run.requested_aspect_ratio}, effective {run.effective_aspect_ratio}</p></div><div className="toolbar-actions">{["failed", "interrupted"].includes(run.status) && <button className="button primary" onClick={rerun}>Run again</button>}<button className="button secondary" onClick={duplicate}>Duplicate recipe</button><button className="button secondary" onClick={() => onRefresh()}>Refresh</button></div></div><div className="run-summary surface"><span><b>{run.sources_snapshot.length}</b> portraits</span><span><b>{run.references_snapshot.length}</b> style refs</span><span><b>{run.model}</b></span><span><b>{run.effective_aspect_ratio}</b> effective ratio</span>{run.status === "failed" && <strong className="error-text">Some calls failed. Inspect the affected cells.</strong>}</div><div className="sheet-question"><p className="eyebrow">Sheet verdict</p><h3>Do these look like illustrations commissioned for the same set?</h3><div className="verdict-actions"><button className={run.verdict === "coherent" ? "selected" : ""} onClick={() => onReview("coherent")}>Coherent</button><button className={run.verdict === "mixed" ? "selected" : ""} onClick={() => onReview("mixed")}>Mixed</button><button className={run.verdict === "not-useful" ? "selected" : ""} onClick={() => onReview("not-useful")}>Not useful</button></div></div><div className="sheet-grid">{run.items.map((item) => <article className={`sheet-cell ${item.status}`} key={item.item_id} onClick={() => setSelectedItem(item)}>{item.thumbnail_url || item.output_url ? <img src={item.thumbnail_url || item.output_url} alt={item.source_label} /> : <div className="cell-placeholder"><span>{item.status === "running" ? "Painting…" : item.status}</span><i className={item.status === "running" ? "spinner" : ""} /></div>}<div className="sheet-cell-caption"><strong>{item.source_label}</strong><small>{item.status === "complete" ? `${item.dimensions?.join(" × ")} · ${item.elapsed_seconds}s` : item.error || item.status}</small></div></article>)}</div>{selectedItem && <div className="detail-drawer"><button className="close-drawer" onClick={() => setSelectedItem(undefined)}>×</button><p className="eyebrow">Result details</p><h3>{selectedItem.source_label}</h3>{selectedItem.output_url && <img className="detail-output" src={selectedItem.output_url} alt="Generated result" />}<dl><dt>Source input</dt><dd>{selectedItem.source_url ? <a href={selectedItem.source_url} target="_blank">Open exact input</a> : "Not ready"}</dd><dt>Dimensions</dt><dd>{selectedItem.dimensions?.join(" × ") || "—"}</dd><dt>Seed</dt><dd>{selectedItem.seed || "—"}</dd><dt>Model</dt><dd>{selectedItem.model || run.model}</dd><dt>Effective ratio</dt><dd>{run.effective_aspect_ratio}</dd><dt>Reference mapping</dt><dd>{run.backend_mapping.references}</dd></dl><details><summary>Resolved instruction</summary><pre>{run.resolved_instruction}</pre></details>{selectedItem.status === "complete" && <button className="button primary full-width" onClick={() => onUsePortrait(selectedItem.item_id)}>Use this portrait</button>}</div>}<ComparePanel runs={runs} current={run} onNavigate={onNavigate} /></section>;
}

function ComparePanel({ runs, current, onNavigate }: { runs: RunSummary[]; current: Run; onNavigate: (hash: string) => void }) { const candidates = runs.filter((run) => run.run_id !== current.run_id && run.status === "complete"); const [other, setOther] = useState(candidates[0]?.run_id || ""); return candidates.length ? <div className="compare-bar surface"><div><p className="eyebrow">Compare sheets</p><strong>See this benchmark source-for-source</strong></div><select value={other} onChange={(event) => setOther(event.target.value)}>{candidates.map((run) => <option key={run.run_id} value={run.run_id}>{run.recipe_name} · {formatTime(run.created_at)}</option>)}</select><button className="button secondary" onClick={() => other && onNavigate(`#compare/${current.run_id}/${other}`)}>Compare</button></div> : null; }

export function CompareView({ firstId, secondId, onNavigate }: { firstId: string; secondId: string; onNavigate: (hash: string) => void }) {
  const [comparison, setComparison] = useState<Awaited<ReturnType<typeof api.compareRuns>>["comparison"]>();
  const [error, setError] = useState("");
  useEffect(() => { void api.compareRuns(firstId, secondId).then((result) => setComparison(result.comparison)).catch((reason) => setError((reason as Error).message)); }, [firstId, secondId]);
  if (error) return <section className="compare-view"><button className="back-link" onClick={() => onNavigate(`#run/${firstId}`)}>← Back to run</button><div className="empty-panel large-empty"><h2>Comparison unavailable</h2><p>{error}</p></div></section>;
  if (!comparison) return <section className="compare-view"><p className="muted">Loading comparison…</p></section>;
  return <section className="compare-view"><div className="run-toolbar"><button className="back-link" onClick={() => onNavigate(`#run/${firstId}`)}>← Back to run</button><div><p className="eyebrow">Source-for-source comparison</p><h2>{comparison.first.recipe_snapshot.name} <span className="compare-vs">vs</span> {comparison.second.recipe_snapshot.name}</h2><p className="muted">Two immutable benchmark sheets, aligned by source order.</p></div></div>{!comparison.same_benchmark && <div className="compare-warning">These runs use different benchmark membership or order. Rows are shown by source ID where possible; treat the visual comparison as exploratory.</div>}<div className="compare-table"><div className="compare-table-head"><span>Source</span><strong>{comparison.first.recipe_snapshot.name}</strong><strong>{comparison.second.recipe_snapshot.name}</strong></div>{comparison.rows.map((row) => <div className="compare-table-row" key={row.source_id}><span>{row.source_id}</span>{row.first?.thumbnail_url ? <img src={row.first.thumbnail_url} alt={row.first.source_label} /> : <div className="compare-missing">Missing</div>}{row.second?.thumbnail_url ? <img src={row.second.thumbnail_url} alt={row.second.source_label} /> : <div className="compare-missing">Missing</div>}</div>)}</div><div className="recipe-diff surface"><p className="eyebrow">Recipe changes</p>{comparison.recipe_changes.length ? comparison.recipe_changes.map((change) => <div key={change.field}><strong>{change.field}</strong><span>{String(change.first || "—")}</span><span>{String(change.second || "—")}</span></div>) : <p className="muted">No recipe fields changed between these snapshots.</p>}</div></section>;
}
