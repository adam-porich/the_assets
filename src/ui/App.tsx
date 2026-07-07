import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type ReviewStatus = "favorite" | "reject" | "add";

type Review = {
  status?: ReviewStatus;
  note?: string;
};

type Candidate = {
  candidate_id: string;
  preset?: string;
  backend?: string;
  model?: string;
  prompt?: string;
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

type LibraryPayload = {
  sources: Source[];
};

const appBase = import.meta.env.BASE_URL;
const apiPath = (path: string) => `${appBase}${path.replace(/^\//, "")}`;

const defaultModel = "openai/gpt-image-1-mini";
const defaultPreset = "estate-pixel-claimant-v1";

const FALLBACK_MODELS = [
  "openai/gpt-image-1-mini",
  "openai/gpt-image-1",
  "google/gemini-3.1-flash-lite-image",
  "google/gemini-3.1-flash-image",
  "recraft/recraft-v4",
  "recraft/recraft-v3",
];

const COST_TIERS: Record<string, string> = {
  "openai/gpt-image-1-mini": "$",
  "google/gemini-3.1-flash-lite-image": "$",
  "google/gemini-3.1-flash-image": "$$",
  "recraft/recraft-v3": "$",
  "recraft/recraft-v4": "$$",
  "black-forest-labs/flux.2-klein-4b": "$",
  "sourceful/riverflow-v2-fast": "$",
};

function costTier(modelId: string): string {
  return COST_TIERS[modelId] ?? "?";
}

function statusOf(review?: Review): ReviewStatus | "unreviewed" {
  return review?.status ? review.status : "unreviewed";
}

async function postJson(path: string, body: unknown) {
  const response = await fetch(apiPath(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function CandidateDetail({ candidate, onClose }: { candidate: Candidate; onClose: () => void }) {
  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-modal" onClick={(e) => e.stopPropagation()}>
        <button className="detail-close" onClick={onClose}>
          ×
        </button>

        <h2>{candidate.candidate_id}</h2>

        <div className="detail-images">
          <figure className="detail-figure">
            {candidate.raw_url ? (
              <img src={candidate.raw_url} alt="Raw generated" />
            ) : (
              <div className="missing">No raw image</div>
            )}
            <figcaption>Raw generated</figcaption>
          </figure>
          <figure className="detail-figure">
            {candidate.final_url ? (
              <img src={candidate.final_url} alt="Final down-res" />
            ) : (
              <div className="missing">No final image</div>
            )}
            <figcaption>Final (down-res)</figcaption>
          </figure>
        </div>

        <div className="detail-meta">
          <h3>Generation details</h3>
          <dl>
            <dt>Preset</dt>
            <dd>{candidate.preset ?? "unknown"}</dd>

            <dt>Backend</dt>
            <dd>{candidate.backend ?? "unknown"}</dd>

            <dt>Model</dt>
            <dd>{candidate.model ?? "unknown"}</dd>

            <dt>Seed</dt>
            <dd>{candidate.seed ?? "unknown"}</dd>

            <dt>Strength</dt>
            <dd>{candidate.strength ?? "unknown"}</dd>

            <dt>Steps</dt>
            <dd>{candidate.steps ?? "unknown"}</dd>

            <dt>Guidance</dt>
            <dd>{candidate.guidance ?? "unknown"}</dd>

            <dt>Elapsed</dt>
            <dd>{candidate.elapsed_seconds != null ? `${candidate.elapsed_seconds}s` : "unknown"}</dd>

            <dt>Background</dt>
            <dd>{candidate.background_mode ?? "unknown"}</dd>

            <dt>Mask mode</dt>
            <dd>{candidate.mask_mode ?? "unknown"}</dd>

            {candidate.disk_only && (
              <>
                <dt>Source</dt>
                <dd>disk output</dd>
              </>
            )}
          </dl>
        </div>
      </div>
    </div>
  );
}

export function App() {
  const [library, setLibrary] = useState<LibraryPayload>({ sources: [] });
  const [activeId, setActiveId] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();
  const [model, setModel] = useState(defaultModel);
  const [preset, setPreset] = useState(defaultPreset);
  const [pexelsQuery, setPexelsQuery] = useState("");
  const [pexelsCount, setPexelsCount] = useState(5);
  const [generatingSince, setGeneratingSince] = useState<number | null>(null);
  const [genElapsed, setGenElapsed] = useState(0);
  const [generatingModel, setGeneratingModel] = useState<string | null>(null);
  const [modelOptions, setModelOptions] = useState<string[]>(FALLBACK_MODELS);
  const [fetching, setFetching] = useState(false);
  const [actionError, setActionError] = useState<string | undefined>();
  const [detailCandidate, setDetailCandidate] = useState<Candidate | null>(null);
  const [trashedSources, setTrashedSources] = useState<Set<string>>(new Set());
  const [trashedCandidates, setTrashedCandidates] = useState<Set<string>>(new Set());
  const loadedRef = useRef(false);

  const load = useCallback(async () => {
    try {
      const [libRes, modelsRes] = await Promise.all([
        fetch(apiPath("/api/library")),
        fetch(apiPath("/api/models/img2img")).catch(() => null),
      ]);
      if (!libRes.ok) throw new Error(await libRes.text());
      const payload = (await libRes.json()) as LibraryPayload;
      setLibrary(payload);
      if (modelsRes?.ok) {
        const modelsPayload = await modelsRes.json();
        if (modelsPayload.ok && modelsPayload.models?.length) {
          setModelOptions(modelsPayload.models.map((m: { id: string }) => m.id));
        }
      }
      if (!loadedRef.current) {
        const nextId = payload.sources[0]?.photo_id;
        setActiveId(nextId);
        const src = payload.sources.find((s) => s.photo_id === nextId);
        if (!pexelsQuery && src?.query) setPexelsQuery(src.query);
        loadedRef.current = true;
      }
      setError(undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [pexelsQuery]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (generatingSince === null) {
      setGenElapsed(0);
      return;
    }
    const tick = () => setGenElapsed(Math.floor((Date.now() - generatingSince) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [generatingSince]);

  const activeSource = library.sources.find((s) => s.photo_id === activeId) ?? library.sources[0];

  const visibleSources = useMemo(() => {
    return library.sources.filter((s) => !trashedSources.has(s.photo_id));
  }, [library.sources, trashedSources]);

  const candidates = useMemo(() => {
    if (!activeSource) return [];
    return activeSource.candidates.filter((c) => !trashedCandidates.has(c.candidate_id));
  }, [activeSource, trashedCandidates]);

  async function favoriteCandidate(candidate: Candidate) {
    if (!activeSource) return;
    setActionError(undefined);
    try {
      await postJson("/api/favorite-candidate", {
        photo_id: activeSource.photo_id,
        candidate_id: candidate.candidate_id,
      });
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }

  async function trashCandidate(candidate: Candidate) {
    if (statusOf(candidate.review) === "favorite") return;
    setTrashedCandidates((prev) => new Set(prev).add(candidate.candidate_id));
    setActionError(undefined);
    try {
      await postJson("/api/review", {
        collection: "candidates",
        id: candidate.candidate_id,
        status: "reject",
      });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }

  async function favoriteSource(source: Source) {
    setActionError(undefined);
    try {
      await postJson("/api/review", {
        collection: "sources",
        id: source.photo_id,
        status: "favorite",
      });
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }

  async function trashSource(source: Source) {
    if (statusOf(source.review) === "favorite") return;
    setTrashedSources((prev) => new Set(prev).add(source.photo_id));
    if (activeId === source.photo_id) {
      const remaining = visibleSources.filter((s) => s.photo_id !== source.photo_id);
      setActiveId(remaining[0]?.photo_id);
    }
    setActionError(undefined);
    try {
      await postJson("/api/review", {
        collection: "sources",
        id: source.photo_id,
        status: "reject",
      });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }

  async function fetchPexels() {
    if (!pexelsQuery) return;
    setFetching(true);
    setActionError(undefined);
    try {
      const result = await postJson("/api/fetch-pexels", { query: pexelsQuery, count: pexelsCount });
      setLibrary(result.library);
      setError(undefined);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setFetching(false);
    }
  }

  async function generateImg2Img() {
    if (!activeSource) return;
    setGeneratingSince(Date.now());
    setGeneratingModel(model);
    setActionError(undefined);
    try {
      const result = await postJson("/api/generate", {
        photo_id: activeSource.photo_id,
        preset,
        model,
      });
      setLibrary(result.library);
      setError(undefined);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setGeneratingSince(null);
      setGeneratingModel(null);
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="topbar-row">
          <h1>Portrait Review</h1>
          <button className="refresh-btn" onClick={() => void load()}>
            Refresh
          </button>
        </div>
        <div className="topbar-sources">
          <nav className="source-picker">
            {visibleSources.map((source) => {
              const st = statusOf(source.review);
              const isActive = source.photo_id === activeSource?.photo_id;
              const isFav = st === "favorite";
              const imgSrc = source.prepared_url ?? source.source_url;
              return (
                <article
                  key={source.photo_id}
                  className={`source-card ${isActive ? "active" : ""} status-${st}`}
                >
                  <div className="source-card-image" onClick={() => setActiveId(source.photo_id)}>
                    {imgSrc ? (
                      <img src={imgSrc} alt={`Pexels ${source.photo_id}`} />
                    ) : (
                      <div className="missing">No image</div>
                    )}
                  </div>
                  <div className="source-card-overlay">
                    <span className="source-card-label">#{source.photo_id}</span>
                    {st !== "unreviewed" && <span className={`badge badge-${st}`}>{st}</span>}
                    {isActive && <span className="badge badge-selected">active</span>}
                  </div>
                  <div className="source-card-actions">
                    <button
                      className={`action-btn fav-btn ${isFav ? "active" : ""}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        favoriteSource(source);
                      }}
                      title="Favorite source"
                    >
                      ♥
                    </button>
                    {!isFav && (
                      <button
                        className="action-btn trash-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          trashSource(source);
                        }}
                        title="Trash source"
                      >
                        🗑
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </nav>

          <aside className="sidebar-panel pexels-panel">
            <h2>🔍 Pexels Search</h2>
            <label>
              Query
              <input
                value={pexelsQuery}
                onChange={(e) => setPexelsQuery(e.target.value)}
                placeholder="e.g. vintage portrait"
              />
            </label>
            <label>
              Count
              <select value={pexelsCount} onChange={(e) => setPexelsCount(Number(e.target.value))}>
                <option value={3}>3</option>
                <option value={5}>5</option>
                <option value={7}>7</option>
                <option value={10}>10</option>
              </select>
            </label>
            <button className="generate-btn" onClick={fetchPexels} disabled={fetching}>
              {fetching ? "Fetching..." : "Fetch Images"}
            </button>
          </aside>
        </div>
      </header>

      {error && <div className="error">{error}</div>}
      {actionError && <div className="error inline-error">{actionError}</div>}

      {activeSource ? (
        <>
          <section className="candidates-area">
            <div className="candidates-header">
              <h2>Candidates for #{activeSource.photo_id}</h2>
              <span className="candidate-count">{candidates.length} generated</span>
            </div>

            {candidates.length === 0 && generatingSince === null ? (
              <p className="empty">No img2img candidates yet. Generate one from the bottom panel.</p>
            ) : (
              <div className="candidates-grid">
                {generatingSince !== null && (
                  <article className="candidate-card generating">
                    <div className="card-image">
                      <div className="generating-placeholder">
                        <div className="spinner" />
                        <span className="gen-label">Generating...</span>
                        <span className="gen-elapsed">{genElapsed}s</span>
                        {generatingModel && <span className="gen-model">{generatingModel}</span>}
                      </div>
                    </div>
                  </article>
                )}
                {candidates.map((candidate) => {
                  const st = statusOf(candidate.review);
                  const isFav = st === "favorite";
                  const isSelected = activeSource.selected?.variant === candidate.candidate_id;
                  const thumbSrc = candidate.raw_url ?? candidate.final_url;
                  return (
                    <article
                      key={candidate.candidate_id}
                      className={`candidate-card status-${st} ${isSelected ? "selected" : ""}`}
                    >
                      <div className="card-image" onClick={() => setDetailCandidate(candidate)} title="Click for details">
                        {thumbSrc ? (
                          <img src={thumbSrc} alt={candidate.candidate_id} />
                        ) : (
                          <div className="missing">No image</div>
                        )}
                      </div>
                      <div className="card-overlay">
                        <span className="card-model">{candidate.model ?? "unknown"}</span>
                        {candidate.prompt && <span className="card-prompt" title={candidate.prompt}>{candidate.prompt}</span>}
                        {isSelected && <span className="badge badge-selected">selected</span>}
                        {st !== "unreviewed" && <span className={`badge badge-${st}`}>{st}</span>}
                      </div>
                      <div className="card-actions">
                        <button
                          className={`action-btn fav-btn ${isFav ? "active" : ""}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            favoriteCandidate(candidate);
                          }}
                          title="Save to favorites"
                        >
                          ♥
                        </button>
                        {!isFav && (
                          <button
                            className="action-btn trash-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              trashCandidate(candidate);
                            }}
                            title="Move to trash"
                          >
                            🗑
                          </button>
                        )}
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
              <p className="panel-desc">Generate a stylized variant of the active source.</p>

              <label>
                Model
                <select value={model} onChange={(e) => setModel(e.target.value)}>
                  {modelOptions.map((opt) => (
                    <option key={opt} value={opt}>{costTier(opt)} {opt}</option>
                  ))}
                </select>
              </label>

              <label>
                Preset
                <select value={preset} onChange={(e) => setPreset(e.target.value)}>
                  <option value="estate-pixel-claimant-v1">estate-pixel-claimant-v1</option>
                </select>
              </label>

              <button className="generate-btn" onClick={generateImg2Img} disabled={generatingSince !== null}>
                {generatingSince !== null ? `Generating... ${genElapsed}s` : "Generate Image"}
              </button>
            </aside>

            <aside className="sidebar-panel source-info">
              <h3>Source #{activeSource.photo_id}</h3>
              {activeSource.photographer && <p>By {activeSource.photographer}</p>}
              {activeSource.dimensions && (
                <p>
                  {activeSource.dimensions[0]} × {activeSource.dimensions[1]}
                </p>
              )}
              {activeSource.photo_page_url && (
                <a href={activeSource.photo_page_url} target="_blank" rel="noreferrer">
                  Pexels page ↗
                </a>
              )}
              {activeSource.query && <p className="source-query">{activeSource.query}</p>}
            </aside>
          </footer>
        </>
      ) : (
        <p className="empty">No sources found.</p>
      )}

      {detailCandidate && <CandidateDetail candidate={detailCandidate} onClose={() => setDetailCandidate(null)} />}
    </main>
  );
}
