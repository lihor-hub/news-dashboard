import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Loader2, ScatterChart, Type } from 'lucide-react';
import { fetchAiEmbeddingMap, fetchAiWordCloud } from '@/api';
import { WordCloudChart } from '@/components/aiStats/WordCloudChart';
import { EmbeddingMapChart } from '@/components/aiStats/EmbeddingMapChart';
import { cn } from '@/lib/utils';

const RANGES = [7, 14, 30] as const;
const STALE_TIME = 5 * 60 * 1000;

interface SectionErrorProps {
  message: string;
  onRetry: () => void;
}

function SectionError({ message, onRetry }: SectionErrorProps) {
  return (
    <div className="flex min-h-[200px] flex-col items-center justify-center gap-3 text-muted-foreground">
      <AlertCircle className="size-6" />
      <p className="text-sm">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-md bg-surface-2 px-3 py-1.5 text-sm hover:bg-surface-3"
      >
        Retry
      </button>
    </div>
  );
}

function SectionLoading() {
  return (
    <div className="flex min-h-[200px] items-center justify-center">
      <Loader2 className="size-6 animate-spin text-muted-foreground" />
    </div>
  );
}

export function AiStatsPage() {
  const [days, setDays] = useState<number>(7);

  const wordCloud = useQuery({
    queryKey: ['ai-word-cloud', days],
    queryFn: () => fetchAiWordCloud(days),
    staleTime: STALE_TIME,
  });

  const embeddingMap = useQuery({
    queryKey: ['ai-embedding-map', days],
    queryFn: () => fetchAiEmbeddingMap(days),
    staleTime: STALE_TIME,
  });

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">AI Stats</h1>
          <p className="text-xs text-muted-foreground">
            AI-derived statistics about your news corpus
          </p>
        </div>
        <div className="flex gap-1 rounded-md bg-surface-2 p-1">
          {RANGES.map((range) => (
            <button
              key={range}
              type="button"
              onClick={() => setDays(range)}
              className={cn(
                'rounded px-2.5 py-1 text-xs transition-colors',
                days === range
                  ? 'bg-background font-medium shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {range}d
            </button>
          ))}
        </div>
      </div>

      <section className="rounded-xl border border-border bg-surface p-4">
        <div className="mb-3 flex items-center gap-2">
          <Type className="size-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Word Cloud</h2>
          {wordCloud.data && (
            <span className="text-[11px] text-muted-foreground">
              {wordCloud.data.article_count} articles, last {wordCloud.data.days} days
            </span>
          )}
        </div>
        {wordCloud.isLoading && <SectionLoading />}
        {wordCloud.isError && (
          <SectionError
            message="Failed to load word cloud."
            onRetry={() => void wordCloud.refetch()}
          />
        )}
        {wordCloud.data &&
          (wordCloud.data.terms.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              No terms yet — the cloud fills in as articles are ingested.
            </p>
          ) : (
            <WordCloudChart terms={wordCloud.data.terms} />
          ))}
      </section>

      <section className="rounded-xl border border-border bg-surface p-4">
        <div className="mb-3 flex items-center gap-2">
          <ScatterChart className="size-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Embedding Space</h2>
          {embeddingMap.data && (
            <span className="text-[11px] text-muted-foreground">
              {embeddingMap.data.embedded_count} of {embeddingMap.data.total_count} articles
              embedded
            </span>
          )}
        </div>
        {embeddingMap.isLoading && <SectionLoading />}
        {embeddingMap.isError && (
          <SectionError
            message="Failed to load embedding map."
            onRetry={() => void embeddingMap.refetch()}
          />
        )}
        {embeddingMap.data &&
          (embeddingMap.data.points.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              No embedded articles yet — embeddings are generated as you triage articles.
            </p>
          ) : (
            <EmbeddingMapChart
              points={embeddingMap.data.points}
              clusters={embeddingMap.data.clusters}
            />
          ))}
      </section>
    </div>
  );
}
