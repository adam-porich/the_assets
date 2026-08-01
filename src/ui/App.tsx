import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { CardsView, SourcesView, StyleStudio } from "./WorkbenchViews";
import type { Bootstrap } from "./types";

export type Route = { view: "sources" | "cards" | "style"; id?: string; itemId?: string };

function replaceHash(hash: string) { window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${hash}`); }

export function readRoute(): Route {
  const value = window.location.hash.replace(/^#/, "") || "sources";
  const [view, id, itemId] = value.split("/");
  if (view === "sources" || view === "cards" || view === "style") return { view: view as Route["view"], id, itemId };
  if (["explore", "finish", "set", "frames", "completed"].includes(view)) { replaceHash("#cards"); return { view: "cards" }; }
  if (view === "styles" || view === "lab") { replaceHash("#style"); return { view: "style" }; }
  if (view === "card" && id) { replaceHash(`#cards/${id}`); return { view: "cards", id }; }
  if (view === "run" && id) { replaceHash(`#cards/${id}`); return { view: "cards", id }; }
  replaceHash("#sources"); return { view: "sources" };
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
  return <main className="app-shell"><header className="app-header"><a className="brand-block" href="#sources"><span className="brand-symbol">✳</span><span><small>Experimental asset studio</small><strong>Portrait Workbench</strong></span></a><div className="header-tools"><nav aria-label="Primary"><button className={route.view === "sources" ? "active" : ""} onClick={() => navigate("#sources")}>Sources</button><button className={route.view === "cards" ? "active" : ""} onClick={() => navigate("#cards")}>Cards</button></nav><button className="style-chip" onClick={() => navigate("#style")}><span>{bootstrap.style.active.identity.label}</span><small>active · v{bootstrap.style.active.identity.version}</small></button></div></header>{message && <div className={`global-message ${message.kind}`} role={message.kind === "error" ? "alert" : "status"}>{message.text}<button aria-label="Dismiss message" onClick={() => setMessage(undefined)}>×</button></div>}{route.view === "sources" && <SourcesView {...shared} />}{route.view === "cards" && <CardsView {...shared} batchId={route.id} cardId={route.itemId} />}{route.view === "style" && <StyleStudio {...shared} />}<footer className="app-footer"><span>{bootstrap.sources.length} source images</span><span>·</span><span>{bootstrap.style.active.identity.label} · checksum {bootstrap.style.active.checksums.style_sha256.slice(0, 10)}</span></footer></main>;
}
