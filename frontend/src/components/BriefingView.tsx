import { useId, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import {
  RefreshCw,
  Headphones,
  ChevronDown,
  ChevronUp,
  Sparkles,
  AlertCircle,
  Check,
  CheckCircle2,
} from 'lucide-react';
import { AiFeedbackThumbs } from '@/components/AiFeedbackThumbs';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDate, formatWindow } from '@/lib/briefingUtils';
import { estimateReadingMinutes, useBriefReadState } from '@/lib/briefReadState';
import { generateBriefingPodcast } from '@/api';
import { classifyGenerationError, type FriendlyError } from '@/lib/errorPresentation';
import type { Briefing, BriefingArticle, BriefingSection } from '@/types';

// ── Sub-components ────────────────────────────────────────────────────────────

function uniqueSources(articles: BriefingArticle[]): string[] {
  return [...new Set(articles.map((a) => a.source_name).filter(Boolean))];
}

function SourceAvatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="size-6 shrink-0 rounded-full border-2 border-card bg-muted text-muted-foreground text-xs font-semibold grid place-items-center -ms-1.5 first:ms-0 select-none"
    >
      {name.trim().charAt(0).toUpperCase()}
    </span>
  );
}

function SourceStack({ sources, label }: { sources: string[]; label: string }) {
  return (
    <span className="flex items-center gap-2 min-w-0">
      {sources.length > 0 && (
        <span className="flex items-center">
          {sources.slice(0, 3).map((name) => (
            <SourceAvatar key={name} name={name} />
          ))}
        </span>
      )}
      <span className="text-[13px] md:text-xs text-muted-foreground">{label}</span>
    </span>
  );
}

function greetingKey(now: Date): string {
  const hour = now.getHours();
  if (hour < 12) return 'brief.greeting_morning';
  if (hour < 18) return 'brief.greeting_afternoon';
  return 'brief.greeting_evening';
}

export function ProgressRing({ read, total }: { read: number; total: number }) {
  const { t } = useTranslation();
  const radius = 20;
  const circumference = 2 * Math.PI * radius;
  const ratio = total > 0 ? Math.min(read / total, 1) : 0;
  return (
    <div
      role="progressbar"
      aria-label={t('brief.progress_label')}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={read}
      aria-valuetext={t('brief.progress_value', { read, total })}
      className="relative size-12 shrink-0"
    >
      <svg viewBox="0 0 48 48" className="size-12 -rotate-90" aria-hidden="true">
        <circle cx="24" cy="24" r={radius} fill="none" strokeWidth="4" className="stroke-border" />
        <circle
          cx="24"
          cy="24"
          r={radius}
          fill="none"
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
          className="stroke-accent motion-safe:transition-[stroke-dashoffset] motion-safe:duration-500"
        />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-xs font-semibold tabular-nums text-foreground">
        {read}/{total}
      </span>
    </div>
  );
}

export function StoryCard({
  section,
  index,
  articles,
  isRead,
  onRead,
}: {
  section: BriefingSection;
  index: number;
  articles: BriefingArticle[];
  isRead: boolean;
  onRead: () => void;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();
  const sources = uniqueSources(articles);
  const topic = articles[0]?.category || t('brief.topic_fallback');

  function toggle() {
    if (!expanded) onRead();
    setExpanded(!expanded);
  }

  return (
    <article
      aria-label={`Briefing section ${index + 1}: ${section.title}`}
      className={`rounded-2xl border border-border text-card-foreground shadow-sm motion-safe:transition-colors ${
        isRead ? 'bg-surface' : 'bg-card'
      }`}
    >
      <button
        type="button"
        onClick={toggle}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="block w-full min-h-11 rounded-2xl p-4 md:p-5 text-start hover:bg-surface-2/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-safe:transition-colors"
      >
        <span
          className={`flex items-center gap-2 text-xs font-semibold uppercase tracking-wider ${
            isRead ? 'text-muted-foreground' : 'text-accent'
          }`}
        >
          <span className="tabular-nums">{String(index + 1).padStart(2, '0')}</span>
          <span aria-hidden="true">·</span>
          <span className="truncate">{topic}</span>
          {isRead && (
            <span className="ms-auto inline-flex items-center gap-1 text-xs font-medium normal-case tracking-normal text-muted-foreground">
              <Check className="size-4" aria-hidden="true" />
              {t('brief.read')}
            </span>
          )}
        </span>
        <h3 className="mt-1.5 text-base md:text-[17px] font-semibold leading-snug text-foreground break-words">
          {section.title}
        </h3>
        <p
          className={`mt-1.5 text-sm leading-relaxed text-muted-foreground break-words ${
            expanded ? '' : 'line-clamp-2'
          }`}
        >
          {section.body}
        </p>
        <span className="mt-3 flex items-center gap-2">
          <SourceStack sources={sources} label={t('brief.sources', { count: sources.length })} />
          <ChevronDown
            aria-hidden="true"
            className={`ms-auto size-4 shrink-0 text-muted-foreground motion-safe:transition-transform ${
              expanded ? 'rotate-180' : ''
            }`}
          />
        </span>
      </button>
      {expanded && articles.length > 0 && (
        <ul id={panelId} className="flex flex-col gap-0.5 border-t border-border px-2 py-2 md:px-3">
          {articles.map((article) => (
            <li key={article.id}>
              <Link
                to={`/a/${article.id}`}
                className="flex min-h-11 items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-safe:transition-colors"
              >
                <SourceAvatar name={article.source_name} />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium leading-snug text-foreground line-clamp-2 break-words">
                    {article.title}
                  </span>
                  <span className="block text-[13px] md:text-xs text-muted-foreground truncate">
                    {article.source_name}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function TopicChips({
  sections,
  active,
  onSelect,
}: {
  sections: BriefingSection[];
  active: number | null;
  onSelect: (index: number | null) => void;
}) {
  const { t } = useTranslation();
  const chipClass = (on: boolean) =>
    `inline-flex min-h-11 md:min-h-9 shrink-0 items-center gap-1.5 rounded-full px-4 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-safe:transition-colors ${
      on ? 'bg-foreground text-background' : 'bg-surface text-foreground hover:bg-surface-2'
    }`;
  return (
    <div
      role="group"
      aria-label={t('brief.topics')}
      className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 md:mx-0 md:flex-wrap md:px-0"
    >
      <button
        type="button"
        aria-pressed={active === null}
        onClick={() => onSelect(null)}
        className={chipClass(active === null)}
      >
        {t('brief.all_topics')}
      </button>
      {sections.map((section, i) => (
        <button
          key={i}
          type="button"
          aria-pressed={active === i}
          onClick={() => onSelect(active === i ? null : i)}
          className={chipClass(active === i)}
        >
          <span className="tabular-nums opacity-70">{i + 1}</span>
          <span className="max-w-[14rem] truncate">{section.title}</span>
        </button>
      ))}
    </div>
  );
}

function AllCaughtUp() {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      className="mt-4 flex flex-col items-center gap-2 rounded-2xl border border-dashed border-border bg-surface px-6 py-8 text-center"
    >
      <CheckCircle2 className="size-8 text-ok" aria-hidden="true" />
      <h3 className="text-base font-semibold text-foreground">{t('brief.caught_up_title')}</h3>
      <p className="max-w-sm text-sm text-muted-foreground">{t('brief.caught_up_body')}</p>
      <Link
        to="/today"
        className="mt-1 inline-flex min-h-11 items-center rounded-full px-4 text-sm font-medium text-accent hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {t('brief.caught_up_action')}
      </Link>
    </div>
  );
}

export function WorthOpening({ articles }: { articles: BriefingArticle[] }) {
  if (articles.length === 0) return null;
  return (
    <div className="mt-8">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
        Also worth a look
      </h3>
      <div className="flex flex-col gap-1 rounded-2xl border border-border bg-card p-2">
        {articles.map((article) => (
          <Link
            key={article.id}
            to={`/a/${article.id}`}
            className="flex min-h-11 items-start gap-3 rounded-lg p-2 hover:bg-surface-2 transition-colors group"
          >
            <div className="min-w-0">
              <div className="text-sm font-medium text-foreground leading-snug break-words">
                {article.title}
              </div>
              <div className="text-[13px] md:text-xs text-muted-foreground mt-0.5">
                {article.source_name}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function BriefSkeleton() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 md:px-6 pt-5">
      <Skeleton className="h-3 w-1/3 mb-3" />
      <Skeleton className="h-7 w-3/4 mb-2" />
      <Skeleton className="h-3 w-1/2 mb-6" />
      <div className="grid gap-3 md:grid-cols-2">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-2xl border border-border p-4">
            <Skeleton className="h-3 w-1/4 mb-3" />
            <Skeleton className="h-5 w-5/6 mb-2" />
            <Skeleton className="h-4 w-full mb-1.5" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function BriefingView({
  briefing,
  onGenerate,
  isGenerating,
  afterMeta,
  onRefreshBriefing,
  showGreeting = false,
}: {
  briefing: Briefing;
  onGenerate?: () => void;
  isGenerating?: boolean;
  afterMeta?: React.ReactNode;
  onRefreshBriefing?: () => void;
  showGreeting?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const [isGeneratingPodcast, setIsGeneratingPodcast] = useState(false);
  const [podcastError, setPodcastError] = useState<FriendlyError | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const [activeTopic, setActiveTopic] = useState<number | null>(null);
  const { read, markRead } = useBriefReadState(briefing.id);

  async function handleGeneratePodcast() {
    setIsGeneratingPodcast(true);
    setPodcastError(null);
    try {
      await generateBriefingPodcast(briefing.id);
      if (onRefreshBriefing) {
        onRefreshBriefing();
      }
    } catch (err: unknown) {
      setPodcastError(classifyGenerationError(err));
    } finally {
      setIsGeneratingPodcast(false);
    }
  }

  const articleMap = new Map(briefing.articles.map((a) => [a.id, a]));
  const sections = briefing.content?.sections ?? [];
  const worthOpening = briefing.content?.worth_opening?.length
    ? briefing.content.worth_opening
        .map((articleId) => articleMap.get(articleId))
        .filter((article): article is BriefingArticle => Boolean(article))
    : briefing.articles.filter((a) => a.section_index === null);
  const articleCount = briefing.articles.length;

  const total = sections.length;
  const readCount = sections.filter((_, i) => read.has(i)).length;
  const caughtUp = total > 0 && readCount === total;
  const minutes = estimateReadingMinutes([briefing.summary, ...sections.map((s) => s.body)]);
  const created = new Date(briefing.created_at);
  const dayLabel = Number.isNaN(created.getTime())
    ? formatDate(briefing.created_at)
    : new Intl.DateTimeFormat(i18n.language || undefined, {
        weekday: 'long',
        month: 'short',
        day: 'numeric',
      }).format(created);
  const eyebrow = [
    showGreeting ? t(greetingKey(new Date())) : null,
    dayLabel,
    t('brief.reading_time', { count: minutes }),
  ]
    .filter(Boolean)
    .join(' · ');

  const visibleSections = sections
    .map((section, index) => ({ section, index }))
    .filter(({ index }) => activeTopic === null || activeTopic === index);

  return (
    <div className="mx-auto w-full max-w-5xl">
      <header className="px-4 md:px-6 pt-5 pb-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[13px] md:text-xs font-medium text-muted-foreground">
              {eyebrow}
            </div>
            <h2 className="mt-1 text-2xl md:text-[28px] font-semibold tracking-tight leading-tight break-words">
              {briefing.title}
            </h2>
            <div className="text-[13px] md:text-xs text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
              <span>
                {formatWindow(briefing.since_at, briefing.until_at)} · {articleCount}{' '}
                {articleCount === 1 ? 'article' : 'articles'}
              </span>
              {briefing.status === 'complete' && (
                <AiFeedbackThumbs subjectType="briefing" subjectId={briefing.id} />
              )}
            </div>
          </div>
          {total > 0 && <ProgressRing read={readCount} total={total} />}
        </div>
        {(afterMeta || onGenerate) && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {afterMeta}
            {onGenerate && (
              <Button
                size="sm"
                variant="ghost"
                onClick={onGenerate}
                disabled={isGenerating}
                className="min-h-11 md:min-h-9"
                aria-label="Generate new briefing"
              >
                <RefreshCw className={`size-4 ${isGenerating ? 'animate-spin' : ''}`} />
                {isGenerating ? 'Generating…' : 'Refresh'}
              </Button>
            )}
          </div>
        )}
      </header>

      <div className="px-4 md:px-6 pb-8">
        {briefing.summary && (
          <p className="text-[15px] md:text-base text-foreground/85 leading-relaxed mb-5 break-words">
            {briefing.summary}
          </p>
        )}

        {/* Podcast Briefing Card */}
        {briefing.status === 'complete' && (
          <div className="rounded-2xl border border-border bg-card/60 backdrop-blur-md p-4 mb-5 shadow-sm">
            {!briefing.script ? (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="size-10 rounded-full bg-primary/10 flex items-center justify-center text-primary shrink-0">
                    <Headphones className="size-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                      Co-host Podcast Briefing
                      <span className="inline-flex items-center gap-0.5 rounded bg-surface-2 px-1.5 py-0.5 text-xs font-medium text-foreground">
                        <Sparkles className="size-4 text-accent" aria-hidden="true" /> New
                      </span>
                    </h4>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Generate a conversational podcast briefing where co-hosts Alex and Taylor
                      explain today's stories.
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  onClick={() => {
                    void handleGeneratePodcast();
                  }}
                  disabled={isGeneratingPodcast}
                  className="min-h-11 md:min-h-9 sm:self-center shrink-0 self-start"
                >
                  <Headphones className="size-4 me-2" />
                  {isGeneratingPodcast ? 'Creating Podcast…' : 'Create Podcast'}
                </Button>
              </div>
            ) : (
              <div>
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div className="flex items-start gap-3">
                    <div className="size-10 rounded-full bg-primary/10 flex items-center justify-center text-primary shrink-0">
                      <Headphones className="size-5 motion-safe:animate-pulse" />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-foreground">AI Co-host Podcast</h4>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Co-hosts Alex (alloy) and Taylor (shimmer) discussing today's news
                      </p>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setShowTranscript(!showTranscript)}
                    className="min-h-11 md:min-h-9 text-xs gap-1"
                  >
                    {showTranscript ? (
                      <>
                        Hide Transcript <ChevronUp className="size-4" />
                      </>
                    ) : (
                      <>
                        Show Transcript <ChevronDown className="size-4" />
                      </>
                    )}
                  </Button>
                </div>

                <div className="rounded-lg bg-muted/40 p-2 border border-border/40">
                  <audio
                    src={`/api/briefings/${briefing.id}/podcast`}
                    controls
                    className="w-full h-11"
                  />
                </div>

                {showTranscript && briefing.script && (
                  <div className="mt-4 space-y-3 pt-4 border-t border-border/60 max-h-[350px] overflow-y-auto scrollbar-thin pe-1 flex flex-col">
                    {briefing.script.map((turn, index) => {
                      const isAlex = turn.speaker.toLowerCase() === 'alex';
                      return (
                        <div
                          key={index}
                          className={`flex items-start gap-2.5 max-w-[85%] ${
                            isAlex ? 'self-start' : 'self-end flex-row-reverse ms-auto'
                          }`}
                        >
                          <div
                            className={`size-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 select-none ${
                              isAlex ? 'bg-primary/10 text-primary' : 'bg-surface-2 text-foreground'
                            }`}
                          >
                            {turn.speaker[0]}
                          </div>
                          <div
                            className={`rounded-lg p-2.5 text-xs leading-relaxed ${
                              isAlex
                                ? 'bg-muted text-foreground rounded-ss-none border border-border/30'
                                : 'bg-primary/10 text-foreground rounded-se-none border border-primary/20'
                            }`}
                          >
                            <span className="font-semibold block mb-0.5 text-xs uppercase tracking-wider text-muted-foreground">
                              {turn.speaker} ({turn.voice})
                            </span>
                            {turn.text}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {podcastError && (
              <div className="mt-3 flex items-start gap-2 p-3 rounded-lg border border-destructive/20 bg-destructive/5 text-xs text-destructive">
                <AlertCircle className="size-4 shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold">
                    {podcastError.kind === 'no_ai'
                      ? podcastError.title
                      : 'Podcast generation failed'}
                  </div>
                  <div className="mt-0.5">{podcastError.message}</div>
                  {podcastError.detail && (
                    <div className="mt-1 font-mono text-destructive/70">{podcastError.detail}</div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {total > 1 && (
          <div className="mb-4">
            <TopicChips sections={sections} active={activeTopic} onSelect={setActiveTopic} />
          </div>
        )}

        <div className="@container">
          <div className="grid items-start gap-3 @2xl:grid-cols-2">
            {visibleSections.map(({ section, index }) => (
              <StoryCard
                key={index}
                section={section}
                index={index}
                articles={section.citations
                  .map((id) => articleMap.get(id))
                  .filter((a): a is BriefingArticle => Boolean(a))}
                isRead={read.has(index)}
                onRead={() => markRead(index)}
              />
            ))}
          </div>
        </div>

        {caughtUp && <AllCaughtUp />}

        <WorthOpening articles={worthOpening} />
      </div>
    </div>
  );
}
