export type Direction = {
  medium_brushwork: string;
  lighting: string;
  background: string;
  composition: string;
  colour: string;
  detail: string;
  identity: string;
};

export type Source = {
  id: string;
  label: string;
  relative_path: string;
  image_url: string;
  dimensions: [number, number];
  created_at: string;
  provenance: { kind: string; [key: string]: unknown };
};

export type SearchResult = {
  pexels_photo_id: number;
  photographer?: string;
  selected_image_url: string;
  original_image_url?: string;
  preview_url: string;
  query?: string;
  provenance: { kind: "pexels"; [key: string]: unknown };
};

export type Reference = {
  id: string;
  label: string;
  relative_path: string;
  image_url: string;
  checksum_sha256: string;
  position?: number;
  dimensions?: [number, number];
  provenance?: { kind: string; [key: string]: unknown };
};

export type Recipe = {
  id: string;
  name: string;
  model: string;
  execution_mode: "live" | "simulation";
  quality: "low" | "medium" | "high";
  change_note: string;
  direction: Direction;
  avoid: string;
  aspect_policy: "card-window";
  reference_ids: string[];
  references: Reference[];
  created_at: string;
  updated_at: string;
};

export type Workspace = {
  version: number;
  sources: Source[];
  benchmark_source_ids: string[];
  references: Reference[];
  recipes: Recipe[];
  active_recipe_id: string | null;
  candidate_selection?: CandidateSelection | null;
  active_set_id?: string | null;
  links: { runs: string; cards: string };
};

export type Model = {
  id: string;
  name: string;
  description?: string;
  max_input_references: number;
  aspect_ratios: string[];
  qualities: string[];
  supports_negative_prompt: boolean;
  supports_reference_roles: boolean;
  execution_mode: "live" | "simulation";
  available: boolean;
  supported_parameters: Record<string, { type: string; values?: string[]; min?: number; max?: number }>;
  supports_streaming: boolean;
  pricing: Array<{ billable: string; unit: string; cost_usd: number; variant?: string }>;
  provider_name?: string;
  provider_slug?: string;
  provider_tag?: string;
};

export type RunSummary = {
  run_id: string;
  recipe_id: string;
  recipe_name: string;
  status: string;
  source_count: number;
  verdict: string;
  created_at: string;
  completed_calls: number;
  total_calls: number;
  execution_mode: "live" | "simulation";
  model: string;
  cost_usd: number;
  purpose?: "exploration" | "finish" | "set-production";
  purpose_label?: string;
  is_baseline?: boolean;
  selection_id?: string;
  selection_revision?: number;
};

export type RunItem = {
  item_id: string;
  source_id: string;
  source_label: string;
  output_index: number;
  status: string;
  output_path?: string;
  output_url?: string;
  thumbnail_url?: string;
  source_url?: string;
  dimensions?: [number, number];
  seed?: number;
  elapsed_seconds?: number;
  backend?: string;
  model?: string;
  error?: string;
  usage?: Record<string, number>;
  cost_usd?: number;
};

export type Run = RunSummary & {
  updated_at: string;
  recipe_snapshot: Recipe;
  resolved_instruction: string;
  benchmark_source_ids: string[];
  sources_snapshot: Array<Source & { input_url?: string; input_path?: string; input_checksum_sha256?: string }>;
  references_snapshot: Array<Reference & { input_url?: string; input_path?: string; input_checksum_sha256?: string }>;
  model: string;
  execution_mode: "live" | "simulation";
  quality: string;
  requested_aspect_ratio: string;
  effective_aspect_ratio: string;
  backend_capabilities: Record<string, unknown>;
  backend_mapping: Record<string, unknown>;
  outputs_per_source: number;
  total_calls: number;
  completed_calls: number;
  items: RunItem[];
  verdict: "unreviewed" | "coherent" | "mixed" | "not-useful";
  note: string;
  usage: Record<string, number>;
  cost_usd: number;
  model_metadata: Model;
  purpose?: "exploration" | "finish" | "set-production";
  selection_revision?: number;
  candidate_inputs?: CandidateSelectionItem[];
  reference_stack?: Array<Record<string, unknown>>;
};

export type CandidateSelectionItem = {
  order: number;
  run_id: string;
  item_id: string;
  run_item_id?: string;
  source_id: string;
  source_label: string;
  output_path: string;
  output_url?: string | null;
  output_checksum_sha256: string;
  output_dimensions?: [number, number];
  source_path?: string;
  source_url?: string | null;
  recipe_id?: string;
  recipe_name?: string;
  recipe_snapshot?: Recipe;
  references_snapshot?: Reference[];
};

export type CandidateSelection = {
  selection_id: string;
  revision: number;
  created_at: string;
  updated_at: string;
  source_ids: string[];
  selected_items: CandidateSelectionItem[];
  items?: CandidateSelectionItem[];
};

export type FinishSummary = {
  finish_id: string;
  version: number;
  state: "locked" | string;
  trial_run_id: string;
  selection_id: string;
  selection_revision: number;
  candidate_count: number;
  reference_count?: number;
  model?: string;
  recipe_name?: string;
  change_note?: string;
  cost_usd: number;
  locked_at?: string;
};

export type Finish = FinishSummary & {
  candidate_inputs: CandidateSelectionItem[];
  approved_output_items: Array<CandidateSelectionItem & { trial_item_id: string }>;
  recipe_snapshot: Recipe;
  references_snapshot: Reference[];
  resolved_instruction: string;
  model_metadata: Model;
  usage: Record<string, number>;
  backend_mapping: Record<string, unknown>;
};

export type SetItem = {
  set_item_id: string;
  order: number;
  source_id: string;
  source_label: string;
  status: "queued" | "complete" | "failed" | "interrupted" | string;
  anchor: boolean;
  finish_id: string;
  source_snapshot_path: string;
  source_url?: string | null;
  art_source_path?: string | null;
  art_url?: string | null;
  output_url?: string | null;
  art_checksum_sha256?: string | null;
  production_run_id?: string | null;
  production_item_id?: string | null;
  error?: string | null;
  reference_stack?: Array<Record<string, unknown>>;
};

export type SetSummary = {
  set_id: string;
  name: string;
  finish_id: string;
  state: "building" | "ready-with-errors" | "ready" | string;
  source_count: number;
  complete_count: number;
  failed_count: number;
  production_runs: string[];
  cost_usd: number;
  active?: boolean;
};

export type PortraitSet = SetSummary & {
  items: SetItem[];
  source_ids: string[];
  recipe_snapshot: Recipe;
  references_snapshot: Reference[];
};

export type Card = {
  card_id: string;
  run_id: string;
  run_item_id: string;
  label: string;
  template_id: string;
  archetype: "bust" | "tall" | "torso";
  framing: { zoom: number; offset_x: number; offset_y: number };
  decision: "working" | "keep" | "discard";
  render_path: string;
  render_url: string;
  art_render_path: string;
  art_url?: string;
  source_output_path: string;
  source_url?: string;
  source_dimensions?: [number, number];
  render_dimensions?: [number, number];
  transform?: Record<string, unknown>;
  treatment: "painterly" | "estate-pixel-v1";
  treatment_version: string;
  render_metadata?: Record<string, unknown>;
  source_run_provenance?: Record<string, unknown>;
  selected_preview_id?: string;
  created_at: string;
  updated_at: string;
  set_id?: string | null;
  set_item_id?: string | null;
  finish_id?: string | null;
  legacy?: boolean;
};

export type CardPreviewOption = {
  option_id: string;
  preset: "bust" | "tall" | "torso";
  preset_label: string;
  treatment: Card["treatment"];
  treatment_label: string;
  framing: Card["framing"];
  render_path: string;
  render_url: string;
  art_render_path: string;
  art_url: string;
  render_dimensions: [number, number];
  render_metadata: Record<string, unknown>;
};

export type Bootstrap = {
  ok: boolean;
  workspace: Workspace;
  runs: RunSummary[];
  cards: Card[];
  models: Model[];
  integrations: { pexels: { configured: boolean }; openrouter: { configured: boolean } };
  starter: { photo_ids: number[] };
  candidate_selection?: CandidateSelection | null;
  finishes?: FinishSummary[];
  sets?: SetSummary[];
  active_set_id?: string | null;
  baseline_exploration_run_id?: string | null;
};
