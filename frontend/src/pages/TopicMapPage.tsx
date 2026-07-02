import { useState, useRef, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Loader2, AlertCircle, Network, RefreshCw } from 'lucide-react';
import { fetchTopicMap } from '@/api';
import type { TopicMapArticle } from '@/types';
import { cn } from '@/lib/utils';
import { categoryColorMap, colorForCategory } from '@/lib/categoryColor';
import { convexHull, hullPath, padHull } from '@/lib/convexHull';

const CANVAS_W = 800;
const CANVAS_H = 560;
const ARTICLE_R = 7;
const HULL_PAD = 20;

function toCanvas(normalized: number, size: number): number {
  const padding = 60;
  return padding + ((normalized + 1) / 2) * (size - padding * 2);
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

  const clusters = useMemo(() => data?.clusters ?? [], [data]);

  const colors = useMemo(
    () => categoryColorMap(clusters.flatMap((c) => c.articles.map((a) => a.category))),
    [clusters]
  );

  const hulls = useMemo(
    () =>
      clusters
        .filter((c) => c.articles.length >= 3)
        .map((cluster) => {
          const canvasPoints = cluster.articles.map((a) => ({
            x: toCanvas(a.x, CANVAS_W),
            y: toCanvas(a.y, CANVAS_H),
          }));
          const hull = padHull(convexHull(canvasPoints), HULL_PAD);
          return { cluster, path: hullPath(hull), topY: Math.min(...hull.map((h) => h.y)) };
        }),
    [clusters]
  );

  const showTooltip = useCallback(
    (title: string, subtitle: string | undefined, x: number, y: number) => {
      setTooltip({ visible: true, x, y, content: { title, subtitle } });
    },
    []
  );

  const hideTooltip = useCallback(() => {
    setTooltip((t) => ({ ...t, visible: false }));
  }, []);

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
    (articleId: number) => void navigate(`/a/${articleId}`),
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

  const selectedCluster =
    selectedClusterId !== null ? clusters.find((c) => c.id === selectedClusterId) : null;

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Topic Map</h1>
          <p className="text-xs text-muted-foreground">
            {clusters.length} story cluster{clusters.length !== 1 ? 's' : ''} from the last 7 days —
            articles positioned by embedding similarity
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
          {hulls.map(({ cluster, path }) => (
            <path
              key={`hull-${cluster.id}`}
              data-testid="cluster-hull"
              d={path}
              className={cn(
                'cursor-pointer transition-all',
                selectedClusterId === cluster.id
                  ? 'fill-primary/15 stroke-primary/60 stroke-[2]'
                  : 'fill-primary/5 stroke-primary/20 stroke-[1] hover:fill-primary/10'
              )}
              onClick={() => handleClusterClick(cluster.id)}
            />
          ))}

          {clusters.map((cluster) =>
            cluster.articles.map((article) => (
              <circle
                key={article.id}
                data-testid="article-point"
                cx={toCanvas(article.x, CANVAS_W)}
                cy={toCanvas(article.y, CANVAS_H)}
                r={ARTICLE_R}
                fill={colorForCategory(colors, article.category)}
                fillOpacity={
                  selectedClusterId === null || selectedClusterId === cluster.id ? 0.8 : 0.25
                }
                className="cursor-pointer stroke-background stroke-[1.5] transition-all"
                onMouseEnter={(e) => handleArticleHover(article, e.clientX, e.clientY)}
                onMouseLeave={() => handleArticleHover(null, 0, 0)}
                onClick={() => handleArticleClick(article.id)}
              />
            ))
          )}

          {hulls.map(({ cluster, topY }) => {
            const cx =
              cluster.articles.reduce((sum, a) => sum + toCanvas(a.x, CANVAS_W), 0) /
              cluster.articles.length;
            return (
              <text
                key={`label-${cluster.id}`}
                x={cx}
                y={topY - 8}
                textAnchor="middle"
                className="pointer-events-none select-none fill-foreground text-[11px] font-semibold"
              >
                {cluster.headline}
              </text>
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

      <div className="flex flex-wrap gap-x-4 gap-y-1">
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
        Click a cluster outline to inspect its articles · Click a point to open the article
      </p>
    </div>
  );
}
