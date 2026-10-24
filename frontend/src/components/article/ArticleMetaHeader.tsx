import { Clock, ExternalLink } from 'lucide-react';
import { formatDate, readingTime, signalLabel } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { WorkflowArticle } from '@/lib/workflowTypes';
import { ArticleTags } from '@/components/article/ArticleTags';

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English',
  ja: 'Japanese',
  zh: 'Chinese',
  ru: 'Russian',
  fr: 'French',
  de: 'German',
  es: 'Spanish',
  ko: 'Korean',
  it: 'Italian',
  pt: 'Portuguese',
  vi: 'Vietnamese',
  ar: 'Arabic',
  tr: 'Turkish',
};

export function ArticleMetaHeader({
  article,
  isShared,
  showOriginal,
  setShowOriginal,
}: {
  article: WorkflowArticle;
  isShared: boolean;
  showOriginal: boolean;
  setShowOriginal: (v: boolean) => void;
}) {
  const signalColor =
    article.signal === 'high'
      ? 'text-signal-high'
      : article.signal === 'mid'
        ? 'text-signal-mid'
        : 'text-signal-low';

  const signalPill =
    article.signal === 'high'
      ? 'border-signal-high/30 bg-signal-high/10'
      : article.signal === 'mid'
        ? 'border-signal-mid/30 bg-signal-mid/10'
        : 'border-border bg-surface';
  const translatedFrom = article.detectedLang
    ? LANGUAGE_NAMES[article.detectedLang] || article.detectedLang.toUpperCase()
    : '';

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-meta text-subtle">
        <span className="font-semibold text-foreground">{article.sourceName}</span>
        <span aria-hidden="true">·</span>
        <span>{article.category}</span>
        <span aria-hidden="true">·</span>
        <span>{formatDate(article.publishedAt)}</span>
      </div>

      <h1 className="mt-2 text-balance text-[26px] font-semibold leading-tight tracking-tight md:text-[32px]">
        {showOriginal && article.originalTitle ? article.originalTitle : article.title}
      </h1>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-meta text-muted-foreground">
        <span
          className={cn(
            'inline-flex items-center rounded-full border px-2.5 py-0.5 font-medium',
            signalPill,
            signalColor
          )}
        >
          {signalLabel(article.signal)}
        </span>
        {article.bodyStatus === 'ok' && article.body && (
          <span className="inline-flex items-center gap-1">
            <Clock className="size-4" strokeWidth={1.75} />
            <span>{readingTime(article.body)} min read</span>
          </span>
        )}
        <a
          href={article.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-touch items-center gap-1 hover:text-foreground md:min-h-0"
          aria-label="Open original article"
        >
          <ExternalLink className="size-4" strokeWidth={1.75} />
          Open original
        </a>
        {article.detectedLang && article.detectedLang !== 'en' && article.originalTitle && (
          <button
            onClick={() => setShowOriginal(!showOriginal)}
            className="inline-flex min-h-touch items-center gap-1 rounded-md border border-border bg-surface px-2 text-xs font-medium text-accent transition-colors hover:bg-surface-hover hover:text-foreground md:min-h-7"
          >
            {showOriginal
              ? `Show English (Translated from ${translatedFrom})`
              : `Show Original (${article.detectedLang.toUpperCase()} → EN)`}
          </button>
        )}
      </div>

      {!isShared && <ArticleTags articleId={article.id} />}
    </>
  );
}
