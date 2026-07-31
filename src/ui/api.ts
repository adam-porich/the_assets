import type { Bootstrap, Card, Recipe, Run, SearchResult, Workspace } from "./types";

const base = import.meta.env.BASE_URL.replace(/\/$/, "");
export const apiPath = (path: string) => `${base}/${path.replace(/^\//, "")}`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiPath(path), init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok === false) throw new Error(body.error || `Request failed (${response.status})`);
  return body as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  bootstrap: () => request<Bootstrap>("/api/workspace"),
  getRun: (id: string) => request<{ run: Run }>(`/api/runs/${id}`),
  compareRuns: (first: string, second: string) => request<{ comparison: { first: Run; second: Run; same_benchmark: boolean; rows: Array<{ source_id: string; first?: { thumbnail_url?: string; source_label: string }; second?: { thumbnail_url?: string; source_label: string } }>; recipe_changes: Array<{ field: string; first: unknown; second: unknown }> } }>(`/api/runs/${first}/compare?with=${encodeURIComponent(second)}`),
  getCard: (id: string) => request<{ card: Card }>(`/api/cards/${id}`),
  listCards: (includeDiscarded = false) => request<{ cards: Card[] }>(`/api/cards${includeDiscarded ? "?include_discarded=true" : ""}`),
  searchSources: (query: string, count = 8) => request<{ results: SearchResult[] }>("/api/sources/search", json("POST", { query, count })),
  importSource: (candidate: unknown) => request<{ workspace: Workspace }>("/api/sources/import", json("POST", { candidate })),
  upload: (kind: "sources" | "references", file: File, label: string) => {
    const form = new FormData(); form.append("file", file); form.append("label", label);
    return request<{ workspace: Workspace }>(`/api/${kind}/upload`, { method: "POST", body: form });
  },
  updateBenchmark: (source_ids: string[]) => request<{ workspace: Workspace }>("/api/benchmark", json("POST", { source_ids })),
  deleteSource: (id: string) => request<{ workspace: Workspace }>(`/api/sources/${id}`, json("DELETE", { confirm: true })),
  deleteReference: (id: string) => request<{ workspace: Workspace }>(`/api/references/${id}`, json("DELETE", { confirm: true })),
  updateReference: (id: string, patch: unknown) => request<{ workspace: Workspace }>(`/api/references/${id}`, json("PUT", patch)),
  createRecipe: (recipe: unknown) => request<{ workspace: Workspace; recipe: Recipe }>("/api/recipes", json("POST", recipe)),
  updateRecipe: (id: string, recipe: unknown) => request<{ workspace: Workspace }>(`/api/recipes/${id}`, json("PUT", recipe)),
  duplicateRecipe: (id: string) => request<{ workspace: Workspace; recipe: Recipe }>(`/api/recipes/${id}/duplicate`, json("POST", {})),
  selectRecipe: (id: string) => request<{ workspace: Workspace }>(`/api/recipes/${id}/select`, json("POST", {})),
  startRun: (recipe_id: string, outputs_per_source: number) => request<{ run: Run }>("/api/runs", json("POST", { recipe_id, outputs_per_source })),
  reviewRun: (id: string, verdict: string, note: string) => request<{ run: Run }>(`/api/runs/${id}/review`, json("POST", { verdict, note })),
  duplicateRecipeFromRun: (id: string) => request<{ workspace: Workspace }>(`/api/runs/${id}/duplicate-recipe`, json("POST", {})),
  createCard: (run_id: string, run_item_id: string, label: string, preset: string) => request<{ card: Card }>("/api/cards", json("POST", { run_id, run_item_id, label, preset })),
  updateCard: (id: string, patch: unknown) => request<{ card: Card }>(`/api/cards/${id}`, json("PUT", patch)),
  decideCard: (id: string, decision: string) => request<{ card: Card }>(`/api/cards/${id}/decision`, json("POST", { decision })),
};
