import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App, readRoute } from "./App";
import { api } from "./api";

const style = { identity: { family_id: "amiga-ocs-portrait", style_version_id: "style_amiga_ocs_portrait_v1", version: 1, state: "locked", label: "Amiga OCS Portrait v1" }, generation: { model_id: "fake/painterly-deterministic", execution_mode: "simulation", quality: "low", direction: { intent: "Portrait" }, avoid: "", requested_aspect_policy: "28:23", reference_limit: 9 }, reference_pack: { id: "pack", version: 1, assets: [{ id: "gen", label: "Generation reference", role: "generation-reference" as const, checksum_sha256: "gen", image_url: "/gen.png" }, { id: "target", label: "Target", role: "target-example" as const, checksum_sha256: "target", image_url: "/target.png" }] }, composition: { logical_art_size: [168, 138] as [number, number], default_framing: { zoom: 1, offset_x: 0, offset_y: 0 }, centering: [0.5, 0.44] as [number, number], requested_art_ratio: "28:23" }, renderer: { driver_id: "amiga-ocs", logical_art_size: [168, 138] as [number, number], output_scale: 2, palette_space: "Amiga", palette: ["#111111"], preprocess: {}, dither: { matrix: "bayer-4x4", strength: .62, edge_threshold: .09 } }, card_assembly: { driver_id: "amiga-ocs", logical_card_size: [210, 300] as [number, number], output_scale: 2, layout: {}, text: {} }, editor_descriptors: [], checksums: { style_sha256: "style-checksum" } };
const base = { workspace: { sources: [{ id: "source-1", label: "Ada", image_url: "/ada.png" }], benchmark_source_ids: ["source-1"] }, sources: [{ id: "source-1", label: "Ada", image_url: "/ada.png" }], selected_source_ids: ["source-1"], style: { active: style, draft: null, versions: [], driver: { id: "amiga-ocs", label: "Amiga OCS", output: "420×600 final cards" } }, batches: [], cards: [], models: [{ id: "fake/painterly-deterministic", name: "Simulation", execution_mode: "simulation" as const, available: true, max_input_references: 9, qualities: ["low"], aspect_ratios: ["5:4"], pricing: [{ cost_usd: 0 }] }], integrations: { pexels: { configured: false }, openrouter: { configured: false } }, starter: { photo_ids: [] } };

let container: HTMLDivElement; let root: Root;
beforeEach(() => { container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container); });
afterEach(() => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks(); window.location.hash = ""; });

describe("unified workbench", () => {
  it("keeps only Sources, Cards, and Style Studio routes", () => {
    window.location.hash = "#frames/card-1";
    expect(readRoute()).toEqual({ view: "cards" });
    window.location.hash = "#style";
    expect(readRoute()).toEqual({ view: "style" });
    window.location.hash = "#cards/batch-1/item-1";
    expect(readRoute()).toEqual({ view: "cards", id: "batch-1", itemId: "item-1" });
  });

  it("shows the selected-source production action and active style", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue(base as never);
    await act(async () => root.render(<App />));
    expect(container.textContent).toContain("Sources");
    expect(container.textContent).toContain("Amiga OCS Portrait v1");
    expect(container.textContent).toContain("Make 1 card with Amiga OCS Portrait v1");
  });

  it("shows final cards first and keeps provenance collapsed", async () => {
    const batch = { batch_id: "batch-1", purpose: "card-production" as const, status: "ready", created_at: "now", updated_at: "now", style_version_id: style.identity.style_version_id, style_checksum_sha256: "style-checksum", selected_source_ids: ["source-1"], requested_paid_calls: 1, paid_calls: 1, cost_usd: 0, progress: { selected_sources: 1, ready_cards: 1, approved_cards: 0, failed_sources: 0, paid_calls: 1, total_attempts: 1 }, items: [{ item_id: "item-1", source_id: "source-1", source_label: "Ada", attempt_number: 1, lineage_id: "lineage", status: "ready" as const, card_url: "/card.png", art_url: "/art.png", render_revision: 1, render_revisions: [], reference_stack: [] }] };
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, batches: [batch] } as never);
    vi.spyOn(api, "getProduction").mockResolvedValue({ batch } as never);
    await act(async () => { window.location.hash = "#cards"; root.render(<App />); });
    expect(container.querySelector('img[alt="Ada finished card"]')).toBeTruthy();
    expect(container.textContent).toContain("How this was made");
    expect(document.querySelector("details")?.open).toBe(false);
    expect([...container.querySelectorAll("button")].some((button) => button.textContent?.includes("Approve card"))).toBe(true);
  });

  it("makes framing a render action and keeps the paid action distinct", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue(base as never);
    vi.spyOn(api, "createProduction").mockResolvedValue({ batch: { batch_id: "batch-1" } } as never);
    await act(async () => root.render(<App />));
    const make = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Make 1 card"));
    await act(async () => make?.click());
    expect(api.createProduction).toHaveBeenCalledWith(["source-1"], style.identity.style_version_id);
  });
});
