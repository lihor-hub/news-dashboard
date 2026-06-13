import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Newspaper, RefreshCw, AlertCircle, Inbox } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { fetchLatestBriefing, createBriefing } from '@/api';
import type { Briefing, BriefingArticle, BriefingSection } from '@/types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function formatWindow(sinceAt: string, untilAt: string): string {
  const since = new Date(sinceAt);
  const until = new Date(untilAt);
  const sameDay = since.toDateString() === until.toDateString();
  if (sameDay) {
    return since.toLocaleDateString(undefined, { dateStyle: 'medium' });
  }
  return `${since.toLocaleDateString(undefined, { dateStyle: 'medium' })} – ${until.toLocaleDateString(undefined, { dateStyle: 'medium' })}`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function CitationChip({ article }: { article: BriefingArticle }) {
  return (
    <Link
      to={`/a/${article.id}`}
      className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/50 px-2.5 py-0.5 text-xs font-medium text-foreground hover:bg-accent hover:text-accent-foreground transition-colors max-w-[200px] shrink-0"
    >
      <span className="truncate">{article.title}</span>
      <span className="text-muted-foreground shrink-0">·</span>
      <span className="text-muted-foreground shrink-0 truncate max-w-[60px]">
        {article.source_name}
      </span>
    </Link>
  );
}

function BriefSection({
  section,
  articleMap,
  index,
}: {
  section: BriefingSection;
  articleMap: Map<number, BriefingArticle>;
  index: number;
}) {
  return (
    <div className={index > 0 ? 'mt-5 pt-5 border-t border-border' : ''}>
      <h3 className="text-sm font-semibold text-foreground mb-1.5">{section.title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed">{section.body}</p>
      {section.citations.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {section.citations.map((id) => {
            const article = articleMap.get(id);
            if (!article) return null;
            return <CitationChip key={id} article={article} />;
          })}
        </div>
      )}
    </div>
  );
}

function WorthOpening({ articles }: { articles: BriefingArticle[] }) {
  if (articles.length === 0) return null;
  return (
    <div className="mt-6 pt-5 border-t border-border">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
        Also worth a look
      </h3>
      <div className="flex flex-col gap-2">
        {articles.map((article) => (
          <Link
            key={article.id}
            to={`/a/${article.id}`}
            className="flex items-start gap-3 rounded-md p-2 hover:bg-accent transition-colors group"
          >
            <div className="min-w-0">
              <div className="text-sm font-medium text-foreground group-hover:text-accent-foreground leading-snug">
                {article.title}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">{article.source_name}</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function BriefingView({
  briefing,
  onGenerate,
  isGenerating,
}: {
  briefing: Briefing;
  onGenerate: () => void;
  isGenerating: boolean;
}) {
  const articleMap = new Map(briefing.articles.map((a) => [a.id, a]));
  const worthOpening = briefing.articles.filter((a) => a.section_index === null);
  const sections = briefing.content?.sections ?? [];
  const articleCount = briefing.articles.length;

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[22px] font-semibold tracking-tight leading-tight">
            {briefing.title}
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            {formatDate(briefing.created_at)} · {formatWindow(briefing.since_at, briefing.until_at)}{' '}
            · {articleCount} {articleCount === 1 ? 'article' : 'articles'}
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={onGenerate}
          disabled={isGenerating}
          className="shrink-0 mt-1"
          aria-label="Generate new briefing"
        >
          <RefreshCw className={isGenerating ? 'animate-spin' : ''} />
          {isGenerating ? 'Generating…' : 'Refresh'}
        </Button>
      </div>

      <div className="px-4 md:px-5 pb-6">
        {briefing.summary && (
          <p className="text-sm text-muted-foreground leading-relaxed mb-5 pb-5 border-b border-border">
            {briefing.summary}
          </p>
        )}
        <div>
          {sections.map((section, i) => (
            <BriefSection key={i} section={section} articleMap={articleMap} index={i} />
          ))}
        </div>
        <WorthOpening articles={worthOpening} />
      </div>
    </div>
  );
}

function BriefSkeleton() {
  return (
    <div className="px-4 md:px-5 pt-4">
      <Skeleton className="h-6 w-3/4 mb-2" />
      <Skeleton className="h-3 w-1/2 mb-6" />
      <Skeleton className="h-4 w-full mb-2" />
      <Skeleton className="h-4 w-5/6 mb-2" />
      <Skeleton className="h-4 w-4/6 mb-6" />
      <Skeleton className="h-4 w-3/4 mb-2" />
      <Skeleton className="h-4 w-full mb-2" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

interface GenerateError {
  kind: 'no_ai' | 'failed';
  message: string;
}
interface NoCandidates {
  shown: boolean;
}

export function BriefPage() {
  const navigate = useNavigate();
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<GenerateError | null>(null);
  const [noCandidates, setNoCandidates] = useState<NoCandidates>({ shown: false });

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['briefings', 'latest'],
    queryFn: fetchLatestBriefing,
  });

  function generate() {
    void handleGenerate();
  }

  async function handleGenerate() {
    setIsGenerating(true);
    setGenerateError(null);
    setNoCandidates({ shown: false });
    try {
      const result = await createBriefing();
      if ('status' in result && result.status === 'no_candidates') {
        setNoCandidates({ shown: true });
      } else {
        await refetch();
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        if (err.message.startsWith('503')) {
          setGenerateError({ kind: 'no_ai', message: err.message });
        } else {
          setGenerateError({ kind: 'failed', message: err.message });
        }
      } else {
        setGenerateError({ kind: 'failed', message: 'Unexpected error' });
      }
    } finally {
      setIsGenerating(false);
    }
  }

  if (isLoading) {
    return <BriefSkeleton />;
  }

  // Error states (after attempted generation)
  if (generateError) {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <div className="flex items-start gap-3 p-4 rounded-lg border border-destructive/30 bg-destructive/5 mb-4">
          <AlertCircle className="size-4 text-destructive mt-0.5 shrink-0" />
          <div>
            <div className="text-sm font-medium text-foreground">
              {generateError.kind === 'no_ai' ? 'AI not configured' : 'Generation failed'}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              {generateError.kind === 'no_ai'
                ? 'OPENAI_API_KEY is not set. Configure it in the app environment to enable briefings.'
                : 'The AI returned an unexpected response. Try again or review the raw feed.'}
            </div>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {generateError.kind === 'failed' && (
            <Button size="sm" onClick={generate} disabled={isGenerating}>
              <RefreshCw className={isGenerating ? 'animate-spin' : ''} />
              {isGenerating ? 'Retrying…' : 'Retry'}
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => navigate('/')}>
            <Inbox />
            Review Today feed
          </Button>
        </div>
      </div>
    );
  }

  // No candidates after generation attempt
  if (noCandidates.shown) {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <div className="flex flex-col items-center justify-center text-center py-16 text-muted-foreground">
          <Newspaper className="size-10 text-subtle mb-3" strokeWidth={1.25} />
          <div className="text-sm font-medium text-foreground">No articles to brief</div>
          <div className="text-xs mt-1 max-w-xs">
            No new articles in the Today feed. Check back after your next ingest.
          </div>
        </div>
        <div className="flex justify-center">
          <Button size="sm" variant="outline" onClick={() => navigate('/')}>
            <Inbox />
            Review Today feed
          </Button>
        </div>
      </div>
    );
  }

  // Empty state — no briefings yet
  if (!data || ('status' in data && data.status === 'empty')) {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <div className="flex flex-col items-center justify-center text-center py-16 text-muted-foreground">
          <Newspaper className="size-10 text-subtle mb-3" strokeWidth={1.25} />
          <div className="text-sm font-medium text-foreground">No briefing yet</div>
          <div className="text-xs mt-1 max-w-xs">
            Generate your first briefing to see a summary of today's news.
          </div>
        </div>
        <div className="flex gap-2 justify-center flex-wrap">
          <Button size="sm" onClick={generate} disabled={isGenerating}>
            <RefreshCw className={isGenerating ? 'animate-spin' : ''} />
            {isGenerating ? 'Generating…' : 'Generate briefing'}
          </Button>
          <Button size="sm" variant="outline" onClick={() => navigate('/')}>
            <Inbox />
            Review Today feed
          </Button>
        </div>
      </div>
    );
  }

  // Failed briefing state (last briefing itself failed)
  if (data.status === 'failed') {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <div className="flex items-start gap-3 p-4 rounded-lg border border-destructive/30 bg-destructive/5 mb-4">
          <AlertCircle className="size-4 text-destructive mt-0.5 shrink-0" />
          <div>
            <div className="text-sm font-medium text-foreground">Last briefing failed</div>
            {data.error && (
              <div className="text-xs text-muted-foreground mt-1 font-mono">{data.error}</div>
            )}
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" onClick={generate} disabled={isGenerating}>
            <RefreshCw className={isGenerating ? 'animate-spin' : ''} />
            {isGenerating ? 'Retrying…' : 'Retry'}
          </Button>
          <Button size="sm" variant="outline" onClick={() => navigate('/')}>
            <Inbox />
            Review Today feed
          </Button>
        </div>
      </div>
    );
  }

  return <BriefingView briefing={data} onGenerate={generate} isGenerating={isGenerating} />;
}
