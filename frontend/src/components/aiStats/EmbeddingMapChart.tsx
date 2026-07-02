import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { EmbeddingMapCluster, EmbeddingMapPoint } from '@/types';
import { categoryColorMap, colorForCategory } from '@/lib/categoryColor';
import { convexHull, hullPath, padHull } from '@/lib/convexHull';

const CANVAS_W = 800;
const CANVAS_H = 560;
const PADDING = 48;
const POINT_R = 6;
const HULL_PAD = 18;
const MIN_HULL_SIZE = 3;

function toCanvasX(v: number): number {
  return PADDING + ((v + 1) / 2) * (CANVAS_W - PADDING * 2);
}

function toCanvasY(v: number): number {
  return PADDING + ((v + 1) / 2) * (CANVAS_H - PADDING * 2);
}

interface TooltipState {
  x: number;
  y: number;
  title: string;
}

interface EmbeddingMapChartProps {
  points: EmbeddingMapPoint[];
  clusters: EmbeddingMapCluster[];
}

export function EmbeddingMapChart({ points, clusters }: EmbeddingMapChartProps) {
  const navigate = useNavigate();
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const colors = useMemo(() => categoryColorMap(points.map((p) => p.category)), [points]);

  const hulls = useMemo(() => {
    const byCluster = new Map<number, EmbeddingMapPoint[]>();
    for (const p of points) {
      const list = byCluster.get(p.cluster) ?? [];
      list.push(p);
      byCluster.set(p.cluster, list);
    }
    return clusters
      .filter((c) => (byCluster.get(c.id)?.length ?? 0) >= MIN_HULL_SIZE)
      .map((cluster) => {
        const members = byCluster.get(cluster.id) ?? [];
        const hull = padHull(
          convexHull(members.map((p) => ({ x: toCanvasX(p.x), y: toCanvasY(p.y) }))),
          HULL_PAD
        );
        const cx = members.reduce((s, p) => s + toCanvasX(p.x), 0) / members.length;
        const topY = Math.min(...hull.map((h) => h.y));
        return { cluster, path: hullPath(hull), cx, topY };
      });
  }, [points, clusters]);

  const handleClick = useCallback((id: number) => void navigate(`/a/${id}`), [navigate]);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`} className="h-auto w-full" role="img">
        <title>Embedding-space map of recent articles</title>
        {hulls.map(({ cluster, path, cx, topY }) => (
          <g key={`hull-${cluster.id}`} className="pointer-events-none">
            <path d={path} className="fill-primary/5 stroke-primary/20 stroke-[1]" />
            <text
              x={cx}
              y={topY - 6}
              textAnchor="middle"
              className="select-none fill-muted-foreground text-[11px] font-medium"
            >
              {cluster.label}
            </text>
          </g>
        ))}
        {points.map((p) => (
          <circle
            key={p.id}
            data-testid="embedding-point"
            cx={toCanvasX(p.x)}
            cy={toCanvasY(p.y)}
            r={POINT_R}
            fill={colorForCategory(colors, p.category)}
            fillOpacity={0.75}
            className="cursor-pointer stroke-background stroke-[1.5] transition-all hover:fill-opacity-100"
            onMouseEnter={(e) => setTooltip({ x: e.clientX, y: e.clientY, title: p.title })}
            onMouseLeave={() => setTooltip(null)}
            onClick={() => handleClick(p.id)}
          />
        ))}
      </svg>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {[...colors.entries()].map(([category, color]) => (
          <span
            key={category}
            className="flex items-center gap-1.5 text-[11px] text-muted-foreground"
          >
            <span className="size-2.5 rounded-full" style={{ backgroundColor: color }} />
            {category}
          </span>
        ))}
      </div>

      {tooltip && (
        <div
          className="pointer-events-none fixed z-50 max-w-xs rounded-lg border border-border bg-background/95 px-3 py-2 shadow-lg backdrop-blur-sm"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          <p className="text-xs font-semibold leading-snug">{tooltip.title}</p>
        </div>
      )}
    </div>
  );
}
