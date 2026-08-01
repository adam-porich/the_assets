import type { Approval, Bootstrap, Framing, PipelineStyle, ProductionBatch, SearchResult, Source, StyleBootstrap } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok === false) throw new Error(body.error || `Request failed (${response.status})`);
  return body as T;
}
const json = (method: string, body: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  bootstrap: () => request<Bootstrap>("/api/workspace"),
  styleBootstrap: () => request<{ style: StyleBootstrap }>("/api/styles/bootstrap"),
  searchSources: (query: string, count = 12, page = 1) => request<{ results: SearchResult[]; page: number; has_more: boolean }>("/api/sources/search", json("POST", { query, count, page })),
  importSources: (candidates: SearchResult[]) => request<{ workspace: Bootstrap["workspace"]; imported: number; deduplicated: number; failed: number }>("/api/sources/import-bulk", json("POST", { candidates, include_in_selection: false })),
  loadStarterSources: () => request<{ workspace: Bootstrap["workspace"] }>("/api/sources/starter", json("POST", {})),
  uploadSource: (file: File, label: string) => { const form = new FormData(); form.append("label", label); form.append("file", file); return request<{ workspace: Bootstrap["workspace"]; record: Source }>("/api/sources/upload", { method: "POST", body: form }); },
  updateSelection: (source_ids: string[]) => request<{ workspace: Bootstrap["workspace"]; selected_source_ids: string[] }>("/api/sources/selection", json("POST", { source_ids })),
  deleteSource: (id: string) => request<{ workspace: Bootstrap["workspace"] }>(`/api/sources/${id}`, json("DELETE", { confirm: true })),
  createProduction: (source_ids: string[], style_version_id: string) => request<{ batch: ProductionBatch }>("/api/production", json("POST", { source_ids, style_version_id })),
  listProduction: () => request<{ batches: Bootstrap["batches"] }>("/api/production"),
  getProduction: (id: string) => request<{ batch: ProductionBatch }>(`/api/production/${id}`),
  retryFailed: (id: string) => request<{ batch: ProductionBatch }>(`/api/production/${id}/retry`, json("POST", {})),
  tryAnother: (id: string, source_id: string) => request<{ batch: ProductionBatch }>(`/api/production/${id}/try-another`, json("POST", { source_id })),
  renderFraming: (id: string, item_id: string, framing: Framing) => request<{ batch: ProductionBatch }>(`/api/production/${id}/render`, json("POST", { item_id, framing })),
  approve: (id: string, item_id: string) => request<{ approval: Approval }>(`/api/production/${id}/approve`, json("POST", { item_id })),
  bundle: (id: string) => request<{ download_url: string; manifest: Record<string, unknown> }>(`/api/production/${id}/bundle`, json("POST", {})),
  createDraft: () => request<{ style: PipelineStyle }>("/api/styles/draft", json("POST", {})),
  updateDraft: (patch: Partial<PipelineStyle>) => request<{ style: PipelineStyle }>("/api/styles/draft", json("PUT", patch)),
  uploadDraftReference: (file: File) => { const form = new FormData(); form.append("file", file); return request<{ style: PipelineStyle }>("/api/styles/draft/references", { method: "POST", body: form }); },
  runTrial: (source_ids: string[]) => request<{ batch: ProductionBatch }>("/api/styles/trials", json("POST", { source_ids })),
  activateTrial: (id: string) => request<{ style: StyleBootstrap }>(`/api/styles/trials/${id}/activate`, json("POST", {})),
};
