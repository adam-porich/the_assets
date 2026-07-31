import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type ReviewStatus = "favorite" | "reject" | "add";

type Review = { status?: ReviewStatus; note?: string };

type Candidate = {
  candidate_id: string;
  preset?: string;
  backend?: string;
  model?: string;
  prompt?: string;
  created_at?: string;
  seed?: number;
  strength?: number;
  steps?: number;
  guidance?: number;
  elapsed_seconds?: number;
  background_mode?: string;
  mask_mode?: string;
  disk_only?: boolean;
  raw_url?: string;
  final_url?: string;
  review?: Review;
};

type Source = {
  photo_id: string;
  photographer?: string;
  photo_page_url?: string;
  query?: string;
  dimensions?: [number, number];
  processing_status?: string;
  review?: Review;
  selected?: { variant?: string; tags?: string[] };
  source_url?: string;
  prepared_url?: string;
  mask_url?: string;
  foreground_url?: string;
  composite_url?: string;
  candidates: Candidate[];
  all_outputs: Candidate[];
};

type LibraryPayload = { sources: Source[] };

type StyleEntry = {
  id: string;
  prompt: string;
  model: string;
  created_at: string;
  filename: string;
  url: string;
};

type GenerationEntry = {
  candidate_id: string;
  source: { photo_id: string; photographer?: string; query?: string };
  model?: string;
  preset?: string;
  prompt?: string;
  seed?: number;
  review?: Review;
  raw_url?: string;
  final_url?: string;
  source_url?: string;
};

type CardEntry = {
  card_id: string;
  master_id: string;
  template_id: string;
  template_version: number;
  archetype_id: string;
  label: string;
  card_url?: string;
  master_url?: string;
  review?: { status?: "approved" | "keep" | "reject"; note?: string };
};

type PortraitComposition = {
  face_anchor?: [number, number];
  preferred_archetype?: string;
  head_box?: number[];
  shoulder_line?: number;
  silhouette_box?: number[];
};

type MasterEntry = {
  master_id: string;
  source_photo_id: number;
  candidate_id: string;
  style_id: string;
  style_version: number;
  master_url?: string;
  composition?: PortraitComposition;
  renders: CardEntry[];
};

type TemplateEntry = {
  id: string;
  version: number;
  width: number;
  height: number;
  archetypes: Record<string, { label?: string }>;
};

type ValidationReport = {
  card_count: number;
  ok: boolean;
  issues: { level: "error" | "warning"; message: string; card_id?: string }[];
};

type PresetEntry = {
  name: string;
  prompt: string;
  negative_prompt: string;
  strength?: number;
  steps?: number;
};

const appBase = import.meta.env.BASE_URL;
const apiPath = (p: string) => `${appBase}${p.replace(/^\//, "")}`;

const defaultModel = "openai/gpt-image-1-mini";
const defaultPreset = "estate-pixel-claimant-v1";
const DEFAULT_STYLE_PROMPT = "Magic the Gathering card art, fantasy illustration, detailed character portrait, painterly style, dramatic lighting, rich colors, high quality";

const FALLBACK_MODELS = [
  "openai/gpt-image-1-mini", "google/gemini-3.1-flash-lite-image",
  "google/gemini-3.1-flash-image", "black-forest-labs/flux.2-klein-4b",
  "sourceful/riverflow-v2-fast",
];

const COST_TIERS: Record<string, string> = {
  "openai/gpt-image-1-mini": "$", "google/gemini-3.1-flash-lite-image": "$",
  "google/gemini-3.1-flash-image": "$$", "black-forest-labs/flux.2-klein-4b": "$",
  "sourceful/riverflow-v2-fast": "$",
};
function costTier(id: string) { return COST_TIERS[id] ?? "?"; }

type Tab = "source" | "style" | "prompt" | "generations" | "cards";

function statusOf(review?: Review): ReviewStatus | "unreviewed" {
  return review?.status ? review.status : "unreviewed";
}

async function postJson(path: string, body: unknown) {
  const res = await fetch(apiPath(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) {
    if (res.status === 404 && ["/api/promote-master", "/api/master-composition", "/api/render-card", "/api/validate-cards"].includes(path)) {
      throw new Error("The portrait review server is out of date. Restart `uv run python -m tools.portraits review-server`, then refresh this page.");
    }
    throw new Error(await res.text());
  }
  return res.json();
}

/* ── candidate detail modal ── */

function CandidateDetail({ candidate, onClose }: { candidate: Candidate; onClose: () => void }) {
  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-modal" onClick={(e) => e.stopPropagation()}>
        <button className="detail-close" onClick={onClose}>×</button>
        <h2>{candidate.candidate_id}</h2>
        <div className="detail-images">
          <figure className="detail-figure">
            {candidate.raw_url ? <img src={candidate.raw_url} alt="Raw" /> : <div className="missing">No raw</div>}
            <figcaption>Raw generated</figcaption>
          </figure>
          <figure className="detail-figure">
            {candidate.final_url ? <img src={candidate.final_url} alt="Final" /> : <div className="missing">No final</div>}
            <figcaption>Final (down-res)</figcaption>
          </figure>
        </div>
        <div className="detail-meta">
          <h3>Generation details</h3>
          <dl>
            <dt>Preset</dt><dd>{candidate.preset ?? "unknown"}</dd>
            <dt>Backend</dt><dd>{candidate.backend ?? "unknown"}</dd>
            <dt>Model</dt><dd>{candidate.model ?? "unknown"}</dd>
            <dt>Seed</dt><dd>{candidate.seed ?? "unknown"}</dd>
            <dt>Strength</dt><dd>{candidate.strength ?? "unknown"}</dd>
            <dt>Steps</dt><dd>{candidate.steps ?? "unknown"}</dd>
            <dt>Guidance</dt><dd>{candidate.guidance ?? "unknown"}</dd>
            <dt>Elapsed</dt><dd>{candidate.elapsed_seconds != null ? `${candidate.elapsed_seconds}s` : "unknown"}</dd>
            <dt>Background</dt><dd>{candidate.background_mode ?? "unknown"}</dd>
            <dt>Mask mode</dt><dd>{candidate.mask_mode ?? "unknown"}</dd>
            {candidate.disk_only && <><dt>Source</dt><dd>disk output</dd></>}
          </dl>
        </div>
      </div>
    </div>
  );
}

/* ── main app ── */

export function App() {
  const [tab, setTab] = useState<Tab>("source");
  const [library, setLibrary] = useState<LibraryPayload>({ sources: [] });
  const [activeId, setActiveId] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();
  const [actionError, setActionError] = useState<string | undefined>();

  // source tab
  const [pexelsQuery, setPexelsQuery] = useState("");
  const [pexelsCount, setPexelsCount] = useState(5);
  const [fetching, setFetching] = useState(false);

  // img2img
  const [model, setModel] = useState(defaultModel);
  const [preset, setPreset] = useState(defaultPreset);
  const [styleRefUrl, setStyleRefUrl] = useState("");
  const [modelOptions, setModelOptions] = useState<string[]>(FALLBACK_MODELS);
  const [generatingSince, setGeneratingSince] = useState<number | null>(null);
  const [genElapsed, setGenElapsed] = useState(0);
  const [generatingModel, setGeneratingModel] = useState<string | null>(null);

  // style tab
  const [stylePrompt, setStylePrompt] = useState(DEFAULT_STYLE_PROMPT);
  const [styleModel, setStyleModel] = useState(defaultModel);
  const [styles, setStyles] = useState<StyleEntry[]>([]);
  const [styleGeneratingSince, setStyleGeneratingSince] = useState<number | null>(null);
  const [styleGenElapsed, setStyleGenElapsed] = useState(0);

  // prompt tab
  const [presets, setPresets] = useState<PresetEntry[]>([]);

  // generations tab
  const [generations, setGenerations] = useState<GenerationEntry[]>([]);
  const [genDetail, setGenDetail] = useState<Candidate | null>(null);
  const [cards, setCards] = useState<CardEntry[]>([]);
  const [masters, setMasters] = useState<MasterEntry[]>([]);
  const [templates, setTemplates] = useState<TemplateEntry[]>([]);
  const [selectedMasterId, setSelectedMasterId] = useState<string | undefined>();
  const [templateId, setTemplateId] = useState("estate-card-v1");
  const [archetypeId, setArchetypeId] = useState("standard-bust");
  const [cardLabel, setCardLabel] = useState("Experimental claimant");
  const [anchorX, setAnchorX] = useState("0.5");
  const [anchorY, setAnchorY] = useState("0.35");
  const [masterArchetype, setMasterArchetype] = useState("standard-bust");
  const [validation, setValidation] = useState<ValidationReport | null>(null);

  // trash
  const [trashedSources, setTrashedSources] = useState<Set<string>>(new Set());
  const [trashedCandidates, setTrashedCandidates] = useState<Set<string>>(new Set());
  const loadedRef = useRef(false);

  const load = useCallback(async () => {
    try {
      const [libRes, modelsRes, stylesRes, presetsRes, gensRes, cardsRes, mastersRes, templatesRes] = await Promise.all([
        fetch(apiPath("/api/library")),
        fetch(apiPath("/api/models/img2img")).catch(() => null),
        fetch(apiPath("/api/styles")).catch(() => null),
        fetch(apiPath("/api/presets")).catch(() => null),
        fetch(apiPath("/api/generations")).catch(() => null),
        fetch(apiPath("/api/cards")).catch(() => null),
        fetch(apiPath("/api/masters")).catch(() => null),
        fetch(apiPath("/api/card-templates")).catch(() => null),
      ]);
      if (!libRes.ok) throw new Error(await libRes.text());
      const payload = (await libRes.json()) as LibraryPayload;
      setLibrary(payload);
      if (modelsRes?.ok) {
        const mp = await modelsRes.json();
        if (mp.ok && mp.models?.length) setModelOptions(mp.models.map((m: { id: string }) => m.id));
      }
      if (stylesRes?.ok) {
        const sp = await stylesRes.json();
        if (sp.styles) setStyles(sp.styles);
      }
      if (presetsRes?.ok) {
        const pp = await presetsRes.json();
        if (pp.presets) setPresets(pp.presets);
      }
      if (gensRes?.ok) {
        const gp = await gensRes.json();
        if (gp.generations) setGenerations(gp.generations);
      }
      if (cardsRes?.ok) {
        const cp = await cardsRes.json();
        if (cp.cards) setCards(cp.cards);
      }
      if (mastersRes?.ok) {
        const mp = await mastersRes.json();
        if (mp.masters) setMasters(mp.masters);
      }
      if (templatesRes?.ok) {
        const tp = await templatesRes.json();
        if (tp.templates) setTemplates(tp.templates);
      }
      if (!loadedRef.current) {
        setActiveId(payload.sources[0]?.photo_id);
        const src = payload.sources.find((s) => s.photo_id === payload.sources[0]?.photo_id);
        if (!pexelsQuery && src?.query) setPexelsQuery(src.query);
        loadedRef.current = true;
      }
      setError(undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [pexelsQuery]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (selectedMasterId || masters.length === 0) return;
    chooseMaster(masters[0]);
  }, [masters, selectedMasterId]);

  useEffect(() => {
    if (generatingSince === null) { setGenElapsed(0); return; }
    const tick = () => setGenElapsed(Math.floor((Date.now() - generatingSince) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [generatingSince]);

  useEffect(() => {
    if (styleGeneratingSince === null) { setStyleGenElapsed(0); return; }
    const tick = () => setStyleGenElapsed(Math.floor((Date.now() - styleGeneratingSince) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [styleGeneratingSince]);

  const activeSource = library.sources.find((s) => s.photo_id === activeId) ?? library.sources[0];
  const visibleSources = useMemo(() =>
    library.sources
      .filter((s) => !trashedSources.has(s.photo_id))
      .sort((a, b) => Number(b.photo_id) - Number(a.photo_id)),
    [library.sources, trashedSources]);
  const candidates = useMemo(() => {
    if (!activeSource) return [];
    return activeSource.candidates
      .filter((c) => !trashedCandidates.has(c.candidate_id))
      .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
  }, [activeSource, trashedCandidates]);
  const selectedMaster = masters.find((master) => master.master_id === selectedMasterId) ?? masters[0];
  const selectedTemplate = templates.find((template) => template.id === templateId) ?? templates[0];

  async function fetchPexels() {
    if (!pexelsQuery) return;
    setFetching(true); setActionError(undefined);
    try {
      const r = await postJson("/api/fetch-pexels", { query: pexelsQuery, count: pexelsCount });
      setLibrary(r.library);
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
    finally { setFetching(false); }
  }

  async function generateImg2Img() {
    if (!activeSource) return;
    setGeneratingSince(Date.now()); setGeneratingModel(model); setActionError(undefined);
    try {
      const r = await postJson("/api/generate", { photo_id: activeSource.photo_id, preset, model, style_reference_url: styleRefUrl || undefined });
      setLibrary(r.library);
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
    finally { setGeneratingSince(null); setGeneratingModel(null); }
  }

  async function generateStyle() {
    if (!stylePrompt) return;
    setStyleGeneratingSince(Date.now()); setActionError(undefined);
    try {
      const r = await postJson("/api/generate-style", { prompt: stylePrompt, model: styleModel, count: 1 });
      if (r.styles) setStyles(r.styles);
      if (r.all) setStyles(r.all);
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
    finally { setStyleGeneratingSince(null); }
  }

  async function favoriteCandidate(c: Candidate) {
    if (!activeSource) return;
    setActionError(undefined);
    try { await postJson("/api/favorite-candidate", { photo_id: activeSource.photo_id, candidate_id: c.candidate_id }); await load(); }
    catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }
  async function promoteCandidate(c: Candidate) {
    if (!activeSource) return;
    const fallback = `claimant-${activeSource.photo_id}-${c.seed ?? "candidate"}`;
    const masterId = window.prompt("Portrait master ID", fallback);
    if (!masterId) return;
    setActionError(undefined);
    try {
      const promoted = await postJson("/api/promote-master", {
        photo_id: activeSource.photo_id,
        candidate_id: c.candidate_id,
        master_id: masterId,
      });
      await postJson("/api/render-card", { master_id: promoted.master.master_id });
      await load();
      setTab("cards");
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }
  async function trashCandidate(c: Candidate) {
    if (statusOf(c.review) === "favorite") return;
    setTrashedCandidates((p) => new Set(p).add(c.candidate_id)); setActionError(undefined);
    try { await postJson("/api/review", { collection: "candidates", id: c.candidate_id, status: "reject" }); }
    catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }
  async function favoriteSource(s: Source) {
    setActionError(undefined);
    try { await postJson("/api/review", { collection: "sources", id: s.photo_id, status: "favorite" }); await load(); }
    catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }
  async function trashSource(s: Source) {
    if (statusOf(s.review) === "favorite") return;
    setTrashedSources((p) => new Set(p).add(s.photo_id));
    if (activeId === s.photo_id) { const rem = visibleSources.filter((x) => x.photo_id !== s.photo_id); setActiveId(rem[0]?.photo_id); }
    setActionError(undefined);
    try { await postJson("/api/review", { collection: "sources", id: s.photo_id, status: "reject" }); }
    catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }
  async function reviewCard(card: CardEntry, status: "approved" | "reject") {
    setActionError(undefined);
    try {
      await postJson("/api/review", { collection: "cards", id: card.card_id, status });
      await load();
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }
  function chooseMaster(master: MasterEntry) {
    setSelectedMasterId(master.master_id);
    const [x, y] = master.composition?.face_anchor ?? [0.5, 0.35];
    setAnchorX(String(x)); setAnchorY(String(y));
    setMasterArchetype(master.composition?.preferred_archetype ?? "standard-bust");
    setArchetypeId(master.composition?.preferred_archetype ?? "standard-bust");
    setCardLabel(master.master_id.replace(/[-_]/g, " "));
  }
  async function saveMasterComposition() {
    if (!selectedMaster) return;
    setActionError(undefined);
    try {
      await postJson("/api/master-composition", {
        master_id: selectedMaster.master_id,
        composition: {
          ...selectedMaster.composition,
          face_anchor: [Number(anchorX), Number(anchorY)],
          preferred_archetype: masterArchetype,
        },
      });
      await load();
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }
  async function renderSelectedCard() {
    if (!selectedMaster || !selectedTemplate) return;
    setActionError(undefined);
    try {
      await postJson("/api/render-card", {
        master_id: selectedMaster.master_id,
        template_id: selectedTemplate.id,
        archetype_id: archetypeId,
        label: cardLabel,
      });
      await load();
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }
  async function validateBatch() {
    setActionError(undefined);
    try {
      const result = await postJson("/api/validate-cards", {});
      setValidation(result.report);
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }

  const TABS: { key: Tab; label: string }[] = [
    { key: "source", label: "Source" },
    { key: "style", label: "Style" },
    { key: "prompt", label: "Prompt" },
    { key: "generations", label: "Generations" },
    { key: "cards", label: "Cards" },
  ];

  return (
    <main>
      <header className="topbar">
        <div className="topbar-row">
          <h1>Portrait Review</h1>
          <button className="refresh-btn" onClick={() => void load()}>Refresh</button>
        </div>
        <nav className="tab-bar">
          {TABS.map((t) => (
            <button key={t.key} className={`tab-btn ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </nav>
        {error && <div className="error">{error}</div>}
        {actionError && <div className="error inline-error">{actionError}</div>}
      </header>

      {/* ── SOURCE TAB ── */}
      {tab === "source" && (
        <div className="tab-content">
          <div className="source-top">
            <nav className="source-picker">
              {visibleSources.map((s) => {
                const st = statusOf(s.review); const isActive = s.photo_id === activeSource?.photo_id;
                const isFav = st === "favorite"; const img = s.prepared_url ?? s.source_url;
                return (
                  <article key={s.photo_id} className={`source-card ${isActive ? "active" : ""} status-${st}`}>
                    <div className="source-card-image" onClick={() => setActiveId(s.photo_id)}>
                      {img ? <img src={img} alt={`#${s.photo_id}`} /> : <div className="missing">?</div>}
                    </div>
                    <div className="source-card-overlay">
                      <span className="source-card-label">#{s.photo_id}</span>
                      {st !== "unreviewed" && <span className={`badge badge-${st}`}>{st}</span>}
                      {isActive && <span className="badge badge-selected">active</span>}
                    </div>
                    <div className="source-card-actions">
                      <button className={`action-btn fav-btn ${isFav ? "active" : ""}`} onClick={(e) => { e.stopPropagation(); favoriteSource(s); }} title="Favorite">♥</button>
                      {!isFav && <button className="action-btn trash-btn" onClick={(e) => { e.stopPropagation(); trashSource(s); }} title="Trash">🗑</button>}
                    </div>
                  </article>
                );
              })}
            </nav>
            <aside className="sidebar-panel pexels-panel">
              <h2>🔍 Pexels Search</h2>
              <label>Query<input value={pexelsQuery} onChange={(e) => setPexelsQuery(e.target.value)} placeholder="e.g. vintage portrait" /></label>
              <label>Count<select value={pexelsCount} onChange={(e) => setPexelsCount(Number(e.target.value))}>{[3,5,7,10].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
              <button className="generate-btn" onClick={fetchPexels} disabled={fetching}>{fetching ? "Fetching..." : "Fetch Images"}</button>
            </aside>
          </div>

          {activeSource && (
            <>
              <section className="candidates-area">
                <div className="candidates-header"><h2>Candidates for #{activeSource.photo_id}</h2><span className="candidate-count">{candidates.length} generated</span></div>
                {candidates.length === 0 && generatingSince === null ? (
                  <p className="empty">No candidates yet.</p>
                ) : (
                  <div className="candidates-grid">
                    {generatingSince !== null && (
                      <article className="candidate-card generating">
                        <div className="card-image"><div className="generating-placeholder"><div className="spinner" /><span className="gen-label">Generating...</span><span className="gen-elapsed">{genElapsed}s</span>{generatingModel && <span className="gen-model">{generatingModel}</span>}</div></div>
                      </article>
                    )}
                    {candidates.map((c) => {
                      const st = statusOf(c.review); const isFav = st === "favorite";
                      const isSel = activeSource.selected?.variant === c.candidate_id;
                      return (
                        <article key={c.candidate_id} className={`candidate-card status-${st} ${isSel ? "selected" : ""}`}>
                          <div className="card-image" onClick={() => setGenDetail(c)} title="Click for details">
                            {(c.raw_url ?? c.final_url) ? <img src={c.raw_url ?? c.final_url} alt={c.candidate_id} /> : <div className="missing">?</div>}
                          </div>
                          <div className="card-overlay">
                            <span className="card-model">{c.model ?? "?"}</span>
                            {c.prompt && <span className="card-prompt" title={c.prompt}>{c.prompt}</span>}
                            {isSel && <span className="badge badge-selected">selected</span>}
                            {st !== "unreviewed" && <span className={`badge badge-${st}`}>{st}</span>}
                          </div>
                          <div className="card-actions">
                            <button className="action-btn" onClick={(e) => { e.stopPropagation(); promoteCandidate(c); }} title="Promote to portrait master and render a card preview">♜</button>
                            <button className={`action-btn fav-btn ${isFav ? "active" : ""}`} onClick={(e) => { e.stopPropagation(); favoriteCandidate(c); }} title="Favorite">♥</button>
                            {!isFav && <button className="action-btn trash-btn" onClick={(e) => { e.stopPropagation(); trashCandidate(c); }} title="Trash">🗑</button>}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                )}
              </section>
              <footer className="bottom-panels">
                <aside className="sidebar-panel">
                  <h2>⚡ img2img</h2>
                  <label>Model<select value={model} onChange={(e) => setModel(e.target.value)}>{modelOptions.map((o) => <option key={o} value={o}>{costTier(o)} {o}</option>)}</select></label>
                  <label>Preset<select value={preset} onChange={(e) => setPreset(e.target.value)}><option value="estate-pixel-claimant-v1">estate-pixel-claimant-v1</option></select></label>
                  <label>Style ref<select value={styleRefUrl} onChange={(e) => setStyleRefUrl(e.target.value)}><option value="">— none —</option>{styles.map((s) => (<option key={s.id} value={apiPath(`/asset/portrait-review/styles/${s.filename}`)}>{s.prompt.slice(0, 60)}...</option>))}</select></label>
                  <button className="generate-btn" onClick={generateImg2Img} disabled={generatingSince !== null}>{generatingSince !== null ? `Generating... ${genElapsed}s` : "Generate Image"}</button>
                </aside>
                <aside className="sidebar-panel source-info">
                  <h3>Source #{activeSource.photo_id}</h3>
                  {activeSource.photographer && <p>By {activeSource.photographer}</p>}
                  {activeSource.dimensions && <p>{activeSource.dimensions[0]} × {activeSource.dimensions[1]}</p>}
                  {activeSource.photo_page_url && <a href={activeSource.photo_page_url} target="_blank" rel="noreferrer">Pexels page ↗</a>}
                  {activeSource.query && <p className="source-query">{activeSource.query}</p>}
                </aside>
              </footer>
            </>
          )}
        </div>
      )}

      {/* ── STYLE TAB ── */}
      {tab === "style" && (
        <div className="tab-content">
          <aside className="sidebar-panel style-gen-panel">
            <h2>🎨 Generate Style Reference</h2>
            <p className="panel-desc">Create a style template image to use as a reference in img2img.</p>
            <label>Prompt<textarea value={stylePrompt} onChange={(e) => setStylePrompt(e.target.value)} rows={3} /></label>
            <label>Model<select value={styleModel} onChange={(e) => setStyleModel(e.target.value)}>{modelOptions.map((o) => <option key={o} value={o}>{costTier(o)} {o}</option>)}</select></label>
            <button className="generate-btn" onClick={generateStyle} disabled={styleGeneratingSince !== null}>{styleGeneratingSince !== null ? `Generating... ${styleGenElapsed}s` : "Generate Style"}</button>
          </aside>
          <section className="styles-grid">
            <h2>Style references ({styles.length})</h2>
            {styles.length === 0 && styleGeneratingSince === null ? <p className="empty">No style references yet.</p> : (
              <div className="candidates-grid">
                {styleGeneratingSince !== null && (
                  <article className="candidate-card generating">
                    <div className="card-image"><div className="generating-placeholder"><div className="spinner" /><span className="gen-label">Generating style...</span><span className="gen-elapsed">{styleGenElapsed}s</span><span className="gen-model">{styleModel}</span></div></div>
                  </article>
                )}
                {styles.map((s) => (
                  <article key={s.id} className="candidate-card style-card" onClick={() => { setStyleRefUrl(apiPath(`/asset/portrait-review/styles/${s.filename}`)); setTab("source"); }}>
                    <div className="card-image"><img src={apiPath(`/asset/portrait-review/styles/${s.filename}`)} alt={s.prompt} /></div>
                    <div className="card-overlay">
                      <span className="card-model">{s.model}</span>
                      <span className="card-prompt" title={s.prompt}>{s.prompt}</span>
                    </div>
                    <div className="card-actions">
                      <span className="style-use-hint">Click to use as style ref →</span>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {/* ── PROMPT TAB ── */}
      {tab === "prompt" && (
        <div className="tab-content">
          <h2>Presets ({presets.length})</h2>
          {presets.length === 0 ? <p className="empty">No presets found.</p> : (
            <div className="presets-list">
              {presets.map((p) => (
                <article key={p.name} className="preset-card sidebar-panel">
                  <h3>{p.name}</h3>
                  <div className="preset-field"><strong>Prompt:</strong> <span>{p.prompt}</span></div>
                  {p.negative_prompt && <div className="preset-field"><strong>Negative:</strong> <span>{p.negative_prompt}</span></div>}
                  <div className="preset-params">
                    {p.strength != null && <span>strength={p.strength}</span>}
                    {p.steps != null && <span>steps={p.steps}</span>}
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── GENERATIONS TAB ── */}
      {tab === "generations" && (
        <div className="tab-content">
          <div className="candidates-header"><h2>All generations</h2><span className="candidate-count">{generations.length} total</span></div>
          {generations.length === 0 ? <p className="empty">No generations yet.</p> : (
            <div className="candidates-grid">
              {generations.map((g) => (
                <article key={g.candidate_id} className="candidate-card">
                  <div className="card-image">
                    {(g.raw_url ?? g.final_url) ? <img src={g.raw_url ?? g.final_url} alt={g.candidate_id} /> : <div className="missing">?</div>}
                  </div>
                  <div className="card-overlay">
                    <span className="card-model">{g.model ?? "?"}</span>
                    {g.prompt && <span className="card-prompt" title={g.prompt}>{g.prompt}</span>}
                  </div>
                  <div className="card-meta-footer">
                    <button className="link-btn" onClick={() => { setActiveId(g.source.photo_id); setTab("source"); }}>
                      ← #{g.source.photo_id}
                    </button>
                    <span className="card-preset">{g.preset}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── CARDS TAB ── */}
      {tab === "cards" && (
        <div className="tab-content">
          <div className="candidates-header cards-heading">
            <div><h2>Card-context previews</h2><span className="candidate-count">{cards.length} renders · {masters.length} portrait masters</span></div>
            <button className="refresh-btn" onClick={validateBatch}>Validate batch</button>
          </div>
          <section className="card-workbench">
            <aside className="sidebar-panel master-picker-panel">
              <h3>1. Portrait master</h3>
              {masters.length === 0 ? <p>Promote a source candidate with ♜ to begin.</p> : masters.map((master) => (
                <button key={master.master_id} className={`master-picker ${selectedMaster?.master_id === master.master_id ? "active" : ""}`} onClick={() => chooseMaster(master)}>
                  {master.master_url && <img src={master.master_url} alt={master.master_id} />}
                  <span>{master.master_id}</span>
                </button>
              ))}
            </aside>
            <aside className="sidebar-panel">
              <h3>2. Master anchors</h3>
              {selectedMaster ? <>
                <p>Move the face anchor to control where this reusable master sits in the card window.</p>
                <label>Face X<input type="number" min="0" max="1" step="0.01" value={anchorX} onChange={(e) => setAnchorX(e.target.value)} /></label>
                <label>Face Y<input type="number" min="0" max="1" step="0.01" value={anchorY} onChange={(e) => setAnchorY(e.target.value)} /></label>
                <label>Preferred archetype<select value={masterArchetype} onChange={(e) => setMasterArchetype(e.target.value)}>
                  {Object.entries(selectedTemplate?.archetypes ?? {}).map(([id, archetype]) => <option key={id} value={id}>{archetype.label ?? id}</option>)}
                </select></label>
                <button className="generate-btn" onClick={saveMasterComposition}>Save anchors</button>
              </> : <p>Select or promote a portrait master.</p>}
            </aside>
            <aside className="sidebar-panel">
              <h3>3. Card composition</h3>
              <label>Template<select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>{templates.map((template) => <option key={template.id} value={template.id}>{template.id} v{template.version}</option>)}</select></label>
              <label>Framing archetype<select value={archetypeId} onChange={(e) => setArchetypeId(e.target.value)}>{Object.entries(selectedTemplate?.archetypes ?? {}).map(([id, archetype]) => <option key={id} value={id}>{archetype.label ?? id}</option>)}</select></label>
              <label>Preview label<input value={cardLabel} onChange={(e) => setCardLabel(e.target.value)} /></label>
              <button className="generate-btn" onClick={renderSelectedCard} disabled={!selectedMaster || !selectedTemplate}>Render card preview</button>
            </aside>
            {validation && <aside className={`validation-panel ${validation.ok ? "ok" : "has-errors"}`}>
              <strong>{validation.ok ? "Batch checks passed" : "Batch has errors"}</strong>
              <span>{validation.card_count} render{validation.card_count === 1 ? "" : "s"} checked</span>
              {validation.issues.map((issue, index) => <p key={`${issue.card_id ?? "batch"}-${index}`} className={`validation-${issue.level}`}>{issue.card_id ? `${issue.card_id}: ` : ""}{issue.message}</p>)}
            </aside>}
          </section>
          {cards.length === 0 ? <p className="empty cards-empty">The first promoted master will be rendered here in card context.</p> : (
            <div className="candidates-grid">
              {cards.map((card) => (
                <article key={card.card_id} className={`candidate-card card-preview status-${card.review?.status ?? "unreviewed"}`}>
                  <div className="card-image">
                    {card.card_url ? <img src={card.card_url} alt={card.label} /> : <div className="missing">?</div>}
                  </div>
                  <div className="card-overlay">
                    <span className="card-model">{card.template_id} v{card.template_version}</span>
                    <span className="card-prompt">{card.archetype_id} · {card.master_id}</span>
                    {card.review?.status && <span className={`badge badge-${card.review.status}`}>{card.review.status}</span>}
                  </div>
                  <div className="card-actions">
                    <button className="action-btn fav-btn" onClick={() => reviewCard(card, "approved")} title="Approve card">✓</button>
                    <button className="action-btn trash-btn" onClick={() => reviewCard(card, "reject")} title="Reject card">🗑</button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      )}

      {genDetail && <CandidateDetail candidate={genDetail} onClose={() => setGenDetail(null)} />}
    </main>
  );
}
