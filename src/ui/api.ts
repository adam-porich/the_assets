import type { Bootstrap, Framing, PipelineStyle, ProductionBatch, SearchResult, Source, StyleBootstrap } from "./types";

const apiRoot = `${import.meta.env.BASE_URL.replace(/\/$/, "")}/api`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiRoot}${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok === false) throw new Error(body.error || `Request failed (${response.status})`);
  return body as T;
}
const json = (method: string, body: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  bootstrap: () => request<Bootstrap>("/workspace"),
  styleBootstrap: () => request<{ style: StyleBootstrap }>("/styles/bootstrap"),
  searchSources: (query: string, count = 12, page = 1) => request<{ results: SearchResult[]; page: number; has_more: boolean }>("/sources/search", json("POST", { query, count, page })),
  importSources: (candidates: SearchResult[]) => request<{ workspace: Bootstrap["workspace"]; imported: number; deduplicated: number; failed: number }>("/sources/import-bulk", json("POST", { candidates, include_in_selection: true })),
  loadStarterSources: () => request<{ workspace: Bootstrap["workspace"] }>("/sources/starter", json("POST", {})),
  uploadSource: (file: File, label: string) => { const form = new FormData(); form.append("label", label); form.append("file", file); return request<{ workspace: Bootstrap["workspace"]; record: Source }>("/sources/upload", { method: "POST", body: form }); },
  updateSelection: (source_ids: string[]) => request<{ workspace: Bootstrap["workspace"]; selected_source_ids: string[] }>("/sources/selection", json("POST", { source_ids })),
  deleteSource: (id: string) => request<{ workspace: Bootstrap["workspace"] }>(`/sources/${id}`, json("DELETE", { confirm: true })),
  createProduction: (source_ids: string[], pipeline_id: string, consent = false) => request<{ batch: ProductionBatch }>("/production", json("POST", { source_ids, pipeline_id, consent })),
  listProduction: () => request<{ batches: Bootstrap["batches"] }>("/production"),
  getProduction: (id: string) => request<{ batch: ProductionBatch }>(`/production/${id}`),
  retryFailed: (id: string, consent = false) => request<{ batch: ProductionBatch }>(`/production/${id}/retry`, json("POST", { consent })),
  tryAnother: (id: string, source_id: string, consent = false) => request<{ batch: ProductionBatch }>(`/production/${id}/try-another`, json("POST", { source_id, consent })),
  renderFraming: (id: string, item_id: string, framing: Framing) => request<{ batch: ProductionBatch }>(`/production/${id}/render`, json("POST", { item_id, framing })),
  createDraft: (pipeline_id: string) => request<{ style: PipelineStyle }>("/styles/draft", json("POST", { pipeline_id })),
  updateDraft: (patch: Partial<PipelineStyle>) => request<{ style: PipelineStyle }>("/styles/draft", json("PUT", patch)),
  uploadDraftReference: (file: File) => { const form = new FormData(); form.append("file", file); return request<{ style: PipelineStyle }>("/styles/draft/references", { method: "POST", body: form }); },
  runTrial: (source_ids: string[], consent = false) => request<{ batch: ProductionBatch }>("/styles/trials", json("POST", { source_ids, consent })),
  activateTrial: (id: string) => request<{ style: StyleBootstrap }>(`/styles/trials/${id}/activate`, json("POST", {})),
  activatePipeline: (pipeline_id: string) => request<{ style: StyleBootstrap }>(`/pipelines/${pipeline_id}/activate`, json("POST", {})),
  favorite: (batch_id: string, item_id: string) => request<{ favorite: Record<string, unknown> }>("/favorites", json("POST", { batch_id, item_id })),
  unfavorite: (batch_id: string, item_id: string) => request<{ removed: boolean }>(`/favorites/${batch_id}/${item_id}`, { method: "DELETE" }),
};
