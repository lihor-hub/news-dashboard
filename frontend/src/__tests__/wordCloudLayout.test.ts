import { describe, it, expect } from 'vitest';
import { layoutWordCloud, type PlacedTerm } from '../lib/wordCloudLayout';

const CANVAS = { width: 800, height: 480 };

function boxesOverlap(a: PlacedTerm, b: PlacedTerm): boolean {
  return (
    Math.abs(a.x - b.x) * 2 < a.boxWidth + b.boxWidth &&
    Math.abs(a.y - b.y) * 2 < a.boxHeight + b.boxHeight
  );
}

describe('layoutWordCloud', () => {
  it('returns an empty layout for no terms', () => {
    expect(layoutWordCloud([], CANVAS.width, CANVAS.height)).toEqual([]);
  });

  it('is deterministic for the same input', () => {
    const terms = [
      { term: 'kubernetes', weight: 1 },
      { term: 'quantum', weight: 0.6 },
      { term: 'rust', weight: 0.3 },
    ];
    const a = layoutWordCloud(terms, CANVAS.width, CANVAS.height);
    const b = layoutWordCloud(terms, CANVAS.width, CANVAS.height);
    expect(a).toEqual(b);
  });

  it('gives higher-weighted terms a larger font size', () => {
    const placed = layoutWordCloud(
      [
        { term: 'big', weight: 1 },
        { term: 'small', weight: 0.1 },
      ],
      CANVAS.width,
      CANVAS.height
    );
    const big = placed.find((p) => p.term === 'big')!;
    const small = placed.find((p) => p.term === 'small')!;
    expect(big.fontSize).toBeGreaterThan(small.fontSize);
  });

  it('places terms without overlapping boxes and inside the canvas', () => {
    const terms = Array.from({ length: 30 }, (_, i) => ({
      term: `term-${i}`,
      weight: 1 - i / 30,
    }));
    const placed = layoutWordCloud(terms, CANVAS.width, CANVAS.height);
    expect(placed.length).toBeGreaterThan(0);
    for (let i = 0; i < placed.length; i++) {
      expect(placed[i].x - placed[i].boxWidth / 2).toBeGreaterThanOrEqual(0);
      expect(placed[i].x + placed[i].boxWidth / 2).toBeLessThanOrEqual(CANVAS.width);
      expect(placed[i].y - placed[i].boxHeight / 2).toBeGreaterThanOrEqual(0);
      expect(placed[i].y + placed[i].boxHeight / 2).toBeLessThanOrEqual(CANVAS.height);
      for (let j = i + 1; j < placed.length; j++) {
        expect(boxesOverlap(placed[i], placed[j])).toBe(false);
      }
    }
  });

  it('assigns a stable color index per term', () => {
    const placed = layoutWordCloud(
      [
        { term: 'alpha', weight: 1 },
        { term: 'beta', weight: 0.5 },
      ],
      CANVAS.width,
      CANVAS.height
    );
    for (const p of placed) {
      expect(p.colorIndex).toBeGreaterThanOrEqual(0);
      expect(Number.isInteger(p.colorIndex)).toBe(true);
    }
  });
});
