import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { modelsForMode, selectedModel } from "./runDraft";
import type { CandidateSelection, FinishSummary, Model, Recipe, Run, RunSummary, Workspace } from "./types";

type Props = {
  workspace: Workspace;
  selection?: CandidateSelection | null;
  runs: RunSummary[];
  finishes?: FinishSummary[];
  models: Model[];
  initialRun?: Run;
  onRun: (run: Run) => void;
  onRefresh: () => Promise<void>;
  onNavigate: (hash: string) => void;
  onMessage: (message: string, kind?: "success" | "error") => void;
};

function isCurrentFinishRun(candidate: Run | undefined, selection?: CandidateSelection | null) {
  return Boolean(
    candidate?.purpose === "finish" &&
    candidate.selection_id === selection?.selection_id &&
    candidate.selection_revision === selection?.revision,
  );
}

export function FinishStage({ workspace, selection, runs, finishes = [], models, initialRun, onRun, onRefresh, onNavigate, onMessage }: Props) {
  const inherited = selection?.selected_items[0]?.recipe_snapshot || workspace.recipes.find((item) => item.id === workspace.active_recipe_id) || workspace.recipes[0];
  const [recipe, setRecipe] = useState<Recipe | undefined>(inherited);
  const [run, setRun] = useState<Run | undefined>(() => isCurrentFinishRun(initialRun, selection) ? initialRun : undefined);
  const [busy, setBusy] = useState("");
  const [compareId, setCompareId] = useState("");
  const [comparison, setComparison] = useState<Awaited<ReturnType<typeof api.compareFinishTrials>>["comparison"]>();
  const finishRuns = useMemo(() => runs.filter((item) => item.purpose === "finish" && item.selection_id === selection?.selection_id && item.selection_revision === selection?.revision), [runs, selection?.selection_id, selection?.revision]);

  useEffect(() => { setRecipe(inherited); }, [inherited?.id, selection?.revision]);
  useEffect(() => { setRun(isCurrentFinishRun(initialRun, selection) ? initialRun : undefined); }, [initialRun?.run_id, initialRun?.updated_at, initialRun?.purpose, initialRun?.selection_id, initialRun?.selection_revision, selection?.selection_id, selection?.revision]);
  useEffect(() => {
    if (!run || !["queued", "running"].includes(run.status)) return;
    const timer = window.setInterval(async () => {
      try { const next = (await api.getRun(run.run_id)).run; setRun(next); onRun(next); if (!["queued", "running"].includes(next.status)) await onRefresh(); }
      catch (error) { onMessage((error as Error).message, "error"); }
    }, 800);
    return () => window.clearInterval(timer);
  }, [run?.run_id, run?.status]);

  function patch(patchValue: Partial<Recipe>) { setRecipe((current) => current ? { ...current, ...patchValue } : current); }
  function patchDirection(key: keyof Recipe["direction"], value: string) { setRecipe((current) => current ? { ...current, direction: { ...current.direction, [key]: value } } : current); }

  async function launch() {
    if (!selection || !recipe) return;
    const problem = !selection.selected_items.length ? "Select 1–3 Explore candidates first." : !recipe.change_note.trim() ? "Describe the finish change before starting a trial." : "";
    if (problem) { onMessage(problem, "error"); return; }
    setBusy("launch");
    try { const response = await api.createFinishTrial(selection.revision, recipe); setRun(response.run); onRun(response.run); onMessage(`Finish trial queued: exactly ${selection.selected_items.length} image call${selection.selected_items.length === 1 ? "" : "s"}.`); }
    catch (error) { onMessage((error as Error).message, "error"); }
    finally { setBusy(""); }
  }

  async function lock() {
    if (!run || run.status !== "complete" || !isCurrentFinishRun(run, selection)) return;
    setBusy("lock");
    try { await api.lockFinish(run.run_id); await onRefresh(); onMessage("Finish locked as an immutable cohort"); onNavigate("#set"); }
    catch (error) { onMessage((error as Error).message, "error"); }
    finally { setBusy(""); }
  }

  async function compare() {
    if (!run || !compareId) return;
    try { setComparison((await api.compareFinishTrials(run.run_id, compareId)).comparison); }
    catch (error) { onMessage((error as Error).message, "error"); }
  }

  if (!selection?.selected_items.length) return <section className="stage-page finish-page"><div className="page-heading"><div><p className="eyebrow">Stage 3 of 6 · Finish</p><h2>Choose a coherent finish</h2><p>Select representative Explore outputs first. Finish applies one generative look to the whole cohort.</p></div><button className="button secondary" onClick={() => onNavigate("#styles")}>← Back to Explore</button></div><div className="empty-panel"><span className="empty-glyph">✦</span><h3>No Finish candidates yet</h3><p>Explore a few variants, then select one output for each source portrait.</p><button className="button primary" onClick={() => onNavigate("#styles")}>Open Explore</button></div></section>;

  const model = recipe ? selectedModel(models, recipe) : undefined;
  const finishItems = run?.items || [];
  return <section className="stage-page finish-page">
    <div className="page-heading"><div><p className="eyebrow">Stage 3 of 6 · Finish</p><h2>Iterate one finish across the cohort</h2><p>The selected candidates stay aligned by source. Every trial requests exactly {selection.selected_items.length} image call{selection.selected_items.length === 1 ? "" : "s"} and can only be approved as a complete cohort.</p></div><button className="button secondary" onClick={() => onNavigate("#styles")}>← Back to Explore</button></div>
    <section className="surface cohort-strip"><div className="panel-heading"><div><p className="eyebrow">Selection revision {selection.revision}</p><h3>Candidate cohort</h3></div><span className="status-chip">{selection.selected_items.length} selected</span></div><div className="cohort-grid">{selection.selected_items.map((item) => <article key={`${item.run_id}:${item.item_id}`}><img src={item.output_url || undefined} alt={item.source_label} /><strong>{item.order + 1}. {item.source_label}</strong><small>{item.recipe_name || item.run_id}</small></article>)}</div></section>
    <section className="surface finish-setup"><div className="panel-heading"><div><p className="eyebrow">Finish direction</p><h3>What should change across all candidates?</h3></div><span className="status-chip">{model?.name || recipe?.model || "Model required"}</span></div><label className="change-field"><span>Plain-language finish change</span><textarea value={recipe?.change_note || ""} onChange={(event) => patch({ change_note: event.target.value })} rows={3} placeholder="For example: unify the portraits with quiet dusk light and broad dry-brush edges." /><small>This becomes the requested finish change; inherited Explore art direction remains separately traceable.</small></label>{recipe && <><div className="finish-reference-stack"><p className="eyebrow">Inherited ordered style references</p><div className="reference-thumbs">{recipe.reference_ids.map((id, index) => { const reference = workspace.references.find((item) => item.id === id); return reference ? <figure key={id}><img src={reference.image_url} alt={reference.label} /><figcaption>{index + 1}. {reference.label}</figcaption></figure> : null; })}</div></div><details className="surface nested-details"><summary>Advanced finish recipe</summary><div className="direction-grid">{(["medium_brushwork", "lighting", "background", "composition", "colour", "detail", "identity"] as const).map((key) => <label className="field-label" key={key}>{key.replace("_", " ")}<textarea rows={2} value={recipe.direction[key]} onChange={(event) => patchDirection(key, event.target.value)} /></label>)}</div><label className="field-label">Model<select value={recipe.model} onChange={(event) => patch({ model: event.target.value })}>{modelsForMode(models, recipe.execution_mode).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></details></>}
      <div className="generation-bar"><span>Ordered references: {recipe?.reference_ids.length || 0}</span><span>Quality: {recipe?.quality || "—"}</span><button className="button primary" disabled={Boolean(busy) || Boolean(run && ["queued", "running"].includes(run.status))} onClick={() => void launch()}>{busy === "launch" ? "Starting…" : "Start Finish trial"}</button></div>
    </section>
    {run && <section className="surface cohort-results"><div className="panel-heading"><div><p className="eyebrow">Trial cohort</p><h3>{run.status} · {run.completed_calls}/{run.total_calls} complete</h3></div><span className="status-chip">${Number(run.cost_usd || 0).toFixed(4)}</span></div><div className="progress-track"><span style={{ width: `${run.total_calls ? (run.completed_calls / run.total_calls) * 100 : 0}%` }} /></div><div className="cohort-grid trial-grid">{selection.selected_items.map((candidate, index) => { const item = finishItems[index]; return <article key={candidate.source_id}><div className="cohort-pair"><img src={candidate.output_url || undefined} alt={`${candidate.source_label} candidate`} />{item?.output_url ? <img src={item.output_url} alt={`${candidate.source_label} Finish trial`} /> : <div className="result-placeholder">{item?.status || "queued"}</div>}</div><strong>{candidate.source_label}</strong><small>{item?.error || `${item?.status || "queued"} · ${Number(item?.cost_usd || 0).toFixed(4)}`}</small></article>; })}</div>{run.status === "complete" && <button className="button primary large" disabled={busy === "lock"} onClick={() => void lock()}>{busy === "lock" ? "Locking…" : "Lock this finish"}</button>}{run.status !== "complete" && <p className="validation-note">Locking is available only when every cohort output is complete.</p>}</section>}
    {finishRuns.length > 0 && <details className="surface run-history"><summary>Finish trial history ({finishRuns.length})</summary>{finishRuns.map((item) => <button key={item.run_id} onClick={() => void api.getRun(item.run_id).then((response) => { setRun(response.run); onRun(response.run); })}><strong>{item.status}</strong><span>{item.run_id} · {item.completed_calls}/{item.total_calls} · ${Number(item.cost_usd || 0).toFixed(4)}</span></button>)}</details>}
    {run?.status === "complete" && finishRuns.some((item) => item.run_id !== run.run_id && item.status === "complete") && <section className="surface compare-tool"><label>Compare complete cohorts<select value={compareId} onChange={(event) => setCompareId(event.target.value)}><option value="">Choose a Finish trial</option>{finishRuns.filter((item) => item.run_id !== run.run_id && item.status === "complete").map((item) => <option key={item.run_id} value={item.run_id}>{item.run_id} · ${Number(item.cost_usd || 0).toFixed(4)}</option>)}</select></label><button className="button secondary" disabled={!compareId} onClick={() => void compare()}>Compare cohorts</button></section>}
    {comparison && <section className="surface compare-table cohort-comparison"><div className="compare-row head"><span>Candidate</span><strong>Trial A</strong><strong>Trial B</strong></div>{comparison.rows.map((row) => <div className="compare-row" key={row.source_id}><span>{row.source_label || row.source_id}</span>{row.first?.output_url ? <img src={row.first.output_url} alt="First Finish trial" /> : <i>Missing</i>}{row.second?.output_url ? <img src={row.second.output_url} alt="Second Finish trial" /> : <i>Missing</i>}</div>)}</section>}
    {finishes.filter((item) => item.selection_id === selection.selection_id).length > 0 && <section className="surface locked-finish-summary"><div className="panel-heading"><div><p className="eyebrow">Locked Finish history</p><h3>Immutable approved cohorts</h3></div></div>{finishes.filter((item) => item.selection_id === selection.selection_id).map((item) => <article key={item.finish_id}><div><strong>Finish v{item.version}</strong><span>{item.recipe_name || item.finish_id} · {item.candidate_count} anchors · {item.model || "model recorded"}</span><small>{item.change_note || "No additional finish note"} · ${Number(item.cost_usd || 0).toFixed(4)} · locked {item.locked_at || "—"}</small></div><span className="status-chip">Immutable</span></article>)}</section>}
    <div className="stage-actions"><button className="button secondary" onClick={() => onNavigate("#styles")}>← Explore</button><button className="button primary" onClick={() => onNavigate("#set")}>Continue to Build Set →</button></div>
  </section>;
}
