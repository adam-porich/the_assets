import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { Card, CardPreviewOption, Run } from "./types";

type StageProps = {
  cards: Card[];
  onNavigate: (hash: string) => void;
  onMessage: (message: string, kind?: "success" | "error") => void;
  onRefresh: () => Promise<void>;
};

export function FramesStage({ cards, initialCard, onNavigate, onMessage, onRefresh }: StageProps & { initialCard?: Card }) {
  const [card, setCard] = useState<Card | undefined>(initialCard);
  const [previews, setPreviews] = useState<CardPreviewOption[]>([]);
  const [sourceRun, setSourceRun] = useState<Run>();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const working = cards.filter((item) => item.decision === "working");

  useEffect(() => setCard(initialCard), [initialCard?.card_id, initialCard?.updated_at]);
  useEffect(() => {
    if (!card) { setPreviews([]); return; }
    setBusy("previews"); setError("");
    void Promise.all([api.getCardPreviews(card.card_id), api.getRun(card.run_id)])
      .then(([previewResponse, runResponse]) => { setPreviews(previewResponse.previews); setSourceRun(runResponse.run); })
      .catch((nextError) => setError((nextError as Error).message))
      .finally(() => setBusy(""));
  }, [card?.card_id]);

  async function selectPreview(option: CardPreviewOption) {
    if (!card || busy === "select") return;
    setBusy("select");
    try {
      const response = await api.updateCard(card.card_id, { preview_id: option.option_id });
      setCard(response.card); onMessage(`${option.preset_label} · ${option.treatment_label} selected`); await onRefresh();
    } catch (nextError) { onMessage((nextError as Error).message, "error"); }
    finally { setBusy(""); }
  }

  async function decide(value: "keep" | "discard") {
    if (!card) return;
    setBusy(value);
    try {
      await api.decideCard(card.card_id, value);
      await onRefresh();
      if (value === "keep") {
        onMessage("Kept as completed"); onNavigate("#completed");
      } else {
        const next = working.find((item) => item.card_id !== card.card_id);
        onMessage("Candidate marked ‘Not this one’"); onNavigate(next ? `#frames/${next.card_id}` : "#frames");
      }
    } catch (nextError) { onMessage((nextError as Error).message, "error"); }
    finally { setBusy(""); }
  }

  if (!card) return <section className="stage-page frames-page"><div className="page-heading"><div><p className="eyebrow">Stage 3 of 4</p><h2>Frame your candidates</h2><p>Working candidates sent from Styles wait here. Choose one to answer two visual questions.</p></div><button className="button secondary" onClick={() => onNavigate("#styles")}>← Back to Styles</button></div>{working.length ? <div className="candidate-grid">{working.map((item) => <article className="candidate-card" key={item.card_id}><img src={`${item.render_url}?v=${encodeURIComponent(item.updated_at)}`} alt={item.label} /><div><strong>{summary(item, "source_label") || item.label}</strong><small>{summary(item, "change_note") || "Structured style direction"}</small><button className="button primary" onClick={() => onNavigate(`#frames/${item.card_id}`)}>Choose frame →</button></div></article>)}</div> : <div className="empty-panel"><span className="empty-glyph">▱</span><h3>No working candidates</h3><p>Send a successful result from Styles. Sending the same result again reopens its existing working or kept card.</p><button className="button primary" onClick={() => onNavigate("#styles")}>Open Styles</button></div>}<div className="stage-actions"><button className="button secondary" onClick={() => onNavigate("#styles")}>← Back to Styles</button><button className="button primary" onClick={() => onNavigate("#completed")}>View Completed →</button></div></section>;

  const chosenPreset = card.archetype || "bust";
  const chosenTreatment = card.treatment || "painterly";
  const compositionOptions = (["bust", "tall", "torso"] as const).map((preset) => previews.find((item) => item.preset === preset && item.treatment === chosenTreatment)).filter(Boolean) as CardPreviewOption[];
  const treatmentOptions = previews.filter((item) => item.preset === chosenPreset);

  return <section className="stage-page frames-page"><div className="page-heading"><div><p className="eyebrow">Stage 3 of 4</p><h2>Choose the card frame</h2><p>These are exact saved renders, not approximations. Pick a composition, then its finish.</p></div><button className="button secondary" onClick={() => onNavigate("#frames")}>← Candidate list</button></div>
    {error && <div className="inline-error" role="alert">{error}</div>}
    <section className="frame-context surface"><img src={card.source_url} alt="Generated portrait before framing" /><div><p className="eyebrow">Working candidate</p><h3>{summary(card, "source_label") || card.label}</h3><p>{summary(card, "change_note") || sourceRun?.recipe_snapshot.change_note || "Structured style direction"}</p><span>{sourceRun?.recipe_name || summary(card, "recipe_name") || card.run_id}</span></div></section>
    {busy === "previews" ? <div className="loading-inline"><span className="spinner" /> Rendering six exact previews…</div> : <>
      <section className="visual-question"><div><span className="question-number">1</span><div><p className="eyebrow">Composition</p><h3>Which crop feels right?</h3></div></div><div className="preview-grid composition-grid">{compositionOptions.map((option) => <button key={option.option_id} className={chosenPreset === option.preset ? "selected" : ""} onClick={() => void selectPreview(option)} disabled={busy === "select"}><img src={option.render_url} alt={`${option.preset_label} ${option.treatment_label} card preview`} /><span><strong>{option.preset_label}</strong><small>Exact preset</small></span></button>)}</div></section>
      <section className="visual-question"><div><span className="question-number">2</span><div><p className="eyebrow">Treatment</p><h3>Which finish belongs on it?</h3></div></div><div className="preview-grid treatment-grid">{treatmentOptions.map((option) => <button key={option.option_id} className={chosenTreatment === option.treatment ? "selected" : ""} onClick={() => void selectPreview(option)} disabled={busy === "select"}><img src={option.render_url} alt={`${option.preset_label} ${option.treatment_label} card preview`} /><span><strong>{option.treatment_label}</strong><small>{option.treatment === "estate-pixel-v1" ? "32 colours · no dither" : "Original painterly render"}</small></span></button>)}</div></section>
    </>}
    <section className="selected-render surface"><div><p className="eyebrow">Chosen render</p><h3>{card.archetype[0].toUpperCase() + card.archetype.slice(1)} · {card.treatment === "estate-pixel-v1" ? "Estate Pixel" : "Painterly"}</h3><p>The saved PNG now matches the selected preview byte for byte.</p></div><img src={`${card.render_url}?v=${encodeURIComponent(card.updated_at)}`} alt="Chosen final card render" /></section>
    <details className="surface provenance-panel"><summary>Read-only provenance and numeric transform</summary><dl><dt>Run</dt><dd>{card.run_id}</dd><dt>Run item</dt><dd>{card.run_item_id}</dd><dt>Model</dt><dd>{sourceRun?.model || "—"}</dd><dt>Preset</dt><dd>{card.archetype}</dd><dt>Framing</dt><dd><code>{JSON.stringify(card.framing)}</code></dd><dt>Transform</dt><dd><code>{JSON.stringify(card.transform || {})}</code></dd><dt>Treatment version</dt><dd>{card.treatment_version}</dd><dt>Render metadata</dt><dd><code>{JSON.stringify(card.render_metadata || {})}</code></dd></dl>{sourceRun && <div className="reference-thumbs">{sourceRun.references_snapshot.map((reference) => <img key={reference.id} src={reference.input_url} alt={reference.label} title={reference.label} />)}</div>}</details>
    <div className="decision-bar"><button className="button secondary" disabled={Boolean(busy)} onClick={() => void decide("discard")}>{busy === "discard" ? "Saving…" : "Not this one"}</button><button className="button primary large" disabled={Boolean(busy) || !previews.length} onClick={() => void decide("keep")}>{busy === "keep" ? "Saving…" : "Keep as completed →"}</button></div>
  </section>;
}

export function CompletedStage({ cards, onNavigate, onMessage, onRefresh }: StageProps) {
  const kept = useMemo(() => cards.filter((card) => card.decision === "keep"), [cards]);

  async function reconsider(card: Card) {
    try {
      await api.decideCard(card.card_id, "working"); await onRefresh(); onMessage("Moved back to Frames"); onNavigate(`#frames/${card.card_id}`);
    } catch (error) { onMessage((error as Error).message, "error"); }
  }

  return <section className="stage-page completed-page"><div className="page-heading"><div><p className="eyebrow">Stage 4 of 4</p><h2>Completed cards</h2><p>Only cards you chose to keep appear here. Each PNG is the exact deterministic render from Frames.</p></div><button className="button secondary" onClick={() => onNavigate("#frames")}>← Back to Frames</button></div>{kept.length ? <div className="completed-grid">{kept.map((card) => <article className="completed-card surface" key={card.card_id}><img src={`${card.render_url}?v=${encodeURIComponent(card.updated_at)}`} alt={card.label} /><div><p className="eyebrow">Completed</p><h3>{summary(card, "source_label") || card.label}</h3><p>{summary(card, "change_note") || "Structured style direction"}</p><span>{summary(card, "recipe_name") || card.run_id} · {card.archetype} · {card.treatment === "estate-pixel-v1" ? "Estate Pixel" : "Painterly"}</span><div><a className="button primary" href={card.render_url} download={`${card.label.replace(/[^a-z0-9]+/gi, "-").toLowerCase() || card.card_id}.png`}>Download PNG</a><button className="button secondary" onClick={() => void reconsider(card)}>Reconsider in Frames</button></div></div></article>)}</div> : <div className="empty-panel"><span className="empty-glyph">✓</span><h3>Nothing completed yet</h3><p>Keep a framed candidate and its full render will appear here.</p><button className="button primary" onClick={() => onNavigate("#frames")}>Open Frames</button></div>}</section>;
}

function summary(card: Card, key: string): string {
  const value = card.source_run_provenance?.[key];
  return typeof value === "string" ? value : "";
}
