import { describe, it, expect } from 'vitest';
import { forceLayout } from '../lib/forceLayout';

const W = 800;
const H = 600;

const NODES = Array.from({ length: 8 }, (_, i) => ({ id: `n${i}` }));
const EDGES = [
  { source: 'n0', target: 'n1', weight: 3 },
  { source: 'n1', target: 'n2', weight: 1 },
  { source: 'n3', target: 'n4', weight: 2 },
];

describe('forceLayout', () => {
  it('returns an empty map for no nodes', () => {
    expect(forceLayout([], [], W, H).size).toBe(0);
  });

  it('positions every node inside the viewport without NaN', () => {
    const layout = forceLayout(NODES, EDGES, W, H);
    expect(layout.size).toBe(NODES.length);
    for (const { x, y } of layout.values()) {
      expect(Number.isFinite(x)).toBe(true);
      expect(Number.isFinite(y)).toBe(true);
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(W);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(H);
    }
  });

  it('is deterministic for the same input', () => {
    const a = forceLayout(NODES, EDGES, W, H);
    const b = forceLayout(NODES, EDGES, W, H);
    expect([...a.entries()]).toEqual([...b.entries()]);
  });

  it('pulls connected nodes closer than the average unconnected pair', () => {
    const layout = forceLayout(NODES, EDGES, W, H);
    const dist = (a: string, b: string) => {
      const pa = layout.get(a)!;
      const pb = layout.get(b)!;
      return Math.hypot(pa.x - pb.x, pa.y - pb.y);
    };
    const connected = EDGES.map((e) => dist(e.source, e.target));
    const connectedSet = new Set(EDGES.map((e) => [e.source, e.target].sort().join('|')));
    const unconnected: number[] = [];
    for (let i = 0; i < NODES.length; i++) {
      for (let j = i + 1; j < NODES.length; j++) {
        const key = [NODES[i].id, NODES[j].id].sort().join('|');
        if (!connectedSet.has(key)) unconnected.push(dist(NODES[i].id, NODES[j].id));
      }
    }
    const mean = (xs: number[]) => xs.reduce((s, v) => s + v, 0) / xs.length;
    expect(mean(connected)).toBeLessThan(mean(unconnected));
  });

  describe('with a large sparse graph (realistic entity extraction shape)', () => {
    const MARGIN = 28;
    const bigNodes = Array.from({ length: 60 }, (_, i) => ({ id: `b${i}` }));
    const bigEdges = [
      // hub-and-spoke around b0
      ...Array.from({ length: 8 }, (_, i) => ({
        source: 'b0',
        target: `b${i + 1}`,
        weight: 1 + (i % 3),
      })),
      // a chain b10..b20
      ...Array.from({ length: 10 }, (_, i) => ({
        source: `b${i + 10}`,
        target: `b${i + 11}`,
        weight: 1,
      })),
      // a few cross links; the rest of the nodes stay isolated
      { source: 'b5', target: 'b15', weight: 2 },
      { source: 'b8', target: 'b30', weight: 1 },
      { source: 'b25', target: 'b40', weight: 3 },
    ];

    it('does not pile nodes up along the viewport boundary', () => {
      const layout = forceLayout(bigNodes, bigEdges, W, H, MARGIN);
      let onBoundary = 0;
      for (const { x, y } of layout.values()) {
        const atEdge =
          Math.abs(x - MARGIN) < 0.5 ||
          Math.abs(x - (W - MARGIN)) < 0.5 ||
          Math.abs(y - MARGIN) < 0.5 ||
          Math.abs(y - (H - MARGIN)) < 0.5;
        if (atEdge) onBoundary++;
      }
      // A fitted layout touches the boundary only at its bounding-box extremes.
      expect(onBoundary).toBeLessThanOrEqual(Math.ceil(bigNodes.length * 0.15));
    });

    it('keeps every pair of nodes far enough apart for labels to stay legible', () => {
      const layout = forceLayout(bigNodes, bigEdges, W, H, MARGIN);
      const pts = [...layout.values()];
      let minDist = Infinity;
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          minDist = Math.min(minDist, Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y));
        }
      }
      expect(minDist).toBeGreaterThanOrEqual(24);
    });

    it('stays inside the margin bounds', () => {
      const layout = forceLayout(bigNodes, bigEdges, W, H, MARGIN);
      for (const { x, y } of layout.values()) {
        expect(x).toBeGreaterThanOrEqual(MARGIN);
        expect(x).toBeLessThanOrEqual(W - MARGIN);
        expect(y).toBeGreaterThanOrEqual(MARGIN);
        expect(y).toBeLessThanOrEqual(H - MARGIN);
      }
    });
  });

  it('ignores edges that reference unknown nodes', () => {
    const layout = forceLayout(
      [{ id: 'a' }, { id: 'b' }],
      [{ source: 'a', target: 'ghost', weight: 1 }],
      W,
      H
    );
    expect(layout.size).toBe(2);
    for (const { x, y } of layout.values()) {
      expect(Number.isFinite(x)).toBe(true);
      expect(Number.isFinite(y)).toBe(true);
    }
  });
});
