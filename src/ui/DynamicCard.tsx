import { memo } from "react";
import type { ProducedCard, ProductionItem } from "./types";

const GLYPHS: Record<string, string[]> = {
  A: ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
  B: ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
  C: ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
  D: ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
  E: ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
  F: ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
  G: ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
  H: ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
  I: ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
  J: ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
  K: ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
  L: ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
  M: ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
  N: ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
  O: ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
  P: ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
  Q: ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
  R: ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
  S: ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
  T: ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
  U: ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
  V: ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
  W: ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
  X: ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
  Y: ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
  Z: ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
  "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
  "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
  "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
  "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
  "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
  "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
  "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
  "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
  "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
  "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
  " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
  "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
  ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
};
const UNKNOWN = ["11111", "00001", "00010", "00100", "00100", "00000", "00100"];

export const PixelText = memo(function PixelText({
  children,
  className = "",
}: {
  children: string;
  className?: string;
}) {
  return (
    <span
      className={`pixel-text ${className}`}
      role="img"
      aria-label={children}
    >
      {[...children.toUpperCase()].map((character, index) => (
        <span
          className="pixel-glyph"
          aria-hidden="true"
          key={`${character}-${index}`}
        >
          {(GLYPHS[character] || UNKNOWN).flatMap((row, y) =>
            [...row].map((pixel, x) =>
              pixel === "1" ? (
                <i
                  key={`${x}-${y}`}
                  style={{ gridColumn: x + 1, gridRow: y + 1 }}
                />
              ) : null,
            ),
          )}
        </span>
      ))}
    </span>
  );
});

export const DynamicCard = memo(function DynamicCard({
  item,
  artUrl,
  text,
}: {
  item?: Pick<
    ProductionItem,
    "art_url" | "card_text" | "source_label" | "attempt_number"
  > &
    Partial<Pick<ProducedCard, "batch_id" | "pipeline_label">>;
  artUrl?: string;
  text?: ProductionItem["card_text"];
}) {
  const cardText = text ||
    item?.card_text || {
      title: item?.source_label || "Untitled",
      lines: [
        item?.pipeline_label || "Rendered artwork",
        item?.batch_id || "Asset Workbench",
        `Attempt ${item?.attempt_number || 1}`,
      ],
    };
  const image = artUrl || item?.art_url;
  return (
    <article
      className="dynamic-card"
      aria-label={`${cardText.title} showcase card`}
    >
      <div className="dynamic-card-frame">
        <header className="dynamic-card-brand">
          <PixelText>Asset Workbench</PixelText>
        </header>
        <div className="dynamic-card-art">
          {image ? (
            <img src={image} alt="Rendered artwork" />
          ) : (
            <span>Artwork unavailable</span>
          )}
        </div>
        <div className="dynamic-card-nameplate">
          <PixelText className="dynamic-card-title">{cardText.title}</PixelText>
        </div>
        <div className="dynamic-card-details">
          <div className="dynamic-card-lines">
            {cardText.lines.map((line, index) => (
              <span key={index}>{line || "\u00a0"}</span>
            ))}
          </div>
        </div>
      </div>
    </article>
  );
});
