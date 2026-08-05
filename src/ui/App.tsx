import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { CandidatesView, CollectionView, InputsView, PipelinesView } from "./WorkbenchViews";
import type { Bootstrap } from "./types";

export type Route = { view: "inputs" | "pipelines" | "candidates" | "collection"; id?: string; itemId?: string };

function replaceHash(hash: string) { window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${hash}`); }

export function readRoute(): Route {
  const value = window.location.hash.replace(/^#/, "") || "inputs";
  const [view, id, itemId] = value.split("/");
  if (view === "inputs" || view === "pipelines" || view === "candidates" || view === "collection") return { view: view as Route["view"], id, itemId };
  if (view === "sources") { replaceHash("#inputs"); return { view: "inputs", id }; }
  if (view === "cards") { replaceHash(id ? `#candidates/${id}${itemId ? `/${itemId}` : ""}` : "#candidates"); return { view: "candidates", id, itemId }; }
  if (["explore", "finish", "set", "frames", "completed"].includes(view)) { replaceHash("#candidates"); return { view: "candidates" }; }
  if (["style", "styles", "lab"].includes(view)) { replaceHash(id ? `#pipelines/${id}` : "#pipelines"); return { view: "pipelines", id }; }
  if (view === "card" && id) { replaceHash(`#candidates/${id}`); return { view: "candidates", id }; }
  if (view === "run" && id) { replaceHash(`#candidates/${id}`); return { view: "candidates", id }; }
  replaceHash("#inputs"); return { view: "inputs" };
}

export function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap>();
  const [route, setRoute] = useState<Route>(readRoute);
  const [message, setMessage] = useState<{ text: string; kind: "success" | "error" }>();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const refresh = useCallback(async () => { try { setBootstrap(await api.bootstrap()); setLoadError(""); } catch (error) { setLoadError((error as Error).message); } finally { setLoading(false); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { const handler = () => setRoute(readRoute()); window.addEventListener("hashchange", handler); return () => window.removeEventListener("hashchange", handler); }, []);
  useEffect(() => { if (!message || message.kind === "error") return; const timer = window.setTimeout(() => setMessage(undefined), 4500); return () => window.clearTimeout(timer); }, [message]);
  useEffect(() => { if (!bootstrap) return; const active = bootstrap.batches.some((batch) => ["queued", "running", "processing"].includes(batch.status)); if (!active) return; const timer = window.setInterval(() => void refresh(), 900); return () => window.clearInterval(timer); }, [bootstrap, refresh]);
  function navigate(hash: string) { window.location.hash = hash.replace(/^#?/, "#"); }
  function notify(text: string, kind: "success" | "error" = "success") { setMessage({ text, kind }); }
  if (loading && !bootstrap) return <main className="app-shell loading-shell"><div className="loading-mark">✳</div><p>Opening the asset workbench…</p></main>;
  if (loadError && !bootstrap) return <main className="app-shell loading-shell"><div className="empty-glyph">!</div><h1>Asset workbench is unavailable</h1><p>{loadError}</p><button className="button primary" onClick={() => { setLoading(true); void refresh(); }}>Try again</button></main>;
  if (!bootstrap) return null;
  const shared = { bootstrap, navigate, refresh, notify };
  const pipelineCount = bootstrap.style.pipelines.length;
  return <main className="app-shell">
    <header className="app-header"><a className="brand-block" href="#inputs"><span className="brand-symbol">✳</span><span><small>Experimental asset studio</small><strong>Asset Workbench</strong></span></a><nav aria-label="Primary"><button className={route.view === "inputs" ? "active" : ""} onClick={() => navigate("#inputs")}>Inputs</button><button className={route.view === "pipelines" ? "active" : ""} onClick={() => navigate("#pipelines")}>Pipeline</button><button className={route.view === "candidates" ? "active" : ""} onClick={() => navigate("#candidates")}>Candidates</button><button className={route.view === "collection" ? "active" : ""} onClick={() => navigate("#collection")}>Collection</button></nav></header>
    {message && <div className={`global-message ${message.kind}`} role={message.kind === "error" ? "alert" : "status"}>{message.text}<button aria-label="Dismiss message" onClick={() => setMessage(undefined)}>×</button></div>}
    {route.view === "inputs" && <InputsView {...shared} />}
    {route.view === "pipelines" && <PipelinesView {...shared} pipelineId={route.id} />}
    {route.view === "candidates" && <CandidatesView {...shared} batchId={route.id} cardId={route.itemId} />}
    {route.view === "collection" && <CollectionView {...shared} />}
    <footer className="app-footer"><span>{bootstrap.inputs.length} inputs</span><span>→</span><span>{pipelineCount} pipeline</span><span>→</span><span>{bootstrap.cards.length} candidates</span><span>→</span><span>{bootstrap.favorites.length} saved</span></footer>
  </main>;
}
