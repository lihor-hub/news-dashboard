import { useEffect, useState } from 'react';
import { AlertCircle, GraduationCap, Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { LessonDetailView } from '@/components/LessonDetailView';
import { LessonSuggestions } from '@/components/LessonSuggestions';
import { useLessonPolling } from '@/hooks/useLessonPolling';
import {
  createLessonFromLink,
  fetchLessonGenerations,
  regenerateLesson,
  HttpError,
  type Lesson,
  type LessonDepth,
  type LessonPersona,
} from '@/api';

const LESSON_DEPTHS: LessonDepth[] = ['tiny', 'normal', 'deep', 'expert'];
const LESSON_PERSONAS: LessonPersona[] = [
  'developer',
  'product_builder',
  'new_to_ai',
  'preparing_talk',
];

export function LearnPage() {
  const { t } = useTranslation();
  const [url, setUrl] = useState('');
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [depth, setDepth] = useState<LessonDepth>('normal');
  const [persona, setPersona] = useState<LessonPersona>('developer');
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [generationCount, setGenerationCount] = useState<number | null>(null);

  useEffect(() => {
    if (lesson?.generation_status !== 'complete') return;

    let isActive = true;
    void fetchLessonGenerations(lesson.id)
      .then((generations) => {
        if (isActive) setGenerationCount(generations.length);
      })
      .catch(() => {
        if (isActive) setGenerationCount(null);
      });

    return () => {
      isActive = false;
    };
  }, [lesson?.id, lesson?.generation_status]);

  useLessonPolling(lesson, setLesson, setRequestError, t('learn.refresh_error'));

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    setIsSubmitting(true);
    setRequestError(null);
    try {
      setLesson(await createLessonFromLink(trimmed, depth, persona));
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

  async function handleRegenerate() {
    if (!lesson) return;
    setIsRegenerating(true);
    setRequestError(null);
    try {
      setLesson(await regenerateLesson(lesson.id, depth, persona));
    } catch (error) {
      if (error instanceof HttpError) {
        setRequestError(error.message);
      } else {
        setRequestError(
          error instanceof Error ? error.message : t('learn.controls.regenerate_error')
        );
      }
    } finally {
      setIsRegenerating(false);
    }
  }

  const hasLesson = lesson !== null;
  const isPendingLesson = lesson?.generation_status === 'pending';

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

      <LessonSuggestions onGenerated={setLesson} />

      <form
        noValidate
        className="mb-6 flex flex-col gap-3"
        onSubmit={(event) => {
          void handleSubmit(event);
        }}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
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
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div>
            <label htmlFor="learn-depth" className="mb-2 block text-sm font-medium text-foreground">
              {t('learn.controls.depth_label')}
            </label>
            <select
              id="learn-depth"
              value={depth}
              onChange={(event) => setDepth(event.target.value as LessonDepth)}
              className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {LESSON_DEPTHS.map((value) => (
                <option key={value} value={value}>
                  {t(`learn.controls.depth.${value}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="learn-persona"
              className="mb-2 block text-sm font-medium text-foreground"
            >
              {t('learn.controls.persona_label')}
            </label>
            <select
              id="learn-persona"
              value={persona}
              onChange={(event) => setPersona(event.target.value as LessonPersona)}
              className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {LESSON_PERSONAS.map((value) => (
                <option key={value} value={value}>
                  {t(`learn.controls.persona.${value}`)}
                </option>
              ))}
            </select>
          </div>
        </div>
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
          {!isPendingLesson ? (
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">
                {t('learn.controls.active_summary', {
                  persona: t(`learn.controls.persona.${lesson.persona}`),
                  depth: t(`learn.controls.depth.${lesson.depth}`).toLowerCase(),
                })}
              </Badge>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={isRegenerating}
                onClick={() => {
                  void handleRegenerate();
                }}
              >
                {isRegenerating ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="size-3.5" />
                )}
                {isRegenerating ? t('learn.controls.regenerating') : t('learn.controls.regenerate')}
              </Button>
              {generationCount !== null && generationCount > 1 ? (
                <span className="text-xs text-muted-foreground">
                  {t('learn.controls.history_summary', { count: generationCount })}
                </span>
              ) : null}
            </div>
          ) : null}

          <LessonDetailView lesson={lesson} />
        </section>
      )}
    </div>
  );
}
