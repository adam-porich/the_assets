export type Source = {
  id: string; label: string; dimensions?: [number, number]; image_url?: string;
  relative_path?: string; checksum_sha256?: string; provenance?: Record<string, unknown>;
};

export type SearchResult = Source & { pexels_photo_id?: number; selected_image_url?: string; preview_url?: string; photographer?: string };

export type StyleAsset = { id: string; asset_key?: string; label: string; role: "generation-reference" | "target-example"; checksum_sha256: string; image_url?: string; relative_path?: string };
export type PipelineStyle = {
  schema_version: number;
  identity: { family_id: string; style_version_id: string; version: number; state: "draft" | "locked"; label: string };
  generation: { model_id: string; execution_mode: "simulation" | "live"; quality: "low" | "medium" | "high"; direction: Record<string, string>; avoid: string; requested_aspect_policy: string; reference_limit: number };
  reference_pack: { id: string; version: number; assets: StyleAsset[] };
  composition: { logical_art_size: [number, number]; default_framing: { zoom: number; offset_x: number; offset_y: number }; centering: [number, number]; requested_art_ratio: string };
  renderer: { driver_id: string; logical_art_size: [number, number]; output_scale: number; palette_space: string; palette: string[]; preprocess: Record<string, number>; dither: { matrix: string; strength: number; edge_threshold: number } };
  card_assembly: { driver_id: string; logical_card_size: [number, number]; output_scale: number; layout: Record<string, unknown>; text: Record<string, string> };
  editor_descriptors: Array<Record<string, unknown>>;
  checksums: { style_sha256: string; assets?: Record<string, string> };
  provenance?: Record<string, unknown>;
};

export type StyleBootstrap = { active: PipelineStyle; draft?: PipelineStyle | null; versions: Array<{ style_version_id: string; label: string; version: number; checksum_sha256: string; active: boolean }>; driver: { id: string; label: string; output: string } };

export type Model = { id: string; name: string; execution_mode: "simulation" | "live"; available: boolean; max_input_references: number; qualities: string[]; aspect_ratios: string[]; pricing: Array<Record<string, unknown>>; provider_name?: string; provider_slug?: string };
export type Framing = { zoom: number; offset_x: number; offset_y: number };
export type ProductionItem = {
  item_id: string; source_id: string; source_label: string; attempt_number: number; lineage_id: string; approved?: boolean; status: "queued" | "generating" | "processing" | "ready" | "failed" | "interrupted";
  error?: string | null; source_url?: string; master_url?: string; logical_art_url?: string; art_url?: string; card_url?: string; card_checksum_sha256?: string | null;
  master_checksum_sha256?: string | null; render_revision: number; render_revisions: Array<Record<string, unknown>>; framing?: Framing | null; generation?: Record<string, unknown>; render_metadata?: Record<string, unknown>; usage?: Record<string, unknown>; cost_usd?: number | null;
  reference_stack: Array<Record<string, unknown>>; reference_urls?: Array<string | null>;
};
export type ProductionProgress = { selected_sources: number; ready_cards: number; approved_cards: number; failed_sources: number; paid_calls: number; total_attempts: number };
export type ProductionBatch = { batch_id: string; purpose: "card-production" | "style-trial"; status: string; created_at: string; updated_at: string; style_version_id: string; style_checksum_sha256: string; selected_source_ids: string[]; requested_paid_calls: number; paid_calls: number; cost_usd?: number | null; items: ProductionItem[]; progress: ProductionProgress; style_snapshot?: PipelineStyle; calibration_source_ids?: string[] | null };
export type ProductionSummary = Omit<ProductionBatch, "items" | "style_snapshot">;
export type Approval = { approval_id: string; source_id: string; attempt_id: string; batch_id: string; style_version_id: string; style_checksum_sha256: string; card_checksum_sha256: string; render_revision: number; approved_at: string };

export type Bootstrap = { workspace: { sources: Source[]; benchmark_source_ids: string[] }; sources: Source[]; selected_source_ids: string[]; style: StyleBootstrap; batches: ProductionSummary[]; cards: ProductionItem[]; models: Model[]; integrations: { pexels: { configured: boolean }; openrouter: { configured: boolean } }; starter: { photo_ids: number[] } };
