import { describe, expect, it } from "vitest";
import { makeRunPayload, recipeIsDirty, referenceLimitProblem, selectedModel } from "./runDraft";
import type { Model, Recipe } from "./types";

const recipe = {
  id: "recipe_1", name: "Draft", model: "saved/stale", execution_mode: "live", quality: "low",
  change_note: "Warmer light",
  direction: { medium_brushwork: "paint", lighting: "", background: "", composition: "", colour: "", detail: "", identity: "" },
  avoid: "type", aspect_policy: "card-window", reference_ids: ["one", "two"], references: [], created_at: "now", updated_at: "now",
} satisfies Recipe;
const stale = {
  id: "saved/stale", name: "saved/stale", execution_mode: "live", available: false,
  supported_parameters: {}, max_input_references: 0, aspect_ratios: [], qualities: [],
  supports_negative_prompt: false, supports_reference_roles: false, supports_streaming: false, pricing: [],
} satisfies Model;

describe("atomic run drafts", () => {
  it("keeps the saved stale model visible instead of selecting the first live model", () => {
    expect(selectedModel([stale, { ...stale, id: "new/live", available: true }], recipe)?.id).toBe("saved/stale");
    expect(referenceLimitProblem(recipe, stale)).toMatch(/unavailable/i);
  });

  it("submits visible edits as the recipe snapshot payload", () => {
    const draft = { ...recipe, name: "Visible unsaved name" };
    expect(recipeIsDirty(recipe, draft)).toBe(true);
    const payload = makeRunPayload(draft, ["source_1"], 4);
    expect(payload.recipe.name).toBe("Visible unsaved name");
    expect(payload.recipe.model).toBe("saved/stale");
    expect(payload.source_ids).toEqual(["source_1"]);
    expect(payload.execution_mode).toBe("live");
    expect(payload.outputs_per_source).toBe(4);
    expect(payload).not.toHaveProperty("confirm_paid");
  });
});
