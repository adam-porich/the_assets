import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { calculateCoverTransform } from "./framing";
import type { Card, Run, Workspace } from "./types";

const presets = {
  bust: { zoom: 1, offset_x: 0, offset_y: 0.02 },
  tall: { zoom: 1.16, offset_x: 0, offset_y: -0.06 },
  torso: { zoom: 1.28, offset_x: 0, offset_y: 0.08 },
} as const;

export function CardGallery({ cards, newestCompletedRunId, onNavigate, onRefresh }: { cards: Card[]; newestCompletedRunId?: string; onNavigate: (hash: string) => void; onRefresh: () => Promise<void> }) {
  const [includeDiscarded, setIncludeDiscarded] = useState(false);
  const [allCards, setAllCards] = useState(cards);
  useEffect(() => setAllCards(cards), [cards]);
  useEffect(() => {
    if (includeDiscarded) void api.listCards(true).then((body) => setAllCards(body.cards)).catch(() => setAllCards(cards));
    else setAllCards(cards);
  }, [includeDiscarded, cards]);
  return <section className="gallery-view">
    <div className="page-heading"><div><p className="eyebrow">Saved explorations</p><h2>Card drafts</h2><p className="muted">Reopen a frame with its treatment and trace it to the immutable painterly run source.</p></div><label className="toggle"><input type="checkbox" checked={includeDiscarded} onChange={(event) => setIncludeDiscarded(event.target.checked)} /> Show discarded</label></div>
    {allCards.length === 0 ? <div className="empty-panel large-empty"><div className="empty-glyph">◇</div><h3>No card drafts yet</h3><p>Choose a completed run result, then use its visible “Frame this portrait” action.</p>{newestCompletedRunId ? <button className="button primary" onClick={() => onNavigate(`#run/${newestCompletedRunId}`)}>Open newest completed run</button> : <button className="button primary" onClick={() => onNavigate("#lab")}>Set up a run in Style Lab</button>}</div> : <div className="gallery-grid">{allCards.map((card) => <article className="draft-card" key={card.card_id} onClick={() => onNavigate(`#card/${card.card_id}`)}><div className="draft-image"><img src={`${card.render_url}?v=${encodeURIComponent(card.updated_at)}`} alt={card.label} /><span className={`decision-badge ${card.decision}`}>{card.decision}</span></div><div className="draft-meta"><strong>{card.label}</strong><span>{card.archetype} · {card.treatment === "estate-pixel-v1" ? "Estate Pixel" : "Painterly"} · zoom {card.framing.zoom.toFixed(2)}</span><small>Updated {new Date(card.updated_at).toLocaleDateString()}</small></div></article>)}</div>}
    <button className="button secondary refresh-gallery" onClick={() => onRefresh()}>Refresh drafts</button>
  </section>;
}

export function CardWorkbench({ card: initialCard, onNavigate, onMessage }: { card: Card; workspace: Workspace; onNavigate: (hash: string) => void; onMessage: (message: string, kind?: "success" | "error") => void; onRefresh: () => Promise<void> }) {
  const [card, setCard] = useState(initialCard);
  const [frame, setFrame] = useState(initialCard.framing);
  const [saving, setSaving] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [interactivePreview, setInteractivePreview] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [sourceRun, setSourceRun] = useState<Run>();
  const drag = useRef<{ x: number; y: number; frame: typeof frame } | undefined>(undefined);
  const saveTimer = useRef<number | undefined>(undefined);
  useEffect(() => { setCard(initialCard); setFrame(initialCard.framing); }, [initialCard]);
  useEffect(() => { if (showDetails) void api.getRun(card.run_id).then((response) => setSourceRun(response.run)).catch(() => undefined); }, [showDetails, card.run_id]);
  useEffect(() => () => { if (saveTimer.current) window.clearTimeout(saveTimer.current); }, []);

  function scheduleSave(next: typeof frame, archetype = card.archetype) {
    setSaving("saving");
    setInteractivePreview(true);
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(async () => {
      try {
        const response = await api.updateCard(card.card_id, { framing: next, archetype });
        setCard(response.card);
        setFrame(response.card.framing);
        setSaving("saved");
        setInteractivePreview(false);
      } catch (error) {
        setSaving("error");
        onMessage((error as Error).message, "error");
      }
    }, 280);
  }
  function updateFrame(next: typeof frame, persist = true, archetype = card.archetype) {
    const clamped = { zoom: Math.max(1, Math.min(3, next.zoom)), offset_x: Math.max(-0.8, Math.min(0.8, next.offset_x)), offset_y: Math.max(-0.8, Math.min(0.8, next.offset_y)) };
    setFrame(clamped);
    setInteractivePreview(true);
    if (persist) scheduleSave(clamped, archetype);
  }
  function applyPreset(name: keyof typeof presets) {
    setCard((current) => ({ ...current, archetype: name }));
    updateFrame(presets[name], true, name);
  }
  function nudge(axis: "offset_x" | "offset_y", amount: number) {
    updateFrame({ ...frame, [axis]: frame[axis] + amount });
  }
  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, y: event.clientY, frame };
    setInteractivePreview(true);
  }
  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    updateFrame({ ...drag.current.frame, offset_x: drag.current.frame.offset_x + (event.clientX - drag.current.x) / bounds.width, offset_y: drag.current.frame.offset_y + (event.clientY - drag.current.y) / bounds.height });
  }
  function onPointerUp() {
    drag.current = undefined;
    scheduleSave(frame);
  }
  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const amount = event.shiftKey ? 0.04 : event.altKey ? 0.002 : 0.012;
    if (event.key === "ArrowLeft") { event.preventDefault(); nudge("offset_x", -amount); }
    if (event.key === "ArrowRight") { event.preventDefault(); nudge("offset_x", amount); }
    if (event.key === "ArrowUp") { event.preventDefault(); nudge("offset_y", -amount); }
    if (event.key === "ArrowDown") { event.preventDefault(); nudge("offset_y", amount); }
  }
  async function editLabel(value: string) {
    setCard((current) => ({ ...current, label: value }));
    try { const response = await api.updateCard(card.card_id, { label: value }); setCard(response.card); setSaving("saved"); } catch (error) { onMessage((error as Error).message, "error"); }
  }
  async function changeTreatment(treatment: Card["treatment"]) {
    if (treatment === card.treatment) return;
    setSaving("saving");
    try {
      const response = await api.updateCard(card.card_id, { treatment, framing: frame });
      setCard(response.card);
      setFrame(response.card.framing);
      setSaving("saved");
      setInteractivePreview(false);
      onMessage(treatment === "estate-pixel-v1" ? "Estate Pixel treatment applied after framing" : "Painterly source treatment restored", "success");
    } catch (error) {
      setSaving("error");
      onMessage((error as Error).message, "error");
    }
  }
  async function decision(value: "keep" | "discard") {
    try {
      const response = await api.decideCard(card.card_id, value);
      setCard(response.card);
      onMessage(value === "keep" ? "Card kept with framing, treatment, and provenance" : "Card marked discarded", "success");
    } catch (error) { onMessage((error as Error).message, "error"); }
  }

  const transform = calculateCoverTransform(card.source_dimensions || [336, 276], [336, 276], frame);
  const imageStyle = { width: `${(transform.scaled_width / 336) * 100}%`, height: `${(transform.scaled_height / 276) * 100}%`, left: `${(transform.left / 336) * 100}%`, top: `${(transform.top / 276) * 100}%`, objectFit: "fill" as const };
  return <section className="card-workbench-view">
    <div className="workbench-top"><button className="back-link" onClick={() => onNavigate(`#run/${card.run_id}`)}>← Try another result</button><div><p className="eyebrow">Card Workbench</p><h2>Frame and treat one result</h2><p className="muted">Painterly generation stays immutable. Framing and the selected post-frame treatment belong to this draft.</p></div><button className="button secondary" onClick={() => setShowDetails((value) => !value)}>{showDetails ? "Hide details" : "Details"}</button></div>
    <div className="card-workbench-layout"><div className="live-card-column"><div className="live-card-shell"><div className="live-card-heading">{card.label}</div><div className={`live-art-window ${card.treatment}`} tabIndex={0} role="application" aria-label="Portrait framing surface. Use arrow keys to nudge." onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onKeyDown={onKeyDown}>{interactivePreview || !card.art_url ? <img src={card.source_url} alt="Selected immutable run output" style={imageStyle} /> : <img className="treated-art" src={`${card.art_url}?v=${encodeURIComponent(card.updated_at)}`} alt={`${card.treatment === "estate-pixel-v1" ? "Estate Pixel" : "Painterly"} framed preview`} />}<span className="center-line horizontal" /><span className="center-line vertical" /></div><div className="live-card-copy"><strong>Experimental card-context preview</strong><span>336 × 276 art window · {card.treatment === "estate-pixel-v1" ? "112 × 92 logical, 3× nearest" : "painterly source"}</span></div></div><div className="save-state" role="status"><span className={`save-dot ${saving}`} />{saving === "saving" ? "Rendering exact preview…" : saving === "error" ? "Could not save" : saving === "saved" ? "Saved · preview matches Pillow render" : "Ready"}</div><p className="keyboard-help">Focus the art window. Arrow keys nudge · Alt = fine · Shift = large.</p></div>
      <aside className="frame-controls surface"><p className="eyebrow">Visible framing</p><h3>Choose a starting frame</h3><div className="preset-buttons">{(Object.keys(presets) as Array<keyof typeof presets>).map((name) => <button key={name} className={card.archetype === name ? "selected" : ""} onClick={() => applyPreset(name)}>{name[0].toUpperCase() + name.slice(1)}<small>{presets[name].zoom.toFixed(2)}× start</small></button>)}</div><label className="field-label zoom-field">Zoom <output>{frame.zoom.toFixed(2)}×</output><input type="range" min="1" max="3" step="0.01" value={frame.zoom} onChange={(event) => updateFrame({ ...frame, zoom: Number(event.target.value) })} /></label><div className="nudge-grid"><button onClick={() => nudge("offset_y", -0.012)} aria-label="Nudge up">↑</button><button onClick={() => nudge("offset_y", 0.012)} aria-label="Nudge down">↓</button><button onClick={() => nudge("offset_x", -0.012)} aria-label="Nudge left">←</button><button onClick={() => nudge("offset_x", 0.012)} aria-label="Nudge right">→</button></div><button className="button secondary full-width" onClick={() => applyPreset("bust")}>Reset to Bust</button><div className="treatment-control"><span className="field-label">Art treatment</span><div className="mode-switch compact" role="group" aria-label="Art treatment"><button className={card.treatment === "painterly" ? "selected" : ""} onClick={() => changeTreatment("painterly")}>Painterly<small>Immutable source crop</small></button><button className={card.treatment === "estate-pixel-v1" ? "selected" : ""} onClick={() => changeTreatment("estate-pixel-v1")}>Estate Pixel<small>32 colours · no dither</small></button></div></div><label className="field-label">Card label<input value={card.label} onChange={(event) => editLabel(event.target.value)} /></label><div className="decision-actions"><button className={`button ${card.decision === "keep" ? "keep-active" : "primary"}`} onClick={() => decision("keep")}>Keep card</button><button className={`button ${card.decision === "discard" ? "discard-active" : "secondary"}`} onClick={() => decision("discard")}>Discard</button></div><button className="button secondary full-width" onClick={() => onNavigate(`#run/${card.run_id}`)}>Try another result</button></aside>
    </div>
    {showDetails && <CardDetails card={card} run={sourceRun} onNavigate={onNavigate} />}
  </section>;
}

function CardDetails({ card, run, onNavigate }: { card: Card; run?: Run; onNavigate: (hash: string) => void }) {
  return <aside className="details-panel surface"><div><p className="eyebrow">Traceable provenance</p><h3>Source, framing, and render details</h3></div><dl><dt>Run</dt><dd><button className="text-button" onClick={() => onNavigate(`#run/${card.run_id}`)}>{run?.recipe_snapshot.name || card.run_id}</button></dd><dt>Run item</dt><dd>{card.run_item_id}</dd><dt>Execution</dt><dd>{run?.execution_mode || "—"}</dd><dt>Model</dt><dd>{run?.model || "—"}</dd><dt>Reference pack</dt><dd>{run ? `${run.references_snapshot.length} ordered references` : "Loading…"}</dd><dt>Treatment</dt><dd>{card.treatment_version}</dd><dt>Source dimensions</dt><dd>{card.source_dimensions?.join(" × ") || "—"}</dd><dt>Framing transform</dt><dd><code>{JSON.stringify(card.framing)}</code></dd><dt>Render metadata</dt><dd><code>{JSON.stringify(card.render_metadata || {})}</code></dd></dl>{run && <div className="reference-thumbs">{run.references_snapshot.map((reference) => <img key={reference.id} src={reference.input_url} alt={reference.label} title={reference.label} />)}</div>}<p className="muted">Keep and reopen preserve the run source, frame, treatment version, and rendered output.</p></aside>;
}
