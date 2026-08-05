import type { Bootstrap, Framing, InputAsset, PipelineStyle, ProductionBatch, SearchResult, StyleBootstrap } from "./types";

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
  searchInputs: (query: string, count = 12, page = 1) => request<{ results: SearchResult[]; page: number; has_more: boolean }>("/inputs/search", json("POST", { query, count, page })),
  importInput: (candidate: SearchResult) => request<{ workspace: Bootstrap["workspace"]; input: InputAsset }>("/inputs/import", json("POST", { candidate })),
  uploadInput: (file: File, label: string) => { const form = new FormData(); form.append("label", label); form.append("file", file); return request<{ workspace: Bootstrap["workspace"]; input: InputAsset }>("/inputs/upload", { method: "POST", body: form }); },
  getInput: (id: string) => request<{ input: InputAsset }>(`/inputs/${id}`),
  normaliseInput: (id: string, prompt: string, quality: string, consent = false, mode: "preserve" | "reconstruct" = "preserve") => request<{ input: InputAsset }>(`/inputs/${id}/normalisations`, json("POST", { prompt, quality, consent, mode })),
  acceptInput: (id: string, attempt_id: string) => request<{ workspace: Bootstrap["workspace"]; input: InputAsset }>(`/inputs/${id}/accept`, json("POST", { attempt_id })),
  deleteInput: (id: string) => request<{ workspace: Bootstrap["workspace"] }>(`/inputs/${id}`, json("DELETE", { confirm: true })),
  createProduction: (source_ids: string[], pipeline_id: string, consent = false, content_direction?: string) => request<{ batch: ProductionBatch }>("/production", json("POST", { source_ids, pipeline_id, consent, content_direction })),
  listProduction: () => request<{ batches: Bootstrap["batches"] }>("/production"),
  getProduction: (id: string) => request<{ batch: ProductionBatch }>(`/production/${id}`),
  retryFailed: (id: string, consent = false) => request<{ batch: ProductionBatch }>(`/production/${id}/retry`, json("POST", { consent })),
  tryAnother: (id: string, source_id: string, consent = false) => request<{ batch: ProductionBatch }>(`/production/${id}/try-another`, json("POST", { source_id, consent })),
  acceptCandidate: (id: string, item_id: string) => request<{ batch: ProductionBatch }>(`/production/${id}/accept`, json("POST", { item_id })),
  renderFraming: (id: string, item_id: string, framing: Framing, palette_mode?: string) => request<{ batch: ProductionBatch }>(`/production/${id}/render`, json("POST", { item_id, framing, palette_mode })),
  createDraft: (pipeline_id: string) => request<{ style: PipelineStyle }>("/styles/draft", json("POST", { pipeline_id })),
  updateDraft: (patch: Partial<PipelineStyle>) => request<{ style: PipelineStyle }>("/styles/draft", json("PUT", patch)),
  uploadDraftReference: (file: File) => { const form = new FormData(); form.append("file", file); return request<{ style: PipelineStyle }>("/styles/draft/references", { method: "POST", body: form }); },
  runTrial: (source_ids: string[], consent = false) => request<{ batch: ProductionBatch }>("/styles/trials", json("POST", { source_ids, consent })),
  activateTrial: (id: string) => request<{ style: StyleBootstrap }>(`/styles/trials/${id}/activate`, json("POST", {})),
  activatePipeline: (pipeline_id: string) => request<{ style: StyleBootstrap }>(`/pipelines/${pipeline_id}/activate`, json("POST", {})),
  favorite: (batch_id: string, item_id: string) => request<{ favorite: Record<string, unknown> }>("/favorites", json("POST", { batch_id, item_id })),
  unfavorite: (batch_id: string, item_id: string) => request<{ removed: boolean }>(`/favorites/${batch_id}/${item_id}`, { method: "DELETE" }),
};
