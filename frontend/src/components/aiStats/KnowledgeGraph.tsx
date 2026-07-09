import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Background,
  BaseEdge,
  Controls,
  Handle,
  Position,
  ReactFlow,
  applyNodeChanges,
  getStraightPath,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
  type OnNodesChange,
} from '@xyflow/react';
import { Link } from 'react-router-dom';
import type {
  EntityType,
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgeGraphResponse,
} from '@/types';
import { forceLayout } from '@/lib/forceLayout';
import { cn } from '@/lib/utils';

const CANVAS_W = 800;
const CANVAS_H = 600;
type EdgeFilter = 'all' | 'cooccurrence' | 'typed';

const TYPE_COLORS: Record<EntityType, string> = {
  person: 'var(--color-chart-1)',
  org: 'var(--color-chart-2)',
  product: 'var(--color-chart-3)',
  place: 'var(--color-chart-4)',
};

function nodeRadius(count: number): number {
  return 6 + 3 * Math.sqrt(count);
}

/** Generous upper bound for margin so nodes never clip at the viewport boundary */
const MAX_RADIUS = nodeRadius(50);

function isIncident(edge: KnowledgeGraphEdge, nodeId: string): boolean {
  return edge.source === nodeId || edge.target === nodeId;
}

function edgeKind(edge: KnowledgeGraphEdge): 'cooccurrence' | 'typed' {
  return edge.kind ?? 'cooccurrence';
}

type KnowledgeFlowNodeData = Record<string, unknown> & {
  entity: KnowledgeGraphNode;
  color: string;
  dimmed: boolean;
  radius: number;
};

type KnowledgeFlowEdgeData = Record<string, unknown> & {
  kind: 'cooccurrence' | 'typed';
};

type KnowledgeFlowNode = Node<KnowledgeFlowNodeData, 'entity'>;
type KnowledgeFlowEdge = Edge<KnowledgeFlowEdgeData, 'relationship'>;

function EntityNode({ data }: NodeProps<KnowledgeFlowNode>) {
  const diameter = data.radius * 2;
  return (
    <div className="relative flex items-center justify-center">
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <div
        data-testid="kg-node"
        data-entity={data.entity.id}
        title={`${data.entity.name} - ${data.entity.count} article${
          data.entity.count !== 1 ? 's' : ''
        }`}
        className={cn(
          'grid place-items-center rounded-full border-[1.5px] border-background text-[10px] font-semibold text-background shadow-sm transition-opacity',
          data.dimmed ? 'opacity-30' : 'opacity-90'
        )}
        style={{
          width: diameter,
          height: diameter,
          backgroundColor: data.color,
        }}
      />
      <span
        className={cn(
          'pointer-events-none absolute left-1/2 top-0 max-w-28 -translate-x-1/2 -translate-y-full select-none truncate pb-1 text-[11px] font-medium text-foreground',
          data.dimmed && 'opacity-30'
        )}
      >
        {data.entity.name}
      </span>
      <Handle type="source" position={Position.Right} className="opacity-0" />
    </div>
  );
}

function RelationshipEdge({
  data,
  id,
  sourceX,
  sourceY,
  style,
  targetX,
  targetY,
}: EdgeProps<KnowledgeFlowEdge>) {
  const [edgePath] = getStraightPath({ sourceX, sourceY, targetX, targetY });
  const kind = data?.kind ?? 'cooccurrence';
  return <BaseEdge id={id} data-testid="kg-edge" data-kind={kind} path={edgePath} style={style} />;
}

const NODE_TYPES = { entity: EntityNode };
const EDGE_TYPES = { relationship: RelationshipEdge };

function makeNode(
  entity: KnowledgeGraphNode,
  position: { x: number; y: number },
  selectedId: string | null
): KnowledgeFlowNode {
  const radius = nodeRadius(entity.count);
  const diameter = radius * 2;
  return {
    id: entity.id,
    type: 'entity',
    position,
    width: diameter,
    height: diameter,
    initialWidth: diameter,
    initialHeight: diameter,
    origin: [0.5, 0.5],
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    handles: [
      {
        id: null,
        type: 'target',
        position: Position.Left,
        x: 0,
        y: radius,
        width: 1,
        height: 1,
      },
      {
        id: null,
        type: 'source',
        position: Position.Right,
        x: diameter,
        y: radius,
        width: 1,
        height: 1,
      },
    ],
    data: {
      entity,
      color: TYPE_COLORS[entity.type],
      dimmed: selectedId !== null && selectedId !== entity.id,
      radius,
    },
    draggable: true,
    focusable: true,
    selectable: false,
  };
}

function makeEdge(edge: KnowledgeGraphEdge, index: number, selectedId: string | null) {
  const kind = edgeKind(edge);
  const dimmed = selectedId !== null && !isIncident(edge, selectedId);
  return {
    id: `${edge.source}--${edge.target}--${kind}--${edge.relationship_type ?? index}`,
    source: edge.source,
    target: edge.target,
    type: 'relationship',
    data: { kind },
    selectable: false,
    style: {
      stroke:
        kind === 'typed'
          ? 'color-mix(in oklch, var(--color-accent-foreground) 50%, transparent)'
          : 'color-mix(in oklch, var(--color-primary) 30%, transparent)',
      strokeDasharray: kind === 'typed' ? '5 4' : undefined,
      strokeWidth: Math.min(1 + edge.weight, 6),
      opacity: dimmed ? 0.35 : 1,
    },
  } satisfies KnowledgeFlowEdge;
}

interface KnowledgeGraphProps {
  graph: KnowledgeGraphResponse;
}

export function KnowledgeGraph({ graph }: KnowledgeGraphProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [edgeFilter, setEdgeFilter] = useState<EdgeFilter>('all');
  const [flowNodes, setFlowNodes] = useState<KnowledgeFlowNode[]>([]);

  useEffect(() => {
    const positions = forceLayout(graph.nodes, graph.edges, CANVAS_W, CANVAS_H, MAX_RADIUS);
    setFlowNodes(
      graph.nodes.map((entity) =>
        makeNode(entity, positions.get(entity.id) ?? { x: CANVAS_W / 2, y: CANVAS_H / 2 }, null)
      )
    );
    setSelectedId(null);
  }, [graph.nodes, graph.edges]);

  useEffect(() => {
    setFlowNodes((nodes) =>
      nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          dimmed: selectedId !== null && selectedId !== node.id,
        },
      }))
    );
  }, [selectedId]);

  const onNodesChange = useCallback<OnNodesChange<KnowledgeFlowNode>>(
    (changes) => setFlowNodes((nodes) => applyNodeChanges(changes, nodes)),
    []
  );

  const selected = useMemo(
    () => graph.nodes.find((n: KnowledgeGraphNode) => n.id === selectedId) ?? null,
    [graph.nodes, selectedId]
  );

  const nodeNameById = useMemo(
    () => new Map(graph.nodes.map((node: KnowledgeGraphNode) => [node.id, node.name])),
    [graph.nodes]
  );

  const visibleEdges = useMemo(
    () => graph.edges.filter((edge) => edgeFilter === 'all' || edgeKind(edge) === edgeFilter),
    [edgeFilter, graph.edges]
  );

  const flowEdges = useMemo(
    () => visibleEdges.map((edge, index) => makeEdge(edge, index, selectedId)),
    [selectedId, visibleEdges]
  );

  const selectedArticles = useMemo(() => {
    if (!selected) return [];
    const wanted = new Set(selected.article_ids);
    return graph.articles.filter((a) => wanted.has(a.id));
  }, [graph.articles, selected]);

  const selectedRelationships = useMemo(() => {
    if (!selected) return [];
    return visibleEdges.filter((edge) => isIncident(edge, selected.id));
  }, [selected, visibleEdges]);

  const handleNodeClick = useCallback((_event: React.MouseEvent, node: KnowledgeFlowNode) => {
    setSelectedId((prev) => (prev === node.id ? null : node.id));
  }, []);

  if (graph.graph_enabled === false) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        {graph.disabled_reason ?? 'Knowledge graph storage is not enabled.'}
      </p>
    );
  }

  if (graph.nodes.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        {graph.pending_count > 0
          ? `No entities yet - extraction is still running for ${graph.pending_count} article${
              graph.pending_count !== 1 ? 's' : ''
            }.`
          : 'No entities yet - the graph fills in as articles are analyzed.'}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {[
          ['all', 'All relationships'],
          ['cooccurrence', 'Co-occurrence'],
          ['typed', 'Typed relationships'],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={edgeFilter === value}
            onClick={() => setEdgeFilter(value as EdgeFilter)}
            className={cn(
              'rounded px-2.5 py-1 text-xs transition-colors',
              edgeFilter === value
                ? 'bg-primary text-primary-foreground'
                : 'bg-surface-2 text-muted-foreground hover:text-foreground'
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="relative h-[28rem] w-full overflow-hidden rounded-lg border border-border bg-surface-2">
        <ReactFlow<KnowledgeFlowNode, KnowledgeFlowEdge>
          className="h-full w-full"
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          onNodeClick={handleNodeClick}
          onNodesChange={onNodesChange}
          fitView
          minZoom={0.35}
          maxZoom={2.5}
          nodesConnectable={false}
          edgesFocusable={false}
          panOnScroll
          proOptions={{ hideAttribution: true }}
        >
          <Background color="var(--color-border)" gap={24} />
          <Controls position="bottom-right" showInteractive={false} />
        </ReactFlow>

        <p className="pointer-events-none absolute bottom-2 left-2 select-none text-[10px] text-muted-foreground/50">
          Scroll to zoom · Drag background to pan · Drag nodes to move
        </p>
      </div>

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
        <span className="text-[11px] text-muted-foreground">solid: co-occurrence</span>
        <span className="text-[11px] text-muted-foreground">dashed: typed relationship</span>
      </div>

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
          {selectedRelationships.length > 0 && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-muted-foreground">Relationships</h4>
              <ul className="mt-2 grid gap-1.5">
                {selectedRelationships.map((edge, index) => {
                  const otherId = edge.source === selected.id ? edge.target : edge.source;
                  const otherName = nodeNameById.get(otherId) ?? otherId;
                  const label =
                    edge.label ??
                    (edge.kind === 'typed'
                      ? (edge.relationship_type ?? 'related to').replace(/_/g, ' ')
                      : 'co-mentioned with');
                  const articles = graph.articles.filter((article) =>
                    edge.article_ids.includes(article.id)
                  );
                  return (
                    <li
                      key={`${edge.source}--${edge.target}--${edge.relationship_type ?? index}`}
                      className="text-xs text-muted-foreground"
                    >
                      <span className="font-medium text-foreground">
                        {label} {otherName}
                      </span>
                      {articles.length > 0 && (
                        <span>
                          {' '}
                          ·{' '}
                          {articles.map((article, articleIndex) => (
                            <span key={article.id}>
                              {articleIndex > 0 ? ', ' : ''}
                              <Link
                                to={`/a/${article.id}`}
                                className="text-foreground hover:text-primary hover:underline"
                              >
                                {article.title}
                              </Link>
                            </span>
                          ))}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
