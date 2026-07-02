export interface WordCloudInput {
  term: string;
  weight: number;
}

export interface PlacedTerm {
  term: string;
  x: number;
  y: number;
  fontSize: number;
  boxWidth: number;
  boxHeight: number;
  colorIndex: number;
}

const MIN_FONT = 12;
const FONT_RANGE = 30;
// Rough glyph metrics for a sans-serif face; layout only needs an estimate.
const CHAR_WIDTH_RATIO = 0.62;
const LINE_HEIGHT_RATIO = 1.1;

function overlaps(a: PlacedTerm, b: PlacedTerm): boolean {
  return (
    Math.abs(a.x - b.x) * 2 < a.boxWidth + b.boxWidth &&
    Math.abs(a.y - b.y) * 2 < a.boxHeight + b.boxHeight
  );
}

function insideCanvas(p: PlacedTerm, width: number, height: number): boolean {
  return (
    p.x - p.boxWidth / 2 >= 0 &&
    p.x + p.boxWidth / 2 <= width &&
    p.y - p.boxHeight / 2 >= 0 &&
    p.y + p.boxHeight / 2 <= height
  );
}

/**
 * Deterministic word-cloud layout: terms are placed heaviest-first along an
 * Archimedean spiral from the canvas center, rejecting positions that overlap
 * already-placed boxes. Terms that cannot fit are dropped.
 */
export function layoutWordCloud(
  terms: WordCloudInput[],
  width: number,
  height: number
): PlacedTerm[] {
  const placed: PlacedTerm[] = [];
  const sorted = [...terms].sort((a, b) => b.weight - a.weight || a.term.localeCompare(b.term));

  sorted.forEach((input, index) => {
    const fontSize = MIN_FONT + input.weight * FONT_RANGE;
    const candidate: PlacedTerm = {
      term: input.term,
      x: width / 2,
      y: height / 2,
      fontSize,
      boxWidth: Math.max(CHAR_WIDTH_RATIO * fontSize * input.term.length, fontSize),
      boxHeight: LINE_HEIGHT_RATIO * fontSize,
      colorIndex: index % 5,
    };

    const step = 0.35;
    const radiusPerTurn = 4.5;
    for (let i = 0; i < 2000; i++) {
      const angle = step * i;
      candidate.x = width / 2 + ((radiusPerTurn * angle) / (2 * Math.PI)) * Math.cos(angle);
      candidate.y = height / 2 + ((radiusPerTurn * angle) / (2 * Math.PI)) * Math.sin(angle) * 0.7;
      if (insideCanvas(candidate, width, height) && placed.every((p) => !overlaps(p, candidate))) {
        placed.push({ ...candidate });
        return;
      }
    }
  });

  return placed;
}
