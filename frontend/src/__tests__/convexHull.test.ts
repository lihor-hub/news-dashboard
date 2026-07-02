import { describe, it, expect } from 'vitest';
import { convexHull, padHull } from '../lib/convexHull';

describe('convexHull', () => {
  it('returns the input for fewer than 3 points', () => {
    expect(convexHull([])).toEqual([]);
    expect(convexHull([{ x: 1, y: 2 }])).toEqual([{ x: 1, y: 2 }]);
  });

  it('drops interior points of a square', () => {
    const square = [
      { x: 0, y: 0 },
      { x: 4, y: 0 },
      { x: 4, y: 4 },
      { x: 0, y: 4 },
      { x: 2, y: 2 }, // interior
    ];
    const hull = convexHull(square);
    expect(hull).toHaveLength(4);
    expect(hull).not.toContainEqual({ x: 2, y: 2 });
  });

  it('handles collinear and duplicate points', () => {
    const points = [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 2, y: 0 },
      { x: 2, y: 0 },
      { x: 2, y: 2 },
    ];
    const hull = convexHull(points);
    expect(hull).toHaveLength(3);
  });
});

describe('padHull', () => {
  it('expands the hull outward from its centroid', () => {
    const hull = [
      { x: 0, y: 0 },
      { x: 2, y: 0 },
      { x: 2, y: 2 },
      { x: 0, y: 2 },
    ];
    const padded = padHull(hull, 1);
    // Centroid is (1,1); every padded vertex must be further from it.
    for (let i = 0; i < hull.length; i++) {
      const before = Math.hypot(hull[i].x - 1, hull[i].y - 1);
      const after = Math.hypot(padded[i].x - 1, padded[i].y - 1);
      expect(after).toBeGreaterThan(before);
    }
  });
});
