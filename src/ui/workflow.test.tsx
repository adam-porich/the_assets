import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { readRoute, runIdForStage } from "./App";
import { CompletedStage, FramesStage } from "./CardViews";
import { FinishStage } from "./FinishLab";
import { SourcesStage, StylesStage } from "./StyleLab";
import type { CandidateSelection, Card, CardPreviewOption, Model, Recipe, Run, Source, Workspace } from "./types";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const reference = (id: string) => ({ id, label: id, relative_path: `references/${id}.png`, image_url: `/asset/${id}.png`, checksum_sha256: id, provenance: { kind: "bundled" } });
const recipe: Recipe = {
  id: "recipe_1", name: "Estate", model: "openai/gpt-image-1-mini", execution_mode: "live", quality: "low", change_note: "",
  direction: { medium_brushwork: "paint", lighting: "quiet", background: "stone", composition: "bust", colour: "umber", detail: "eyes", identity: "retain" },
  avoid: "type", aspect_policy: "card-window", reference_ids: ["ref_1", "ref_2"], references: [], created_at: "2026-01-01", updated_at: "2026-01-01",
};
const source = (id: string): Source => ({ id, label: `Portrait ${id}`, relative_path: `sources/${id}.jpg`, image_url: `/asset/${id}.jpg`, dimensions: [160, 220], created_at: "2026-01-01", provenance: { kind: "pexels", photo_id: id } });
const sourceOne = source("one");
const sourceTwo = source("two");
const emptyWorkspace: Workspace = { version: 1, sources: [], benchmark_source_ids: [], references: [reference("ref_1"), reference("ref_2")], recipes: [recipe], active_recipe_id: recipe.id, links: { runs: "api/runs", cards: "api/cards" } };
const workspace: Workspace = { ...emptyWorkspace, sources: [sourceOne, sourceTwo], benchmark_source_ids: [sourceOne.id, sourceTwo.id] };
const liveModel: Model = { id: recipe.model, name: "GPT Image Mini", execution_mode: "live", available: true, supported_parameters: { input_references: { type: "range", max: 16 }, quality: { type: "enum", values: ["low", "medium", "high"] } }, max_input_references: 16, aspect_ratios: ["3:2"], qualities: ["low", "medium", "high"], supports_negative_prompt: false, supports_reference_roles: false, supports_streaming: true, pricing: [{ billable: "output_image", unit: "token", cost_usd: 0.000008 }] };

function runFixture(draft: Recipe = recipe, sourceIds = [sourceOne.id], outputs = 4): Run {
  const sources = sourceIds.map((id) => workspace.sources.find((item) => item.id === id)!);
  return {
    run_id: "run_1", recipe_id: draft.id, recipe_name: draft.name, status: "complete", source_count: sourceIds.length, verdict: "unreviewed", created_at: "2026-01-01", completed_calls: sourceIds.length * outputs, total_calls: sourceIds.length * outputs, execution_mode: draft.execution_mode, model: draft.model, cost_usd: 0,
    updated_at: "2026-01-01", recipe_snapshot: draft, resolved_instruction: `Requested change: ${draft.change_note}`, benchmark_source_ids: sourceIds, sources_snapshot: sources.map((item) => ({ ...item, input_url: item.image_url })), references_snapshot: workspace.references.map((item) => ({ ...item, input_url: item.image_url })), quality: "low", requested_aspect_ratio: "28:23", effective_aspect_ratio: "5:4", backend_capabilities: {}, backend_mapping: { references: "identity_first_style_after" }, outputs_per_source: outputs, usage: {}, model_metadata: liveModel,
    items: sourceIds.flatMap((id) => Array.from({ length: outputs }, (_, index) => ({ item_id: `item_${id}_${index}`, source_id: id, source_label: `Portrait ${id}`, output_index: index, status: "complete", output_url: `/asset/output-${id}-${index}.png`, thumbnail_url: `/asset/thumb-${id}-${index}.jpg`, source_url: `/asset/${id}.jpg`, dimensions: [320, 256] as [number, number], elapsed_seconds: 0.2, cost_usd: 0 }))), note: "",
  };
}

function cardFixture(decision: Card["decision"] = "working", preset: Card["archetype"] = "bust", treatment: Card["treatment"] = "painterly", id = "card_1"): Card {
  return { card_id: id, run_id: "run_1", run_item_id: "item_one_0", label: "Claimant", template_id: "estate-card-v1", archetype: preset, framing: preset === "tall" ? { zoom: 1.16, offset_x: 0, offset_y: -0.06 } : { zoom: 1, offset_x: 0, offset_y: 0.02 }, decision, render_path: `cards/${id}.png`, render_url: `/asset/${id}.png`, art_render_path: `cards/${id}-art.png`, art_url: `/asset/${id}-art.png`, source_output_path: "runs/output.png", source_url: "/asset/output.png", source_dimensions: [320, 256], render_dimensions: [420, 600], treatment, treatment_version: treatment === "painterly" ? "painterly-source-v1" : treatment, render_metadata: {}, source_run_provenance: { source_label: "Portrait one", change_note: "Warmer light", recipe_name: "Estate" }, created_at: "2026-01-01", updated_at: `2026-01-01-${preset}-${treatment}-${decision}` };
}

const previews: CardPreviewOption[] = (["bust", "tall", "torso"] as const).flatMap((preset) => (["painterly", "estate-pixel-v1"] as const).map((treatment) => ({ option_id: `cache:${preset}:${treatment}`, preset, preset_label: preset[0].toUpperCase() + preset.slice(1), treatment, treatment_label: treatment === "painterly" ? "Painterly" : "Estate Pixel", framing: preset === "tall" ? { zoom: 1.16, offset_x: 0, offset_y: -0.06 } : preset === "torso" ? { zoom: 1.28, offset_x: 0, offset_y: 0.08 } : { zoom: 1, offset_x: 0, offset_y: 0.02 }, render_path: `cards/previews/${preset}-${treatment}.png`, render_url: `/asset/${preset}-${treatment}.png`, art_render_path: `cards/previews/${preset}-${treatment}-art.png`, art_url: `/asset/${preset}-${treatment}-art.png`, render_dimensions: [420, 600] as [number, number], render_metadata: {} })));

let container: HTMLDivElement;
let root: Root;
afterEach(() => {
  if (root) act(() => root.unmount());
  container?.remove();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "#sources");
});

function mount(node: React.ReactNode) {
  container = document.createElement("div"); document.body.append(container); root = createRoot(container); act(() => root.render(node));
}

function clickButton(text: string, index = 0) {
  const buttons = [...container.querySelectorAll("button")].filter((candidate) => candidate.textContent?.includes(text));
  expect(buttons.length).toBeGreaterThan(index); act(() => (buttons[index] as HTMLButtonElement).click());
}

function setText(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(element, value);
  act(() => element.dispatchEvent(new Event("input", { bubbles: true })));
}

async function flush() { await act(async () => { await Promise.resolve(); await Promise.resolve(); }); }

describe("guided six-stage graphics workflow", () => {
  it("keeps Explore runs out of Finish and selects only the current Finish cohort", () => {
    const explore = runFixture();
    const finish = { ...runFixture(), run_id: "finish_1", purpose: "finish" as const, selection_id: "selection_1", selection_revision: 2 };
    const selection = { selection_id: "selection_1", revision: 2 } as CandidateSelection;
    expect(runIdForStage("finish", explore, [finish], selection)).toBe("finish_1");
    expect(runIdForStage("finish", finish, [], selection)).toBe("finish_1");
    expect(runIdForStage("styles", finish, [explore], selection)).toBe("run_1");
  });

  it("does not offer Finish locking for an Explore run", () => {
    const selection: CandidateSelection = {
      selection_id: "selection_1", revision: 1, created_at: "2026-01-01", updated_at: "2026-01-01", source_ids: [sourceOne.id],
      selected_items: [{ order: 0, run_id: "run_1", item_id: "item_one_0", source_id: sourceOne.id, source_label: sourceOne.label, output_path: "runs/run_1/item.png", output_checksum_sha256: "checksum", output_url: "/asset/output.png", recipe_snapshot: recipe }],
    };
    mount(<FinishStage workspace={workspace} selection={selection} runs={[]} models={[liveModel]} initialRun={runFixture()} onRun={() => undefined} onRefresh={async () => undefined} onNavigate={() => undefined} onMessage={() => undefined} />);
    expect(container.textContent).not.toContain("Lock this finish");
  });

  it("keeps the new stage hashes refreshable and redirects legacy hashes", () => {
    window.location.hash = "#frames/card_7";
    expect(readRoute()).toEqual({ view: "frames", id: "card_7" });
    window.location.hash = "#completed";
    expect(readRoute()).toEqual({ view: "completed" });
    window.location.hash = "#lab";
    expect(readRoute()).toEqual({ view: "styles" });
    expect(window.location.hash).toBe("#styles");
    window.location.hash = "#run/run_9";
    expect(readRoute()).toEqual({ view: "styles", runId: "run_9" });
    expect(window.location.hash).toBe("#styles");
    window.location.hash = "#cards";
    expect(readRoute()).toEqual({ view: "frames" });
    expect(window.location.hash).toBe("#frames");
    window.location.hash = "#explore";
    expect(readRoute()).toEqual({ view: "styles" });
    window.location.hash = "#finish";
    expect(readRoute()).toEqual({ view: "finish" });
    window.location.hash = "#set";
    expect(readRoute()).toEqual({ view: "set" });
  });

  it("shows an accessible Sources empty state, loads the library, and continues freely", async () => {
    vi.spyOn(api, "loadStarterSources").mockResolvedValue({ workspace, imported: 2, deduplicated: 0, failed: 0, results: [{ status: "imported" }, { status: "imported" }] });
    const navigate = vi.fn();
    function Harness() { const [value, setValue] = React.useState(emptyWorkspace); return <SourcesStage workspace={value} pexelsAvailable onWorkspace={setValue} onNavigate={navigate} onMessage={() => undefined} />; }
    mount(<Harness />);
    expect(container.textContent).toContain("No source images yet");
    clickButton("Continue to Explore");
    expect(navigate).toHaveBeenCalledWith("#explore");
    await act(async () => clickButton("Load six starter images"));
    expect(container.textContent).toContain("2 selected source images");
    expect(container.textContent).not.toContain("Benchmark portraits");
  });

  it("edits a plain-language style and generates four quick variants without a modal", async () => {
    let submitted: { draft?: Recipe; ids?: string[]; outputs?: number } = {};
    vi.spyOn(api, "startRun").mockImplementation(async (draft, ids, outputs) => { submitted = { draft, ids, outputs }; return { run: runFixture(draft, ids, outputs), workspace: { ...workspace, recipes: [draft] } }; });
    const navigate = vi.fn();
    mount(<StylesStage workspace={workspace} models={[liveModel]} runs={[]} openrouterAvailable onWorkspace={() => undefined} onRun={() => undefined} onRefresh={async () => undefined} onNavigate={navigate} onMessage={() => undefined} />);
    const note = container.querySelector(".change-field textarea") as HTMLTextAreaElement;
    setText(note, "Warmer light and looser edges");
    await act(async () => clickButton("Generate 4 variants"));
    expect(submitted.draft?.change_note).toBe("Warmer light and looser edges");
    expect(submitted.ids).toEqual([sourceOne.id]);
    expect(submitted.outputs).toBe(4);
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.querySelectorAll(".result-card")).toHaveLength(4);
    expect(container.textContent).toContain("Select for Finish");
  });

  it("tests consistency once per project source", async () => {
    const start = vi.spyOn(api, "startRun").mockImplementation(async (draft, ids, outputs) => ({ run: runFixture(draft, ids, outputs), workspace }));
    mount(<StylesStage workspace={workspace} models={[liveModel]} runs={[]} openrouterAvailable onWorkspace={() => undefined} onRun={() => undefined} onRefresh={async () => undefined} onNavigate={() => undefined} onMessage={() => undefined} />);
    await act(async () => clickButton("Test across all sources"));
    expect(start).toHaveBeenCalledWith(expect.anything(), [sourceOne.id, sourceTwo.id], 1, "live");
  });

  it("shows exact composition and treatment choices, then keeps the selected render", async () => {
    let current = cardFixture();
    vi.spyOn(api, "getCardPreviews").mockResolvedValue({ previews });
    vi.spyOn(api, "getRun").mockResolvedValue({ run: runFixture() });
    vi.spyOn(api, "updateCard").mockImplementation(async (_id, patch: unknown) => { const option = previews.find((item) => item.option_id === (patch as { preview_id: string }).preview_id)!; current = { ...current, archetype: option.preset, framing: option.framing, treatment: option.treatment, updated_at: `${current.updated_at}-selected` }; return { card: current }; });
    vi.spyOn(api, "decideCard").mockImplementation(async (_id, decision) => ({ card: { ...current, decision: decision as Card["decision"] } }));
    const navigate = vi.fn();
    mount(<FramesStage cards={[current]} initialCard={current} onNavigate={navigate} onMessage={() => undefined} onRefresh={async () => undefined} />);
    await flush();
    expect(container.querySelectorAll(".composition-grid button")).toHaveLength(3);
    clickButton("Tall"); await flush();
    expect(current.archetype).toBe("tall");
    clickButton("Estate Pixel"); await flush();
    expect(current.treatment).toBe("estate-pixel-v1");
    await act(async () => clickButton("Keep as completed"));
    expect(api.decideCard).toHaveBeenCalledWith("card_1", "keep");
    expect(navigate).toHaveBeenCalledWith("#completed");
  });

  it("discards and advances, while Completed shows only kept cards with download and reconsider", async () => {
    const first = cardFixture("working", "bust", "painterly", "card_1");
    const second = cardFixture("working", "bust", "painterly", "card_2");
    const kept = cardFixture("keep", "tall", "estate-pixel-v1", "card_kept");
    vi.spyOn(api, "getCardPreviews").mockResolvedValue({ previews });
    vi.spyOn(api, "getRun").mockResolvedValue({ run: runFixture() });
    vi.spyOn(api, "decideCard").mockImplementation(async (id, decision) => ({ card: { ...(id === kept.card_id ? kept : first), decision: decision as Card["decision"] } }));
    const navigate = vi.fn();
    mount(<FramesStage cards={[first, second, kept]} initialCard={first} onNavigate={navigate} onMessage={() => undefined} onRefresh={async () => undefined} />);
    await flush();
    await act(async () => clickButton("Not this one"));
    expect(navigate).toHaveBeenCalledWith("#frames/card_2");

    act(() => root.unmount()); root = createRoot(container);
    act(() => root.render(<CompletedStage cards={[first, kept]} onNavigate={navigate} onMessage={() => undefined} onRefresh={async () => undefined} />));
    expect(container.querySelectorAll(".completed-card")).toHaveLength(1);
    expect(container.querySelector<HTMLAnchorElement>('a[download]')?.textContent).toContain("Download PNG");
    await act(async () => clickButton("Reconsider in Frames"));
    expect(api.decideCard).toHaveBeenCalledWith("card_kept", "working");
    expect(navigate).toHaveBeenCalledWith("#frames/card_kept");
  });
});
