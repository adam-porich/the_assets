import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { modelsForMode, recipeIsDirty, referenceLimitProblem, selectedModel } from "./runDraft";
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
const searchPresets = ["character portrait", "older face portrait", "dramatic side light", "distinctive clothing portrait"];

function formatTime(value: string) {
  return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

type Props = {
  workspace: Workspace;
  models: Model[];
  runs: RunSummary[];
  activeRun?: Run;
  pexelsAvailable: boolean;
  openrouterAvailable: boolean;
  onWorkspace: (workspace: Workspace) => void;
  onRefresh: () => Promise<void>;
  onNavigate: (hash: string) => void;
  onMessage: (message: string, kind?: "success" | "error") => void;
};

export function StyleLab({ workspace, models, runs, activeRun, pexelsAvailable, openrouterAvailable, onWorkspace, onRefresh, onNavigate, onMessage }: Props) {
  const savedRecipe = workspace.recipes.find((item) => item.id === workspace.active_recipe_id) || workspace.recipes[0];
  const [recipe, setRecipe] = useState<Recipe | undefined>(savedRecipe);
  const [sourcePanel, setSourcePanel] = useState(false);
  const [referencePanel, setReferencePanel] = useState(false);
  const [query, setQuery] = useState(searchPresets[0]);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [selectedSearch, setSelectedSearch] = useState<number[]>([]);
  const [searchPage, setSearchPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [busy, setBusy] = useState("");
  const [uploadLabel, setUploadLabel] = useState("");
  const [runOutputs, setRunOutputs] = useState(1);
  const [confirmDelete, setConfirmDelete] = useState("");
  const [sourceError, setSourceError] = useState("");
  const [runIntent, setRunIntent] = useState<"smoke" | "benchmark">();

  useEffect(() => setRecipe(savedRecipe), [savedRecipe?.id, savedRecipe?.updated_at]);
  const benchmark = useMemo(
    () => workspace.benchmark_source_ids.map((id) => workspace.sources.find((source) => source.id === id)).filter(Boolean) as Source[],
    [workspace],
  );
  const unselected = workspace.sources.filter((source) => !workspace.benchmark_source_ids.includes(source.id));
  const model = recipe ? selectedModel(models, recipe) : undefined;
  const dirty = recipeIsDirty(savedRecipe, recipe);
  const referenceProblem = recipe ? referenceLimitProblem(recipe, model) : "Recipe unavailable";
  const liveSmokeComplete = Boolean(recipe && runs.some((run) => run.status === "complete" && run.execution_mode === "live" && run.model === recipe.model && run.source_count === 1));

  function patchRecipe(patch: Partial<Recipe>) {
    setRecipe((current) => current ? { ...current, ...patch } : current);
  }
  function patchDirection(key: keyof Recipe["direction"], value: string) {
    setRecipe((current) => current ? { ...current, direction: { ...current.direction, [key]: value } } : current);
  }
  function changeMode(mode: Recipe["execution_mode"]) {
    if (!recipe || mode === recipe.execution_mode) return;
    const candidates = modelsForMode(models, mode);
    const replacement = candidates.find((candidate) => candidate.available && candidate.id === "openai/gpt-image-1-mini") || candidates.find((candidate) => candidate.available) || candidates[0];
    patchRecipe({ execution_mode: mode, model: replacement?.id || recipe.model, quality: "low" });
  }
  async function updateBenchmark(ids: string[]) {
    setBusy("benchmark");
    try {
      const result = await api.updateBenchmark(ids);
      onWorkspace(result.workspace);
      onMessage("Benchmark order saved", "success");
    } catch (error) {
      onMessage((error as Error).message, "error");
    } finally {
      setBusy("");
    }
  }
  async function moveSource(index: number, direction: -1 | 1) {
    const next = [...workspace.benchmark_source_ids];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    await updateBenchmark(next);
  }
  async function search(page = 1) {
    setBusy("search");
    setSourceError("");
    try {
      const response = await api.searchSources(query, 12, page);
      setSearchResults(response.results);
      setSelectedSearch([]);
      setSearchPage(response.page);
      setHasMore(response.has_more);
    } catch (error) {
      const message = (error as Error).message;
      setSourceError(message);
      onMessage(message, "error");
    } finally {
      setBusy("");
    }
  }
  async function loadStarter() {
    setBusy("starter");
    setSourceError("");
    try {
      const response = await api.loadStarterSources();
      onWorkspace(response.workspace);
      const summary = `${response.imported} imported, ${response.deduplicated} already present`;
      if (response.failed) {
        const errors = response.results.filter((item) => item.status === "failed").map((item) => `Pexels ${item.photo_id}: ${item.error}`).join(" · ");
        setSourceError(`Starter benchmark partially loaded: ${summary}. ${errors}`);
        onMessage(`Starter benchmark partially loaded (${response.failed} failed)`, "error");
      } else {
        onMessage(`Starter benchmark ready: ${summary}`, "success");
      }
    } catch (error) {
      const message = (error as Error).message;
      setSourceError(message);
      onMessage(message, "error");
    } finally {
      setBusy("");
    }
  }
  async function bulkImport() {
    const candidates = searchResults.filter((result) => selectedSearch.includes(result.pexels_photo_id));
    if (!candidates.length) return;
    setBusy("bulk-import");
    try {
      const response = await api.importSources(candidates);
      onWorkspace(response.workspace);
      setSelectedSearch([]);
      if (response.failed) {
        const errors = response.results.filter((item) => item.status === "failed").map((item) => `Pexels ${item.photo_id}: ${item.error}`).join(" · ");
        setSourceError(`${response.imported} imported; ${response.failed} failed. ${errors}`);
        onMessage("Some selected portraits could not be downloaded", "error");
      } else {
        onMessage(`${response.imported} imported; ${response.deduplicated} duplicates skipped`, "success");
      }
    } catch (error) {
      onMessage((error as Error).message, "error");
    } finally {
      setBusy("");
    }
  }
  async function upload(kind: "sources" | "references", event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(`upload-${kind}`);
    try {
      const result = await api.upload(kind, file, uploadLabel);
      onWorkspace(result.workspace);
      setUploadLabel("");
      onMessage(`${kind === "sources" ? "Source" : "Reference"} added`, "success");
    } catch (error) {
      onMessage((error as Error).message, "error");
    } finally {
      setBusy("");
      event.target.value = "";
    }
  }
  async function removeItem(kind: "source" | "reference", id: string) {
    const token = `${kind}:${id}`;
    if (confirmDelete !== token) {
      setConfirmDelete(token);
      return;
    }
    try {
      const response = kind === "source" ? await api.deleteSource(id) : await api.deleteReference(id);
      onWorkspace(response.workspace);
      setConfirmDelete("");
    } catch (error) {
      onMessage((error as Error).message, "error");
    }
  }
  async function duplicateRecipe() {
    if (!recipe) return;
    try {
      const response = await api.duplicateRecipe(recipe.id);
      const selected = await api.selectRecipe(response.recipe.id);
      onWorkspace(selected.workspace);
      onMessage("Recipe duplicated", "success");
    } catch (error) {
      onMessage((error as Error).message, "error");
    }
  }
  async function selectRecipe(id: string) {
    try {
      onWorkspace((await api.selectRecipe(id)).workspace);
    } catch (error) {
      onMessage((error as Error).message, "error");
    }
  }
  async function confirmRun() {
    if (!recipe || !runIntent) return;
    const sourceIds = runIntent === "smoke" ? workspace.benchmark_source_ids.slice(0, 1) : workspace.benchmark_source_ids;
    setBusy("run");
    try {
      const response = await api.startRun(recipe, sourceIds, runOutputs, recipe.execution_mode, recipe.execution_mode === "live");
      onWorkspace(response.workspace);
      setRunIntent(undefined);
      onNavigate(`#run/${response.run.run_id}`);
      onMessage(`${recipe.execution_mode === "live" ? "Live generation" : "Simulation"} queued`, "success");
    } catch (error) {
      onMessage((error as Error).message, "error");
    } finally {
      setBusy("");
    }
  }
  async function reviewRun(verdict: string) {
    if (!activeRun) return;
    try {
      await api.reviewRun(activeRun.run_id, verdict, activeRun.note || "");
      await onRefresh();
      onMessage("Sheet verdict saved", "success");
    } catch (error) {
      onMessage((error as Error).message, "error");
    }
  }
  async function framePortrait(itemId: string) {
    if (!activeRun) return;
    try {
      const response = await api.createCard(activeRun.run_id, itemId, "Experimental claimant", "bust", "painterly");
      onNavigate(`#card/${response.card.card_id}`);
    } catch (error) {
      onMessage((error as Error).message, "error");
    }
  }

  if (activeRun) {
    return <RunSheet run={activeRun} runs={runs} onReview={reviewRun} onFramePortrait={framePortrait} onNavigate={onNavigate} onRefresh={onRefresh} onMessage={onMessage} />;
  }

  const modeModels = recipe ? modelsForMode(models, recipe.execution_mode) : [];
  const runBlocked = !recipe || !benchmark.length || Boolean(referenceProblem) || (recipe.execution_mode === "live" && !openrouterAvailable);
  const runSources = runIntent === "smoke" ? 1 : benchmark.length;
  return <div className="lab-layout">
    <div className="readiness surface" aria-label="Style Lab readiness">
      <span className={benchmark.length ? "ready" : ""}>1 · Sources <b>{benchmark.length || "needed"}</b></span>
      <span className={recipe?.reference_ids.length ? "ready" : ""}>2 · Style pack <b>{recipe?.reference_ids.length || "needed"}</b></span>
      <span className={recipe && !dirty ? "ready" : ""}>3 · Art direction <b>{dirty ? "unsaved draft" : "ready"}</b></span>
      <span className={!runBlocked ? "ready" : ""}>4 · Generate <b>{recipe?.execution_mode || "blocked"}</b></span>
    </div>

    <section className="benchmark-strip surface">
      <div className="section-heading">
        <div><p className="eyebrow">01 / Sources</p><h2>Benchmark portraits</h2></div>
        <span className="recommendation">6 fixed starters · {benchmark.length} selected</span>
        <button className="button secondary" onClick={() => setSourcePanel((value) => !value)}>{sourcePanel ? "Close source finder" : "Find or upload"}</button>
      </div>
      <p className="section-help">Load the standard six in one operation, or build an ordered set with paged search and bulk selection.</p>
      <div className="starter-action">
        <button className="button primary" onClick={loadStarter} disabled={!pexelsAvailable || busy === "starter"}>{busy === "starter" ? "Loading six portraits…" : "Load starter benchmark"}</button>
        {!pexelsAvailable && <span>Pexels needs a configured API key; local upload remains available.</span>}
      </div>
      {sourceError && <div className="source-error" role="alert">{sourceError}</div>}
      {sourcePanel && <div className="setup-drawer source-drawer">
        <div className="drawer-column">
          <div className="search-presets" aria-label="Search presets">{searchPresets.map((preset) => <button key={preset} className={query === preset ? "selected" : ""} onClick={() => setQuery(preset)}>{preset}</button>)}</div>
          <label className="field-label">Search Pexels<input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && void search(1)} /></label>
          <button className="button primary" onClick={() => search(1)} disabled={busy === "search" || !pexelsAvailable}>{busy === "search" ? "Searching…" : "Search portraits"}</button>
          {searchResults.length > 0 && <>
            <div className="bulk-bar"><span>{selectedSearch.length} selected</span><button className="button primary" disabled={!selectedSearch.length || busy === "bulk-import"} onClick={bulkImport}>{busy === "bulk-import" ? "Importing…" : "Import selected"}</button></div>
            <div className="search-results">{searchResults.map((result) => <label className={`search-result ${selectedSearch.includes(result.pexels_photo_id) ? "selected" : ""}`} key={result.pexels_photo_id}><input type="checkbox" checked={selectedSearch.includes(result.pexels_photo_id)} onChange={(event) => setSelectedSearch((current) => event.target.checked ? [...current, result.pexels_photo_id] : current.filter((id) => id !== result.pexels_photo_id))} /><img src={result.preview_url} alt={`Portrait by ${result.photographer || "Pexels"}`} /><span><strong>Pexels {result.pexels_photo_id}</strong><small>{result.photographer || "Pexels"}</small></span></label>)}</div>
            <div className="pagination"><button className="button secondary" disabled={searchPage <= 1 || busy === "search"} onClick={() => search(searchPage - 1)}>Previous</button><span>Page {searchPage}</span><button className="button secondary" disabled={!hasMore || busy === "search"} onClick={() => search(searchPage + 1)}>Next</button></div>
          </>}
        </div>
        <div className="drawer-column upload-column"><p className="field-label">Local upload</p><p className="muted">Uploaded sources are added to the current benchmark automatically.</p><input className="text-input" value={uploadLabel} onChange={(event) => setUploadLabel(event.target.value)} placeholder="Optional source label" /><label className="file-button button secondary">{busy === "upload-sources" ? "Uploading…" : "Choose image"}<input type="file" accept="image/*" onChange={(event) => upload("sources", event)} disabled={Boolean(busy)} /></label></div>
      </div>}
      <div className="benchmark-row">{benchmark.map((source, index) => <article className="benchmark-card" key={source.id}><img src={source.image_url} alt={source.label} /><div className="benchmark-card-body"><span className="order-number">{String(index + 1).padStart(2, "0")}</span><strong>{source.label}</strong><small>{source.provenance.kind === "pexels" ? `Pexels · ${String(source.provenance.photographer || "")}` : "Local upload"}</small><div className="card-actions"><button className="icon-button" onClick={() => moveSource(index, -1)} disabled={index === 0} aria-label={`Move ${source.label} left`}>←</button><button className="icon-button" onClick={() => moveSource(index, 1)} disabled={index === benchmark.length - 1} aria-label={`Move ${source.label} right`}>→</button><button className="text-button danger-text" onClick={() => updateBenchmark(workspace.benchmark_source_ids.filter((id) => id !== source.id))}>Remove</button></div></div></article>)}{!benchmark.length && <div className="empty-strip">Load the starter benchmark, upload a source, or bulk-import search results.</div>}</div>
      {unselected.length > 0 && <div className="available-sources"><span>Imported, not selected:</span>{unselected.map((source) => <button className="source-chip" key={source.id} onClick={() => updateBenchmark([...workspace.benchmark_source_ids, source.id])}><img src={source.image_url} alt="" />{source.label}<b>+</b></button>)}</div>}
      {workspace.sources.length > 0 && <details className="secondary-list"><summary>All imported sources ({workspace.sources.length})</summary><div>{workspace.sources.map((source) => <span key={source.id}>{source.label} <button className="text-button danger-text" onClick={() => removeItem("source", source.id)}>{confirmDelete === `source:${source.id}` ? "Confirm delete" : "Delete"}</button></span>)}</div></details>}
    </section>

    <section className="style-pack-panel surface">
      <div className="section-heading"><div><p className="eyebrow">02 / Style pack</p><h2>Ordered estate references</h2></div><span className="recommendation">{recipe?.reference_ids.length || 0} selected · identity image also counts</span><button className="button secondary" onClick={() => setReferencePanel((value) => !value)}>{referencePanel ? "Close controls" : "Manage references"}</button></div>
      <p className="section-help">New workspaces include the two restored estate-card-v1 references. Their order and provenance are recorded in every run.</p>
      <div className="reference-gallery">{workspace.references.map((reference) => <article className={recipe?.reference_ids.includes(reference.id) ? "selected" : ""} key={reference.id}><img src={reference.image_url} alt={reference.label} /><strong>{reference.label}</strong><small>{String(reference.provenance?.kind || "upload")}</small></article>)}</div>
      {recipe && referencePanel && <ReferenceManager workspace={workspace} recipe={recipe} onWorkspace={onWorkspace} onRecipe={setRecipe} onUpload={upload} onDelete={(id) => removeItem("reference", id)} confirmDelete={confirmDelete} onMessage={onMessage} uploadBusy={busy === "upload-references"} />}
    </section>

    <section className="recipe-panel surface">
      <div className="section-heading"><div><p className="eyebrow">03 / Art direction</p><h2>Generation recipe</h2></div><span className={`draft-state ${dirty ? "dirty" : "saved"}`}>{dirty ? "Unsaved visible edits" : "Saved"}</span><button className="button secondary" onClick={duplicateRecipe} disabled={!recipe}>Duplicate</button></div>
      {workspace.recipes.length > 1 && <label className="field-label compact-field">Recipe version<select value={recipe?.id || ""} onChange={(event) => selectRecipe(event.target.value)}>{workspace.recipes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      {recipe ? <>
        <div className="mode-switch" role="group" aria-label="Execution mode"><button className={recipe.execution_mode === "live" ? "selected" : ""} onClick={() => changeMode("live")}>Live generation<small>OpenRouter · paid</small></button><button className={recipe.execution_mode === "simulation" ? "selected" : ""} onClick={() => changeMode("simulation")}>Simulation<small>Local · zero cost · not artwork</small></button></div>
        <div className="recipe-basics"><label className="field-label">Name<input value={recipe.name} onChange={(event) => patchRecipe({ name: event.target.value })} /></label><label className="field-label">Model<select value={recipe.model} onChange={(event) => patchRecipe({ model: event.target.value })}>{modeModels.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}{candidate.available ? "" : " · unavailable"}</option>)}</select></label><label className="field-label">Quality<select value={recipe.quality} onChange={(event) => patchRecipe({ quality: event.target.value as Recipe["quality"] })}>{(model?.qualities.length ? model.qualities.filter((quality): quality is Recipe["quality"] => ["low", "medium", "high"].includes(quality)) : ["low", "medium", "high"]).map((quality) => <option key={quality} value={quality}>{quality}</option>)}</select></label></div>
        {model && !model.available && <div className="source-error" role="alert">Saved model <code>{recipe.model}</code> is unavailable. It remains visible so a different model cannot be submitted silently.</div>}
        {recipe.execution_mode === "live" && !openrouterAvailable && <div className="source-error" role="alert">OPENROUTER_API_KEY is not configured. Live controls remain visible, but only explicit simulation can run.</div>}
        <details className="advanced-direction"><summary>Advanced art direction</summary><div className="advanced-fields">{directionLabels.map(([key, label, help]) => <label className="field-label" key={key}>{label}<span className="field-help">{help}</span><textarea rows={2} value={recipe.direction[key]} onChange={(event) => patchDirection(key, event.target.value)} /></label>)}<label className="field-label">Avoid<span className="field-help">Mapped into the instruction when the provider has no negative-prompt field.</span><textarea rows={2} value={recipe.avoid} onChange={(event) => patchRecipe({ avoid: event.target.value })} /></label><div className="instruction-preview"><span className="eyebrow">Resolved instruction preview</span><pre>{resolveInstruction(recipe)}</pre></div></div></details>
      </> : <div className="empty-panel">Starter recipe unavailable.</div>}
    </section>

    <section className="experiment-panel surface">
      <div className="section-heading"><div><p className="eyebrow">04 / Generate</p><h2>Save and run this exact draft</h2></div><span className={`mode-badge ${recipe?.execution_mode}`}>{recipe?.execution_mode === "live" ? "Paid live generation" : "Zero-cost simulation"}</span></div>
      <p className="section-help">The run request normalizes and saves every visible edit, then snapshots that exact recipe, ordered sources, and style pack.</p>
      {referenceProblem && recipe && <div className="source-error" role="alert">{referenceProblem}</div>}
      {recipe && <div className="run-preflight"><div><span>Selected model</span><strong>{recipe.model}</strong></div><div><span>Style images</span><strong>{recipe.reference_ids.length} + identity</strong></div><div><span>Outputs / source</span><select value={runOutputs} onChange={(event) => setRunOutputs(Number(event.target.value))}><option value={1}>1</option><option value={2}>2</option></select></div><div><span>Streaming</span><strong>{model?.supports_streaming ? "Supported" : "Buffered"}</strong></div><button className="button secondary large-button" onClick={() => setRunIntent("smoke")} disabled={runBlocked}>{recipe.execution_mode === "live" ? "Save and run 1-source smoke test" : "Save and run 1-source simulation"}</button><button className="button primary large-button" onClick={() => setRunIntent("benchmark")} disabled={runBlocked || (recipe.execution_mode === "live" && !liveSmokeComplete)}>{recipe.execution_mode === "live" ? "Save and run paid benchmark" : "Save and run full simulation"}</button></div>}
      {recipe?.execution_mode === "live" && !liveSmokeComplete && <div className="setup-guidance"><strong>The full paid benchmark is locked.</strong><span>Complete one live source successfully with {recipe.model} first.</span></div>}
      {!benchmark.length && <div className="setup-guidance"><strong>Add at least one benchmark source.</strong><span>The smoke test uses the first selected portrait.</span></div>}
      <RunHistory runs={runs} onNavigate={onNavigate} />
    </section>

    {runIntent && recipe && <div className="modal-backdrop" role="presentation"><div className="run-confirm surface" role="dialog" aria-modal="true" aria-labelledby="run-confirm-title"><p className="eyebrow">Confirm {recipe.execution_mode} execution</p><h2 id="run-confirm-title">{runIntent === "smoke" ? "One-source smoke test" : "Full benchmark"}</h2><dl><dt>Mode</dt><dd>{recipe.execution_mode === "live" ? "Live OpenRouter generation (cost-bearing)" : "Local deterministic simulation (not generated artwork)"}</dd><dt>Model</dt><dd>{recipe.model}</dd><dt>Sources</dt><dd>{runSources}</dd><dt>Style references</dt><dd>{recipe.reference_ids.length}</dd><dt>Image calls</dt><dd>{runSources * runOutputs}</dd><dt>Pricing metadata</dt><dd>{model?.pricing.length ? model.pricing.map((line) => `$${line.cost_usd}/${line.unit} ${line.billable}`).join(", ") : "No estimate available; exact usage is recorded after each call."}</dd></dl><p>{dirty ? "Your unsaved visible edits will be saved atomically and used by this run." : "The saved draft shown above will be snapshotted into this run."}</p><div className="modal-actions"><button className="button secondary" onClick={() => setRunIntent(undefined)} disabled={busy === "run"}>Cancel</button><button className="button primary" onClick={confirmRun} disabled={busy === "run"}>{busy === "run" ? "Starting…" : recipe.execution_mode === "live" ? "Confirm paid generation" : "Confirm simulation"}</button></div></div></div>}
  </div>;
}

function resolveInstruction(recipe: Recipe) {
  return Object.entries(recipe.direction).filter(([, value]) => value).map(([key, value]) => `${key.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase())}: ${value}`).concat(recipe.avoid ? [`Avoid: ${recipe.avoid}`] : []).join("\n");
}

function ReferenceManager({ workspace, recipe, onWorkspace, onRecipe, onUpload, onDelete, confirmDelete, onMessage, uploadBusy }: { workspace: Workspace; recipe: Recipe; onWorkspace: (workspace: Workspace) => void; onRecipe: (recipe: Recipe) => void; onUpload: (kind: "sources" | "references", event: React.ChangeEvent<HTMLInputElement>) => void; onDelete: (id: string) => void; confirmDelete: string; onMessage: (message: string, kind?: "success" | "error") => void; uploadBusy: boolean }) {
  function toggle(id: string) {
    onRecipe({ ...recipe, reference_ids: recipe.reference_ids.includes(id) ? recipe.reference_ids.filter((value) => value !== id) : [...recipe.reference_ids, id] });
  }
  async function updateReference(id: string, patch: { label?: string; position?: number }) {
    try { onWorkspace((await api.updateReference(id, patch)).workspace); } catch (error) { onMessage((error as Error).message, "error"); }
  }
  async function replace(id: string, event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try { onWorkspace((await api.replaceReference(id, file)).workspace); onMessage("Reference image replaced; provenance updated", "success"); } catch (error) { onMessage((error as Error).message, "error"); }
    event.target.value = "";
  }
  return <div className="reference-manager"><label className="file-button button secondary">{uploadBusy ? "Uploading…" : "Upload another reference"}<input type="file" accept="image/*" onChange={(event) => onUpload("references", event)} disabled={uploadBusy} /></label>{workspace.references.map((reference, index) => <div className="reference-row" key={reference.id}><img src={reference.image_url} alt="" /><button className={`reference-select ${recipe.reference_ids.includes(reference.id) ? "selected" : ""}`} onClick={() => toggle(reference.id)}>{recipe.reference_ids.includes(reference.id) ? "Included" : "Include"}</button><input className="reference-label" value={reference.label} onChange={(event) => onWorkspace({ ...workspace, references: workspace.references.map((item) => item.id === reference.id ? { ...item, label: event.target.value } : item) })} onBlur={(event) => updateReference(reference.id, { label: event.target.value })} /><button className="icon-button" disabled={index === 0} onClick={() => updateReference(reference.id, { position: index - 1 })} aria-label={`Move ${reference.label} up`}>↑</button><button className="icon-button" disabled={index === workspace.references.length - 1} onClick={() => updateReference(reference.id, { position: index + 1 })} aria-label={`Move ${reference.label} down`}>↓</button><label className="text-button replace-button">Replace<input type="file" accept="image/*" onChange={(event) => replace(reference.id, event)} /></label><button className="text-button danger-text" onClick={() => onDelete(reference.id)}>{confirmDelete === `reference:${reference.id}` ? "Confirm delete" : "Delete"}</button></div>)}</div>;
}

function RunHistory({ runs, onNavigate }: { runs: RunSummary[]; onNavigate: (hash: string) => void }) {
  return <div className="run-history"><div className="history-heading"><h3>Run history</h3><span>Newest first</span></div>{runs.length === 0 ? <p className="muted">Runs will appear here with explicit live/simulation provenance.</p> : runs.map((run) => <button className="history-row" key={run.run_id} onClick={() => onNavigate(`#run/${run.run_id}`)}><span className={`status-dot ${run.status}`} /><span className="history-main"><strong>{run.recipe_name}</strong><small>{formatTime(run.created_at)} · {run.execution_mode} · {run.source_count} sources · {run.completed_calls}/{run.total_calls} calls · ${run.cost_usd.toFixed(4)}</small></span><span className="verdict-pill">{run.verdict}</span><span>→</span></button>)}</div>;
}

function RunSheet({ run, runs, onReview, onFramePortrait, onNavigate, onRefresh, onMessage }: { run: Run; runs: RunSummary[]; onReview: (verdict: string) => void; onFramePortrait: (itemId: string) => void; onNavigate: (hash: string) => void; onRefresh: () => Promise<void>; onMessage: (message: string, kind?: "success" | "error") => void }) {
  const [selectedItem, setSelectedItem] = useState<Run["items"][number]>();
  useEffect(() => { if (["queued", "running"].includes(run.status)) { const timer = window.setInterval(() => onRefresh(), 1500); return () => window.clearInterval(timer); } }, [run.status, onRefresh]);
  async function duplicate() { try { await api.duplicateRecipeFromRun(run.run_id); onMessage("Recipe duplicated from the immutable run snapshot", "success"); } catch (error) { onMessage((error as Error).message, "error"); } }
  return <section className="run-view"><div className="run-toolbar"><button className="back-link" onClick={() => onNavigate("#lab")}>← Back to Style Lab</button><div><p className="eyebrow">Run sheet · {run.execution_mode}</p><h2>{run.recipe_snapshot.name}</h2><p className="muted">{run.status} · {run.completed_calls}/{run.total_calls} calls · requested {run.requested_aspect_ratio}, effective {run.effective_aspect_ratio}</p></div><div className="toolbar-actions"><button className="button secondary" onClick={duplicate}>Duplicate recipe</button><button className="button secondary" onClick={() => onRefresh()}>Refresh</button></div></div><div className={`run-summary surface ${run.execution_mode}`}><span><b>{run.sources_snapshot.length}</b> portraits</span><span><b>{run.references_snapshot.length}</b> style refs</span><span><b>{run.model}</b></span><span><b>{run.execution_mode}</b> execution</span><span><b>${run.cost_usd.toFixed(6)}</b> recorded cost</span>{run.execution_mode === "simulation" && <strong>Simulation output is a filtered workflow fixture, not generated artwork.</strong>}{run.status === "failed" && <strong className="error-text">Some calls failed. Inspect the affected cells.</strong>}</div><div className="sheet-question"><p className="eyebrow">Sheet verdict</p><h3>Do these look like illustrations commissioned for the same set?</h3><div className="verdict-actions"><button className={run.verdict === "coherent" ? "selected" : ""} onClick={() => onReview("coherent")}>Coherent</button><button className={run.verdict === "mixed" ? "selected" : ""} onClick={() => onReview("mixed")}>Mixed</button><button className={run.verdict === "not-useful" ? "selected" : ""} onClick={() => onReview("not-useful")}>Not useful</button></div></div><div className="sheet-grid">{run.items.map((item) => <article className={`sheet-cell ${item.status} ${selectedItem?.item_id === item.item_id ? "selected" : ""}`} key={item.item_id} onClick={() => setSelectedItem(item)}>{item.thumbnail_url || item.output_url ? <img src={item.thumbnail_url || item.output_url} alt={item.source_label} /> : <div className="cell-placeholder"><span>{item.status === "running" ? (run.execution_mode === "live" ? "Generating…" : "Simulating…") : item.status}</span><i className={item.status === "running" ? "spinner" : ""} /></div>}<div className="sheet-cell-caption"><strong>{item.source_label}</strong><small>{item.status === "complete" ? `${item.dimensions?.join(" × ")} · ${item.elapsed_seconds}s · $${Number(item.cost_usd || 0).toFixed(5)}` : item.error || item.status}</small>{item.status === "complete" && <button className="button primary frame-action" onClick={(event) => { event.stopPropagation(); onFramePortrait(item.item_id); }}>Frame this portrait</button>}</div></article>)}</div>{selectedItem && <div className="detail-drawer"><button className="close-drawer" onClick={() => setSelectedItem(undefined)} aria-label="Close details">×</button><p className="eyebrow">Result details</p><h3>{selectedItem.source_label}</h3>{selectedItem.output_url && <img className="detail-output" src={selectedItem.output_url} alt={`${run.execution_mode} result`} />}<dl><dt>Execution</dt><dd>{run.execution_mode}</dd><dt>Source input</dt><dd>{selectedItem.source_url ? <a href={selectedItem.source_url} target="_blank" rel="noreferrer">Open exact input</a> : "Not ready"}</dd><dt>Dimensions</dt><dd>{selectedItem.dimensions?.join(" × ") || "—"}</dd><dt>Seed</dt><dd>{selectedItem.seed || "—"}</dd><dt>Model</dt><dd>{selectedItem.model || run.model}</dd><dt>Usage</dt><dd><code>{JSON.stringify(selectedItem.usage || {})}</code></dd><dt>Reference mapping</dt><dd>{String(run.backend_mapping.references || "—")}</dd></dl><details><summary>Resolved instruction</summary><pre>{run.resolved_instruction}</pre></details>{selectedItem.status === "complete" && <div className="sticky-frame-action"><button className="button primary full-width" onClick={() => onFramePortrait(selectedItem.item_id)}>Frame this portrait</button></div>}</div>}<ComparePanel runs={runs} current={run} onNavigate={onNavigate} /></section>;
}

function ComparePanel({ runs, current, onNavigate }: { runs: RunSummary[]; current: Run; onNavigate: (hash: string) => void }) {
  const candidates = runs.filter((run) => run.run_id !== current.run_id && run.status === "complete");
  const [other, setOther] = useState(candidates[0]?.run_id || "");
  return candidates.length ? <div className="compare-bar surface"><div><p className="eyebrow">Compare sheets</p><strong>See this benchmark source-for-source</strong></div><select value={other} onChange={(event) => setOther(event.target.value)}>{candidates.map((run) => <option key={run.run_id} value={run.run_id}>{run.recipe_name} · {run.execution_mode} · {formatTime(run.created_at)}</option>)}</select><button className="button secondary" onClick={() => other && onNavigate(`#compare/${current.run_id}/${other}`)}>Compare</button></div> : null;
}

export function CompareView({ firstId, secondId, onNavigate }: { firstId: string; secondId: string; onNavigate: (hash: string) => void }) {
  const [comparison, setComparison] = useState<Awaited<ReturnType<typeof api.compareRuns>>["comparison"]>();
  const [error, setError] = useState("");
  useEffect(() => { void api.compareRuns(firstId, secondId).then((result) => setComparison(result.comparison)).catch((reason) => setError((reason as Error).message)); }, [firstId, secondId]);
  if (error) return <section className="compare-view"><button className="back-link" onClick={() => onNavigate(`#run/${firstId}`)}>← Back to run</button><div className="empty-panel large-empty"><h2>Comparison unavailable</h2><p>{error}</p></div></section>;
  if (!comparison) return <section className="compare-view"><p className="muted">Loading comparison…</p></section>;
  return <section className="compare-view"><div className="run-toolbar"><button className="back-link" onClick={() => onNavigate(`#run/${firstId}`)}>← Back to run</button><div><p className="eyebrow">Source-for-source comparison</p><h2>{comparison.first.recipe_snapshot.name} <span className="compare-vs">vs</span> {comparison.second.recipe_snapshot.name}</h2><p className="muted">Two immutable benchmark sheets, aligned by source order.</p></div></div>{!comparison.same_benchmark && <div className="compare-warning">These runs use different benchmark membership or order. Rows are shown by source ID where possible.</div>}<div className="compare-table"><div className="compare-table-head"><span>Source</span><strong>{comparison.first.recipe_snapshot.name}</strong><strong>{comparison.second.recipe_snapshot.name}</strong></div>{comparison.rows.map((row) => <div className="compare-table-row" key={row.source_id}><span>{row.source_id}</span>{row.first?.thumbnail_url ? <img src={row.first.thumbnail_url} alt={row.first.source_label} /> : <div className="compare-missing">Missing</div>}{row.second?.thumbnail_url ? <img src={row.second.thumbnail_url} alt={row.second.source_label} /> : <div className="compare-missing">Missing</div>}</div>)}</div><div className="recipe-diff surface"><p className="eyebrow">Recipe changes</p>{comparison.recipe_changes.length ? comparison.recipe_changes.map((change) => <div key={change.field}><strong>{change.field}</strong><span>{String(change.first || "—")}</span><span>{String(change.second || "—")}</span></div>) : <p className="muted">No recipe fields changed between these snapshots.</p>}</div></section>;
}
