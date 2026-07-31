import type { Model, Recipe } from "./types";

export function modelsForMode(models: Model[], mode: Recipe["execution_mode"]): Model[] {
  return models.filter((model) => model.execution_mode === mode);
}

export function selectedModel(models: Model[], recipe: Recipe): Model | undefined {
  return models.find((model) => model.id === recipe.model && model.execution_mode === recipe.execution_mode);
}

export function recipeIsDirty(saved: Recipe | undefined, draft: Recipe | undefined): boolean {
  if (!saved || !draft) return false;
  const project = (recipe: Recipe) => ({
    name: recipe.name,
    model: recipe.model,
    execution_mode: recipe.execution_mode,
    quality: recipe.quality,
    change_note: recipe.change_note,
    direction: recipe.direction,
    avoid: recipe.avoid,
    reference_ids: recipe.reference_ids,
  });
  return JSON.stringify(project(saved)) !== JSON.stringify(project(draft));
}

export function referenceLimitProblem(recipe: Recipe, model?: Model): string {
  if (!model) return "The selected model is not in the current catalogue.";
  if (!model.available) return "The selected model is unavailable. Choose an explicit replacement.";
  const needed = 1 + recipe.reference_ids.length;
  if (needed > model.max_input_references) {
    return `${model.name} accepts ${model.max_input_references} total image references; this recipe needs ${needed}.`;
  }
  return "";
}

export function makeRunPayload(recipe: Recipe, sourceIds: string[], outputsPerSource: number) {
  return {
    recipe,
    source_ids: sourceIds,
    outputs_per_source: outputsPerSource,
    execution_mode: recipe.execution_mode,
  };
}
