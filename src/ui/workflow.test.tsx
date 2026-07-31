import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { CardGallery, CardWorkbench } from "./CardViews";
import { StyleLab } from "./StyleLab";
import type { Card, Model, Recipe, Run, Source, Workspace } from "./types";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const reference = (id: string) => ({ id, label: id, relative_path: `references/${id}.png`, image_url: `/asset/${id}.png`, checksum_sha256: id, provenance: { kind: "bundled" } });
const recipe: Recipe = {
  id: "recipe_1", name: "Estate", model: "openai/gpt-image-1-mini", execution_mode: "live", quality: "low",
  direction: { medium_brushwork: "paint", lighting: "quiet", background: "stone", composition: "bust", colour: "umber", detail: "eyes", identity: "retain" },
  avoid: "type", aspect_policy: "card-window", reference_ids: ["ref_1", "ref_2"], references: [], created_at: "2026-01-01", updated_at: "2026-01-01",
};
const source: Source = { id: "source_1", label: "Portrait one", relative_path: "sources/one.jpg", image_url: "/asset/one.jpg", dimensions: [160, 220], created_at: "2026-01-01", provenance: { kind: "pexels", photo_id: 1 } };
const workspace: Workspace = { version: 1, sources: [], benchmark_source_ids: [], references: [reference("ref_1"), reference("ref_2")], recipes: [recipe], active_recipe_id: recipe.id, links: { runs: "api/runs", cards: "api/cards" } };
const loadedWorkspace: Workspace = { ...workspace, sources: [source], benchmark_source_ids: [source.id] };
const liveModel: Model = { id: recipe.model, name: "GPT Image Mini", execution_mode: "live", available: true, supported_parameters: { input_references: { type: "range", max: 16 }, quality: { type: "enum", values: ["low", "medium", "high"] } }, max_input_references: 16, aspect_ratios: ["3:2"], qualities: ["low", "medium", "high"], supports_negative_prompt: false, supports_reference_roles: false, supports_streaming: true, pricing: [{ billable: "output_image", unit: "token", cost_usd: 0.000008 }] };
const simulationModel: Model = { ...liveModel, id: "fake/painterly-deterministic", name: "Simulation", execution_mode: "simulation", supports_streaming: false, pricing: [{ billable: "output_image", unit: "image", cost_usd: 0 }] };

function runFixture(draft: Recipe): Run {
  return {
    run_id: "run_1", recipe_id: draft.id, recipe_name: draft.name, status: "complete", source_count: 1, verdict: "unreviewed", created_at: "2026-01-01", completed_calls: 1, total_calls: 1, execution_mode: draft.execution_mode, model: draft.model, cost_usd: 0,
    updated_at: "2026-01-01", recipe_snapshot: draft, resolved_instruction: "paint", benchmark_source_ids: [source.id], sources_snapshot: [{ ...source, input_url: source.image_url }], references_snapshot: workspace.references.map((item) => ({ ...item, input_url: item.image_url })), quality: "low", requested_aspect_ratio: "28:23", effective_aspect_ratio: "5:4", backend_capabilities: {}, backend_mapping: { references: "identity_first_style_after" }, outputs_per_source: 1, usage: {}, model_metadata: draft.execution_mode === "live" ? liveModel : simulationModel,
    items: [{ item_id: "item_1", source_id: source.id, source_label: source.label, output_index: 0, status: "complete", output_url: "/asset/output.png", thumbnail_url: "/asset/thumb.jpg", source_url: source.image_url, dimensions: [320, 256], elapsed_seconds: 0.2, cost_usd: 0 }], note: "",
  };
}

function cardFixture(treatment: Card["treatment"] = "painterly", decision: Card["decision"] = "working"): Card {
  return { card_id: "card_1", run_id: "run_1", run_item_id: "item_1", label: "Claimant", template_id: "estate-card-v1", archetype: "bust", framing: { zoom: 1, offset_x: 0, offset_y: 0.02 }, decision, render_path: "cards/card.png", render_url: "/asset/card.png", art_render_path: "cards/art.png", art_url: "/asset/art.png", source_output_path: "runs/output.png", source_url: "/asset/output.png", source_dimensions: [320, 256], render_dimensions: [400, 560], treatment, treatment_version: treatment === "painterly" ? "painterly-source-v1" : treatment, render_metadata: { palette_colours: treatment === "estate-pixel-v1" ? 32 : null }, created_at: "2026-01-01", updated_at: `2026-01-01-${treatment}-${decision}` };
}

let container: HTMLDivElement;
let root: Root;
afterEach(() => {
  if (root) act(() => root.unmount());
  container?.remove();
  vi.restoreAllMocks();
});

function mount(node: React.ReactNode) {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(node));
}

function clickButton(text: string, index = 0) {
  const buttons = [...container.querySelectorAll("button")].filter((candidate) => candidate.textContent?.includes(text));
  expect(buttons.length).toBeGreaterThan(index);
  act(() => (buttons[index] as HTMLButtonElement).click());
}

describe("visible portrait workflow", () => {
  it("loads sources, confirms explicit simulation, frames, treats, keeps, and reopens", async () => {
    vi.spyOn(api, "loadStarterSources").mockResolvedValue({ workspace: loadedWorkspace, imported: 1, deduplicated: 0, failed: 0, results: [{ status: "imported" }] });
    let submitted: Recipe | undefined;
    vi.spyOn(api, "startRun").mockImplementation(async (draft) => { submitted = draft; return { run: runFixture(draft), workspace: { ...loadedWorkspace, recipes: [draft] } }; });
    const navigate = vi.fn();
    function Harness() {
      const [value, setValue] = React.useState(workspace);
      return <StyleLab workspace={value} models={[simulationModel, liveModel]} runs={[]} pexelsAvailable openrouterAvailable onWorkspace={setValue} onRefresh={async () => undefined} onNavigate={navigate} onMessage={() => undefined} />;
    }
    const React = await import("react");
    mount(<Harness />);
    await act(async () => clickButton("Load starter benchmark"));
    expect(container.textContent).toContain("Portrait one");

    clickButton("Save and run 1-source smoke test");
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain("Live OpenRouter generation (cost-bearing)");
    clickButton("Cancel");
    clickButton("Simulation");
    clickButton("Save and run full simulation");
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain("not generated artwork");
    await act(async () => clickButton("Confirm simulation"));
    expect(submitted?.model).toBe("fake/painterly-deterministic");
    expect(submitted?.execution_mode).toBe("simulation");
    expect(navigate).toHaveBeenCalledWith("#run/run_1");

    act(() => root.unmount());
    const simulatedRun = runFixture(submitted!);
    vi.spyOn(api, "createCard").mockResolvedValue({ card: cardFixture() });
    root = createRoot(container);
    act(() => root.render(<StyleLab workspace={{ ...loadedWorkspace, recipes: [submitted!] }} models={[simulationModel, liveModel]} runs={[simulatedRun]} activeRun={simulatedRun} pexelsAvailable openrouterAvailable onWorkspace={() => undefined} onRefresh={async () => undefined} onNavigate={navigate} onMessage={() => undefined} />));
    await act(async () => clickButton("Frame this portrait"));
    expect(navigate).toHaveBeenCalledWith("#card/card_1");

    act(() => root.unmount());
    let currentCard = cardFixture();
    vi.spyOn(api, "updateCard").mockImplementation(async (_id, patch: unknown) => { const value = patch as Partial<Card>; currentCard = { ...currentCard, ...value, treatment_version: value.treatment === "estate-pixel-v1" ? "estate-pixel-v1" : currentCard.treatment_version, updated_at: `${currentCard.updated_at}-updated` }; return { card: currentCard }; });
    vi.spyOn(api, "decideCard").mockImplementation(async (_id, decision) => { currentCard = { ...currentCard, decision: decision as Card["decision"] }; return { card: currentCard }; });
    root = createRoot(container);
    act(() => root.render(<CardWorkbench card={currentCard} workspace={loadedWorkspace} onNavigate={navigate} onMessage={() => undefined} onRefresh={async () => undefined} />));
    await act(async () => clickButton("Estate Pixel"));
    await act(async () => clickButton("Keep card"));
    expect(currentCard.treatment).toBe("estate-pixel-v1");
    expect(currentCard.decision).toBe("keep");

    act(() => root.unmount());
    root = createRoot(container);
    act(() => root.render(<CardGallery cards={[currentCard]} newestCompletedRunId="run_1" onNavigate={navigate} onRefresh={async () => undefined} />));
    act(() => (container.querySelector(".draft-card") as HTMLElement).click());
    expect(navigate).toHaveBeenCalledWith("#card/card_1");
  });

  it("links an empty gallery directly to the newest completed run", () => {
    const navigate = vi.fn();
    mount(<CardGallery cards={[]} newestCompletedRunId="run_newest" onNavigate={navigate} onRefresh={async () => undefined} />);
    clickButton("Open newest completed run");
    expect(navigate).toHaveBeenCalledWith("#run/run_newest");
  });
});
