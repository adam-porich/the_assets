import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App, readRoute } from "./App";
import { api } from "./api";

const style = {
  schema_version: 3,
  identity: {
    family_id: "amiga-ocs-portrait",
    pipeline_id: "face-free-style-board",
    style_version_id: "style-face-free",
    version: 3,
    state: "locked",
    label: "Face-free Style Board",
  },
  generation: {
    model_id: "live-model",
    execution_mode: "live",
    quality: "low",
    prompt: "Apply only the visual language.",
    requested_aspect_policy: "16:9",
    reference_limit: 9,
  },
  reference_pack: {
    id: "pack",
    version: 1,
    assets: [
      {
        id: "gen",
        label: "Face-free board",
        role: "generation-reference" as const,
        checksum_sha256: "gen",
        image_url: "/gen.png",
      },
      {
        id: "target",
        label: "Target",
        role: "target-example" as const,
        checksum_sha256: "target",
        image_url: "/target.png",
      },
    ],
  },
  composition: {
    logical_art_size: [176, 99] as [number, number],
    default_framing: { zoom: 1, offset_x: 0, offset_y: 0 },
    centering: [0.5, 0.44] as [number, number],
    requested_art_ratio: "16:9",
  },
  renderer: {
    driver_id: "amiga-ocs",
    logical_art_size: [176, 99] as [number, number],
    output_scale: 2,
    palette_space: "Amiga",
    palette: ["#111111"],
    preprocess: {},
    dither: { matrix: "bayer-4x4", strength: 0.62, edge_threshold: 0.09 },
  },
  editor_descriptors: [],
  checksums: { style_sha256: "style-checksum" },
};
Object.assign(style, {
  backgrounds: {
    default_id: "warm-parchment",
    composite_size: [352, 198],
    presets: [
      {
        id: "warm-parchment",
        label: "Warm parchment",
        top: "#d3be8e",
        bottom: "#674d34",
        glow: "#ecd6a5",
        glow_strength: 0.22,
      },
      {
        id: "cool-slate",
        label: "Cool slate",
        top: "#5a7076",
        bottom: "#1c272d",
        glow: "#8b978f",
        glow_strength: 0.22,
      },
    ],
  },
});
const portraitStyle = {
  ...style,
  identity: {
    ...style.identity,
    pipeline_id: "portrait-style-reference",
    style_version_id: "style-portrait",
    version: 1,
    label: "Portrait Style Reference",
  },
  reference_pack: {
    ...style.reference_pack,
    assets: [
      {
        ...style.reference_pack.assets[0],
        id: "old-gen",
        label: "Original portrait style reference",
        checksum_sha256: "old-gen",
      },
      style.reference_pack.assets[1],
    ],
  },
  checksums: { style_sha256: "portrait-checksum" },
};
const revisions = (id: string, checksum: string) => [
  {
    style_version_id: id,
    checksum_sha256: checksum,
    created_at: "2026-08-01T00:00:00Z",
  },
];
const pipelines = [
  {
    pipeline_id: "face-free-style-board",
    label: "Face-free Style Board",
    description: "Uses the face-free board.",
    active: true,
    current_version_id: style.identity.style_version_id,
    revision_count: 1,
    revisions: revisions(
      style.identity.style_version_id,
      style.checksums.style_sha256,
    ),
    style,
  },
  {
    pipeline_id: "portrait-style-reference",
    label: "Portrait Style Reference",
    description: "Uses the original portrait reference.",
    active: false,
    current_version_id: portraitStyle.identity.style_version_id,
    revision_count: 1,
    revisions: revisions(
      portraitStyle.identity.style_version_id,
      portraitStyle.checksums.style_sha256,
    ),
    style: portraitStyle,
  },
];
const versions = pipelines.map((pipeline) => ({
  pipeline_id: pipeline.pipeline_id,
  style_version_id: pipeline.current_version_id,
  label: pipeline.label,
  version: pipeline.style.identity.version,
  checksum_sha256: pipeline.style.checksums.style_sha256,
  active: pipeline.active,
  created_at: "2026-08-01T00:00:00Z",
  execution_mode: "live" as const,
  model_id: "live-model",
  quality: "low",
  reference_count: 1,
  renderer_id: "amiga-ocs",
}));
const model = {
  id: "live-model",
  name: "Live image model",
  execution_mode: "live" as const,
  available: true,
  credentials_configured: true,
  max_input_references: 9,
  qualities: ["low"],
  aspect_ratios: ["5:4"],
  pricing: [{ cost_usd: 0.04 }],
};
const input = {
  id: "source-1",
  label: "Ada",
  status: "ready" as const,
  image_url: "/ada.png",
  original_url: "/ada-original.png",
  accepted_normalisation: {
    id: "norm-1",
    status: "ready" as const,
    prompt: "Keep Ada",
    quality: "low" as const,
    model_id: "live-model",
    preview_url: "/ada.png",
  },
};
const base = {
  workspace: { inputs: [input] },
  inputs: [input],
  style: {
    active: style,
    active_pipeline_id: "face-free-style-board",
    pipelines,
    draft: null,
    versions,
    driver: {
      id: "amiga-ocs",
      label: "Amiga OCS",
      output: "420×600 final cards",
    },
  },
  batches: [],
  cards: [],
  favorites: [],
  models: [model],
  integrations: {
    pexels: { configured: false },
    openrouter: { configured: true },
  },
  starter: { photo_ids: [] },
  normalisation: {
    default_prompt: "Preserve the exact subject.",
    default_quality: "low" as const,
    active: false,
  },
};

function produced(overrides: Record<string, unknown> = {}) {
  return {
    item_id: "item-1",
    source_id: "source-1",
    source_label: "Ada",
    attempt_number: 1,
    lineage_id: "lineage",
    status: "ready" as const,
    source_url: "/ada.png",
    master_url: "/master.png",
    art_url: "/art.png",
    art_checksum_sha256: "art-checksum",
    card_text: { title: "Ada", lines: ["Face-free Style Board", "batch-1", "Attempt 1"] },
    render_revision: 1,
    render_revisions: [],
    framing: { zoom: 1, offset_x: 0, offset_y: 0 },
    generation: { execution_mode: "live", model: "live-model" },
    reference_stack: [],
    batch_id: "batch-1",
    batch_created_at: "2026-08-02T00:00:00Z",
    purpose: "card-production" as const,
    style_version_id: style.identity.style_version_id,
    style_checksum_sha256: "style-checksum",
    pipeline_id: "face-free-style-board",
    pipeline_label: "Face-free Style Board",
    pipeline_description: "Uses the face-free board.",
    pipeline_version: 2,
    favorite: false,
    favorited_at: null,
    ...overrides,
  };
}

let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  window.location.hash = "";
});

describe("pipeline workbench", () => {
  it("uses image-first search results and prepares only after previewing", async () => {
    const result = {
      id: "pexels-42",
      label: "Mountain portrait",
      preview_url: "/mountain-small.jpg",
      selected_image_url: "/mountain-large.jpg",
      photographer: "Hidden Artist",
    };
    vi.spyOn(api, "bootstrap").mockResolvedValue(base as never);
    vi.spyOn(api, "searchInputs").mockResolvedValue({
      results: [result],
      page: 1,
      has_more: false,
    });
    vi.spyOn(api, "importInput").mockResolvedValue({
      workspace: base.workspace,
      input: {
        id: "pending-42",
        label: "Mountain portrait",
        status: "pending",
        original_url: "/mountain-large.jpg",
      },
    } as never);

    await act(async () => {
      window.location.hash = "#inputs";
      root.render(<App />);
    });
    const searchInput = container.querySelector(
      'input[aria-label="Search input images"]',
    ) as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set?.call(searchInput, "mountain");
      searchInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      searchInput.closest("form")?.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
    });

    expect(container.querySelectorAll(".search-result")).toHaveLength(1);
    expect(container.textContent).not.toContain("Hidden Artist");
    expect(
      [...container.querySelectorAll("button")].some(
        (button) => button.textContent === "Prepare",
      ),
    ).toBe(false);

    await act(async () =>
      (container.querySelector(".search-result") as HTMLButtonElement).click(),
    );
    const dialog = container.querySelector(".search-result-dialog");
    expect(dialog?.textContent).toContain("Prepare");
    expect(dialog?.querySelector("img")?.getAttribute("src")).toBe(
      "/mountain-large.jpg",
    );

    await act(async () =>
      [...dialog!.querySelectorAll("button")]
        .find((button) => button.textContent === "Prepare")
        ?.click(),
    );
    expect(api.importInput).toHaveBeenCalledWith(result);
    expect(container.querySelector(".search-result-dialog")).toBeNull();
    expect(container.querySelector("#input-dialog-title")?.textContent).toBe(
      "Mountain portrait",
    );
  });

  it("uses one Cards route and redirects the retired views", () => {
    window.location.hash = "#cards/batch-1/item-1";
    expect(readRoute()).toEqual({
      view: "cards",
      id: "batch-1",
      itemId: "item-1",
    });
    window.location.hash = "#batches/batch-1/item-1";
    expect(readRoute()).toEqual({
      view: "cards",
      id: "batch-1",
      itemId: "item-1",
    });
    window.location.hash = "#collection";
    expect(readRoute()).toEqual({ view: "cards" });
  });

  it("shows every attempt and exposes favorite, trash, and generation controls", async () => {
    const failed = produced({
      item_id: "failed",
      batch_id: "batch-2",
      status: "failed",
      art_url: undefined,
      master_url: undefined,
      error: "model failed",
    });
    vi.spyOn(api, "bootstrap").mockResolvedValue({
      ...base,
      cards: [produced(), failed],
    } as never);
    await act(async () => {
      window.location.hash = "#cards";
      root.render(<App />);
    });
    expect(container.querySelectorAll(".app-header nav button")).toHaveLength(
      3,
    );
    expect(container.querySelectorAll(".raw-result-card")).toHaveLength(2);
    expect(container.textContent).toContain("Generation failed");
    expect(
      container.querySelector('button[aria-label="Favorite card"]'),
    ).toBeTruthy();
    expect(
      container.querySelector('button[aria-label="Move card to Trash"]'),
    ).toBeTruthy();
    expect(container.textContent).toContain("＋ Generate");
  });

  it("starts generation by choosing an Input and keeps the result without acceptance", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue(base as never);
    vi.spyOn(api, "createProduction").mockResolvedValue({
      batch: { batch_id: "batch-2", status: "ready", items: [produced()] },
    } as never);
    await act(async () => {
      window.location.hash = "#cards";
      root.render(<App />);
    });
    await act(async () =>
      [...container.querySelectorAll("button")]
        .find((button) => button.textContent?.includes("Generate"))
        ?.click(),
    );
    expect(container.textContent).toContain("Choose an Input");
    await act(async () =>
      container
        .querySelector(".input-picker .source-select")
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true })),
    );
    expect(
      container.querySelector('[aria-labelledby="candidate-dialog-title"]'),
    ).toBeTruthy();
    expect(container.querySelector(".generation-prompt-details")).toBeTruthy();
    expect(
      (
        container.querySelector(
          ".generation-prompt-details textarea",
        ) as HTMLTextAreaElement
      ).value,
    ).toBe("Apply only the visual language.");
    await act(async () =>
      [...container.querySelectorAll("button")]
        .find((button) => button.textContent === "Generate")
        ?.click(),
    );
    expect(api.createProduction).toHaveBeenCalledWith(
      ["source-1"],
      "face-free-style-board",
      true,
      "",
      "warm-parchment",
      "Apply only the visual language.",
    );
    expect(container.textContent).not.toContain("Add to pack");
  });

  it("opens a candidate as a complete source-to-card inspector", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue({
      ...base,
      cards: [
        produced({
          foreground_url: "/foreground.png",
          background_id: "warm-parchment",
        }),
      ],
    } as never);
    await act(async () => {
      window.location.hash = "#candidates/batch-1/item-1";
      root.render(<App />);
    });
    expect(container.textContent).toContain("Candidate details");
    expect(
      container.querySelector('[role="dialog"][aria-modal="true"]'),
    ).toBeTruthy();
    expect(container.textContent).toContain("Foreground");
    expect(container.textContent).toContain("Background composite");
    expect(container.textContent).toContain("Warm parchment");
    expect(container.querySelector(".candidate-preview-card .dynamic-card")).toBeTruthy();
    expect(container.querySelector('img[alt="Rendered artwork"]')?.getAttribute("src")).toBe("/art.png");
    expect(container.querySelector(".pixel-text[aria-label=\"Asset Workbench\"]")).toBeTruthy();
    expect(container.querySelector(".dynamic-card-lines")).toBeTruthy();
    expect(container.textContent).toContain(
      "Adaptive · 10 anchors + 22 image colours",
    );
    expect(container.textContent).not.toContain("Zoom");
    expect(container.textContent).not.toContain("Horizontal");
    expect(container.textContent).not.toContain("Vertical");
    expect(container.textContent).toContain("Preview changes");
    expect(container.textContent).toContain("Save changes");
    expect(container.textContent).toContain("Favorite");
  });

  it("shows graceful placeholders for legacy candidate artifacts", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue({
      ...base,
      cards: [
        produced({
          source_url: undefined,
          foreground_url: undefined,
          master_url: undefined,
          art_url: undefined,
        }),
      ],
    } as never);
    await act(async () => {
      window.location.hash = "#candidates/batch-1/item-1";
      root.render(<App />);
    });
    expect(container.textContent).toContain("Input unavailable");
    expect(container.textContent).toContain("Foreground unavailable");
    expect(container.textContent).toContain("Composite unavailable");
    expect(container.textContent).toContain("Card unavailable");
  });

  it("previews candidate edits without saving them", async () => {
    const card = produced({
      foreground_url: "/foreground.png",
      background_id: "warm-parchment",
    });
    vi.spyOn(api, "bootstrap").mockResolvedValue({
      ...base,
      cards: [card],
    } as never);
    vi.spyOn(api, "previewFraming").mockResolvedValue({
      preview: {
        ...card,
        master_url: "/preview-composite.png",
        art_url: "/preview-art.png",
      },
    } as never);
    await act(async () => {
      window.location.hash = "#candidates/batch-1/item-1";
      root.render(<App />);
    });
    const preview = [...container.querySelectorAll("button")].find(
      (button) => button.textContent === "Preview changes",
    );
    await act(async () =>
      preview?.dispatchEvent(new MouseEvent("click", { bubbles: true })),
    );
    expect(api.previewFraming).toHaveBeenCalled();
    expect(container.querySelector('.candidate-preview-card img[alt="Rendered artwork"]')?.getAttribute("src")).toBe("/preview-art.png");
    expect(container.textContent).toContain("Preview card · unsaved");
  });

  it("previews card text locally and saves it independently", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue({ ...base, cards: [produced()] } as never);
    vi.spyOn(api, "updateCardText").mockResolvedValue({ card: produced() } as never);
    vi.spyOn(api, "previewFraming");
    await act(async () => { window.location.hash = "#cards/batch-1/item-1"; root.render(<App />); });
    const title = container.querySelector('.card-text-editor input[maxlength="48"]') as HTMLInputElement;
    expect(container.querySelectorAll(".card-text-editor input")).toHaveLength(7);
    await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(title, "Ada Prime"); title.dispatchEvent(new Event("input", { bubbles: true })); });
    expect(container.querySelector('.dynamic-card-title[aria-label="Ada Prime"]')).toBeTruthy();
    await act(async () => [...container.querySelectorAll("button")].find((button) => button.textContent === "Save text")?.click());
    expect(api.updateCardText).toHaveBeenCalledWith("batch-1", "item-1", expect.objectContaining({ title: "Ada Prime" }));
    expect(api.previewFraming).not.toHaveBeenCalled();
  });

  it("starts candidate inspection from the accepted Input", async () => {
    vi.spyOn(api, "bootstrap").mockResolvedValue({
      ...base,
      cards: [produced()],
    } as never);
    await act(async () => {
      window.location.hash = "#candidates/batch-1/item-1";
      root.render(<App />);
    });
    expect(
      container.querySelector('img[alt="Prepared Input"]')?.getAttribute("src"),
    ).toBe("/ada.png");
    expect(container.querySelector('img[alt="Normalised source"]')).toBeFalsy();
  });

  it("exposes editing on the selected real pipeline", async () => {
    const draft = {
      ...style,
      schema_version: 3,
      identity: {
        ...style.identity,
        state: "draft" as const,
        style_version_id: "draft-style",
      },
      generation: {
        ...style.generation,
        prompt: "Apply only the visual language.",
      },
      provenance: { derived_from: style.identity.style_version_id },
    };
    vi.spyOn(api, "bootstrap").mockResolvedValue({
      ...base,
      style: { ...base.style, draft },
    } as never);
    vi.spyOn(api, "updateDraft").mockResolvedValue({ style: draft } as never);
    window.location.hash = "#pipelines/face-free-style-board";
    await act(async () => root.render(<App />));
    expect(container.textContent).toContain("Generation model");
    expect(container.textContent).toContain("Style prompt");
    expect(container.textContent).not.toContain("Normalise prompt");
    expect(container.textContent).not.toContain("identity to retain");
    expect(container.textContent).toContain("Amiga artwork renderer");
    expect(container.textContent).toContain("1 saved revision");
  });
});
