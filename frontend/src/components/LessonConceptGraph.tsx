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
import { Link } from 'react-router';
import type { LessonDetail, LessonGraphContext, LessonGraphEntity } from '@/api';
import { Badge } from '@/components/ui/badge';
import { forceLayout } from '@/lib/forceLayout';
import { cn } from '@/lib/utils';

const CANVAS_W = 760;
const CANVAS_H = 480;
const MAX_RADIUS = 28;

const TYPE_COLORS: Record<LessonGraphEntity['type'], string> = {
  concept: 'var(--color-primary)',
  person: 'var(--color-chart-1)',
  org: 'var(--color-chart-2)',
  product: 'var(--color-chart-3)',
  place: 'var(--color-chart-4)',
};

type LessonFlowNodeData = Record<string, unknown> & {
  entity: LessonGraphEntity;
  color: string;
  dimmed: boolean;
};

type LessonFlowEdgeData = Record<string, unknown> & {
  label: string;
  confidence: number;
};

type LessonFlowNode = Node<LessonFlowNodeData, 'lessonConcept'>;
type LessonFlowEdge = Edge<LessonFlowEdgeData, 'lessonRelationship'>;

function ConceptNode({ data }: NodeProps<LessonFlowNode>) {
  return (
    <div className="relative flex items-center justify-center">
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <div
        role="button"
        tabIndex={0}
        data-testid="lesson-graph-node"
        data-entity={data.entity.id}
        title={`${data.entity.name} - ${data.entity.type}`}
        className={cn(
          'grid size-10 place-items-center rounded-full border-[1.5px] border-background text-[10px] font-semibold text-background shadow-sm transition-opacity',
          data.dimmed ? 'opacity-35' : 'opacity-95'
        )}
        style={{ backgroundColor: data.color }}
      />
      <span
        className={cn(
          'pointer-events-none absolute left-1/2 top-0 max-w-32 -translate-x-1/2 -translate-y-full select-none truncate pb-1 text-[11px] font-medium text-foreground',
          data.dimmed && 'opacity-35'
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
}: EdgeProps<LessonFlowEdge>) {
  const [edgePath] = getStraightPath({ sourceX, sourceY, targetX, targetY });
  return (
    <BaseEdge
      id={id}
      data-testid="lesson-graph-edge"
      data-label={data?.label}
      path={edgePath}
      style={style}
    />
  );
}

const NODE_TYPES = { lessonConcept: ConceptNode };
const EDGE_TYPES = { lessonRelationship: RelationshipEdge };

function makeNode(
  entity: LessonGraphEntity,
  position: { x: number; y: number },
  selectedId: string | null
): LessonFlowNode {
  return {
    id: entity.id,
    type: 'lessonConcept',
    position,
    width: 40,
    height: 40,
    initialWidth: 40,
    initialHeight: 40,
    origin: [0.5, 0.5],
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    handles: [
      { id: null, type: 'target', position: Position.Left, x: 0, y: 20, width: 1, height: 1 },
      { id: null, type: 'source', position: Position.Right, x: 40, y: 20, width: 1, height: 1 },
    ],
    data: {
      entity,
      color: TYPE_COLORS[entity.type],
      dimmed: selectedId !== null && selectedId !== entity.id,
    },
    draggable: true,
    focusable: true,
    selectable: false,
  };
}

function relationKey(source: string, target: string, relationshipType: string): string {
  return `${source}--${target}--${relationshipType}`;
}

function isIncident(edge: LessonFlowEdge, nodeId: string): boolean {
  return edge.source === nodeId || edge.target === nodeId;
}

function relationshipLabel(relationshipType: string): string {
  return relationshipType.replace(/_/g, ' ');
}

interface LessonConceptGraphProps {
  context: LessonGraphContext | null | undefined;
  detail: LessonDetail;
}

export function LessonConceptGraph({ context, detail }: LessonConceptGraphProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [flowNodes, setFlowNodes] = useState<LessonFlowNode[]>([]);
  const entities = useMemo(() => context?.entities ?? [], [context?.entities]);
  const relationships = useMemo(() => context?.relationships ?? [], [context?.relationships]);
  const nodeNameById = useMemo(
    () => new Map(entities.map((entity) => [entity.id, entity.name])),
    [entities]
  );

  const flowEdges = useMemo(
    () =>
      relationships
        .filter(
          (relationship) =>
            nodeNameById.has(relationship.source) && nodeNameById.has(relationship.target)
        )
        .map((relationship) => {
          const dimmed =
            selectedId !== null &&
            selectedId !== relationship.source &&
            selectedId !== relationship.target;
          return {
            id: relationKey(
              relationship.source,
              relationship.target,
              relationship.relationship_type
            ),
            source: relationship.source,
            target: relationship.target,
            type: 'lessonRelationship',
            data: {
              label: relationship.label || relationshipLabel(relationship.relationship_type),
              confidence: relationship.confidence,
            },
            selectable: false,
            style: {
              stroke: 'color-mix(in oklch, var(--color-accent-foreground) 48%, transparent)',
              strokeWidth: 1 + Math.max(0, Math.min(relationship.confidence, 1)) * 3,
              opacity: dimmed ? 0.3 : 1,
            },
          } satisfies LessonFlowEdge;
        }),
    [nodeNameById, relationships, selectedId]
  );

  useEffect(() => {
    const positions = forceLayout(
      entities,
      relationships.map((relationship) => ({
        source: relationship.source,
        target: relationship.target,
        weight: Math.max(1, Math.round(relationship.confidence * 5)),
      })),
      CANVAS_W,
      CANVAS_H,
      MAX_RADIUS
    );
    setFlowNodes(
      entities.map((entity) =>
        makeNode(entity, positions.get(entity.id) ?? { x: CANVAS_W / 2, y: CANVAS_H / 2 }, null)
      )
    );
    setSelectedId(null);
  }, [entities, relationships]);

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

  const onNodesChange = useCallback<OnNodesChange<LessonFlowNode>>(
    (changes) => setFlowNodes((nodes) => applyNodeChanges(changes, nodes)),
    []
  );

  const selected = useMemo(
    () => entities.find((entity) => entity.id === selectedId) ?? null,
    [entities, selectedId]
  );

  const selectedRelationships = useMemo(() => {
    if (!selected) return [];
    return flowEdges.filter((edge) => isIncident(edge, selected.id));
  }, [flowEdges, selected]);

  const handleNodeClick = useCallback((_event: React.MouseEvent, node: LessonFlowNode) => {
    setSelectedId((current) => (current === node.id ? null : node.id));
  }, []);

  if (!context || !context.available) {
    return (
      <section className="space-y-2 rounded-lg border border-border bg-card/60 p-4">
        <h3 className="text-sm font-semibold text-foreground">Concept graph</h3>
        <p className="text-sm leading-6 text-muted-foreground">
          Graph extraction is not available for this lesson yet.
        </p>
      </section>
    );
  }

  if (entities.length === 0) {
    return (
      <section className="space-y-2 rounded-lg border border-border bg-card/60 p-4">
        <h3 className="text-sm font-semibold text-foreground">Concept graph</h3>
        <p className="text-sm leading-6 text-muted-foreground">
          No graph nodes were extracted from this lesson. The lesson text is still available below.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-foreground">Concept graph</h3>
          <p className="text-xs text-muted-foreground">
            {entities.length} node{entities.length !== 1 ? 's' : ''} · {relationships.length}{' '}
            relationship{relationships.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {Array.from(new Set(entities.map((entity) => entity.type))).map((type) => (
            <Badge key={type} variant="outline" className="gap-1">
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: TYPE_COLORS[type] }}
              />
              {type}
            </Badge>
          ))}
        </div>
      </div>

      <div className="relative h-[22rem] w-full overflow-hidden rounded-lg border border-border bg-surface-2 sm:h-[28rem]">
        <ReactFlow<LessonFlowNode, LessonFlowEdge>
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

      {selected ? (
        <div className="rounded-lg border border-border bg-background p-3">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold text-foreground">{selected.name}</h4>
            <Badge variant="secondary">{selected.type}</Badge>
          </div>
          {selectedRelationships.length > 0 ? (
            <ul className="mt-2 grid gap-1.5">
              {selectedRelationships.map((edge) => {
                const otherId = edge.source === selected.id ? edge.target : edge.source;
                const otherName = nodeNameById.get(otherId) ?? otherId;
                return (
                  <li key={edge.id} className="text-xs leading-5 text-muted-foreground">
                    <span className="font-medium text-foreground">{edge.data.label}</span>{' '}
                    {otherName}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">
              This node has no extracted relationships in the lesson graph.
            </p>
          )}
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2 rounded-lg border border-border bg-background p-3">
          <h4 className="text-xs font-semibold uppercase text-muted-foreground">Source claims</h4>
          <ul className="space-y-1.5">
            {detail.key_claims.slice(0, 4).map((claim) => (
              <li key={claim} className="text-xs leading-5 text-foreground">
                {claim}
              </li>
            ))}
          </ul>
        </div>
        <div className="space-y-2 rounded-lg border border-border bg-background p-3">
          <h4 className="text-xs font-semibold uppercase text-muted-foreground">Related items</h4>
          {context.related_article_ids.length === 0 && context.related_briefing_ids.length === 0 ? (
            <p className="text-xs leading-5 text-muted-foreground">
              No related articles or briefings were linked for this lesson.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {context.related_article_ids.map((id) => (
                <Link
                  key={`article-${id}`}
                  to={`/a/${id}`}
                  className="text-xs text-primary hover:underline"
                >
                  Article #{id}
                </Link>
              ))}
              {context.related_briefing_ids.map((id) => (
                <Link
                  key={`brief-${id}`}
                  to={`/briefs/${id}`}
                  className="text-xs text-primary hover:underline"
                >
                  Briefing #{id}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
