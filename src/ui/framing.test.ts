import { describe, expect, it } from "vitest";
import { calculateCoverTransform } from "./framing";

describe("cover framing", () => {
  it("covers the art window at minimum zoom", () => {
    const result = calculateCoverTransform([160, 220], [336, 276], { zoom: 1, offset_x: 0, offset_y: 0 });
    expect(result.image_bounds[0]).toBeLessThanOrEqual(0);
    expect(result.image_bounds[1]).toBeLessThanOrEqual(0);
    expect(result.image_bounds[2]).toBeGreaterThanOrEqual(336);
    expect(result.image_bounds[3]).toBeGreaterThanOrEqual(276);
  });

  it("clamps offsets without exposing empty pixels", () => {
    const result = calculateCoverTransform([160, 220], [336, 276], { zoom: 1.1, offset_x: 99, offset_y: -99 });
    expect(result.image_bounds[0]).toBeLessThanOrEqual(0);
    expect(result.image_bounds[1]).toBeLessThanOrEqual(0);
    expect(result.image_bounds[2]).toBeGreaterThanOrEqual(336);
    expect(result.image_bounds[3]).toBeGreaterThanOrEqual(276);
  });
});
