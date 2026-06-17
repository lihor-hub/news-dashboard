import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDate, formatWindow } from '@/lib/briefingUtils';
import type { Briefing, BriefingArticle, BriefingSection } from '@/types';

// ── Sub-components ────────────────────────────────────────────────────────────

export function CitationChip({ article }: { article: BriefingArticle }) {
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

export function BriefSection({
  section,
  articleMap,
  index,
}: {
  section: BriefingSection;
  articleMap: Map<number, BriefingArticle>;
  index: number;
}) {
  return (
    <section
      aria-label={`Briefing section ${index + 1}: ${section.title}`}
      className={index > 0 ? 'mt-5 pt-5 border-t border-border' : ''}
    >
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
    </section>
  );
}

export function WorthOpening({ articles }: { articles: BriefingArticle[] }) {
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

export function BriefSkeleton() {
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

// ── Main view ─────────────────────────────────────────────────────────────────

export function BriefingView({
  briefing,
  onGenerate,
  isGenerating,
  afterMeta,
}: {
  briefing: Briefing;
  onGenerate?: () => void;
  isGenerating?: boolean;
  afterMeta?: React.ReactNode;
}) {
  const articleMap = new Map(briefing.articles.map((a) => [a.id, a]));
  const sections = briefing.content?.sections ?? [];
  const worthOpening = briefing.content?.worth_opening?.length
    ? briefing.content.worth_opening
        .map((articleId) => articleMap.get(articleId))
        .filter((article): article is BriefingArticle => Boolean(article))
    : briefing.articles.filter((a) => a.section_index === null);
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
          {afterMeta}
        </div>
        {onGenerate && (
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
        )}
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
