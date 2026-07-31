import { useEffect, useState } from "react";
import { api } from "./api";
import type { FinishSummary, Model, PortraitSet, SetSummary, Workspace } from "./types";

type Props = {
  workspace: Workspace;
  finishes: FinishSummary[];
  sets: SetSummary[];
  models: Model[];
  activeSetId?: string | null;
  onWorkspace: (workspace: Workspace) => void;
  onRefresh: () => Promise<void>;
  onNavigate: (hash: string) => void;
  onMessage: (message: string, kind?: "success" | "error") => void;
};

export function SetStage({ workspace, finishes, sets, activeSetId, onWorkspace, onRefresh, onNavigate, onMessage }: Props) {
  const locked = finishes.filter((item) => item.state === "locked");
  const [finishId, setFinishId] = useState(locked[0]?.finish_id || "");
  const [name, setName] = useState("");
  const [set, setSet] = useState<PortraitSet>();
  const [busy, setBusy] = useState("");
  useEffect(() => { if (activeSetId) void api.getSet(activeSetId).then((response) => setSet(response.set)).catch(() => undefined); }, [activeSetId]);

  async function build() {
    if (!finishId || !name.trim()) { onMessage("Choose a locked Finish and name the set.", "error"); return; }
    setBusy("build");
    try { const response = await api.buildSet(name, finishId, workspace.benchmark_source_ids); setSet(response.set); onWorkspace(response.workspace); await onRefresh(); onMessage("Set build started; approved anchors were preserved without generation calls."); }
    catch (error) { onMessage((error as Error).message, "error"); }
    finally { setBusy(""); }
  }
  async function retry() { if (!set) return; setBusy("retry"); try { const response = await api.retrySet(set.set_id); setSet(response.set); await onRefresh(); onMessage("Failed set items queued in a new production run."); } catch (error) { onMessage((error as Error).message, "error"); } finally { setBusy(""); } }
  async function switchSet(id: string) { setBusy("switch"); try { const response = await api.switchSet(id); setSet(response.set); onWorkspace({ ...workspace, active_set_id: id }); await onRefresh(); onMessage("Active set switched"); } catch (error) { onMessage((error as Error).message, "error"); } finally { setBusy(""); } }

  return <section className="stage-page set-page"><div className="page-heading"><div><p className="eyebrow">Stage 4 of 6 · Build Set</p><h2>Build one coherent portrait set</h2><p>Keep the locked Finish anchors and generate only the remaining project sources with the exact identity → finish anchors → base references stack.</p></div><button className="button secondary" onClick={() => onNavigate("#finish")}>← Back to Finish</button></div>
    {!locked.length ? <div className="empty-panel"><span className="empty-glyph">▦</span><h3>No locked Finish yet</h3><p>Finish a complete cohort before starting set-wide production.</p><button className="button primary" onClick={() => onNavigate("#finish")}>Open Finish</button></div> : <section className="surface set-setup"><div className="panel-heading"><div><p className="eyebrow">Production preflight</p><h3>Choose the locked generative look</h3></div><span className="status-chip">{workspace.benchmark_source_ids.length} source{workspace.benchmark_source_ids.length === 1 ? "" : "s"}</span></div><div className="form-grid"><label className="field-label">Set name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Estate claimants · dusk set" /></label><label className="field-label">Locked Finish<select value={finishId} onChange={(event) => setFinishId(event.target.value)}><option value="">Choose a Finish</option>{locked.map((item) => <option key={item.finish_id} value={item.finish_id}>v{item.version} · {item.recipe_name || item.finish_id}</option>)}</select></label></div>{(() => { const selected = locked.find((item) => item.finish_id === finishId); const anchors = selected?.candidate_count || 0; return <p className="validation-note">Model: {selected?.model || "—"} · References: {selected?.reference_count || 0} anchors + base stack · Anchor subjects: {anchors} · Remaining sources: {Math.max(0, workspace.benchmark_source_ids.length - anchors)} · Paid image calls: {Math.max(0, workspace.benchmark_source_ids.length - anchors)}</p>; })()}<button className="button primary large" disabled={Boolean(busy)} onClick={() => void build()}>{busy === "build" ? "Building…" : "Build Set"}</button></section>}
    {set && <SetProgress set={set} busy={busy} onRetry={() => void retry()} onNavigate={onNavigate} />}
    {sets.length > 0 && <section className="surface set-history"><div className="panel-heading"><div><p className="eyebrow">History</p><h3>Historical portrait sets</h3></div></div>{sets.map((item) => <article key={item.set_id} className={item.set_id === activeSetId ? "active" : ""}><div><strong>{item.name}</strong><small>{item.state} · {item.complete_count}/{item.source_count} complete · Finish {item.finish_id}</small></div><button className="button secondary" disabled={item.set_id === activeSetId || Boolean(busy)} onClick={() => void switchSet(item.set_id)}>{item.set_id === activeSetId ? "Active" : "Switch to set"}</button></article>)}</section>}
    <div className="stage-actions"><button className="button secondary" onClick={() => onNavigate("#finish")}>← Finish</button><button className="button primary" disabled={!set || set.state !== "ready"} onClick={() => onNavigate("#frames")}>Continue to Frames →</button></div>
  </section>;
}

function SetProgress({ set, busy, onRetry, onNavigate }: { set: PortraitSet; busy: string; onRetry: () => void; onNavigate: (hash: string) => void }) {
  const complete = set.items.filter((item) => item.status === "complete").length;
  return <section className="surface set-progress"><div className="panel-heading"><div><p className="eyebrow">{set.name}</p><h3>{set.state}</h3></div><span className="status-chip">{complete}/{set.items.length} ready · ${Number(set.cost_usd || 0).toFixed(4)}</span></div><div className="progress-track"><span style={{ width: `${set.items.length ? complete / set.items.length * 100 : 0}%` }} /></div><div className="set-item-grid">{set.items.map((item) => <article key={item.set_item_id}><div className="set-item-image">{item.art_url ? <img src={item.art_url} alt={item.source_label} /> : <span className="spinner" />}</div><strong>{item.order + 1}. {item.source_label}</strong><span className={item.anchor ? "anchor-badge" : "generated-badge"}>{item.anchor ? "Locked anchor" : "Generated"}</span>{item.error && <small className="error-text">{item.error}</small>}</article>)}</div>{set.state === "ready-with-errors" && <button className="button secondary" disabled={Boolean(busy)} onClick={onRetry}>{busy === "retry" ? "Retrying…" : "Retry failed items"}</button>}{set.state === "ready" && <button className="button primary" onClick={() => onNavigate("#frames")}>Open Frames →</button>}</section>;
}
