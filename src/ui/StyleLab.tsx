import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { modelsForMode, recipeIsDirty, referenceLimitProblem, selectedModel } from "./runDraft";
import type { CandidateSelection, Model, Recipe, Run, RunSummary, SearchResult, Source, Workspace } from "./types";

const searchPresets = ["character portrait", "older face portrait", "dramatic side light", "distinctive clothing portrait"];
const directionLabels: Array<[keyof Recipe["direction"], string]> = [
  ["medium_brushwork", "Medium & brushwork"],
  ["lighting", "Lighting"],
  ["background", "Background"],
  ["composition", "Composition"],
  ["colour", "Colour"],
  ["detail", "Detail"],
  ["identity", "Identity retention"],
];

function formatTime(value: string) {
  return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

type SharedProps = {
  workspace: Workspace;
  onWorkspace: (workspace: Workspace) => void;
  onNavigate: (hash: string) => void;
  onMessage: (message: string, kind?: "success" | "error") => void;
};

export function SourcesStage({ workspace, pexelsAvailable, onWorkspace, onNavigate, onMessage }: SharedProps & { pexelsAvailable: boolean }) {
  const [query, setQuery] = useState(searchPresets[0]);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [selectedSearch, setSelectedSearch] = useState<number[]>([]);
  const [searchPage, setSearchPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [uploadLabel, setUploadLabel] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState("");
  const selected = useMemo(() => workspace.benchmark_source_ids.map((id) => workspace.sources.find((source) => source.id === id)).filter(Boolean) as Source[], [workspace]);

  async function updateSelection(ids: string[]) {
    setBusy("selection");
    try {
      const result = await api.updateBenchmark(ids);
      onWorkspace(result.workspace);
      onMessage("Source selection saved");
    } catch (nextError) { onMessage((nextError as Error).message, "error"); }
    finally { setBusy(""); }
  }

  async function moveSource(index: number, direction: -1 | 1) {
    const ids = [...workspace.benchmark_source_ids];
    const target = index + direction;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    await updateSelection(ids);
  }

  async function search(page = 1) {
    setBusy("search"); setError("");
    try {
      const response = await api.searchSources(query, 12, page);
      setSearchResults(response.results); setSearchPage(response.page); setHasMore(response.has_more); setSelectedSearch([]);
    } catch (nextError) { setError((nextError as Error).message); }
    finally { setBusy(""); }
  }

  async function loadStarter() {
    setBusy("starter"); setError("");
    try {
      const response = await api.loadStarterSources();
      onWorkspace(response.workspace);
      const summary = `${response.imported} imported, ${response.deduplicated} already present`;
      if (response.failed) {
        const details = response.results.filter((item) => item.status === "failed").map((item) => item.error).join(" · ");
        setError(`${summary}; ${response.failed} failed. ${details}`);
      } else onMessage(`Starter source images ready: ${summary}`);
    } catch (nextError) { setError((nextError as Error).message); }
    finally { setBusy(""); }
  }

  async function importSelected() {
    const candidates = searchResults.filter((item) => selectedSearch.includes(item.pexels_photo_id));
    if (!candidates.length) return;
    setBusy("import"); setError("");
    try {
      const response = await api.importSources(candidates);
      onWorkspace(response.workspace); setSelectedSearch([]);
      if (response.failed) setError(`${response.imported} imported and ${response.failed} failed. ${response.results.filter((item) => item.error).map((item) => item.error).join(" · ")}`);
      else onMessage(`${response.imported} source images imported`);
    } catch (nextError) { setError((nextError as Error).message); }
    finally { setBusy(""); }
  }

  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy("upload");
    try {
      const response = await api.upload("sources", file, uploadLabel);
      onWorkspace(response.workspace); setUploadLabel(""); onMessage("Source image added");
    } catch (nextError) { onMessage((nextError as Error).message, "error"); }
    finally { setBusy(""); event.target.value = ""; }
  }

  async function deleteSource(source: Source) {
    if (confirmDelete !== source.id) { setConfirmDelete(source.id); return; }
    try {
      let current = workspace;
      if (current.benchmark_source_ids.includes(source.id)) current = (await api.updateBenchmark(current.benchmark_source_ids.filter((id) => id !== source.id))).workspace;
      const response = await api.deleteSource(source.id);
      onWorkspace(response.workspace); setConfirmDelete(""); onMessage("Source image deleted");
    } catch (nextError) { onMessage((nextError as Error).message, "error"); }
  }

  return <section className="stage-page sources-page">
    <div className="page-heading"><div><p className="eyebrow">Stage 1 of 6</p><h2>Choose source images</h2><p>Build the ordered set of people you want to explore. Search, upload, provenance, and selection all live here.</p></div><button className="button primary next-action" onClick={() => onNavigate("#explore")}>Continue to Explore →</button></div>

    <div className="source-tools">
      <section className="surface tool-panel"><div className="panel-heading"><div><p className="eyebrow">Pexels library</p><h3>Find source images</h3></div>{!pexelsAvailable && <span className="status-chip warning">API key needed</span>}</div>
        <div className="search-presets">{searchPresets.map((preset) => <button key={preset} className={query === preset ? "selected" : ""} onClick={() => setQuery(preset)}>{preset}</button>)}</div>
        <div className="inline-form"><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && void search(1)} aria-label="Search Pexels" /><button className="button primary" disabled={!pexelsAvailable || busy === "search"} onClick={() => void search(1)}>{busy === "search" ? "Searching…" : "Search"}</button></div>
        <button className="button secondary" disabled={!pexelsAvailable || busy === "starter"} onClick={() => void loadStarter()}>{busy === "starter" ? "Loading starters…" : "Load six starter images"}</button>
      </section>
      <section className="surface tool-panel"><p className="eyebrow">Local library</p><h3>Upload an image</h3><p className="muted">Uploads retain their filename, checksum, dimensions, and local provenance.</p><label className="field-label">Optional label<input value={uploadLabel} onChange={(event) => setUploadLabel(event.target.value)} /></label><label className="button secondary file-button">{busy === "upload" ? "Uploading…" : "Choose image"}<input type="file" accept="image/*" disabled={Boolean(busy)} onChange={upload} /></label></section>
    </div>
    {error && <div className="inline-error" role="alert">{error}</div>}

    {searchResults.length > 0 && <section className="surface search-panel"><div className="panel-heading"><div><p className="eyebrow">Search results · page {searchPage}</p><h3>Select images to import</h3></div><button className="button primary" disabled={!selectedSearch.length || busy === "import"} onClick={() => void importSelected()}>{busy === "import" ? "Importing…" : `Import ${selectedSearch.length || "selected"}`}</button></div><div className="image-library search-library">{searchResults.map((result) => <label key={result.pexels_photo_id} className={`library-card ${selectedSearch.includes(result.pexels_photo_id) ? "selected" : ""}`}><input type="checkbox" checked={selectedSearch.includes(result.pexels_photo_id)} onChange={(event) => setSelectedSearch((current) => event.target.checked ? [...current, result.pexels_photo_id] : current.filter((id) => id !== result.pexels_photo_id))} /><img src={result.preview_url} alt={`Portrait by ${result.photographer || "Pexels"}`} /><span><strong>{result.photographer || "Pexels photographer"}</strong><small>Pexels {result.pexels_photo_id}</small></span></label>)}</div><div className="pagination"><button className="button secondary" disabled={searchPage <= 1} onClick={() => void search(searchPage - 1)}>Previous</button><button className="button secondary" disabled={!hasMore} onClick={() => void search(searchPage + 1)}>Next</button></div></section>}

    <section className="surface library-panel"><div className="panel-heading"><div><p className="eyebrow">Project library</p><h3>{selected.length} selected source image{selected.length === 1 ? "" : "s"}</h3></div><span className="muted">Click a card to include or remove it. Arrows set generation order.</span></div>
      {workspace.sources.length ? <div className="image-library">{workspace.sources.map((source) => { const index = workspace.benchmark_source_ids.indexOf(source.id); const isSelected = index >= 0; return <article key={source.id} className={`library-card source-card ${isSelected ? "selected" : ""}`}><button className="image-select" onClick={() => void updateSelection(isSelected ? workspace.benchmark_source_ids.filter((id) => id !== source.id) : [...workspace.benchmark_source_ids, source.id])} aria-pressed={isSelected}><img src={source.image_url} alt={source.label} /><span className="selection-mark">{isSelected ? `✓ ${index + 1}` : "+"}</span></button><div className="library-meta"><strong>{source.label}</strong><small>{source.provenance.kind === "pexels" ? "Pexels source" : "Local upload"}</small>{isSelected && <div className="order-actions"><button onClick={() => void moveSource(index, -1)} disabled={index === 0} aria-label={`Move ${source.label} earlier`}>←</button><button onClick={() => void moveSource(index, 1)} disabled={index === selected.length - 1} aria-label={`Move ${source.label} later`}>→</button></div>}<details><summary>Provenance</summary><code>{JSON.stringify(source.provenance)}</code></details><button className="text-button danger" onClick={() => void deleteSource(source)}>{confirmDelete === source.id ? "Confirm delete" : "Delete"}</button></div></article>; })}</div> : <div className="empty-panel"><span className="empty-glyph">◇</span><h3>No source images yet</h3><p>Load the starter set, search Pexels, or upload an image. You can still visit later stages to see what they need.</p></div>}
    </section>
    <div className="stage-actions"><span /><button className="button primary large" onClick={() => onNavigate("#explore")}>Continue to Explore →</button></div>
  </section>;
}

type StylesProps = SharedProps & {
  models: Model[];
  runs: RunSummary[];
  initialRun?: Run;
  openrouterAvailable: boolean;
  onRun: (run: Run) => void;
  onRefresh: () => Promise<void>;
  candidateSelection?: CandidateSelection | null;
  onSelection?: (selection: CandidateSelection | null) => void;
  baselineRunId?: string | null;
};

export function StylesStage({ workspace, models, runs, initialRun, openrouterAvailable, onWorkspace, onRun, onRefresh, onNavigate, onMessage, candidateSelection, onSelection, baselineRunId }: StylesProps) {
  const savedRecipe = workspace.recipes.find((item) => item.id === workspace.active_recipe_id) || workspace.recipes[0];
  const [recipe, setRecipe] = useState<Recipe | undefined>(savedRecipe);
  const [sourceIds, setSourceIds] = useState<string[]>(workspace.benchmark_source_ids.slice(0, 1));
  const [variants, setVariants] = useState(4);
  const [currentRun, setCurrentRun] = useState<Run | undefined>(initialRun);
  const [busy, setBusy] = useState("");
  const [referenceLabel, setReferenceLabel] = useState("");
  const [compareId, setCompareId] = useState("");

  useEffect(() => setRecipe(savedRecipe), [savedRecipe?.id, savedRecipe?.updated_at]);
  useEffect(() => { if (initialRun) setCurrentRun(initialRun); }, [initialRun]);
  useEffect(() => { if (!initialRun && baselineRunId) void openRun(baselineRunId); }, [baselineRunId]);
  useEffect(() => {
    const allowed = new Set(workspace.benchmark_source_ids);
    setSourceIds((current) => {
      const kept = current.filter((id) => allowed.has(id));
      return kept.length ? kept : workspace.benchmark_source_ids.slice(0, 1);
    });
  }, [workspace.benchmark_source_ids.join("|")]);
  useEffect(() => {
    if (!currentRun || !["queued", "running"].includes(currentRun.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = (await api.getRun(currentRun.run_id)).run;
        setCurrentRun(next); onRun(next);
        if (!["queued", "running"].includes(next.status)) await onRefresh();
      } catch (error) { onMessage((error as Error).message, "error"); }
    }, 800);
    return () => window.clearInterval(timer);
  }, [currentRun?.run_id, currentRun?.status]);

  const selectedSources = workspace.benchmark_source_ids.map((id) => workspace.sources.find((source) => source.id === id)).filter(Boolean) as Source[];
  const model = recipe ? selectedModel(models, recipe) : undefined;
  const referenceProblem = recipe ? referenceLimitProblem(recipe, model) : "No style recipe is available.";
  const dirty = recipeIsDirty(savedRecipe, recipe);
  const activeRun = runs.some((item) => ["queued", "running"].includes(item.status)) || Boolean(currentRun && ["queued", "running"].includes(currentRun.status));
  const runProblem = !recipe ? "No style recipe is available." : !sourceIds.length ? "Choose at least one source image." : referenceProblem || (recipe.execution_mode === "live" && !openrouterAvailable ? "OPENROUTER_API_KEY is not configured." : "");
  const allSourcesProblem = !workspace.benchmark_source_ids.length ? "Choose at least one source image." : referenceProblem || (recipe?.execution_mode === "live" && !openrouterAvailable ? "OPENROUTER_API_KEY is not configured." : "");
  const resolvedPrompt = recipe ? [recipe.change_note && `Requested change: ${recipe.change_note}`, ...directionLabels.map(([key, label]) => recipe.direction[key] && `${label}: ${recipe.direction[key]}`), recipe.avoid && `Avoid: ${recipe.avoid}`].filter(Boolean).join("\n") : "";

  function patchRecipe(patch: Partial<Recipe>) { setRecipe((current) => current ? { ...current, ...patch } : current); }
  function patchDirection(key: keyof Recipe["direction"], value: string) { setRecipe((current) => current ? { ...current, direction: { ...current.direction, [key]: value } } : current); }
  function changeMode(mode: Recipe["execution_mode"]) {
    if (!recipe || recipe.execution_mode === mode) return;
    const candidates = modelsForMode(models, mode);
    const replacement = candidates.find((item) => item.available && item.id === "openai/gpt-image-1-mini") || candidates.find((item) => item.available) || candidates[0];
    patchRecipe({ execution_mode: mode, model: replacement?.id || recipe.model, quality: "low" });
  }

  async function saveRecipe() {
    if (!recipe) return;
    setBusy("save");
    try { const response = await api.updateRecipe(recipe.id, recipe); onWorkspace(response.workspace); onMessage("Style changes saved"); }
    catch (error) { onMessage((error as Error).message, "error"); }
    finally { setBusy(""); }
  }

  async function generate(allSources = false) {
    if (!recipe) return;
    if (activeRun) { onMessage("One generation batch is already active.", "error"); return; }
    const ids = allSources ? workspace.benchmark_source_ids : sourceIds;
    const problem = !ids.length ? "Choose at least one source image." : referenceProblem || (recipe.execution_mode === "live" && !openrouterAvailable ? "OPENROUTER_API_KEY is not configured." : "");
    if (problem) { onMessage(problem, "error"); return; }
    setBusy(allSources ? "test-all" : "generate");
    try {
      const response = await api.startRun(recipe, ids, allSources ? 1 : variants, recipe.execution_mode);
      onWorkspace(response.workspace); setRecipe(response.run.recipe_snapshot); setCurrentRun(response.run); onRun(response.run);
      onMessage(allSources ? "Consistency test queued" : `${variants}-variant exploration queued`);
    } catch (error) { onMessage((error as Error).message, "error"); }
    finally { setBusy(""); }
  }

  async function uploadReference(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !recipe) return;
    setBusy("reference");
    try {
      const response = await api.upload("references", file, referenceLabel);
      const newest = response.workspace.references.find((item) => !workspace.references.some((old) => old.id === item.id));
      onWorkspace(response.workspace);
      if (newest) setRecipe((current) => current ? { ...current, reference_ids: [...current.reference_ids, newest.id] } : current);
      setReferenceLabel(""); onMessage("Style reference added");
    } catch (error) { onMessage((error as Error).message, "error"); }
    finally { setBusy(""); event.target.value = ""; }
  }

  function moveReference(index: number, direction: -1 | 1) {
    if (!recipe) return;
    const ids = [...recipe.reference_ids]; const target = index + direction;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]]; patchRecipe({ reference_ids: ids });
  }

  async function duplicateRecipe() {
    if (!recipe) return;
    try { const created = await api.duplicateRecipe(recipe.id); const selected = await api.selectRecipe(created.recipe.id); onWorkspace(selected.workspace); onMessage("Style recipe duplicated"); }
    catch (error) { onMessage((error as Error).message, "error"); }
  }

  async function selectRecipe(id: string) {
    try { onWorkspace((await api.selectRecipe(id)).workspace); }
    catch (error) { onMessage((error as Error).message, "error"); }
  }

  async function openRun(id: string) {
    try { const run = (await api.getRun(id)).run; setCurrentRun(run); onRun(run); }
    catch (error) { onMessage((error as Error).message, "error"); }
  }

  async function toggleCandidate(run: Run, itemId: string) {
    const selected = candidateSelection?.selected_items || [];
    const existing = selected.find((item) => item.run_id === run.run_id && item.item_id === itemId);
    if (existing) {
      const response = await api.removeCandidate(run.run_id, itemId);
      onSelection?.(response.candidate_selection);
      onWorkspace(response.workspace);
      return;
    }
    const item = run.items.find((candidate) => candidate.item_id === itemId);
    if (!item) return;
    const conflict = selected.find((candidate) => candidate.source_id === item.source_id);
    if (conflict) { onMessage("Choose one output per source portrait; remove the existing candidate first.", "error"); return; }
    if (selected.length >= 3) { onMessage("A Finish cohort can contain at most three candidates.", "error"); return; }
    const response = await api.saveCandidateSelection([...selected.map((candidate) => ({ run_id: candidate.run_id, item_id: candidate.item_id })), { run_id: run.run_id, item_id: itemId }]);
    onSelection?.(response.candidate_selection);
    onWorkspace(response.workspace);
  }

  async function moveCandidate(index: number, direction: -1 | 1) {
    if (!candidateSelection) return;
    const target = index + direction;
    if (target < 0 || target >= candidateSelection.selected_items.length) return;
    const items = candidateSelection.selected_items.map((item) => ({ run_id: item.run_id, item_id: item.item_id }));
    [items[index], items[target]] = [items[target], items[index]];
    try { const response = await api.reorderCandidates(items); onSelection?.(response.candidate_selection); onWorkspace(response.workspace); }
    catch (error) { onMessage((error as Error).message, "error"); }
  }

  const references = recipe?.reference_ids.map((id) => workspace.references.find((item) => item.id === id)).filter(Boolean) || [];
  const otherReferences = workspace.references.filter((item) => !recipe?.reference_ids.includes(item.id));
  const grouped = currentRun?.benchmark_source_ids.map((sourceId) => ({ source: currentRun.sources_snapshot.find((item) => item.id === sourceId), items: currentRun.items.filter((item) => item.source_id === sourceId) })) || [];
  const compareCandidates = runs.filter((item) => item.run_id !== currentRun?.run_id && item.status === "complete" && (!item.purpose || item.purpose === "exploration"));

  return <section className="stage-page styles-page">
    <div className="page-heading"><div><p className="eyebrow">Stage 2 of 6 · Explore</p><h2>Explore a style</h2><p>Say what should change, choose a few source images, and generate. Select 1–3 representative outputs to hand off to Finish.</p></div><button className="button secondary" onClick={() => onNavigate("#sources")}>← Back to Sources</button></div>
    {!recipe ? <div className="empty-panel"><h3>No style recipe is available</h3><p>Refresh the workspace to seed its starter recipe.</p></div> : <>
      <section className="surface style-setup">
        <div className="setup-block"><div className="panel-heading"><div><p className="eyebrow">Source images</p><h3>Choose a few to explore</h3></div><span className="status-chip">{sourceIds.length} chosen</span></div>{selectedSources.length ? <div className="choice-thumbs">{selectedSources.map((source) => <button key={source.id} className={sourceIds.includes(source.id) ? "selected" : ""} onClick={() => setSourceIds((current) => current.includes(source.id) ? current.filter((id) => id !== source.id) : [...current, source.id])}><img src={source.image_url} alt={source.label} /><span>{source.label}</span></button>)}</div> : <div className="mini-empty">No project sources yet. <button className="text-button" onClick={() => onNavigate("#sources")}>Add source images</button></div>}</div>
        <div className="setup-block"><div className="panel-heading"><div><p className="eyebrow">Ordered style references</p><h3>{references.length} visual reference{references.length === 1 ? "" : "s"}</h3></div></div><div className="reference-list">{references.map((reference, index) => <article key={reference!.id}><img src={reference!.image_url} alt={reference!.label} /><span><strong>{index + 1}. {reference!.label}</strong><small>{String(reference!.provenance?.kind || "upload")}</small></span><div><button onClick={() => moveReference(index, -1)} disabled={index === 0} aria-label="Move reference earlier">←</button><button onClick={() => moveReference(index, 1)} disabled={index === references.length - 1} aria-label="Move reference later">→</button><button onClick={() => patchRecipe({ reference_ids: recipe.reference_ids.filter((id) => id !== reference!.id) })} aria-label="Remove reference">×</button></div></article>)}</div>{otherReferences.length > 0 && <div className="reference-add">{otherReferences.map((reference) => <button key={reference.id} onClick={() => patchRecipe({ reference_ids: [...recipe.reference_ids, reference.id] })}><img src={reference.image_url} alt="" />+ {reference.label}</button>)}</div>}<div className="inline-form compact"><input value={referenceLabel} onChange={(event) => setReferenceLabel(event.target.value)} placeholder="Optional reference label" /><label className="button secondary file-button">Upload reference<input type="file" accept="image/*" onChange={uploadReference} /></label></div></div>
        <label className="change-field"><span>What should change?</span><textarea value={recipe.change_note} onChange={(event) => patchRecipe({ change_note: event.target.value })} placeholder="For example: warmer evening light, looser brushwork, and a quieter background." rows={4} /><small>This plain-language note is appended to the art direction and snapshotted into every run.</small></label>
        <div className="generation-bar"><label>Variants<select value={variants} onChange={(event) => setVariants(Number(event.target.value))}>{[1, 2, 3, 4].map((count) => <option key={count} value={count}>{count}</option>)}</select></label><button className="button primary generate-button" disabled={Boolean(runProblem) || activeRun || Boolean(busy)} onClick={() => void generate(false)}>{busy === "generate" ? "Starting…" : `Generate ${variants} variant${variants === 1 ? "" : "s"}`}</button><button className="button secondary" disabled={Boolean(allSourcesProblem) || activeRun || Boolean(busy)} onClick={() => void generate(true)}>{busy === "test-all" ? "Starting…" : "Test across all sources"}</button></div>
        {runProblem && <p className="validation-note" role="status">{runProblem}</p>}
      </section>

      <details className="surface advanced-panel"><summary><span>Advanced</span><small>Model, quality, execution, structured direction, prompt, recipes, and provider</small></summary><div className="advanced-content">
        <div className="mode-switch"><button className={recipe.execution_mode === "live" ? "selected" : ""} onClick={() => changeMode("live")}>Live generation<small>OpenRouter · usage recorded</small></button><button className={recipe.execution_mode === "simulation" ? "selected" : ""} onClick={() => changeMode("simulation")}>Simulation<small>Local workflow fixture</small></button></div>
        <div className="form-grid"><label className="field-label">Recipe name<input value={recipe.name} onChange={(event) => patchRecipe({ name: event.target.value })} /></label><label className="field-label">Model<select value={recipe.model} onChange={(event) => patchRecipe({ model: event.target.value })}>{modelsForMode(models, recipe.execution_mode).map((item) => <option key={item.id} value={item.id}>{item.name}{item.available ? "" : " · unavailable"}</option>)}</select></label><label className="field-label">Quality<select value={recipe.quality} onChange={(event) => patchRecipe({ quality: event.target.value as Recipe["quality"] })}>{(["low", "medium", "high"] as const).filter((quality) => !model?.qualities.length || model.qualities.includes(quality)).map((quality) => <option key={quality}>{quality}</option>)}</select></label></div>
        <div className="direction-grid">{directionLabels.map(([key, label]) => <label className="field-label" key={key}>{label}<textarea rows={3} value={recipe.direction[key]} onChange={(event) => patchDirection(key, event.target.value)} /></label>)}</div><label className="field-label">Avoid<textarea rows={3} value={recipe.avoid} onChange={(event) => patchRecipe({ avoid: event.target.value })} /></label>
        <div className="prompt-preview"><strong>Resolved instruction preview</strong><pre>{resolvedPrompt || "No instruction text yet."}</pre></div>
        <dl className="provider-details"><dt>Provider</dt><dd>{model?.provider_name || model?.provider_slug || (recipe.execution_mode === "simulation" ? "Local deterministic adapter" : "Unavailable")}</dd><dt>Reference limit</dt><dd>{model?.max_input_references ?? "—"} total images</dd><dt>Streaming</dt><dd>{model?.supports_streaming ? "Supported" : "Buffered"}</dd><dt>Pricing</dt><dd>{model?.pricing.length ? model.pricing.map((item) => `$${item.cost_usd}/${item.unit}`).join(", ") : "Usage response is the source of truth"}</dd></dl>
        {workspace.recipes.length > 1 && <label className="field-label recipe-select">Saved recipe<select value={recipe.id} onChange={(event) => void selectRecipe(event.target.value)}>{workspace.recipes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        <div className="advanced-actions"><button className="button secondary" onClick={() => void duplicateRecipe()}>Duplicate recipe</button><button className="button primary" disabled={!dirty || busy === "save"} onClick={() => void saveRecipe()}>{busy === "save" ? "Saving…" : dirty ? "Save style changes" : "Saved"}</button></div>
      </div></details>
    </>}

    <section className="results-section"><div className="panel-heading"><div><p className="eyebrow">Generation batches</p><h3>{currentRun ? currentRun.recipe_snapshot.change_note || currentRun.recipe_name : "Results appear here"}</h3></div>{currentRun && <span className={`status-chip ${currentRun.status}`}>{currentRun.status} · {currentRun.completed_calls}/{currentRun.total_calls}</span>}</div>
      {!currentRun ? <div className="empty-panel"><span className="empty-glyph">✦</span><h3>No generation batch selected</h3><p>Generate above, or open a previous batch from history.</p></div> : <>
        <div className="progress-track" aria-label={`${currentRun.completed_calls} of ${currentRun.total_calls} results complete`}><span style={{ width: `${currentRun.total_calls ? (currentRun.completed_calls / currentRun.total_calls) * 100 : 0}%` }} /></div>
        <div className="batch-groups">{grouped.map((group) => <article className="surface batch-group" key={group.source?.id}><header><img src={group.source?.input_url} alt={group.source?.label || "Source"} /><div><p className="eyebrow">Source batch</p><h4>{group.source?.label}</h4></div><details><summary>Batch details</summary><p><strong>Style note:</strong> {currentRun.recipe_snapshot.change_note || "Structured art direction only"}</p><div className="reference-thumbs">{currentRun.references_snapshot.map((reference) => <img src={reference.input_url} alt={reference.label} key={reference.id} />)}</div><p>Cost: ${group.items.reduce((total, item) => total + Number(item.cost_usd || 0), 0).toFixed(4)}</p></details></header><div className="result-grid">{group.items.map((item) => { const selected = candidateSelection?.selected_items.find((candidate) => candidate.run_id === currentRun.run_id && candidate.item_id === item.item_id); return <div className={`result-card ${item.status} ${selected ? "selected" : ""}`} key={item.item_id}>{item.output_url ? <img src={item.output_url} alt={`${item.source_label} variant ${item.output_index + 1}`} /> : <div className="result-placeholder"><span className="spinner" />{item.status}</div>}<div><strong>Variant {item.output_index + 1}</strong>{selected && <span className="selection-badge">Selected #{selected.order + 1}</span>}{item.error && <small className="error-text">{item.error}</small>}{item.status === "complete" && <button className="button primary" onClick={() => void toggleCandidate(currentRun, item.item_id)}>{selected ? "Remove candidate" : "Select for Finish"}</button>}<details><summary>Details</summary><small>{item.elapsed_seconds ?? "—"}s · ${Number(item.cost_usd || 0).toFixed(4)} · seed {item.seed ?? "—"}</small></details></div></div>; })}</div></article>)}</div>
      </>}
      {runs.length > 0 && <details className="run-history"><summary>Run history ({runs.length})</summary><div>{runs.map((run) => <button key={run.run_id} onClick={() => void openRun(run.run_id)}><span className={`status-dot ${run.status}`} /><span><strong>{run.purpose_label || (run.purpose === "finish" ? "Finish trial" : run.purpose === "set-production" ? "Set production" : "Explore")}: {run.recipe_name}</strong><small>{formatTime(run.created_at)} · {run.source_count} source{run.source_count === 1 ? "" : "s"} · ${Number(run.cost_usd || 0).toFixed(4)}</small></span></button>)}</div></details>}
      {currentRun && compareCandidates.length > 0 && <div className="compare-tool"><label>Compare this batch with<select value={compareId} onChange={(event) => setCompareId(event.target.value)}><option value="">Choose a completed batch</option>{compareCandidates.map((run) => <option key={run.run_id} value={run.run_id}>{run.recipe_name} · {formatTime(run.created_at)}</option>)}</select></label><button className="button secondary" disabled={!compareId} onClick={() => onNavigate(`#compare/${currentRun.run_id}/${compareId}`)}>Compare sources</button></div>}
    </section>
    {candidateSelection && <section className="surface selection-tray"><div><p className="eyebrow">Finish handoff</p><h3>{candidateSelection.selected_items.length} / 3 selected</h3><p>One representative output per source. Reorder or remove candidates before starting a Finish trial.</p></div><div className="selection-tray-items">{candidateSelection.selected_items.map((item, index) => <article key={`${item.run_id}:${item.item_id}`}><button onClick={() => void toggleCandidate(currentRun || ({ run_id: item.run_id, items: [] } as unknown as Run), item.item_id)}><span>#{item.order + 1}</span>{item.output_url ? <img src={item.output_url} alt={item.source_label} /> : null}<small>{item.source_label}</small></button><div><button aria-label={`Move ${item.source_label} earlier`} disabled={index === 0} onClick={() => void moveCandidate(index, -1)}>←</button><button aria-label={`Move ${item.source_label} later`} disabled={index === candidateSelection.selected_items.length - 1} onClick={() => void moveCandidate(index, 1)}>→</button></div></article>)}</div></section>}
    <div className="stage-actions"><button className="button secondary" onClick={() => onNavigate("#sources")}>← Back to Sources</button><button className="button primary large" disabled={!candidateSelection?.selected_items.length} onClick={() => onNavigate("#finish")}>Continue to Finish →</button></div>
  </section>;
}

export function CompareView({ firstId, secondId, onNavigate }: { firstId: string; secondId: string; onNavigate: (hash: string) => void }) {
  const [comparison, setComparison] = useState<Awaited<ReturnType<typeof api.compareRuns>>["comparison"]>();
  const [error, setError] = useState("");
  useEffect(() => { void api.compareRuns(firstId, secondId).then((response) => setComparison(response.comparison)).catch((nextError) => setError((nextError as Error).message)); }, [firstId, secondId]);
  if (error) return <section className="stage-page"><div className="inline-error">{error}</div></section>;
  if (!comparison) return <section className="stage-page loading-inline"><span className="spinner" /> Loading comparison…</section>;
  return <section className="stage-page compare-view"><button className="back-link" onClick={() => onNavigate("#styles")}>← Back to Styles</button><div className="page-heading"><div><p className="eyebrow">Secondary tool</p><h2>{comparison.first.recipe_snapshot.name} vs {comparison.second.recipe_snapshot.name}</h2><p>Immutable results aligned by source image.</p></div></div>{!comparison.same_benchmark && <div className="inline-error">These batches use different source membership or order.</div>}<div className="compare-table"><div className="compare-row head"><span>Source</span><strong>{comparison.first.recipe_snapshot.name}</strong><strong>{comparison.second.recipe_snapshot.name}</strong></div>{comparison.rows.map((row) => <div className="compare-row" key={row.source_id}><span>{row.source_id}</span>{row.first?.thumbnail_url ? <img src={row.first.thumbnail_url} alt={row.first.source_label} /> : <i>Missing</i>}{row.second?.thumbnail_url ? <img src={row.second.thumbnail_url} alt={row.second.source_label} /> : <i>Missing</i>}</div>)}</div><div className="surface recipe-diff"><h3>Recipe changes</h3>{comparison.recipe_changes.length ? comparison.recipe_changes.map((change) => <div key={change.field}><strong>{change.field}</strong><span>{String(change.first || "—")}</span><span>{String(change.second || "—")}</span></div>) : <p>No recipe fields changed.</p>}</div></section>;
}
