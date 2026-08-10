import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App, readRoute } from "./App";
import { api } from "./api";

const style = { schema_version: 3, identity: { family_id: "amiga-ocs-portrait", pipeline_id: "face-free-style-board", style_version_id: "style-face-free", version: 3, state: "locked", label: "Face-free Style Board" }, generation: { model_id: "live-model", execution_mode: "live", quality: "low", prompt: "Apply only the visual language.", requested_aspect_policy: "28:23", reference_limit: 9 }, reference_pack: { id: "pack", version: 1, assets: [{ id: "gen", label: "Face-free board", role: "generation-reference" as const, checksum_sha256: "gen", image_url: "/gen.png" }, { id: "target", label: "Target", role: "target-example" as const, checksum_sha256: "target", image_url: "/target.png" }] }, composition: { logical_art_size: [168, 138] as [number, number], default_framing: { zoom: 1, offset_x: 0, offset_y: 0 }, centering: [0.5, 0.44] as [number, number], requested_art_ratio: "28:23" }, renderer: { driver_id: "amiga-ocs", logical_art_size: [168, 138] as [number, number], output_scale: 2, palette_space: "Amiga", palette: ["#111111"], preprocess: {}, dither: { matrix: "bayer-4x4", strength: .62, edge_threshold: .09 } }, card_assembly: { driver_id: "amiga-ocs", logical_card_size: [210, 300] as [number, number], output_scale: 2, layout: {}, text: {} }, editor_descriptors: [], checksums: { style_sha256: "style-checksum" } };
Object.assign(style, { backgrounds: { default_id: "warm-parchment", composite_size: [336, 276], presets: [{ id: "warm-parchment", label: "Warm parchment", top: "#d3be8e", bottom: "#674d34", glow: "#ecd6a5", glow_strength: .22 }, { id: "cool-slate", label: "Cool slate", top: "#5a7076", bottom: "#1c272d", glow: "#8b978f", glow_strength: .22 }] } });
const portraitStyle = { ...style, identity: { ...style.identity, pipeline_id: "portrait-style-reference", style_version_id: "style-portrait", version: 1, label: "Portrait Style Reference" }, reference_pack: { ...style.reference_pack, assets: [{ ...style.reference_pack.assets[0], id: "old-gen", label: "Original portrait style reference", checksum_sha256: "old-gen" }, style.reference_pack.assets[1]] }, checksums: { style_sha256: "portrait-checksum" } };
const revisions = (id: string, checksum: string) => [{ style_version_id: id, checksum_sha256: checksum, created_at: "2026-08-01T00:00:00Z" }];
const pipelines = [
  { pipeline_id: "face-free-style-board", label: "Face-free Style Board", description: "Uses the face-free board.", active: true, current_version_id: style.identity.style_version_id, revision_count: 1, revisions: revisions(style.identity.style_version_id, style.checksums.style_sha256), style },
  { pipeline_id: "portrait-style-reference", label: "Portrait Style Reference", description: "Uses the original portrait reference.", active: false, current_version_id: portraitStyle.identity.style_version_id, revision_count: 1, revisions: revisions(portraitStyle.identity.style_version_id, portraitStyle.checksums.style_sha256), style: portraitStyle },
];
const versions = pipelines.map((pipeline) => ({ pipeline_id: pipeline.pipeline_id, style_version_id: pipeline.current_version_id, label: pipeline.label, version: pipeline.style.identity.version, checksum_sha256: pipeline.style.checksums.style_sha256, active: pipeline.active, created_at: "2026-08-01T00:00:00Z", execution_mode: "live" as const, model_id: "live-model", quality: "low", reference_count: 1, renderer_id: "amiga-ocs" }));
const model = { id: "live-model", name: "Live image model", execution_mode: "live" as const, available: true, credentials_configured: true, max_input_references: 9, qualities: ["low"], aspect_ratios: ["5:4"], pricing: [{ cost_usd: 0.04 }] };
const input = { id: "source-1", label: "Ada", status: "ready" as const, image_url: "/ada.png", original_url: "/ada-original.png", accepted_normalisation: { id: "norm-1", status: "ready" as const, prompt: "Keep Ada", quality: "low" as const, model_id: "live-model", preview_url: "/ada.png" } };
const base = { workspace: { inputs: [input] }, inputs: [input], style: { active: style, active_pipeline_id: "face-free-style-board", pipelines, draft: null, versions, driver: { id: "amiga-ocs", label: "Amiga OCS", output: "420×600 final cards" } }, batches: [], cards: [], favorites: [], models: [model], integrations: { pexels: { configured: false }, openrouter: { configured: true } }, starter: { photo_ids: [] }, normalisation: { default_prompt: "Preserve the exact subject.", default_quality: "low" as const, active: false } };

function produced(overrides: Record<string, unknown> = {}) {
  return { item_id: "item-1", source_id: "source-1", source_label: "Ada", attempt_number: 1, lineage_id: "lineage", status: "ready" as const, source_url: "/ada.png", master_url: "/master.png", art_url: "/art.png", card_url: "/card.png", card_checksum_sha256: "card-checksum", render_revision: 1, render_revisions: [], framing: { zoom: 1, offset_x: 0, offset_y: 0 }, generation: { execution_mode: "live", model: "live-model" }, reference_stack: [], batch_id: "batch-1", batch_created_at: "2026-08-02T00:00:00Z", purpose: "card-production" as const, style_version_id: style.identity.style_version_id, style_checksum_sha256: "style-checksum", pipeline_id: "face-free-style-board", pipeline_label: "Face-free Style Board", pipeline_description: "Uses the face-free board.", pipeline_version: 2, favorite: false, favorited_at: null, ...overrides };
}

let container: HTMLDivElement; let root: Root;
beforeEach(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(() => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks(); window.location.hash = ""; });

describe("pipeline workbench", () => {
  it("uses Inputs, Pipelines, Candidates, Batches, and Collection routes and redirects legacy runs", () => {
    window.location.hash = "#frames/card-1";
    expect(readRoute()).toEqual({ view: "candidates" });
    window.location.hash = "#style";
    expect(readRoute()).toEqual({ view: "pipelines", id: undefined });
    window.location.hash = "#pipelines/portrait-style-reference";
    expect(readRoute()).toEqual({ view: "pipelines", id: "portrait-style-reference", itemId: undefined });
    window.location.hash = "#cards/batch-1/item-1";
    expect(readRoute()).toEqual({ view: "candidates", id: "batch-1", itemId: "item-1" });
    window.location.hash = "#collection";
    expect(readRoute()).toEqual({ view: "collection", id: undefined, itemId: undefined });
    window.location.hash = "#batches/batch-1/item-1";
    expect(readRoute()).toEqual({ view: "batches", id: "batch-1", itemId: "item-1" });
    window.location.hash = "#run/batch-1";
    expect(readRoute()).toEqual({ view: "batches", id: "batch-1" });
  });

  it("keeps only the simple top-level navigation", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue(base as never);
    await act(async () => root.render(<App />));
    expect(container.querySelectorAll('.app-header nav button')).toHaveLength(5);
    expect(container.textContent).toContain("Inputs");
    expect(container.querySelector(".pipeline-rail")).toBeFalsy();
  });

  it("shows every batch item in a clickable raw archive", async () => {
    const batch = { batch_id: "batch-raw", purpose: "card-production" as const, status: "ready", created_at: "2026-08-10T00:00:00Z", updated_at: "2026-08-10T00:01:00Z", style_version_id: "style-face-free", style_checksum_sha256: "style-checksum", selected_source_ids: ["source-1"], requested_paid_calls: 1, paid_calls: 1, progress: { selected_sources: 1, ready_cards: 1, approved_cards: 0, failed_sources: 0, paid_calls: 1, total_attempts: 1 }, items: [produced({ batch_id: undefined, accepted: false, raw_foreground_url: "/raw.png", foreground_url: "/foreground.png", logical_art_url: "/logical.png" })] };
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, batches: [batch] } as never);
    vi.spyOn(api, "getProduction").mockResolvedValue({ batch } as never);
    await act(async () => { window.location.hash = "#batches"; root.render(<App />); });
    expect(container.textContent).toContain("Every run, whether accepted or not.");
    const result = container.querySelector(".raw-result");
    expect(result).toBeTruthy();
    await act(async () => { result?.dispatchEvent(new MouseEvent("click", { bubbles: true })); window.dispatchEvent(new HashChangeEvent("hashchange")); });
    expect(container.querySelector('[role="dialog"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Raw model output"]')?.getAttribute("src")).toBe("/raw.png");
    expect(container.textContent).toContain("not accepted");
  });

  it("opens an accepted Input in the preparation dialog", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue(base as never);
    await act(async () => root.render(<App />));
    await act(async () => container.querySelector(".source-select")?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(container.querySelector('[role="dialog"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Original"]')).toBeTruthy();
    expect(container.textContent).toContain("Preparation prompt");
    expect(container.textContent).toContain("Generate preview");
  });

  it("keeps only the newest three mixed-pipeline cards in each source pack", async () => {
    const other = produced({ item_id: "item-2", batch_id: "batch-2", pipeline_id: "portrait-style-reference", pipeline_label: "Portrait Style Reference", pipeline_description: "Uses the original portrait reference.", style_version_id: "style-portrait", style_checksum_sha256: "portrait-checksum", pipeline_version: 1, card_url: "/portrait-card.png" });
    const third = produced({ item_id: "item-3", batch_id: "batch-3", card_url: "/third-card.png" });
    const old = produced({ item_id: "item-old", batch_id: "batch-old", card_url: "/old-card.png" });
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, cards: [produced(), other, third, old] } as never);
    await act(async () => { window.location.hash = "#candidates"; root.render(<App />); });
    expect(container.textContent).toContain("Next. Next. Ooh, a good one.");
    expect(container.querySelector('img[alt="Ada Face-free Style Board candidate 1"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Ada Portrait Style Reference candidate 2"]')).toBeTruthy();
    expect(container.querySelectorAll(".candidate-pack .generation-card")).toHaveLength(3);
    expect(container.querySelector('img[src="/old-card.png"]')).toBeFalsy();
    expect(container.querySelector(".pack-source")).toBeFalsy();
    expect(container.querySelector('.source-peek[aria-label^="Input: Ada"]')).toBeTruthy();
    expect(container.textContent).toContain("1 older stored");
    expect(container.textContent?.toLowerCase()).not.toContain("baseline");
    expect(container.textContent?.toLowerCase()).not.toContain("strategy");
  });

  it("puts the newest accepted Input pack first", async () => {
    const older = { ...base.inputs[0], created_at: "2026-08-01T00:00:00Z" };
    const newest = { ...input, id: "source-2", label: "Book", image_url: "/book.png", created_at: "2026-08-05T00:00:00Z" };
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, workspace: { inputs: [older, newest] }, inputs: [older, newest] } as never);
    await act(async () => { window.location.hash = "#candidates"; root.render(<App />); });
    expect(container.querySelector(".candidate-pack .source-peek")?.getAttribute("aria-label")).toContain("Input: Book");
  });

  it("imports a search result as a pending Input", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ input: { id: "input-1" } }) } as Response);
    await api.importInput({ id: "result-1", label: "Book", pexels_photo_id: 42, selected_image_url: "/book.png" });
    const body = JSON.parse(String(request.mock.calls[0][1]?.body));
    expect(body.candidate.pexels_photo_id).toBe(42);
    expect(request.mock.calls[0][0]).toContain("/inputs/import");
  });

  it("shows an incoming card in its source pack while generation is active", async () => {
    const activeBatch = { batch_id: "batch-active", purpose: "card-production", status: "running", created_at: "2026-08-04T00:00:00Z", updated_at: "2026-08-04T00:00:01Z", style_version_id: style.identity.style_version_id, style_checksum_sha256: style.checksums.style_sha256, selected_source_ids: ["source-1"], requested_paid_calls: 1, paid_calls: 1, progress: { selected_sources: 1, ready_cards: 0, approved_cards: 0, failed_sources: 0, paid_calls: 1, total_attempts: 1 } };
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, batches: [activeBatch], cards: [produced()] } as never);
    await act(async () => { window.location.hash = "#candidates"; root.render(<App />); });
    expect(container.querySelector('.pending-card[role="status"][aria-label="Generating a new card for Ada"] .spinner')).toBeTruthy();
    expect(container.textContent).not.toContain("Producing new generations");
  });

  it("tolerates a legacy active batch summary without source IDs", async () => {
    const legacyBatch = { batch_id: "batch-legacy", purpose: "card-production", status: "running", created_at: "2026-08-04T00:00:00Z", updated_at: "2026-08-04T00:00:01Z", style_version_id: style.identity.style_version_id, style_checksum_sha256: style.checksums.style_sha256, requested_paid_calls: 1, paid_calls: 1, progress: { selected_sources: 1, ready_cards: 0, approved_cards: 0, failed_sources: 0, paid_calls: 1, total_attempts: 1 } };
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, batches: [legacyBatch], cards: [produced()] } as never);
    await act(async () => { window.location.hash = "#candidates"; root.render(<App />); });
    expect(container.querySelector(".candidate-pack")).toBeTruthy();
    expect(container.querySelector(".pending-card")).toBeFalsy();
  });

  it("previews a prompted candidate before accepting it", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue(base as never);
    vi.spyOn(api, "createProduction").mockResolvedValue({ batch: { batch_id: "batch-2" } } as never);
    await act(async () => { window.location.hash = "#candidates"; root.render(<App />); });
    const open = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Generate new"));
    await act(async () => open?.click());
    expect(container.querySelector('[aria-labelledby="candidate-dialog-title"]')).toBeTruthy();
    const preview = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Generate preview"));
    await act(async () => preview?.click());
    expect(container.textContent).toContain("Content direction");
    expect(api.createProduction).toHaveBeenCalledWith(["source-1"], "face-free-style-board", true, "", "warm-parchment");
  });

  it("adds only an accepted candidate preview to the pack", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue(base as never);
    vi.spyOn(api, "createProduction").mockResolvedValue({ batch: { batch_id: "preview-batch", status: "ready", items: [{ item_id: "preview-item", status: "ready", master_url: "/preview-master.png", card_url: "/preview-card.png" }] } } as never);
    vi.spyOn(api, "acceptCandidate").mockResolvedValue({ batch: {} } as never);
    await act(async () => { window.location.hash = "#candidates"; root.render(<App />); });
    const open = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Generate new"));
    await act(async () => open?.click());
    const preview = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Generate preview"));
    await act(async () => preview?.click());
    expect(container.querySelector('img[alt="Candidate preview"]')).toBeTruthy();
    const accept = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Add to pack"));
    await act(async () => accept?.click());
    expect(api.acceptCandidate).toHaveBeenCalledWith("preview-batch", "preview-item");
  });

  it("favorites candidates and renders saved cards in Collection", async () => {
    const saved = produced({ favorite: true, favorited_at: "2026-08-03T00:00:00Z" });
    vi.spyOn(api, "bootstrap").mockResolvedValueOnce({ ...base, cards: [produced()] } as never).mockResolvedValue({ ...base, cards: [saved], favorites: [saved] } as never);
    vi.spyOn(api, "favorite").mockResolvedValue({ favorite: {} } as never);
    await act(async () => { window.location.hash = "#candidates"; root.render(<App />); });
    const favorite = container.querySelector('button[aria-label="Save to Collection"]');
    await act(async () => favorite?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(api.favorite).toHaveBeenCalledWith("batch-1", "item-1");
    await act(async () => { window.location.hash = "#collection"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
    expect(container.textContent).toContain("Your saved candidate cards");
    expect(container.querySelector('img[alt="Ada from Face-free Style Board"]')).toBeTruthy();
  });

  it("opens a candidate as a complete source-to-card inspector", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, cards: [produced({ foreground_url: "/foreground.png", background_id: "warm-parchment" })] } as never);
    await act(async () => { window.location.hash = "#candidates/batch-1/item-1"; root.render(<App />); });
    expect(container.textContent).toContain("Candidate details");
    expect(container.querySelector('[role="dialog"][aria-modal="true"]')).toBeTruthy();
    expect(container.textContent).toContain("Foreground");
    expect(container.textContent).toContain("Background composite");
    expect(container.textContent).toContain("Warm parchment");
    expect(container.querySelector('img[alt="Candidate card"]')?.getAttribute("src")).toBe("/card.png");
    expect(container.textContent).toContain("Adaptive · 10 anchors + 22 image colours");
    expect(container.textContent).not.toContain("Zoom");
    expect(container.textContent).not.toContain("Horizontal");
    expect(container.textContent).not.toContain("Vertical");
    expect(container.textContent).toContain("Preview changes");
    expect(container.textContent).toContain("Save changes");
    expect(container.textContent).toContain("Save to Collection");
  });

  it("shows graceful placeholders for legacy candidate artifacts", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, cards: [produced({ source_url: undefined, foreground_url: undefined, master_url: undefined, card_url: undefined })] } as never);
    await act(async () => { window.location.hash = "#candidates/batch-1/item-1"; root.render(<App />); });
    expect(container.textContent).toContain("Input unavailable");
    expect(container.textContent).toContain("Foreground unavailable");
    expect(container.textContent).toContain("Composite unavailable");
    expect(container.textContent).toContain("Card unavailable");
  });

  it("previews candidate edits without saving them", async () => {
    const card = produced({ foreground_url: "/foreground.png", background_id: "warm-parchment" });
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, cards: [card] } as never);
    vi.spyOn(api, "previewFraming").mockResolvedValue({ preview: { ...card, master_url: "/preview-composite.png", card_url: "/preview-card.png" } } as never);
    await act(async () => { window.location.hash = "#candidates/batch-1/item-1"; root.render(<App />); });
    const preview = [...container.querySelectorAll("button")].find((button) => button.textContent === "Preview changes");
    await act(async () => preview?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(api.previewFraming).toHaveBeenCalled();
    expect(container.querySelector('img[alt="Candidate card"]')?.getAttribute("src")).toBe("/preview-card.png");
    expect(container.textContent).toContain("Preview card · unsaved");
  });

  it("starts candidate inspection from the accepted Input", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, cards: [produced()] } as never);
    await act(async () => { window.location.hash = "#candidates/batch-1/item-1"; root.render(<App />); });
    expect(container.querySelector('img[alt="Prepared Input"]')?.getAttribute("src")).toBe("/ada.png");
    expect(container.querySelector('img[alt="Normalised source"]')).toBeFalsy();
  });

  it("exposes editing on the selected real pipeline", async () => {
    const draft = { ...style, schema_version: 3, identity: { ...style.identity, state: "draft" as const, style_version_id: "draft-style" }, generation: { ...style.generation, prompt: "Apply only the visual language." }, provenance: { derived_from: style.identity.style_version_id } };
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, style: { ...base.style, draft } } as never);
    vi.spyOn(api, "updateDraft").mockResolvedValue({ style: draft } as never);
    window.location.hash = "#pipelines/face-free-style-board";
    await act(async () => root.render(<App />));
    expect(container.textContent).toContain("Generation model");
    expect(container.textContent).toContain("Style prompt");
    expect(container.textContent).not.toContain("Normalise prompt");
    expect(container.textContent).not.toContain("identity to retain");
    expect(container.textContent).toContain("Amiga renderer and card assembly");
    expect(container.textContent).toContain("1 saved revision");
  });
});
