import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type {
  EntityType,
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgeGraphResponse,
} from '@/types';
import { forceLayout } from '@/lib/forceLayout';
import type { ForcePoint } from '@/lib/forceLayout';
import { useInteractiveViewport } from '@/lib/useInteractiveViewport';
import { cn } from '@/lib/utils';

const CANVAS_W = 800;
const CANVAS_H = 600;

const TYPE_COLORS: Record<EntityType, string> = {
  person: 'var(--color-chart-1)',
  org: 'var(--color-chart-2)',
  product: 'var(--color-chart-3)',
  place: 'var(--color-chart-4)',
};

function nodeRadius(count: number): number {
  return 6 + 3 * Math.sqrt(count);
}

/** Generous upper bound for margin so nodes never clip at the SVG boundary */
const MAX_RADIUS = nodeRadius(50);

function isIncident(edge: KnowledgeGraphEdge, nodeId: string): boolean {
  return edge.source === nodeId || edge.target === nodeId;
}

interface KnowledgeGraphProps {
  graph: KnowledgeGraphResponse;
}

export function KnowledgeGraph({ graph }: KnowledgeGraphProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Mutable positions map (starts from forceLayout, updated by drag)
  const [positions, setPositions] = useState<Map<string, ForcePoint>>(() =>
    forceLayout(graph.nodes, graph.edges, CANVAS_W, CANVAS_H, MAX_RADIUS)
  );

  // Re-run layout when graph data identity changes
  useEffect(() => {
    setPositions(forceLayout(graph.nodes, graph.edges, CANVAS_W, CANVAS_H, MAX_RADIUS));
  }, [graph.nodes, graph.edges]);

  const { viewport, svgRef, svgProps, isPanning, resetViewport } = useInteractiveViewport({
    width: CANVAS_W,
    height: CANVAS_H,
  });

  // Track which node is being dragged (null = none) — kept in state so cursor updates
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);

  // Mutable drag-start data (not state — no re-render needed on update)
  const dragData = useRef<{
    startClientX: number;
    startClientY: number;
    startX: number;
    startY: number;
  } | null>(null);

  const handleNodeMouseDown = useCallback(
    (e: React.MouseEvent<SVGCircleElement>, nodeId: string) => {
      e.stopPropagation();
      const p = positions.get(nodeId);
      if (!p) return;
      dragData.current = {
        startClientX: e.clientX,
        startClientY: e.clientY,
        startX: p.x,
        startY: p.y,
      };
      setDraggingNodeId(nodeId);
    },
    [positions]
  );

  const handleSvgMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (dragData.current && draggingNodeId !== null) {
        e.stopPropagation();
        const svg = svgRef.current;
        if (!svg) return;
        const rect = svg.getBoundingClientRect();
        const scaleX = CANVAS_W / rect.width;
        const scaleY = CANVAS_H / rect.height;
        const dx = ((e.clientX - dragData.current.startClientX) * scaleX) / viewport.scale;
        const dy = ((e.clientY - dragData.current.startClientY) * scaleY) / viewport.scale;
        const newX = Math.max(
          MAX_RADIUS,
          Math.min(CANVAS_W - MAX_RADIUS, dragData.current.startX + dx)
        );
        const newY = Math.max(
          MAX_RADIUS,
          Math.min(CANVAS_H - MAX_RADIUS, dragData.current.startY + dy)
        );
        setPositions((prev) => {
          const next = new Map(prev);
          next.set(draggingNodeId, { x: newX, y: newY });
          return next;
        });
      } else {
        svgProps.onMouseMove(e);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [draggingNodeId, svgProps, viewport.scale]
  );

  const handleSvgMouseUp = useCallback(() => {
    if (draggingNodeId !== null) {
      dragData.current = null;
      setDraggingNodeId(null);
    } else {
      svgProps.onMouseUp();
    }
  }, [draggingNodeId, svgProps]);

  const handleSvgMouseLeave = useCallback(() => {
    if (draggingNodeId !== null) {
      dragData.current = null;
      setDraggingNodeId(null);
    } else {
      svgProps.onMouseLeave();
    }
  }, [draggingNodeId, svgProps]);

  const handleNodeClick = useCallback((e: React.MouseEvent, nodeId: string) => {
    e.stopPropagation();
    setSelectedId((prev) => (prev === nodeId ? null : nodeId));
  }, []);

  const selected = useMemo(
    () => graph.nodes.find((n: KnowledgeGraphNode) => n.id === selectedId) ?? null,
    [graph.nodes, selectedId]
  );

  const selectedArticles = useMemo(() => {
    if (!selected) return [];
    const wanted = new Set(selected.article_ids);
    return graph.articles.filter((a) => wanted.has(a.id));
  }, [graph.articles, selected]);

  if (graph.nodes.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        {graph.pending_count > 0
          ? `No entities yet — extraction is still running for ${graph.pending_count} article${
              graph.pending_count !== 1 ? 's' : ''
            }.`
          : 'No entities yet — the graph fills in as articles are analyzed.'}
      </p>
    );
  }

  const isDraggingNode = draggingNodeId !== null;
  const cursorClass = isDraggingNode || isPanning ? 'cursor-grabbing' : 'cursor-grab';
  const transform = `translate(${viewport.tx} ${viewport.ty}) scale(${viewport.scale})`;

  return (
    <div className="flex flex-col gap-3">
      {/* Graph canvas */}
      <div className="relative overflow-hidden rounded-lg border border-border bg-surface-2">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
          className={cn('h-auto w-full', cursorClass)}
          role="img"
          onMouseDown={svgProps.onMouseDown}
          onMouseMove={handleSvgMouseMove}
          onMouseUp={handleSvgMouseUp}
          onMouseLeave={handleSvgMouseLeave}
          onWheel={svgProps.onWheel}
        >
          <title>Knowledge graph of entities in recent news</title>
          {/* Transparent backdrop to capture pan clicks */}
          <rect x={0} y={0} width={CANVAS_W} height={CANVAS_H} fill="transparent" />

          <g transform={transform}>
            {graph.edges.map((edge) => {
              const a = positions.get(edge.source);
              const b = positions.get(edge.target);
              if (!a || !b) return null;
              const dimmed = selectedId !== null && !isIncident(edge, selectedId);
              return (
                <line
                  key={`${edge.source}--${edge.target}`}
                  data-testid="kg-edge"
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  strokeWidth={Math.min(1 + edge.weight, 6)}
                  className={cn('stroke-primary/30', dimmed && 'stroke-primary/10')}
                />
              );
            })}
            {graph.nodes.map((node: KnowledgeGraphNode) => {
              const p = positions.get(node.id);
              if (!p) return null;
              const dimmed = selectedId !== null && selectedId !== node.id;
              const r = nodeRadius(node.count);
              const isThisNodeDragging = draggingNodeId === node.id;
              return (
                <g key={node.id}>
                  <circle
                    data-testid="kg-node"
                    data-entity={node.id}
                    cx={p.x}
                    cy={p.y}
                    r={r}
                    fill={TYPE_COLORS[node.type]}
                    fillOpacity={dimmed ? 0.3 : 0.85}
                    className={cn(
                      'stroke-background stroke-[1.5] transition-opacity',
                      isThisNodeDragging ? 'cursor-grabbing' : 'cursor-pointer hover:stroke-[2.5]'
                    )}
                    onMouseDown={(e) => handleNodeMouseDown(e, node.id)}
                    onClick={(e) => handleNodeClick(e, node.id)}
                  >
                    <title>{`${node.name} — ${node.count} article${node.count !== 1 ? 's' : ''}`}</title>
                  </circle>
                  <text
                    x={p.x}
                    y={p.y - r - 4}
                    textAnchor="middle"
                    className={cn(
                      'pointer-events-none select-none fill-foreground text-[11px] font-medium',
                      dimmed && 'opacity-30'
                    )}
                  >
                    {node.name}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>

        {/* Controls overlay */}
        <div className="absolute bottom-2 right-2 flex gap-1">
          <button
            type="button"
            title="Reset view"
            onClick={resetViewport}
            className="rounded-md bg-background/80 px-2 py-1 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur hover:text-foreground"
          >
            Reset
          </button>
        </div>

        {/* Hint */}
        <p className="absolute bottom-2 left-2 select-none text-[10px] text-muted-foreground/50">
          Scroll to zoom · Drag background to pan · Drag node to move
        </p>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {(Object.keys(TYPE_COLORS) as EntityType[]).map((type) => (
          <span key={type} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span
              className="size-2.5 rounded-full"
              style={{ backgroundColor: TYPE_COLORS[type] }}
            />
            {type}
          </span>
        ))}
      </div>

      {/* Selected node detail */}
      {selected && (
        <div className="rounded-xl border border-border bg-surface-2 p-4">
          <h3 className="text-sm font-semibold">
            {selected.name}{' '}
            <span className="font-normal text-muted-foreground">
              · {selected.type} · {selected.count} article{selected.count !== 1 ? 's' : ''}
            </span>
          </h3>
          <ul className="mt-2 grid gap-1.5">
            {selectedArticles.map((article) => (
              <li key={article.id}>
                <Link
                  to={`/a/${article.id}`}
                  className="text-xs text-foreground hover:text-primary hover:underline"
                >
                  {article.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
