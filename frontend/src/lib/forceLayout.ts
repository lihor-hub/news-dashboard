export interface ForceNode {
  id: string;
}

export interface ForceEdge {
  source: string;
  target: string;
  weight: number;
}

export interface ForcePoint {
  x: number;
  y: number;
}

const ITERATIONS = 300;
const REPULSION = 0.08; // fraction of area per node pair
const SPRING = 0.02;
const CENTERING = 0.01;
const COOLING = 0.98;

/**
 * Deterministic force-directed layout: nodes start evenly spaced on a circle
 * (so the result is reproducible without randomness), then iterate pairwise
 * repulsion, weighted spring attraction along edges, and a centering pull,
 * with a cooling step cap. Positions are clamped to the viewport with an
 * optional `margin` so node circles never clip at the SVG boundary.
 */
export function forceLayout(
  nodes: ForceNode[],
  edges: ForceEdge[],
  width: number,
  height: number,
  margin = 0
): Map<string, ForcePoint> {
  const layout = new Map<string, ForcePoint>();
  if (nodes.length === 0) return layout;

  const cx = width / 2;
  const cy = height / 2;
  const startRadius = Math.min(width, height) * 0.35;
  nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / nodes.length;
    layout.set(node.id, {
      x: cx + startRadius * Math.cos(angle),
      y: cy + startRadius * Math.sin(angle),
    });
  });
  if (nodes.length === 1) {
    layout.set(nodes[0].id, { x: cx, y: cy });
    return layout;
  }

  const ids = nodes.map((n) => n.id);
  const validEdges = edges.filter((e) => layout.has(e.source) && layout.has(e.target));
  const repulsionK = REPULSION * ((width * height) / nodes.length);
  let maxStep = Math.min(width, height) / 10;

  for (let iter = 0; iter < ITERATIONS; iter++) {
    const force = new Map<string, ForcePoint>(ids.map((id) => [id, { x: 0, y: 0 }]));

    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = layout.get(ids[i])!;
        const b = layout.get(ids[j])!;
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let distSq = dx * dx + dy * dy;
        if (distSq < 1) {
          // Deterministic nudge for coincident points.
          dx = 0.5 * (i - j);
          dy = 0.5;
          distSq = dx * dx + dy * dy;
        }
        const push = repulsionK / distSq;
        const fa = force.get(ids[i])!;
        const fb = force.get(ids[j])!;
        fa.x += dx * push;
        fa.y += dy * push;
        fb.x -= dx * push;
        fb.y -= dy * push;
      }
    }

    for (const edge of validEdges) {
      const a = layout.get(edge.source)!;
      const b = layout.get(edge.target)!;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const pull = SPRING * Math.min(edge.weight, 5);
      const fa = force.get(edge.source)!;
      const fb = force.get(edge.target)!;
      fa.x += dx * pull;
      fa.y += dy * pull;
      fb.x -= dx * pull;
      fb.y -= dy * pull;
    }

    for (const id of ids) {
      const p = layout.get(id)!;
      const f = force.get(id)!;
      f.x += (cx - p.x) * CENTERING;
      f.y += (cy - p.y) * CENTERING;

      const magnitude = Math.hypot(f.x, f.y) || 1;
      const step = Math.min(magnitude, maxStep);
      layout.set(id, {
        x: Math.min(width - margin, Math.max(margin, p.x + (f.x / magnitude) * step)),
        y: Math.min(height - margin, Math.max(margin, p.y + (f.y / magnitude) * step)),
      });
    }

    maxStep *= COOLING;
  }

  return layout;
}
