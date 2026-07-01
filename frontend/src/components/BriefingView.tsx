import { useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, Headphones, ChevronDown, ChevronUp, Sparkles, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDate, formatWindow } from '@/lib/briefingUtils';
import { generateBriefingPodcast } from '@/api';
import { classifyGenerationError, type FriendlyError } from '@/lib/errorPresentation';
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
      <h3 className="text-sm font-semibold text-foreground mb-1.5 break-words">{section.title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed break-words">{section.body}</p>
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
              <div className="text-sm font-medium text-foreground group-hover:text-accent-foreground leading-snug break-words">
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
  onRefreshBriefing,
}: {
  briefing: Briefing;
  onGenerate?: () => void;
  isGenerating?: boolean;
  afterMeta?: React.ReactNode;
  onRefreshBriefing?: () => void;
}) {
  const [isGeneratingPodcast, setIsGeneratingPodcast] = useState(false);
  const [podcastError, setPodcastError] = useState<FriendlyError | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);

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

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[22px] font-semibold tracking-tight leading-tight break-words">
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
          <p className="text-sm text-muted-foreground leading-relaxed mb-5 pb-5 border-b border-border break-words">
            {briefing.summary}
          </p>
        )}

        {/* Podcast Briefing Card */}
        {briefing.status === 'complete' && (
          <div className="rounded-xl border border-border bg-card/60 backdrop-blur-md p-4 mb-6 shadow-sm">
            {!briefing.script ? (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="size-10 rounded-full bg-primary/10 flex items-center justify-center text-primary shrink-0">
                    <Headphones className="size-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                      Co-host Podcast Briefing
                      <span className="inline-flex items-center gap-0.5 rounded bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:text-amber-300">
                        <Sparkles className="size-2.5" /> New
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
                  className="sm:self-center shrink-0 self-start"
                >
                  <Headphones className="size-4 mr-2" />
                  {isGeneratingPodcast ? 'Creating Podcast…' : 'Create Podcast'}
                </Button>
              </div>
            ) : (
              <div>
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div className="flex items-start gap-3">
                    <div className="size-10 rounded-full bg-primary/10 flex items-center justify-center text-primary shrink-0">
                      <Headphones className="size-5 animate-pulse" />
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
                    className="h-8 text-xs gap-1"
                  >
                    {showTranscript ? (
                      <>
                        Hide Transcript <ChevronUp className="size-3.5" />
                      </>
                    ) : (
                      <>
                        Show Transcript <ChevronDown className="size-3.5" />
                      </>
                    )}
                  </Button>
                </div>

                <div className="rounded-lg bg-muted/40 p-2 border border-border/40">
                  <audio
                    src={`/api/briefings/${briefing.id}/podcast`}
                    controls
                    className="w-full h-9"
                  />
                </div>

                {showTranscript && briefing.script && (
                  <div className="mt-4 space-y-3 pt-4 border-t border-border/60 max-h-[350px] overflow-y-auto scrollbar-thin pr-1 flex flex-col">
                    {briefing.script.map((turn, index) => {
                      const isAlex = turn.speaker.toLowerCase() === 'alex';
                      return (
                        <div
                          key={index}
                          className={`flex items-start gap-2.5 max-w-[85%] ${
                            isAlex ? 'self-start' : 'self-end flex-row-reverse ml-auto'
                          }`}
                        >
                          <div
                            className={`size-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 select-none ${
                              isAlex
                                ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300'
                                : 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300'
                            }`}
                          >
                            {turn.speaker[0]}
                          </div>
                          <div
                            className={`rounded-lg p-2.5 text-xs leading-relaxed ${
                              isAlex
                                ? 'bg-muted text-foreground rounded-tl-none border border-border/30'
                                : 'bg-primary/10 text-foreground rounded-tr-none border border-primary/20'
                            }`}
                          >
                            <span className="font-semibold block mb-0.5 text-[9px] uppercase tracking-wider text-muted-foreground">
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
