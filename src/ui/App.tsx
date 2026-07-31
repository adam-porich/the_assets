import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { CardGallery, CardWorkbench } from "./CardViews";
import { CompareView, StyleLab } from "./StyleLab";
import type { Bootstrap, Card, Run } from "./types";

type Route = { view: "lab" | "cards" | "run" | "card" | "compare"; id?: string; other?: string };

function readRoute(): Route {
  const value = window.location.hash.replace(/^#/, "") || "lab";
  const [view, id, other] = value.split("/");
  if (view === "run" && id) return { view, id };
  if (view === "card" && id) return { view, id };
  if (view === "compare" && id && other) return { view, id, other };
  if (view === "cards") return { view };
  return { view: "lab" };
}

export function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap>();
  const [route, setRoute] = useState<Route>(readRoute);
  const [activeRun, setActiveRun] = useState<Run>();
  const [activeCard, setActiveCard] = useState<Card>();
  const [message, setMessage] = useState<{ text: string; kind: "success" | "error" }>();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const next = await api.bootstrap();
      setBootstrap(next); setLoadError("");
      if (route.view === "run" && route.id) setActiveRun((await api.getRun(route.id)).run);
      if (route.view === "card" && route.id) setActiveCard((await api.getCard(route.id)).card);
    } catch (error) { setLoadError((error as Error).message); }
    finally { setLoading(false); }
  }, [route]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { const handler = () => { const next = readRoute(); setRoute(next); if (next.view !== "run") setActiveRun(undefined); if (next.view !== "card") setActiveCard(undefined); }; window.addEventListener("hashchange", handler); return () => window.removeEventListener("hashchange", handler); }, []);
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
  const workspace = bootstrap.workspace;
  const card = activeCard || bootstrap.cards.find((item) => item.card_id === route.id);
  const newestCompletedRun = bootstrap.runs.find((run) => run.status === "complete");
  return <main className="app-shell"><header className="app-header"><div className="brand-block"><span className="brand-symbol">✳</span><div><p className="brand-kicker">Experimental asset studio</p><h1>Portrait Workbench</h1></div></div><nav className="main-nav"><button className={route.view === "lab" || route.view === "run" || route.view === "compare" ? "active" : ""} onClick={() => navigate("#lab")}>Style Lab</button><button className={route.view === "cards" || route.view === "card" ? "active" : ""} onClick={() => navigate("#cards")}>Card drafts <span>{bootstrap.cards.length}</span></button></nav><div className="header-status">{workspace.sources.length} sources · {workspace.references.length} references</div></header><div className="global-band"><span>Workbench state</span><span className="global-rule" />{message && <span className={`toast-inline ${message.kind}`} role={message.kind === "error" ? "alert" : "status"}>{message.text}<button className="toast-dismiss" onClick={() => setMessage(undefined)} aria-label="Dismiss message">Dismiss</button></span>}<span className="global-spacer" /><button className="text-button" onClick={() => void refresh()}>Refresh</button></div>{route.view === "lab" || route.view === "run" ? <StyleLab workspace={workspace} models={bootstrap.models} runs={bootstrap.runs} activeRun={activeRun} pexelsAvailable={bootstrap.integrations.pexels.configured} openrouterAvailable={bootstrap.integrations.openrouter.configured} onWorkspace={workspaceUpdate} onRefresh={refresh} onNavigate={navigate} onMessage={notify} /> : route.view === "compare" && route.id && route.other ? <CompareView firstId={route.id} secondId={route.other} onNavigate={navigate} /> : route.view === "cards" ? <CardGallery cards={bootstrap.cards} newestCompletedRunId={newestCompletedRun?.run_id} onNavigate={navigate} onRefresh={refresh} /> : route.view === "card" && card ? <CardWorkbench card={card} workspace={workspace} onNavigate={navigate} onMessage={notify} onRefresh={refresh} /> : <div className="empty-panel large-empty"><h2>Card draft not found</h2><button className="button primary" onClick={() => navigate("#cards")}>Open card drafts</button></div>}<footer className="app-footer"><span>Live generation and simulation are recorded separately</span><span>Sources and references stay in portrait-library/</span></footer></main>;
}
