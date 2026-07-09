import { useEffect, useState } from 'react';
import { AlertCircle, ExternalLink, GraduationCap, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { LessonChat } from '@/components/LessonChat';
import {
  createLessonFromLink,
  fetchLesson,
  HttpError,
  type Lesson,
  type LessonDetail,
} from '@/api';

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

function verdictBadgeVariant(
  verdict: LessonDetail['read_worthiness']['verdict']
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (verdict === 'study') return 'default';
  if (verdict === 'read') return 'secondary';
  if (verdict === 'skim') return 'outline';
  return 'destructive';
}

function capitalizeLabel(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function renderBulletList(items: string[]) {
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-2 text-sm leading-6 text-foreground">
          <span className="mt-0.5 shrink-0 text-accent">-</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function LearnPage() {
  const { t } = useTranslation();
  const [url, setUrl] = useState('');
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (lesson?.generation_status !== 'pending') return;

    const lessonId = lesson.id;
    let isActive = true;
    let timeoutId: number | null = null;

    const schedulePoll = () => {
      timeoutId = window.setTimeout(() => {
        void (async () => {
          try {
            const nextLesson = await fetchLesson(lessonId);
            if (!isActive) return;
            setRequestError(null);
            setLesson(nextLesson);
            if (nextLesson.id === lessonId && nextLesson.generation_status === 'pending') {
              schedulePoll();
            }
          } catch (error) {
            if (!isActive) return;
            setRequestError(error instanceof Error ? error.message : t('learn.refresh_error'));
            schedulePoll();
          }
        })();
      }, 2000);
    };

    schedulePoll();

    return () => {
      isActive = false;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [lesson?.generation_status, lesson?.id, t]);

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
        setRequestError(error instanceof Error ? error.message : t('learn.request_error'));
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
  const lessonDetail = lesson?.lesson_detail ?? null;
  const hasLessonDetail = isCompleteLesson && lessonDetail !== null;

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="mt-0.5 rounded-md border border-border p-2 text-muted-foreground">
          <GraduationCap className="size-5" />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t('learn.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('learn.description')}</p>
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
            {t('learn.form.url_label')}
          </label>
          <Input
            id="learn-url"
            type="url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder={t('learn.form.url_placeholder')}
          />
        </div>
        <Button type="submit" disabled={isSubmitting || !url.trim()}>
          {isSubmitting ? <Loader2 className="animate-spin" /> : null}
          {isSubmitting ? t('learn.form.submitting') : t('learn.form.submit')}
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
          {t('learn.empty')}
        </div>
      ) : (
        <section className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={statusBadgeVariant(lesson.generation_status)}>
              {isCompleteLesson
                ? t('learn.status.complete')
                : isFailedLesson
                  ? t('learn.status.failed')
                  : t('learn.status.pending')}
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
                <p className="text-sm text-muted-foreground">{t('learn.status.pending')}</p>
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
              {t('learn.link.open_original')}
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

          {hasLessonDetail && lessonDetail ? (
            <div className="space-y-4 rounded-lg border border-border bg-background p-4">
              <div className="flex flex-wrap items-start gap-3">
                <Badge variant={verdictBadgeVariant(lessonDetail.read_worthiness.verdict)}>
                  {capitalizeLabel(lessonDetail.read_worthiness.verdict)}
                </Badge>
                <div className="min-w-0 text-sm text-muted-foreground">
                  {lessonDetail.read_worthiness.rationale}
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <section className="space-y-2">
                  <h3 className="text-sm font-semibold text-foreground">Gist</h3>
                  <p className="text-sm leading-6 text-foreground">{lessonDetail.gist}</p>
                </section>

                <section className="space-y-2">
                  <h3 className="text-sm font-semibold text-foreground">Why it matters</h3>
                  <p className="text-sm leading-6 text-foreground">{lessonDetail.why_it_matters}</p>
                </section>

                <section className="space-y-2 md:col-span-2">
                  <h3 className="text-sm font-semibold text-foreground">Explanation</h3>
                  <p className="text-sm leading-6 text-foreground">{lessonDetail.explanation}</p>
                </section>

                <section className="space-y-2">
                  <h3 className="text-sm font-semibold text-foreground">Key claims</h3>
                  {renderBulletList(lessonDetail.key_claims)}
                </section>

                <section className="space-y-2">
                  <h3 className="text-sm font-semibold text-foreground">Prerequisite concepts</h3>
                  {renderBulletList(lessonDetail.prerequisite_concepts)}
                </section>

                <section className="space-y-2">
                  <h3 className="text-sm font-semibold text-foreground">Who should read</h3>
                  {renderBulletList(lessonDetail.who_should_read)}
                </section>

                <section className="space-y-2">
                  <h3 className="text-sm font-semibold text-foreground">
                    Questions to keep in mind
                  </h3>
                  {renderBulletList(lessonDetail.questions_to_keep_in_mind)}
                </section>

                <section className="space-y-2 md:col-span-2">
                  <h3 className="text-sm font-semibold text-foreground">Citations</h3>
                  <ul className="space-y-3">
                    {lessonDetail.citations.map((citation) => (
                      <li
                        key={`${citation.label}-${citation.source}-${citation.snippet}`}
                        className="space-y-1"
                      >
                        <div className="text-sm font-medium text-foreground">{citation.label}</div>
                        <p className="text-sm leading-6 text-foreground">{citation.snippet}</p>
                        <div className="text-xs text-muted-foreground">{citation.source}</div>
                      </li>
                    ))}
                  </ul>
                </section>
              </div>
            </div>
          ) : null}

          {hasLessonDetail ? <LessonChat lessonId={lesson.id} /> : null}

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
