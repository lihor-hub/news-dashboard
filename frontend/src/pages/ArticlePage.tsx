import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Star,
  Check,
  Clock,
  X as XIcon,
  Archive,
  AlertCircle,
  Loader2,
  Volume2,
  Square,
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchArticle, fetchArticleBody, fetchArticleAudioUrl, fetchArticleInsights } from '@/api';
import { adaptArticle, patchArticleState, patchArticleStar } from '@/api/workflowApi';
import type { WorkflowState } from '@/lib/workflowTypes';
import { formatDate, readingTime, signalLabel } from '@/lib/format';
import { getReaderList } from '@/lib/readerList';
import { cn } from '@/lib/utils';

function renderBody(md: string): string {
  const escape = (s: string) =>
    s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
  const lines = md.split('\n');
  let html = '';
  let inCode = false;
  let inList = false;
  const para: string[] = [];

  const flushPara = () => {
    if (para.length) {
      html += `<p>${inline(para.join(' '))}</p>`;
      para.length = 0;
    }
  };

  const inline = (s: string) =>
    s
      .replace(/`([^`]+)`/g, (_, t: string) => `<code>${escape(t)}</code>`)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');

  for (const raw of lines) {
    if (raw.startsWith('```')) {
      if (inCode) {
        html += '</code></pre>';
        inCode = false;
      } else {
        flushPara();
        html += '<pre><code>';
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      html += escape(raw) + '\n';
      continue;
    }
    if (raw.startsWith('## ')) {
      flushPara();
      if (inList) {
        html += '</ul>';
        inList = false;
      }
      html += `<h2>${inline(escape(raw.slice(3)))}</h2>`;
      continue;
    }
    if (raw.startsWith('- ')) {
      flushPara();
      if (!inList) {
        html += '<ul>';
        inList = true;
      }
      html += `<li>${inline(escape(raw.slice(2)))}</li>`;
      continue;
    }
    if (raw.trim() === '') {
      flushPara();
      if (inList) {
        html += '</ul>';
        inList = false;
      }
      continue;
    }
    para.push(escape(raw));
  }
  flushPara();
  if (inList) html += '</ul>';
  if (inCode) html += '</code></pre>';
  return html;
}

function ActionBtn({
  onClick,
  icon: Icon,
  label,
  active,
  disabled,
}: {
  onClick: () => void;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex flex-col items-center justify-center gap-0.5 py-2 rounded-md text-[11px] font-medium transition-colors',
        active ? 'text-star' : 'text-muted-foreground hover:text-foreground hover:bg-surface',
        disabled && 'opacity-30 cursor-not-allowed hover:bg-transparent'
      )}
    >
      <Icon className={cn('size-5', active && 'fill-current')} strokeWidth={1.75} />
      {label}
    </button>
  );
}

export function ArticlePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: rawArticle, isLoading } = useQuery({
    queryKey: ['article', id],
    queryFn: () => fetchArticle(id!),
    enabled: !!id,
    staleTime: 30_000,
  });

  const article = rawArticle ? adaptArticle(rawArticle) : null;

  // Trigger body fetch in parallel with metadata — fire at mount so we don't
  // wait for the GET /api/articles/:id round-trip before starting the slow scrape.
  const bodyMutation = useMutation({
    mutationFn: () => fetchArticleBody(id!),
    onSuccess: (updated) => {
      queryClient.setQueryData(['article', id], updated);
    },
  });

  useEffect(() => {
    if (!id) return;
    // Skip if the React Query cache already has a fully-fetched body for this article.
    const cached = queryClient.getQueryData<{ body_status?: string }>(['article', id]);
    if (cached?.body_status === 'ok') return;
    bodyMutation.mutate();
    // Run once per article id; bodyMutation is intentionally omitted from deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const {
    data: insightBullets,
    isLoading: insightsLoading,
    isError: insightsError,
  } = useQuery({
    queryKey: ['article-insights', id],
    queryFn: () => fetchArticleInsights(id!),
    enabled: !!id,
    retry: false,
    staleTime: Infinity,
  });

  // Prev/next navigation from sessionStorage list
  const readerList = getReaderList();
  const idx = readerList ? readerList.ids.indexOf(String(id)) : -1;
  const prevId = idx > 0 ? readerList!.ids[idx - 1] : null;
  const nextId =
    idx >= 0 && idx < (readerList?.ids.length ?? 0) - 1 ? readerList!.ids[idx + 1] : null;

  const goBack = () => navigate(-1);
  const goPrev = () => prevId && navigate(`/a/${prevId}`, { replace: true });
  const goNext = () => nextId && navigate(`/a/${nextId}`, { replace: true });

  // Triage mutations — inline (no extra hook so we stay self-contained)
  async function doAction(state: WorkflowState, label: string) {
    if (!article) return;
    if (state === 'skipped' && article.starred) {
      toast.error("Starred articles can't be skipped");
      return;
    }
    try {
      await patchArticleState(article.id, state, article.starred);
      void queryClient.invalidateQueries({ queryKey: ['articles'] });
      void queryClient.invalidateQueries({ queryKey: ['summary'] });
      toast(label);
      if (nextId) navigate(`/a/${nextId}`, { replace: true });
      else goBack();
    } catch {
      toast.error('Action failed');
    }
  }

  async function doStar() {
    if (!article) return;
    const next = !article.starred;
    try {
      await patchArticleStar(article.id, next);
      await queryClient.invalidateQueries({ queryKey: ['article', id] });
      void queryClient.invalidateQueries({ queryKey: ['articles'] });
      void queryClient.invalidateQueries({ queryKey: ['summary'] });
      toast(next ? 'Starred' : 'Unstarred');
    } catch {
      toast.error('Action failed');
    }
  }

  // TTS audio player
  type AudioState = 'idle' | 'loading' | 'playing' | 'paused';
  const [audioState, setAudioState] = useState<AudioState>('idle');
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  const audioMutation = useMutation({
    mutationFn: () => fetchArticleAudioUrl(id!),
    onSuccess: (url) => {
      audioUrlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setAudioState('paused');
      audio.onerror = () => {
        toast.error('Audio playback failed');
        setAudioState('idle');
      };
      void audio.play();
      setAudioState('playing');
    },
    onError: () => {
      toast.error('Could not load audio');
      setAudioState('idle');
    },
  });

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      if (audioUrlRef.current) {
        URL.revokeObjectURL(audioUrlRef.current);
        audioUrlRef.current = null;
      }
    };
  }, []);

  function handleListen() {
    if (audioState === 'loading') return;
    if (audioState === 'playing') {
      audioRef.current?.pause();
      setAudioState('paused');
      return;
    }
    if (audioState === 'paused' && audioRef.current) {
      void audioRef.current.play();
      setAudioState('playing');
      return;
    }
    setAudioState('loading');
    audioMutation.mutate();
  }

  // Touch swipe
  const swipeRef = useRef<{ x: number; y: number } | null>(null);
  const [swipeDx, setSwipeDx] = useState(0);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t?.tagName === 'INPUT' || t?.tagName === 'TEXTAREA' || t?.isContentEditable) return;
      if (e.key === 'Escape') goBack();
      else if (e.key === 'ArrowLeft') goPrev();
      else if (e.key === 'ArrowRight') goNext();
      else if ((e.key === 'r' || e.key === 'd') && article) void doAction('done', 'Done');
      else if (e.key === 'l' && article) void doAction('later', 'Later');
      else if (e.key === 's' && article) void doStar();
      else if (e.key === 'x' && article) void doAction('skipped', 'Skipped');
      else if (e.key === 'e' && article) void doAction('archived', 'Archived');
      else if (e.key === 'o' && article) window.open(article.url, '_blank');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const signalColor =
    article?.signal === 'high'
      ? 'text-signal-high'
      : article?.signal === 'mid'
        ? 'text-signal-mid'
        : 'text-signal-low';

  if (isLoading || !article) {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
          <div className="mx-auto max-w-2xl flex h-12 items-center px-3">
            <button
              onClick={goBack}
              className="inline-flex items-center gap-1 px-2 py-1 -ml-1 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-surface"
            >
              <ArrowLeft className="size-4" /> Back
            </button>
          </div>
        </header>
        <div className="flex-1 flex items-center justify-center">
          {isLoading ? (
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          ) : (
            <p className="text-sm text-muted-foreground">Article not found.</p>
          )}
        </div>
      </div>
    );
  }

  const bodyLoading =
    bodyMutation.isPending || (article.bodyStatus === 'missing' && bodyMutation.isIdle);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header + scrollable content slide in together.  The action bar is a
          sibling outside this wrapper so its position:fixed always resolves
          against the viewport, even while the entry transform is active. */}
      <div className="flex-1 flex flex-col motion-slide-in-right">
        {/* Sticky header */}
        <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
          <div className="mx-auto max-w-2xl flex h-12 items-center justify-between px-3">
            <button
              onClick={goBack}
              className="inline-flex items-center gap-1 px-2 py-1 -ml-1 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-surface"
            >
              <ChevronLeft className="size-4" /> Back
            </button>
            <div className="flex items-center gap-1">
              <button
                onClick={goPrev}
                disabled={!prevId}
                className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface disabled:opacity-30"
                aria-label="Previous article"
              >
                <ChevronLeft className="size-4" />
              </button>
              <button
                onClick={goNext}
                disabled={!nextId}
                className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface disabled:opacity-30"
                aria-label="Next article"
              >
                <ChevronRight className="size-4" />
              </button>
              <a
                href={article.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface"
                aria-label="Open original"
              >
                <ExternalLink className="size-4" />
              </a>
            </div>
          </div>
        </header>

        {/* Article content */}
        <div
          className="flex-1 pb-32 overflow-x-hidden"
          onTouchStart={(e) => {
            swipeRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
          }}
          onTouchMove={(e) => {
            if (!swipeRef.current) return;
            const dx = e.touches[0].clientX - swipeRef.current.x;
            const dy = Math.abs(e.touches[0].clientY - swipeRef.current.y);
            if (dy < 40) setSwipeDx(dx);
          }}
          onTouchEnd={() => {
            if (swipeDx < -80) goNext();
            else if (swipeDx > 80) goPrev();
            setSwipeDx(0);
            swipeRef.current = null;
          }}
          onTouchCancel={() => {
            swipeRef.current = null;
            setSwipeDx(0);
          }}
        >
          <article
            className="mx-auto max-w-2xl px-5 pt-6"
            style={{
              transform: `translateX(${swipeDx * 0.3}px)`,
              transition: swipeDx ? 'none' : 'transform 0.2s ease',
            }}
          >
            {/* Meta line */}
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
            </div>

            {/* Title */}
            <h1 className="mt-3 text-[26px] md:text-[30px] font-semibold tracking-tight leading-tight">
              {article.title}
            </h1>

            {/* Reading time — only shown once body is available */}
            {article.bodyStatus === 'ok' && article.body && (
              <div className="mt-2 flex items-center gap-1 text-[12px] text-muted-foreground">
                <Clock className="size-3.5" strokeWidth={1.75} />
                <span>{readingTime(article.body)} min read</span>
              </div>
            )}

            {/* AI insights — hidden on 501/error, spinner while loading */}
            {!insightsError &&
              (insightsLoading || (insightBullets && insightBullets.length > 0)) && (
                <div
                  className="mt-4 rounded-lg border border-border bg-surface/40 px-4 py-3"
                  data-testid="insights-section"
                >
                  <div className="text-[10px] font-medium uppercase tracking-wider text-subtle mb-2">
                    Key takeaways
                  </div>
                  {insightsLoading ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="size-3.5 animate-spin" />
                      <span>Analyzing…</span>
                    </div>
                  ) : (
                    <ul className="space-y-1.5">
                      {insightBullets!.map((bullet, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-2 text-[13px] leading-snug text-foreground"
                        >
                          <span className="mt-0.5 shrink-0 text-accent">•</span>
                          <span>{bullet}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

            {/* Why this matters */}
            <div className="mt-4 rounded-lg border-l-2 border-accent bg-surface/60 px-4 py-3">
              <div className="text-[10px] font-medium uppercase tracking-wider text-subtle mb-1">
                Why this matters
              </div>
              <p className="text-[14px] leading-snug text-foreground">{article.reason}</p>
            </div>

            {/* Body */}
            <div className="mt-8">
              {bodyLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground py-12">
                  <Loader2 className="size-4 animate-spin" /> Loading article…
                </div>
              ) : article.bodyStatus === 'error' || !article.body ? (
                <div className="rounded-lg border border-border bg-surface px-4 py-5">
                  <div className="flex items-start gap-2 mb-2">
                    <AlertCircle className="size-4 mt-0.5 text-destructive shrink-0" />
                    <div className="text-sm font-medium text-foreground">
                      Couldn't extract article text
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground mb-4">{article.summary}</p>
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-md bg-foreground text-background px-3 py-1.5 text-sm font-medium hover:opacity-90"
                  >
                    Open original <ExternalLink className="size-3.5" />
                  </a>
                </div>
              ) : (
                <div
                  className="reader-prose"
                  dangerouslySetInnerHTML={{ __html: renderBody(article.body) }}
                />
              )}
            </div>
          </article>
        </div>
      </div>
      {/* end animated wrapper */}

      {/* Action bar — intentionally outside the motion-slide-in-right wrapper
          so position:fixed always resolves against the viewport, not against
          an ancestor that carries a CSS transform during the entry animation */}
      <div
        data-testid="action-bar"
        className="fixed bottom-0 inset-x-0 z-20 border-t border-border bg-background/95 backdrop-blur pb-[env(safe-area-inset-bottom)]"
      >
        <div className="mx-auto max-w-2xl grid grid-cols-6 gap-1 p-2">
          <ActionBtn
            onClick={() => void doStar()}
            icon={Star}
            label={article.starred ? 'Unstar' : 'Star'}
            active={article.starred}
          />
          <ActionBtn onClick={() => void doAction('done', 'Done')} icon={Check} label="Done" />
          <ActionBtn onClick={() => void doAction('later', 'Later')} icon={Clock} label="Later" />
          <ActionBtn
            onClick={() => void doAction('skipped', 'Skipped')}
            icon={XIcon}
            label="Skip"
            disabled={article.starred}
          />
          <ActionBtn
            onClick={() => void doAction('archived', 'Archived')}
            icon={Archive}
            label="Archive"
          />
          <ActionBtn
            onClick={handleListen}
            icon={audioState === 'loading' ? Loader2 : audioState === 'playing' ? Square : Volume2}
            label={
              audioState === 'loading'
                ? 'Loading…'
                : audioState === 'playing'
                  ? 'Stop'
                  : audioState === 'paused'
                    ? 'Resume'
                    : 'Listen'
            }
            disabled={audioState === 'loading'}
          />
        </div>
      </div>
    </div>
  );
}
