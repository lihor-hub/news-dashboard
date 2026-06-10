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
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchArticle, fetchArticleBody } from '@/api';
import { adaptArticle, patchArticleState, patchArticleStar } from '@/api/workflowApi';
import type { WorkflowState } from '@/lib/workflowTypes';
import { formatDate, signalLabel } from '@/lib/format';
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

  // Trigger body fetch on first open when body is missing
  const bodyMutation = useMutation({
    mutationFn: () => fetchArticleBody(id!),
    onSuccess: (updated) => {
      queryClient.setQueryData(['article', id], updated);
    },
  });

  useEffect(() => {
    if (!article) return;
    if (article.bodyStatus === 'missing' && !bodyMutation.isPending) {
      bodyMutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [article?.bodyStatus]);

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

  const bodyLoading = bodyMutation.isPending || article.bodyStatus === 'missing';

  return (
    <div className="min-h-screen bg-background flex flex-col motion-slide-in-right">
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
          </div>

          {/* Title */}
          <h1 className="mt-3 text-[26px] md:text-[30px] font-semibold tracking-tight leading-tight">
            {article.title}
          </h1>

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

      {/* Action bar */}
      <div className="fixed bottom-0 inset-x-0 z-20 border-t border-border bg-background/95 backdrop-blur pb-[env(safe-area-inset-bottom)]">
        <div className="mx-auto max-w-2xl grid grid-cols-5 gap-1 p-2">
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
        </div>
      </div>
    </div>
  );
}
