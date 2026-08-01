import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App, readRoute } from "./App";
import { api } from "./api";

const style = { identity: { family_id: "amiga-ocs-portrait", style_version_id: "style_amiga_ocs_portrait_v2", version: 2, state: "locked", label: "Amiga OCS Neutral Portrait v2" }, generation: { model_id: "live-model", execution_mode: "live", quality: "low", direction: { identity_to_retain: "Portrait" }, avoid: "", requested_aspect_policy: "28:23", reference_limit: 9 }, reference_pack: { id: "pack", version: 1, assets: [{ id: "gen", label: "Generation reference", role: "generation-reference" as const, checksum_sha256: "gen", image_url: "/gen.png" }, { id: "target", label: "Target", role: "target-example" as const, checksum_sha256: "target", image_url: "/target.png" }] }, composition: { logical_art_size: [168, 138] as [number, number], default_framing: { zoom: 1, offset_x: 0, offset_y: 0 }, centering: [0.5, 0.44] as [number, number], requested_art_ratio: "28:23" }, renderer: { driver_id: "amiga-ocs", logical_art_size: [168, 138] as [number, number], output_scale: 2, palette_space: "Amiga", palette: ["#111111"], preprocess: {}, dither: { matrix: "bayer-4x4", strength: .62, edge_threshold: .09 } }, card_assembly: { driver_id: "amiga-ocs", logical_card_size: [210, 300] as [number, number], output_scale: 2, layout: {}, text: {} }, editor_descriptors: [], checksums: { style_sha256: "style-checksum" } };
const version = { style_version_id: style.identity.style_version_id, label: style.identity.label, version: 2, checksum_sha256: "style-checksum", active: true, created_at: "2026-08-01T00:00:00Z", execution_mode: "live" as const, model_id: "live-model", quality: "low", reference_count: 1, renderer_id: "amiga-ocs" };
const model = { id: "live-model", name: "Live image model", execution_mode: "live" as const, available: true, credentials_configured: true, max_input_references: 9, qualities: ["low"], aspect_ratios: ["5:4"], pricing: [{ cost_usd: 0.04 }] };
const base = { workspace: { sources: [{ id: "source-1", label: "Ada", image_url: "/ada.png" }], benchmark_source_ids: ["source-1"] }, sources: [{ id: "source-1", label: "Ada", image_url: "/ada.png" }], selected_source_ids: ["source-1"], style: { active: style, draft: null, versions: [version], driver: { id: "amiga-ocs", label: "Amiga OCS", output: "420×600 final cards" } }, batches: [], cards: [], models: [model], integrations: { pexels: { configured: false }, openrouter: { configured: true } }, starter: { photo_ids: [] } };

function produced(overrides: Record<string, unknown> = {}) {
  return { item_id: "item-1", source_id: "source-1", source_label: "Ada", attempt_number: 1, lineage_id: "lineage", status: "ready" as const, source_url: "/ada.png", master_url: "/master.png", art_url: "/art.png", card_url: "/card.png", card_checksum_sha256: "card-checksum", render_revision: 1, render_revisions: [], framing: { zoom: 1, offset_x: 0, offset_y: 0 }, generation: { execution_mode: "live", model: "live-model" }, reference_stack: [], batch_id: "batch-1", batch_created_at: "2026-08-02T00:00:00Z", purpose: "card-production" as const, style_version_id: style.identity.style_version_id, style_checksum_sha256: "style-checksum", pipeline_label: style.identity.label, pipeline_version: 2, strategy_id: "interpretive-redraw" as const, strategy_label: "Interpretive redraw", strategy_description: "Image-model redraw followed by Amiga rendering", ...overrides };
}

let container: HTMLDivElement; let root: Root;
beforeEach(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(() => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks(); window.location.hash = ""; });

describe("pipeline workbench", () => {
  it("uses Sources, Pipelines, and Cards routes and migrates the old style route", () => {
    window.location.hash = "#frames/card-1";
    expect(readRoute()).toEqual({ view: "cards" });
    window.location.hash = "#style";
    expect(readRoute()).toEqual({ view: "pipelines", id: undefined });
    window.location.hash = "#pipelines/style-1";
    expect(readRoute()).toEqual({ view: "pipelines", id: "style-1", itemId: undefined });
    window.location.hash = "#cards/batch-1/item-1";
    expect(readRoute()).toEqual({ view: "cards", id: "batch-1", itemId: "item-1" });
  });

  it("surfaces the Sources to Pipelines to Cards flow", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue(base as never);
    await act(async () => root.render(<App />));
    expect(container.textContent).toContain("01 · inputs");
    expect(container.textContent).toContain("02 · transform");
    expect(container.textContent).toContain("03 · output");
    expect(container.textContent).toContain("Amiga OCS Neutral Portrait v2");
    expect(container.textContent).toContain("Run 1 source");
  });

  it("starts paid pipeline runs immediately without a confirmation dialog", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue(base as never);
    vi.spyOn(api, "createProduction").mockResolvedValue({ batch: { batch_id: "batch-1" } } as never);
    const confirm = vi.spyOn(window, "confirm");
    await act(async () => root.render(<App />));
    const run = [...container.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Run 1 source");
    await act(async () => run?.click());
    expect(confirm).not.toHaveBeenCalled();
    expect(api.createProduction).toHaveBeenCalledWith(["source-1"], style.identity.style_version_id, true);
  });

  it("collapses configurations into source-stable strategies and no approval workflow", async () => {
    const older = produced({ item_id: "item-old", batch_id: "batch-old", batch_created_at: "2026-08-01T00:00:00Z", style_version_id: "style-v1", style_checksum_sha256: "old-checksum", pipeline_label: "Neutral pipeline v1", pipeline_version: 1, card_url: "/old-card.png", generation: { execution_mode: "simulation", model: "fake/painterly-deterministic" }, strategy_id: "direct-render", strategy_label: "Direct render", strategy_description: "Source-led deterministic rendering baseline" });
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, cards: [produced(), older] } as never);
    await act(async () => { window.location.hash = "#cards"; root.render(<App />); });
    expect(container.textContent).toContain("Two strategies, every generation");
    expect(container.textContent).toContain("2 strategies · 2 generations");
    expect(container.querySelector('img[alt="Ada Interpretive redraw generation 1"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Ada Direct render generation 1"]')).toBeTruthy();
    expect(container.textContent).not.toContain("Approve");
    expect(container.textContent).not.toContain("approved cards");
  });

  it("keeps every generation while folding draft checksums into one strategy", async () => {
    const first = produced({ item_id: "first", batch_id: "first-batch", style_version_id: "draft-1", style_checksum_sha256: "checksum-one", pipeline_label: "Working pipeline", pipeline_version: null });
    const second = produced({ item_id: "second", batch_id: "second-batch", batch_created_at: "2026-08-01T23:00:00Z", style_version_id: "draft-1", style_checksum_sha256: "checksum-two", pipeline_label: "Working pipeline", pipeline_version: null });
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, cards: [first, second] } as never);
    await act(async () => { window.location.hash = "#cards"; root.render(<App />); });
    expect(container.textContent).toContain("1 strategy · 2 generations");
    expect(container.textContent).toContain("2 configurations");
    expect(container.querySelectorAll('img[alt^="Ada Interpretive redraw generation"]')).toHaveLength(2);
  });

  it("opens a produced asset as a complete source-to-card stage inspector", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, cards: [produced()] } as never);
    await act(async () => { window.location.hash = "#cards/batch-1/item-1"; root.render(<App />); });
    expect(container.textContent).toContain("Generated master");
    expect(container.textContent).toContain("Rendered art");
    expect(container.textContent).toContain("Save framing · no generation");
    expect(container.textContent).toContain("Run details");
    expect(document.querySelector("details")?.open).toBe(false);
  });

  it("blocks normal source runs when the active pipeline is simulation-only", async () => {
    const previewStyle = { ...style, generation: { ...style.generation, model_id: "fake/amiga-ocs-deterministic", execution_mode: "simulation" as const } };
    const simulation = { id: "fake/amiga-ocs-deterministic", name: "Simulation", execution_mode: "simulation" as const, available: true, credentials_configured: true, max_input_references: 9, qualities: ["low"], aspect_ratios: ["5:4"], pricing: [{ cost_usd: 0 }] };
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, style: { ...base.style, active: previewStyle }, models: [simulation] } as never);
    await act(async () => root.render(<App />));
    expect(container.textContent).toContain("simulation-only");
    const run = [...container.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Run 1 source");
    expect(run?.disabled).toBe(true);
  });

  it("exposes pipeline provider and renderer controls on the working pipeline", async () => {
    const draft = { ...style, identity: { ...style.identity, state: "draft" as const, style_version_id: "draft-style" } };
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, style: { ...base.style, draft } } as never);
    vi.spyOn(api, "updateDraft").mockResolvedValue({ style: draft } as never);
    window.location.hash = "#pipelines";
    await act(async () => root.render(<App />));
    expect(container.textContent).toContain("Generation model");
    expect(container.textContent).toContain("Amiga renderer and card assembly");
    expect([...container.querySelectorAll("option")].some((option) => option.textContent?.includes("Live image model"))).toBe(true);
  });
});
