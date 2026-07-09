import { useEffect, useState } from 'react';
import { AlertCircle, ExternalLink, GraduationCap, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { createLessonFromLink, fetchLesson, HttpError, type Lesson } from '@/api';

function formatPublishedDate(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function statusBadgeVariant(
  status: Lesson['generation_status']
): 'default' | 'secondary' | 'destructive' {
  if (status === 'complete') return 'default';
  if (status === 'failed') return 'destructive';
  return 'secondary';
}

export function LearnPage() {
  const [url, setUrl] = useState('');
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (lesson?.generation_status !== 'pending') return;
    const timeoutId = window.setTimeout(() => {
      void (async () => {
        try {
          setLesson(await fetchLesson(lesson.id));
        } catch (error) {
          setRequestError(error instanceof Error ? error.message : 'Failed to refresh lesson');
        }
      })();
    }, 2000);
    return () => window.clearTimeout(timeoutId);
  }, [lesson]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    setIsSubmitting(true);
    setRequestError(null);
    try {
      setLesson(await createLessonFromLink(trimmed));
    } catch (error) {
      setLesson(null);
      if (error instanceof HttpError) {
        setRequestError(error.message);
      } else {
        setRequestError(error instanceof Error ? error.message : 'Lesson generation failed');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  const publishedLabel = formatPublishedDate(lesson?.published_at ?? null);
  const hasLesson = lesson !== null;
  const isPendingLesson = lesson?.generation_status === 'pending';
  const isFailedLesson = lesson?.generation_status === 'failed';
  const isCompleteLesson = lesson?.generation_status === 'complete';

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="mt-0.5 rounded-md border border-border p-2 text-muted-foreground">
          <GraduationCap className="size-5" />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-foreground">Learn</h1>
          <p className="text-sm text-muted-foreground">
            Turn one article into a compact lesson you can review inside Radar.
          </p>
        </div>
      </div>

      <form
        noValidate
        className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end"
        onSubmit={(event) => {
          void handleSubmit(event);
        }}
      >
        <div className="flex-1">
          <label htmlFor="learn-url" className="mb-2 block text-sm font-medium text-foreground">
            Article URL
          </label>
          <Input
            id="learn-url"
            type="url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://example.com/article"
          />
        </div>
        <Button type="submit" disabled={isSubmitting || !url.trim()}>
          {isSubmitting ? <Loader2 className="animate-spin" /> : null}
          {isSubmitting ? 'Generating lesson...' : 'Generate lesson'}
        </Button>
      </form>

      {requestError ? (
        <div className="mb-6 flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div className="text-sm text-foreground">{requestError}</div>
        </div>
      ) : null}

      {!hasLesson ? (
        <div className="rounded-lg border border-dashed border-border px-4 py-10 text-sm text-muted-foreground">
          Paste a link to generate a lesson summary from a readable article.
        </div>
      ) : (
        <section className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={statusBadgeVariant(lesson.generation_status)}>
              {isCompleteLesson
                ? 'Lesson generated'
                : isFailedLesson
                  ? 'Lesson generation failed'
                  : 'Generating lesson...'}
            </Badge>
            {isPendingLesson ? (
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
            ) : null}
          </div>

          <div className="space-y-2">
            {lesson.title ? (
              <h2 className="text-xl font-semibold text-foreground">{lesson.title}</h2>
            ) : isPendingLesson ? (
              <div className="space-y-2">
                <Skeleton className="h-7 w-64" />
                <p className="text-sm text-muted-foreground">Generating lesson...</p>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
              {lesson.source_name ? <span>{lesson.source_name}</span> : null}
              {lesson.author ? <span>{lesson.author}</span> : null}
              {publishedLabel ? <span>{publishedLabel}</span> : null}
            </div>
          </div>

          <div className="text-sm">
            <a
              href={lesson.original_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-accent-foreground hover:underline"
            >
              Open original article
              <ExternalLink className="size-3.5" />
            </a>
          </div>

          {lesson.source_content ? (
            <div className="rounded-lg border border-border bg-muted/20 p-4 text-sm leading-6 text-foreground">
              {lesson.source_content}
            </div>
          ) : isPendingLesson ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-10/12" />
            </div>
          ) : null}

          {isFailedLesson && lesson.generation_error ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-foreground">
              {lesson.generation_error}
            </div>
          ) : null}
        </section>
      )}
    </div>
  );
}
