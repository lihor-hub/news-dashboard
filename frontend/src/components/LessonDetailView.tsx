import { useEffect, useState } from 'react';
import {
  AlertCircle,
  BookOpen,
  ExternalLink,
  Headphones,
  Image,
  Loader2,
  Network,
  Presentation,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { LessonChat } from '@/components/LessonChat';
import { LessonConceptGraph } from '@/components/LessonConceptGraph';
import { StudyArtifactsView } from '@/components/StudyArtifactsView';
import {
  generateLessonInfographic,
  generateLessonPodcast,
  generateLessonSlideDeck,
  fetchLessonTrails,
  type Lesson,
  type LessonDetail,
  type LessonTrailResponse,
} from '@/api';
import { classifyGenerationError, type FriendlyError } from '@/lib/errorPresentation';

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

export function LessonDetailView({
  lesson,
  onLessonUpdate,
}: {
  lesson: Lesson;
  onLessonUpdate?: (lesson: Lesson) => void;
}) {
  const { t } = useTranslation();
  const [isGeneratingPodcast, setIsGeneratingPodcast] = useState(false);
  const [podcastError, setPodcastError] = useState<FriendlyError | null>(null);
  const [isGeneratingSlideDeck, setIsGeneratingSlideDeck] = useState(false);
  const [slideDeckError, setSlideDeckError] = useState<FriendlyError | null>(null);
  const [isGeneratingInfographic, setIsGeneratingInfographic] = useState(false);
  const [infographicError, setInfographicError] = useState<FriendlyError | null>(null);
  const [trails, setTrails] = useState<LessonTrailResponse | null>(null);
  const [trailError, setTrailError] = useState<string | null>(null);
  const publishedLabel = formatPublishedDate(lesson.published_at);
  const isPendingLesson = lesson.generation_status === 'pending';
  const isFailedLesson = lesson.generation_status === 'failed';
  const isCompleteLesson = lesson.generation_status === 'complete';
  const lessonDetail = lesson.lesson_detail ?? null;
  const hasLessonDetail = isCompleteLesson && lessonDetail !== null;
  const graphContext = lessonDetail?.graph_context;

  useEffect(() => {
    let cancelled = false;
    setTrails(null);
    setTrailError(null);
    if (!hasLessonDetail) return;

    void fetchLessonTrails(lesson.id)
      .then((nextTrails) => {
        if (!cancelled) setTrails(nextTrails);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setTrailError(error instanceof Error ? error.message : 'Failed to load learning trails.');
        }
      });

    return () => {
      cancelled = true;
    };
  }, [hasLessonDetail, lesson.id]);

  async function handleGeneratePodcast(force: boolean) {
    setIsGeneratingPodcast(true);
    setPodcastError(null);
    try {
      const updated = await generateLessonPodcast(lesson.id, force);
      onLessonUpdate?.(updated);
    } catch (error: unknown) {
      setPodcastError(classifyGenerationError(error));
    } finally {
      setIsGeneratingPodcast(false);
    }
  }

  async function handleGenerateSlideDeck(force: boolean) {
    setIsGeneratingSlideDeck(true);
    setSlideDeckError(null);
    try {
      const updated = await generateLessonSlideDeck(lesson.id, force);
      onLessonUpdate?.(updated);
    } catch (error: unknown) {
      setSlideDeckError(classifyGenerationError(error));
    } finally {
      setIsGeneratingSlideDeck(false);
    }
  }

  async function handleGenerateInfographic(force: boolean) {
    setIsGeneratingInfographic(true);
    setInfographicError(null);
    try {
      const updated = await generateLessonInfographic(lesson.id, force);
      onLessonUpdate?.(updated);
    } catch (error: unknown) {
      setInfographicError(classifyGenerationError(error));
    } finally {
      setIsGeneratingInfographic(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={statusBadgeVariant(lesson.generation_status)}>
          {isCompleteLesson
            ? t('learn.status.complete')
            : isFailedLesson
              ? t('learn.status.failed')
              : t('learn.status.pending')}
        </Badge>
        {isPendingLesson ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}
        {lesson.graph_context_available ? (
          <Badge variant="outline" className="gap-1">
            <Network className="size-3.5" />
            {t('learn.graph_context_available', 'Graph context')}
          </Badge>
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
            {graphContext?.available ? (
              <Badge variant="outline" className="gap-1">
                <Network className="size-3" />
                {t('learn.detail.graph_context_available', 'Graph context available')}
              </Badge>
            ) : null}
            <div className="min-w-0 text-sm text-muted-foreground">
              {lessonDetail.read_worthiness.rationale}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <section className="space-y-2">
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.detail.gist', 'Gist')}
              </h3>
              <p className="text-sm leading-6 text-foreground">{lessonDetail.gist}</p>
            </section>

            <section className="space-y-2">
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.detail.why_it_matters', 'Why it matters')}
              </h3>
              <p className="text-sm leading-6 text-foreground">{lessonDetail.why_it_matters}</p>
            </section>

            <section className="space-y-2 md:col-span-2">
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.detail.explanation', 'Explanation')}
              </h3>
              <p className="text-sm leading-6 text-foreground">{lessonDetail.explanation}</p>
            </section>

            <section className="space-y-2">
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.detail.key_claims', 'Key claims')}
              </h3>
              {renderBulletList(lessonDetail.key_claims)}
            </section>

            <section className="space-y-2">
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.detail.prerequisite_concepts', 'Prerequisite concepts')}
              </h3>
              {renderBulletList(lessonDetail.prerequisite_concepts)}
            </section>

            <section className="space-y-2">
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.detail.who_should_read', 'Who should read')}
              </h3>
              {renderBulletList(lessonDetail.who_should_read)}
            </section>

            <section className="space-y-2">
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.detail.questions_to_keep_in_mind', 'Questions to keep in mind')}
              </h3>
              {renderBulletList(lessonDetail.questions_to_keep_in_mind)}
            </section>

            <section className="space-y-2 md:col-span-2">
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.detail.citations', 'Citations')}
              </h3>
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

      {hasLessonDetail && lessonDetail ? (
        <LessonConceptGraph context={lessonDetail.graph_context} detail={lessonDetail} />
      ) : null}

      {hasLessonDetail && lesson.study_artifacts ? (
        <StudyArtifactsView artifacts={lesson.study_artifacts} />
      ) : null}

      {hasLessonDetail ? (
        <div className="space-y-3 rounded-lg border border-border bg-card/60 p-4">
          <div className="flex items-center gap-2">
            <BookOpen className="size-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">
              {t('learn.trails.title', 'Learning trail')}
            </h3>
          </div>

          {trailError ? (
            <div className="text-sm text-muted-foreground">{trailError}</div>
          ) : trails === null ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-4 w-11/12" />
            </div>
          ) : trails.empty_message ? (
            <div className="text-sm leading-6 text-muted-foreground">{trails.empty_message}</div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {trails.groups
                .filter((group) => group.items.length > 0)
                .map((group) => (
                  <section key={group.path} className="space-y-2">
                    <h4 className="text-xs font-semibold uppercase text-muted-foreground">
                      {group.label}
                    </h4>
                    <ul className="space-y-2">
                      {group.items.map((item) => (
                        <li
                          key={`${item.item_type}-${item.id}`}
                          className="rounded-md border border-border bg-background p-3"
                        >
                          {item.url ? (
                            <a
                              href={item.url}
                              className="text-sm font-semibold text-foreground hover:underline"
                            >
                              {item.title}
                            </a>
                          ) : (
                            <div className="text-sm font-semibold text-foreground">
                              {item.title}
                            </div>
                          )}
                          <p className="mt-1 text-xs leading-5 text-muted-foreground">
                            {item.explanation}
                          </p>
                          {item.matched_signals.length > 0 ? (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {item.matched_signals.map((signal) => (
                                <Badge key={signal} variant="outline" className="text-[11px]">
                                  {signal}
                                </Badge>
                              ))}
                            </div>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
            </div>
          )}
        </div>
      ) : null}

      {hasLessonDetail ? (
        <div className="space-y-3 rounded-lg border border-border bg-card/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Image className="size-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.infographic.title', 'Infographic')}
              </h3>
            </div>
            <Button
              size="sm"
              variant={lesson.infographic_status ? 'outline' : 'default'}
              onClick={() => {
                void handleGenerateInfographic(lesson.infographic_status !== null);
              }}
              disabled={isGeneratingInfographic}
            >
              {isGeneratingInfographic
                ? t('learn.infographic.generating', 'Generating…')
                : lesson.infographic_status
                  ? t('learn.infographic.regenerate', 'Regenerate')
                  : t('learn.infographic.create', 'Create infographic')}
            </Button>
          </div>

          {lesson.infographic_status ? null : (
            <p className="text-xs leading-5 text-muted-foreground">
              {t(
                'learn.infographic.costNotice',
                'Uses one AI generation and usually returns in under a minute.'
              )}
            </p>
          )}

          {lesson.infographic_status === 'complete' && lesson.infographic ? (
            <div className="overflow-hidden rounded-lg border border-border bg-background">
              <div className="border-b border-border bg-muted/30 p-4">
                <div className="text-base font-semibold text-foreground">
                  {lesson.infographic.title}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  {lesson.infographic.subtitle}
                </div>
              </div>
              <div className="grid gap-px bg-border sm:grid-cols-2">
                {lesson.infographic.sections.map((section) => (
                  <section key={`${section.heading}-${section.body}`} className="bg-background p-4">
                    <h4 className="text-xs font-semibold uppercase text-muted-foreground">
                      {section.heading}
                    </h4>
                    <p className="mt-2 text-sm leading-6 text-foreground">{section.body}</p>
                  </section>
                ))}
              </div>
              <div className="border-t border-border p-3 text-xs text-muted-foreground">
                {lesson.infographic.footer}
              </div>
            </div>
          ) : null}

          {infographicError ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div>
                <div className="font-semibold">{infographicError.title}</div>
                <div className="mt-0.5">{infographicError.message}</div>
              </div>
            </div>
          ) : lesson.infographic_status === 'failed' && lesson.infographic_error ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div>{lesson.infographic_error}</div>
            </div>
          ) : null}
        </div>
      ) : null}

      {hasLessonDetail ? (
        <div className="space-y-3 rounded-lg border border-border bg-card/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Headphones className="size-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.podcast.title', 'Podcast audio')}
              </h3>
            </div>
            <Button
              size="sm"
              variant={lesson.podcast_status ? 'outline' : 'default'}
              onClick={() => {
                void handleGeneratePodcast(lesson.podcast_status !== null);
              }}
              disabled={isGeneratingPodcast}
            >
              {isGeneratingPodcast
                ? t('learn.podcast.generating', 'Generating…')
                : lesson.podcast_status
                  ? t('learn.podcast.regenerate', 'Regenerate')
                  : t('learn.podcast.create', 'Create podcast')}
            </Button>
          </div>

          {lesson.podcast_status === 'complete' ? (
            <audio
              src={`/api/learn/lessons/${lesson.id}/podcast`}
              controls
              className="h-9 w-full"
            />
          ) : null}

          {podcastError ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div>
                <div className="font-semibold">{podcastError.title}</div>
                <div className="mt-0.5">{podcastError.message}</div>
              </div>
            </div>
          ) : lesson.podcast_status === 'failed' && lesson.podcast_error ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div>{lesson.podcast_error}</div>
            </div>
          ) : null}
        </div>
      ) : null}

      {hasLessonDetail ? (
        <div className="space-y-3 rounded-lg border border-border bg-card/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Presentation className="size-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">
                {t('learn.slideDeck.title', 'Slide deck')}
              </h3>
            </div>
            <Button
              size="sm"
              variant={lesson.slide_deck_status ? 'outline' : 'default'}
              onClick={() => {
                void handleGenerateSlideDeck(lesson.slide_deck_status !== null);
              }}
              disabled={isGeneratingSlideDeck}
            >
              {isGeneratingSlideDeck
                ? t('learn.slideDeck.generating', 'Generating…')
                : lesson.slide_deck_status
                  ? t('learn.slideDeck.regenerate', 'Regenerate')
                  : t('learn.slideDeck.create', 'Create slide deck')}
            </Button>
          </div>

          {lesson.slide_deck_status === 'complete' && lesson.slide_deck ? (
            <ol className="space-y-3">
              {lesson.slide_deck.slides.map((slide, index) => (
                <li
                  key={`${index}-${slide.title}`}
                  className="rounded-lg border border-border bg-background p-3"
                >
                  <div className="text-xs font-semibold text-muted-foreground">
                    {t('learn.slideDeck.slideLabel', 'Slide {{number}}', { number: index + 1 })}
                  </div>
                  <div className="mt-1 text-sm font-semibold text-foreground">{slide.title}</div>
                  {renderBulletList(slide.bullets)}
                </li>
              ))}
            </ol>
          ) : null}

          {slideDeckError ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div>
                <div className="font-semibold">{slideDeckError.title}</div>
                <div className="mt-0.5">{slideDeckError.message}</div>
              </div>
            </div>
          ) : lesson.slide_deck_status === 'failed' && lesson.slide_deck_error ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div>{lesson.slide_deck_error}</div>
            </div>
          ) : null}
        </div>
      ) : null}

      {hasLessonDetail ? <LessonChat lessonId={lesson.id} /> : null}

      {isFailedLesson && lesson.generation_error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-foreground">
          {lesson.generation_error}
        </div>
      ) : null}
    </section>
  );
}
