export type Framing = { zoom: number; offset_x: number; offset_y: number };
export type FramingTransform = { base_scale: number; scale: number; left: number; top: number; scaled_width: number; scaled_height: number; offset_x: number; offset_y: number; window: [number, number]; image_bounds: [number, number, number, number] };

/** Browser equivalent of tools.cards.pipeline.calculate_cover_transform. */
export function calculateCoverTransform(imageSize: [number, number], windowSize: [number, number], framing: Framing): FramingTransform {
  const [imageWidth, imageHeight] = imageSize;
  const [windowWidth, windowHeight] = windowSize;
  const zoom = Math.max(1, Math.min(3, framing.zoom));
  const baseScale = Math.max(windowWidth / imageWidth, windowHeight / imageHeight);
  const scale = baseScale * zoom;
  const scaledWidth = imageWidth * scale;
  const scaledHeight = imageHeight * scale;
  const centredLeft = (windowWidth - scaledWidth) / 2;
  const centredTop = (windowHeight - scaledHeight) / 2;
  const requestedLeft = centredLeft + framing.offset_x * windowWidth;
  const requestedTop = centredTop + framing.offset_y * windowHeight;
  const left = Math.min(0, Math.max(windowWidth - scaledWidth, requestedLeft));
  const top = Math.min(0, Math.max(windowHeight - scaledHeight, requestedTop));
  return { base_scale: baseScale, scale, left, top, scaled_width: scaledWidth, scaled_height: scaledHeight, offset_x: (left - centredLeft) / windowWidth, offset_y: (top - centredTop) / windowHeight, window: [windowWidth, windowHeight], image_bounds: [left, top, left + scaledWidth, top + scaledHeight] };
}
