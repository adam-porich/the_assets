export type InputAsset = {
  id: string; label: string; status: "pending" | "ready"; dimensions?: [number, number]; image_url?: string; original_url?: string;
  original_path?: string; original_checksum_sha256?: string; created_at?: string; provenance?: Record<string, unknown>;
  accepted_normalisation?: NormalisationAttempt | null; normalisation_attempts?: NormalisationAttempt[];
};

export type NormalisationAttempt = { id: string; status: "queued" | "running" | "ready" | "failed"; prompt: string; quality: "low" | "medium" | "high"; model_id: string; preview_url?: string; checksum_sha256?: string; cost_usd?: number | null; elapsed_seconds?: number; error?: string | null };

export type SearchResult = Partial<InputAsset> & { id: string; label: string; pexels_photo_id?: number; selected_image_url?: string; preview_url?: string; photographer?: string };

export type StyleAsset = { id: string; asset_key?: string; label: string; role: "generation-reference" | "target-example"; checksum_sha256: string; image_url?: string; relative_path?: string };
export type PipelineStyle = {
  schema_version: number;
  identity: { family_id: string; pipeline_id?: string; style_version_id: string; version: number; state: "draft" | "locked"; label: string };
  generation: { model_id: string; execution_mode: "simulation" | "live"; quality: "low" | "medium" | "high"; prompt?: string; stages?: { normalise: { prompt: string }; stylise: { prompt: string } }; direction?: Record<string, string>; avoid?: string; requested_aspect_policy: string; reference_limit: number };
  reference_pack: { id: string; version: number; assets: StyleAsset[] };
  composition: { logical_art_size: [number, number]; default_framing: { zoom: number; offset_x: number; offset_y: number }; centering: [number, number]; requested_art_ratio: string };
  backgrounds: { default_id: string; composite_size: [number, number]; presets: Array<{ id: string; label: string; top: string; bottom: string; glow: string; glow_strength: number }> };
  renderer: { driver_id: string; driver_version?: number; logical_art_size: [number, number]; output_scale: number; palette_space: string; palette_mode?: "fixed-house" | "adaptive-hybrid"; palette: string[]; preprocess: Record<string, number>; dither: { matrix: string; strength: number; edge_threshold: number } };
  editor_descriptors: Array<Record<string, unknown>>;
  checksums: { style_sha256: string; assets?: Record<string, string> };
  provenance?: Record<string, unknown>;
};

export type PipelineVersion = {
  pipeline_id?: string; style_version_id: string; label: string; version: number; checksum_sha256: string; active: boolean;
  created_at?: string | null; execution_mode: "simulation" | "live"; model_id: string; quality: string;
  reference_count: number; renderer_id: string;
};
export type PipelineRecord = {
  pipeline_id: string; label: string; description: string; active: boolean; current_version_id: string; revision_count: number;
  revisions: Array<{ style_version_id: string; checksum_sha256: string; created_at?: string | null }>;
  style: PipelineStyle;
};
export type StyleBootstrap = { active: PipelineStyle; active_pipeline_id: string; pipelines: PipelineRecord[]; draft?: PipelineStyle | null; versions: PipelineVersion[]; driver: { id: string; label: string; output: string } };

export type Model = { id: string; name: string; description?: string; execution_mode: "simulation" | "live"; available: boolean; credentials_configured?: boolean; max_input_references: number; qualities: string[]; aspect_ratios: string[]; pricing: Array<Record<string, unknown>>; provider_name?: string; provider_slug?: string; endpoint_id?: string; endpoint_url?: string };
export type Framing = { zoom: number; offset_x: number; offset_y: number };
export type ProductionItem = {
  item_id: string; source_id: string; source_label: string; attempt_number: number; lineage_id: string; status: "queued" | "generating" | "processing" | "ready" | "failed" | "interrupted";
  error?: string | null; phase?: string; source_url?: string; source_original_url?: string; raw_foreground_url?: string; foreground_url?: string; master_url?: string; logical_art_url?: string; art_url?: string; art_checksum_sha256?: string | null; card_text: { title: string; lines: string[] };
  normalised_url?: string; normalised_checksum_sha256?: string | null; master_checksum_sha256?: string | null; render_revision: number; render_revisions: Array<Record<string, unknown>>; framing?: Framing | null; generation?: Record<string, unknown>; generation_stages?: Array<Record<string, unknown>>; render_metadata?: Record<string, unknown>; usage?: Record<string, unknown>; cost_usd?: number | null;
  accepted?: boolean; accepted_at?: string; prompt_override?: string | null; content_direction?: string | null; background_id?: string | null; background_metadata?: Record<string, unknown>; matte_metadata?: Record<string, unknown>; chroma_key?: { name: string; hex: string }; palette_mode?: "fixed-house" | "adaptive-hybrid";
  reference_stack: Array<Record<string, unknown>>; reference_urls?: Array<string | null>;
  favorite?: boolean; favorited_at?: string | null;
  hidden?: boolean; hidden_at?: string | null;
};
export type ProductionProgress = { selected_sources: number; ready_cards: number; failed_sources: number; paid_calls: number; total_attempts: number };
export type ProductionBatch = { batch_id: string; purpose: "card-production" | "style-trial"; status: string; created_at: string; updated_at: string; style_version_id: string; style_checksum_sha256: string; selected_source_ids: string[]; requested_paid_calls: number; paid_calls: number; cost_usd?: number | null; items: ProductionItem[]; progress: ProductionProgress; style_snapshot?: PipelineStyle; calibration_source_ids?: string[] | null; model?: Model; model_capabilities?: Record<string, unknown>; backend_mapping?: Record<string, unknown>; generation_authorization?: Record<string, unknown> };
export type ProductionSummary = Omit<ProductionBatch, "items" | "style_snapshot" | "selected_source_ids"> & { selected_source_ids?: string[] };
export type ProducedCard = ProductionItem & {
  batch_id: string; batch_created_at: string; purpose: ProductionBatch["purpose"];
  style_version_id: string; style_checksum_sha256: string; pipeline_id: string; pipeline_label: string; pipeline_description: string; pipeline_version?: number | null;
};

export type Bootstrap = { workspace: { inputs: InputAsset[] }; inputs: InputAsset[]; style: StyleBootstrap; batches: ProductionSummary[]; cards: ProducedCard[]; models: Model[]; integrations: { pexels: { configured: boolean }; openrouter: { configured: boolean } }; starter: { photo_ids: number[] }; normalisation: { default_prompt: string; default_quality: "low" | "medium" | "high"; active: boolean } };
