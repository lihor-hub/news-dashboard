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

  return (
    <>
      <div className="text-[11px] text-subtle flex items-center gap-1.5 flex-wrap">
        <span className="font-medium text-muted-foreground">{article.sourceName}</span>
        <span>·</span>
        <span>{article.category}</span>
        <span>·</span>
        <span>{formatDate(article.publishedAt)}</span>
        <span>·</span>
        <span className={cn('font-medium', signalColor)}>{signalLabel(article.signal)}</span>
        <span>·</span>
        <a
          href={article.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-0.5 hover:text-foreground"
          aria-label="Open original article"
        >
          <ExternalLink className="size-3" />
          Open original
        </a>
        {article.detectedLang && article.detectedLang !== 'en' && article.originalTitle && (
          <>
            <span>·</span>
            <button
              onClick={() => setShowOriginal(!showOriginal)}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-surface border border-border text-[10px] font-medium text-accent hover:bg-surface-hover hover:text-foreground transition-colors"
            >
              {showOriginal
                ? `Show English (Translated from ${LANGUAGE_NAMES[article.detectedLang] || article.detectedLang.toUpperCase()})`
                : `Show Original (${article.detectedLang.toUpperCase()} → EN)`}
            </button>
          </>
        )}
      </div>

      <h1 className="mt-3 text-[26px] md:text-[30px] font-semibold tracking-tight leading-tight">
        {showOriginal && article.originalTitle ? article.originalTitle : article.title}
      </h1>

      {!isShared && <ArticleTags articleId={article.id} />}

      {article.bodyStatus === 'ok' && article.body && (
        <div className="mt-2 flex items-center gap-1 text-[12px] text-muted-foreground">
          <Clock className="size-3.5" strokeWidth={1.75} />
          <span>{readingTime(article.body)} min read</span>
        </div>
      )}
    </>
  );
}
