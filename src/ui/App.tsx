import { useEffect, useMemo, useState } from "react";

type ReviewStatus = "favorite" | "reject" | "add" | "clear";

type Review = {
  status?: ReviewStatus;
  note?: string;
};

type Candidate = {
  candidate_id: string;
  preset: string;
  backend: string;
  model: string;
  seed: number;
  strength: number;
  steps: number;
  guidance?: number;
  elapsed_seconds: number;
  background_mode: string;
  mask_mode: string;
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
  crop_url?: string;
  mask_url?: string;
  foreground_url?: string;
  composite_url?: string;
  candidates: Candidate[];
};

type LibraryPayload = {
  sources: Source[];
};

const appBase = import.meta.env.BASE_URL;
const apiPath = (path: string) => `${appBase}${path.replace(/^\//, "")}`;

const statusLabels: Array<ReviewStatus | "unreviewed" | "all"> = [
  "all",
  "favorite",
  "add",
  "reject",
  "unreviewed"
];

function statusOf(review?: Review): ReviewStatus | "unreviewed" {
  return review?.status && review.status !== "clear" ? review.status : "unreviewed";
}

async function postJson(path: string, body: unknown) {
  const response = await fetch(apiPath(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function ImagePanel({ label, src }: { label: string; src?: string }) {
  return (
    <figure className="image-panel">
      {src ? <img src={src} alt={label} /> : <div className="missing">Missing</div>}
      <figcaption>{label}</figcaption>
    </figure>
  );
}

function ReviewButtons({
  collection,
  id,
  onUpdated
}: {
  collection: "sources" | "candidates";
  id: string;
  onUpdated: () => void;
}) {
  async function mark(status: ReviewStatus) {
    await postJson("/api/review", { collection, id, status });
    onUpdated();
  }

  return (
    <div className="review-buttons">
      <button onClick={() => mark("favorite")}>Favorite</button>
      <button onClick={() => mark("add")}>Add</button>
      <button onClick={() => mark("reject")}>Reject</button>
      <button onClick={() => mark("clear")}>Clear</button>
    </div>
  );
}

function CandidateCard({
  source,
  candidate,
  onUpdated
}: {
  source: Source;
  candidate: Candidate;
  onUpdated: () => void;
}) {
  const status = statusOf(candidate.review);
  const selected = source.selected?.variant === candidate.candidate_id;

  async function selectCandidate() {
    await postJson("/api/select", {
      photo_id: source.photo_id,
      candidate_id: candidate.candidate_id,
      tags: source.selected?.tags ?? []
    });
    onUpdated();
  }

  return (
    <article className={`candidate-card status-${status} ${selected ? "selected" : ""}`}>
      <div className="candidate-images">
        <ImagePanel label="Stylized raw" src={candidate.raw_url} />
        <ImagePanel label="Final" src={candidate.final_url} />
      </div>
      <div className="candidate-meta">
        <div className="badge-row">
          <span className={`badge badge-${status}`}>{status}</span>
          {selected ? <span className="badge badge-selected">selected</span> : null}
        </div>
        <p>{candidate.candidate_id}</p>
        <p>
          {candidate.backend} / {candidate.model}
        </p>
        <p>
          seed {candidate.seed} · strength {candidate.strength} · steps {candidate.steps} · {candidate.elapsed_seconds}s
        </p>
        <p>
          {candidate.mask_mode} · {candidate.background_mode}
        </p>
        <ReviewButtons collection="candidates" id={candidate.candidate_id} onUpdated={onUpdated} />
        <button className="select-button" onClick={selectCandidate}>
          Select candidate
        </button>
      </div>
    </article>
  );
}

function SourceDetail({ source, onUpdated }: { source: Source; onUpdated: () => void }) {
  const status = statusOf(source.review);
  return (
    <section className={`source-detail status-${status}`}>
      <aside className="source-meta">
        <div className="badge-row">
          <span className={`badge badge-${status}`}>{status}</span>
          <span className="badge">{source.processing_status ?? "unknown"}</span>
        </div>
        <h2>Pexels {source.photo_id}</h2>
        <p>{source.query}</p>
        <p>
          {source.dimensions?.[0]} x {source.dimensions?.[1]}
        </p>
        {source.photo_page_url ? (
          <a href={source.photo_page_url} target="_blank" rel="noreferrer">
            Source photo
          </a>
        ) : null}
        <ReviewButtons collection="sources" id={source.photo_id} onUpdated={onUpdated} />
      </aside>

      <div className="workflow">
        <div className="stage">
          <h3>Original</h3>
          <div className="image-row">
            <ImagePanel label="Source" src={source.source_url} />
            <ImagePanel label="Crop" src={source.crop_url} />
          </div>
        </div>
        <div className="stage">
          <h3>Rembg</h3>
          <div className="image-row">
            <ImagePanel label="Mask" src={source.mask_url} />
            <ImagePanel label="Composite" src={source.composite_url} />
          </div>
        </div>
        <div className="stage">
          <h3>Stylized Candidates</h3>
          {source.candidates.length ? (
            <div className="candidate-list">
              {source.candidates.map((candidate) => (
                <CandidateCard key={candidate.candidate_id} source={source} candidate={candidate} onUpdated={onUpdated} />
              ))}
            </div>
          ) : (
            <p className="empty">No stylized candidates yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}

export function App() {
  const [library, setLibrary] = useState<LibraryPayload>({ sources: [] });
  const [activeId, setActiveId] = useState<string | undefined>();
  const [filter, setFilter] = useState<ReviewStatus | "unreviewed" | "all">("all");
  const [error, setError] = useState<string | undefined>();

  async function load() {
    try {
      const response = await fetch(apiPath("/api/library"));
      if (!response.ok) throw new Error(await response.text());
      const payload = (await response.json()) as LibraryPayload;
      setLibrary(payload);
      setActiveId((current) => current ?? payload.sources[0]?.photo_id);
      setError(undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const visibleSources = useMemo(() => {
    return library.sources.filter((source) => filter === "all" || statusOf(source.review) === filter);
  }, [filter, library.sources]);

  const activeSource = library.sources.find((source) => source.photo_id === activeId) ?? visibleSources[0] ?? library.sources[0];

  return (
    <main>
      <header className="topbar">
        <div className="title-block">
          <h1>Portrait Review</h1>
          <p>Track the useful candidates: original, rembg, stylized, final.</p>
        </div>
        <div className="filters">
          {statusLabels.map((status) => (
            <button key={status} className={filter === status ? "active" : ""} onClick={() => setFilter(status)}>
              {status}
            </button>
          ))}
          <button onClick={() => void load()}>Refresh</button>
        </div>
        <nav className="picker" aria-label="Portrait picker">
          {visibleSources.map((source) => {
            const sourceStatus = statusOf(source.review);
            return (
              <button
                key={source.photo_id}
                className={`picker-card status-${sourceStatus} ${source.photo_id === activeSource?.photo_id ? "active" : ""}`}
                onClick={() => setActiveId(source.photo_id)}
              >
                {source.source_url ? <img src={source.source_url} alt={`Pexels ${source.photo_id}`} /> : null}
                <span>Pexels {source.photo_id}</span>
                <span className={`badge badge-${sourceStatus}`}>{sourceStatus}</span>
              </button>
            );
          })}
        </nav>
      </header>

      {error ? <div className="error">{error}</div> : null}
      {activeSource ? <SourceDetail source={activeSource} onUpdated={() => void load()} /> : <p className="empty">No sources found.</p>}
    </main>
  );
}
