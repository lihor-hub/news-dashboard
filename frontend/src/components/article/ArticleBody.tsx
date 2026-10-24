import { AlertCircle, ExternalLink, Loader2 } from 'lucide-react';
import { renderMarkdown } from '@/lib/renderMarkdown';
import type { WorkflowArticle } from '@/lib/workflowTypes';

export function ArticleBody({
  article,
  bodyLoading,
  showOriginal,
  onSelectText,
}: {
  article: WorkflowArticle;
  bodyLoading: boolean;
  showOriginal: boolean;
  onSelectText: () => void;
}) {
  if (bodyLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground py-12">
        <Loader2 className="size-4 animate-spin motion-reduce:animate-none" /> Loading article…
      </div>
    );
  }

  if (article.bodyStatus === 'error' || !article.body) {
    return (
      <div className="rounded-xl border border-border bg-surface px-4 py-5">
        <div className="flex items-start gap-2 mb-2">
          <AlertCircle className="size-4 mt-0.5 text-destructive shrink-0" />
          <div className="text-sm font-medium text-foreground">Couldn't extract article text</div>
        </div>
        <p className="text-sm text-muted-foreground mb-4">{article.summary}</p>
        <a
          href={article.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-touch items-center gap-1.5 rounded-md bg-foreground px-4 text-sm font-medium text-background hover:opacity-90 md:min-h-9"
        >
          Open original <ExternalLink className="size-4" />
        </a>
      </div>
    );
  }

  return (
    <div
      className="reader-prose max-w-[70ch] text-reading md:text-[1.125rem]"
      onMouseUp={onSelectText}
      onKeyUp={onSelectText}
      dangerouslySetInnerHTML={{
        __html: renderMarkdown(
          showOriginal && article.originalBody ? article.originalBody : article.body
        ),
      }}
    />
  );
}
