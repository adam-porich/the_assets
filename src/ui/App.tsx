import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { CompletedStage, FramesStage } from "./CardViews";
import { FinishStage } from "./FinishLab";
import { SetStage } from "./SetViews";
import { CompareView, SourcesStage, StylesStage } from "./StyleLab";
import type { Bootstrap, Card, Run } from "./types";

type Route = { view: "sources" | "styles" | "finish" | "set" | "frames" | "completed" | "compare"; id?: string; other?: string; runId?: string };

function replaceHash(hash: string) {
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${hash}`);
}

export function readRoute(): Route {
  const value = window.location.hash.replace(/^#/, "") || "sources";
  const [view, id, other] = value.split("/");
  if (view === "sources" || view === "styles" || view === "finish" || view === "set" || view === "completed") return { view };
  if (view === "explore") return { view: "styles" };
  if (view === "frames") return { view, id };
  if (view === "compare" && id && other) return { view, id, other };
  if (view === "run" && id) { replaceHash("#styles"); return { view: "styles", runId: id }; }
  if (view === "card" && id) { replaceHash(`#frames/${id}`); return { view: "frames", id }; }
  if (view === "cards") { replaceHash("#frames"); return { view: "frames" }; }
  if (view === "lab") { replaceHash("#styles"); return { view: "styles" }; }
  replaceHash("#sources");
  return { view: "sources" };
}

export function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap>();
  const [route, setRoute] = useState<Route>(readRoute);
  const [activeRun, setActiveRun] = useState<Run>();
  const [activeCard, setActiveCard] = useState<Card>();
  const [candidateSelection, setCandidateSelection] = useState<Bootstrap["candidate_selection"]>();
  const [draftSetId, setDraftSetId] = useState<string>();
  const [message, setMessage] = useState<{ text: string; kind: "success" | "error" }>();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const next = await api.bootstrap();
      setBootstrap(next);
      setCandidateSelection(next.candidate_selection || next.workspace.candidate_selection || null);
      setLoadError("");
      if (route.view === "styles" || route.view === "finish") {
        const runId = route.runId || activeRun?.run_id || next.runs[0]?.run_id;
        if (runId) setActiveRun((await api.getRun(runId)).run);
      }
      if (route.view === "frames" && route.id) setActiveCard((await api.getCard(route.id)).card);
      const activeSet = next.sets?.find((item) => item.set_id === next.active_set_id);
      if (route.view === "frames" && !route.id && activeSet?.state === "ready" && next.active_set_id && !next.cards.some((item) => item.set_id === next.active_set_id) && draftSetId !== next.active_set_id) {
        setDraftSetId(next.active_set_id);
        try { await api.createSetDrafts(next.active_set_id); const refreshed = await api.bootstrap(); setBootstrap(refreshed); setCandidateSelection(refreshed.candidate_selection || null); } catch (error) { setLoadError((error as Error).message); }
      }
    } catch (error) {
      setLoadError((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, [route.view, route.id, route.runId, activeRun?.run_id, draftSetId]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const handler = () => {
      const next = readRoute();
      setRoute(next);
      if (next.view !== "styles" && next.view !== "finish") setActiveRun(undefined);
      if (next.view !== "frames" || !next.id) setActiveCard(undefined);
    };
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  useEffect(() => {
    if (!message || message.kind === "error") return;
    const timer = window.setTimeout(() => setMessage(undefined), 4500);
    return () => window.clearTimeout(timer);
  }, [message]);

  function navigate(hash: string) { window.location.hash = hash.replace(/^#?/, "#"); }
  function workspaceUpdate(workspace: Bootstrap["workspace"]) { setBootstrap((current) => current ? { ...current, workspace } : current); }
  function notify(text: string, kind: "success" | "error" = "success") { setMessage({ text, kind }); }

  if (loading && !bootstrap) return <main className="app-shell loading-shell"><div className="loading-mark">✳</div><p>Opening Portrait Workbench…</p></main>;
  if (loadError && !bootstrap) return <main className="app-shell loading-shell"><div className="empty-glyph">!</div><h1>Portrait Workbench is unavailable</h1><p>{loadError}</p><button className="button primary" onClick={() => { setLoading(true); void refresh(); }}>Try again</button></main>;
  if (!bootstrap) return null;

  const selectedSources = bootstrap.workspace.benchmark_source_ids.length;
  const workingCards = bootstrap.cards.filter((card) => card.decision === "working");
  const activeSetId = bootstrap.active_set_id || bootstrap.workspace.active_set_id || null;
  const activeSet = bootstrap.sets?.find((item) => item.set_id === activeSetId);
  const activeCards = activeSetId ? bootstrap.cards.filter((card) => card.set_id === activeSetId) : bootstrap.cards;
  const completedCards = activeCards.filter((card) => card.decision === "keep");
  const stage = route.view === "compare" ? "styles" : route.view;
  const card = activeCard || bootstrap.cards.find((item) => item.card_id === route.id);
  const stages = [
    { id: "sources", label: "Sources", done: selectedSources > 0, count: selectedSources },
    { id: "styles", label: "Explore", done: bootstrap.workspace.recipes.length > 0, count: bootstrap.runs.filter((item) => !item.purpose || item.purpose === "exploration").length },
    { id: "finish", label: "Finish", done: Boolean(bootstrap.finishes?.length), count: bootstrap.finishes?.length || 0 },
    { id: "set", label: "Build Set", done: Boolean(activeSet), count: bootstrap.sets?.length || 0 },
    { id: "frames", label: "Frames", done: Boolean(activeSet?.state === "ready"), count: workingCards.length },
    { id: "completed", label: "Completed", done: completedCards.length > 0, count: completedCards.length },
  ] as const;

  return <main className="app-shell">
    <header className="app-header">
      <div className="brand-block"><span className="brand-symbol">✳</span><div><p className="brand-kicker">Experimental asset studio</p><h1>Portrait Workbench</h1></div></div>
      <div className="header-status">{bootstrap.workspace.sources.length} images · {bootstrap.workspace.references.length} references</div>
    </header>
    <nav className="stage-nav" aria-label="Graphics workflow stages">
      {stages.map((item, index) => <button key={item.id} className={stage === item.id ? "active" : ""} onClick={() => navigate(`#${item.id}`)} aria-current={stage === item.id ? "step" : undefined}><span className={`stage-number ${item.done ? "done" : ""}`}>{item.done ? "✓" : index + 1}</span><span><b>{item.label}</b><small>{item.id === "sources" ? `${item.count} selected` : item.id === "styles" ? `${item.count} batches` : `${item.count} ${item.id === "completed" ? "kept" : "waiting"}`}</small></span></button>)}
    </nav>
    <div className="global-band">{message && <span className={`toast-inline ${message.kind}`} role={message.kind === "error" ? "alert" : "status"}>{message.text}<button className="toast-dismiss" onClick={() => setMessage(undefined)} aria-label="Dismiss message">×</button></span>}<span className="global-spacer" /><button className="text-button" onClick={() => void refresh()}>Refresh</button></div>
    {route.view === "sources" ? <SourcesStage workspace={bootstrap.workspace} pexelsAvailable={bootstrap.integrations.pexels.configured} onWorkspace={workspaceUpdate} onNavigate={navigate} onMessage={notify} />
      : route.view === "styles" ? <StylesStage workspace={bootstrap.workspace} models={bootstrap.models} runs={bootstrap.runs} initialRun={activeRun} baselineRunId={bootstrap.baseline_exploration_run_id} candidateSelection={candidateSelection} onSelection={setCandidateSelection} openrouterAvailable={bootstrap.integrations.openrouter.configured} onWorkspace={workspaceUpdate} onRun={setActiveRun} onRefresh={refresh} onNavigate={navigate} onMessage={notify} />
      : route.view === "finish" ? <FinishStage workspace={bootstrap.workspace} selection={candidateSelection} runs={bootstrap.runs} finishes={bootstrap.finishes} models={bootstrap.models} initialRun={activeRun} onRun={setActiveRun} onRefresh={refresh} onNavigate={navigate} onMessage={notify} />
      : route.view === "set" ? <SetStage workspace={bootstrap.workspace} finishes={bootstrap.finishes || []} sets={bootstrap.sets || []} models={bootstrap.models} activeSetId={activeSetId} onWorkspace={workspaceUpdate} onRefresh={refresh} onNavigate={navigate} onMessage={notify} />
      : route.view === "compare" && route.id && route.other ? <CompareView firstId={route.id} secondId={route.other} onNavigate={navigate} />
      : route.view === "frames" ? <FramesStage cards={activeCards} activeSetId={activeSetId} setItemCount={activeSet?.source_count} initialCard={card} onNavigate={navigate} onMessage={notify} onRefresh={refresh} />
      : <CompletedStage cards={completedCards} activeSetId={activeSetId} legacyCards={activeSetId ? bootstrap.cards.filter((item) => item.legacy) : []} onNavigate={navigate} onMessage={notify} onRefresh={refresh} />}
    <footer className="app-footer"><span>Runs stay immutable; frame choices stay deterministic.</span><span>Sources, previews, and provenance remain in portrait-library/.</span></footer>
  </main>;
}
