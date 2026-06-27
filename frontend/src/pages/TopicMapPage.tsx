import { useState, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Loader2, AlertCircle, Network, RefreshCw } from 'lucide-react';
import { fetchTopicMap } from '@/api';
import type { TopicCluster, TopicMapArticle } from '@/types';
import { cn } from '@/lib/utils';

const CANVAS_W = 800;
const CANVAS_H = 560;
const CLUSTER_R = 32;
const ARTICLE_R = 10;
const ORBIT_R = 90;

function toCanvas(normalized: number, size: number): number {
  const padding = 120;
  return padding + ((normalized + 1) / 2) * (size - padding * 2);
}

interface ArticleNodeProps {
  article: TopicMapArticle;
  cx: number;
  cy: number;
  onHover: (a: TopicMapArticle | null, x: number, y: number) => void;
  onClick: (id: number) => void;
}

function ArticleNode({ article, cx, cy, onHover, onClick }: ArticleNodeProps) {
  return (
    <circle
      cx={cx}
      cy={cy}
      r={ARTICLE_R}
      className="cursor-pointer fill-primary/30 stroke-primary stroke-[1.5] transition-all hover:fill-primary/70"
      onMouseEnter={(e) => onHover(article, e.clientX, e.clientY)}
      onMouseLeave={() => onHover(null, 0, 0)}
      onClick={() => onClick(article.id)}
    />
  );
}

interface ClusterNodeProps {
  cluster: TopicCluster;
  cx: number;
  cy: number;
  isSelected: boolean;
  onHover: (c: TopicCluster | null, x: number, y: number) => void;
  onClick: (id: number) => void;
}

function ClusterNode({ cluster, cx, cy, isSelected, onHover, onClick }: ClusterNodeProps) {
  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={CLUSTER_R + 8}
        className={cn(
          'transition-all',
          isSelected
            ? 'fill-primary/20 stroke-primary/60 stroke-[2]'
            : 'fill-primary/5 stroke-primary/20 stroke-[1]'
        )}
      />
      <circle
        cx={cx}
        cy={cy}
        r={CLUSTER_R}
        className={cn(
          'cursor-pointer transition-all',
          isSelected
            ? 'fill-primary/40 stroke-primary stroke-[2.5]'
            : 'fill-surface-2 stroke-primary/50 stroke-[1.5] hover:fill-primary/20 hover:stroke-primary'
        )}
        onMouseEnter={(e) => onHover(cluster, e.clientX, e.clientY)}
        onMouseLeave={() => onHover(null, 0, 0)}
        onClick={() => onClick(cluster.id)}
      />
      <text
        x={cx}
        y={cy + 4}
        textAnchor="middle"
        className="pointer-events-none select-none fill-foreground text-[11px] font-semibold"
      >
        {cluster.articles.length}
      </text>
    </g>
  );
}

interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
  content: { title: string; subtitle?: string };
}

export function TopicMapPage() {
  const navigate = useNavigate();
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false,
    x: 0,
    y: 0,
    content: { title: '' },
  });

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['topic-map'],
    queryFn: fetchTopicMap,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const showTooltip = useCallback(
    (title: string, subtitle: string | undefined, x: number, y: number) => {
      setTooltip({ visible: true, x, y, content: { title, subtitle } });
    },
    []
  );

  const hideTooltip = useCallback(() => {
    setTooltip((t) => ({ ...t, visible: false }));
  }, []);

  const handleClusterHover = useCallback(
    (cluster: TopicCluster | null, x: number, y: number) => {
      if (cluster) showTooltip(cluster.headline, cluster.trend_summary, x, y);
      else hideTooltip();
    },
    [showTooltip, hideTooltip]
  );

  const handleArticleHover = useCallback(
    (article: TopicMapArticle | null, x: number, y: number) => {
      if (article) showTooltip(article.title, undefined, x, y);
      else hideTooltip();
    },
    [showTooltip, hideTooltip]
  );

  const handleClusterClick = useCallback((clusterId: number) => {
    setSelectedClusterId((prev) => (prev === clusterId ? null : clusterId));
  }, []);

  const handleArticleClick = useCallback(
    (articleId: number) => navigate(`/a/${articleId}`),
    [navigate]
  );

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] flex-1 items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex min-h-[50vh] flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
        <AlertCircle className="size-6" />
        <p className="text-sm">Failed to load topic map.</p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="rounded-md bg-surface-2 px-3 py-1.5 text-sm hover:bg-surface-3"
        >
          Retry
        </button>
      </div>
    );
  }

  const clusters = data?.clusters ?? [];

  if (clusters.length === 0) {
    return (
      <div className="flex min-h-[50vh] flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
        <Network className="size-8 opacity-40" />
        <p className="text-sm font-medium">No story clusters yet</p>
        <p className="max-w-xs text-center text-xs">
          Topic clusters appear once enough articles with similar themes have been ingested in the
          last 7 days.
        </p>
      </div>
    );
  }

  const clusterPositions = clusters.map((c) => ({
    cx: toCanvas(c.x, CANVAS_W),
    cy: toCanvas(c.y, CANVAS_H),
  }));

  const articleNodes: { article: TopicMapArticle; cx: number; cy: number; clusterId: number }[] =
    [];
  for (let ci = 0; ci < clusters.length; ci++) {
    const cluster = clusters[ci];
    if (selectedClusterId !== null && selectedClusterId !== cluster.id) continue;
    const { cx, cy } = clusterPositions[ci];
    cluster.articles.forEach((article, ai) => {
      const angle = (2 * Math.PI * ai) / cluster.articles.length - Math.PI / 2;
      articleNodes.push({
        article,
        cx: cx + ORBIT_R * Math.cos(angle),
        cy: cy + ORBIT_R * Math.sin(angle),
        clusterId: cluster.id,
      });
    });
  }

  const selectedCluster =
    selectedClusterId !== null ? clusters.find((c) => c.id === selectedClusterId) : null;

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Topic Map</h1>
          <p className="text-xs text-muted-foreground">
            {clusters.length} story cluster{clusters.length !== 1 ? 's' : ''} from the last 7 days
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 rounded-md bg-surface-2 px-3 py-1.5 text-xs hover:bg-surface-3 disabled:opacity-50"
        >
          <RefreshCw className={cn('size-3', isFetching && 'animate-spin')} />
          Refresh
        </button>
      </div>

      <div className="relative overflow-hidden rounded-xl border border-border bg-surface">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
          className="h-auto w-full"
          style={{ maxHeight: '560px' }}
        >
          {articleNodes.map(({ article, cx, cy, clusterId }) => {
            const ci = clusters.findIndex((c) => c.id === clusterId);
            const { cx: pcx, cy: pcy } = clusterPositions[ci];
            return (
              <line
                key={`edge-${article.id}`}
                x1={pcx}
                y1={pcy}
                x2={cx}
                y2={cy}
                className="stroke-primary/20 stroke-[1]"
              />
            );
          })}

          {clusters.map((cluster, ci) => (
            <ClusterNode
              key={cluster.id}
              cluster={cluster}
              cx={clusterPositions[ci].cx}
              cy={clusterPositions[ci].cy}
              isSelected={selectedClusterId === cluster.id}
              onHover={handleClusterHover}
              onClick={handleClusterClick}
            />
          ))}

          {articleNodes.map(({ article, cx, cy }) => (
            <ArticleNode
              key={article.id}
              article={article}
              cx={cx}
              cy={cy}
              onHover={handleArticleHover}
              onClick={handleArticleClick}
            />
          ))}

          {clusters.map((cluster, ci) => {
            const { cx, cy } = clusterPositions[ci];
            const words = cluster.headline.split(' ');
            const mid = Math.ceil(words.length / 2);
            const line1 = words.slice(0, mid).join(' ');
            const line2 = words.slice(mid).join(' ');
            return (
              <g key={`label-${cluster.id}`} className="pointer-events-none">
                <text
                  x={cx}
                  y={cy + CLUSTER_R + 16}
                  textAnchor="middle"
                  className="select-none fill-foreground text-[10px] font-medium"
                >
                  {line1}
                </text>
                {line2 && (
                  <text
                    x={cx}
                    y={cy + CLUSTER_R + 28}
                    textAnchor="middle"
                    className="select-none fill-foreground text-[10px] font-medium"
                  >
                    {line2}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {tooltip.visible && (
          <div
            className="pointer-events-none fixed z-50 max-w-xs rounded-lg border border-border bg-background/95 px-3 py-2 shadow-lg backdrop-blur-sm"
            style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
          >
            <p className="text-xs font-semibold leading-snug">{tooltip.content.title}</p>
            {tooltip.content.subtitle && (
              <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                {tooltip.content.subtitle}
              </p>
            )}
          </div>
        )}
      </div>

      {selectedCluster && (
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="mb-3">
            <h2 className="text-sm font-semibold">{selectedCluster.headline}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">{selectedCluster.trend_summary}</p>
          </div>
          <div className="grid gap-2">
            {selectedCluster.articles.map((article) => (
              <button
                key={article.id}
                type="button"
                onClick={() => handleArticleClick(article.id)}
                className="group flex flex-col items-start gap-0.5 rounded-lg bg-surface-2 px-3 py-2.5 text-left transition-colors hover:bg-surface-3"
              >
                <span className="text-xs font-medium group-hover:text-primary">
                  {article.title}
                </span>
                {article.summary && (
                  <span className="line-clamp-2 text-[11px] text-muted-foreground">
                    {article.summary}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      <p className="text-center text-[11px] text-muted-foreground">
        Click a cluster node to expand its articles · Click an article node to open it
      </p>
    </div>
  );
}
