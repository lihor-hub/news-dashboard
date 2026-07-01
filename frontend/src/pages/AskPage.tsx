import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Loader2, AlertCircle, BookOpen, ThumbsUp, ThumbsDown } from 'lucide-react';
import { askAI, submitFeedback } from '@/api';
import type { AskResponse } from '@/types';
import { cn } from '@/lib/utils';

function AnswerFeedback({ traceId }: { traceId: string }) {
  const [sent, setSent] = useState<boolean | null>(null);

  function rate(helpful: boolean) {
    if (sent !== null) return;
    setSent(helpful);
    // Fire-and-forget: feedback must never block or error the UI.
    void submitFeedback(traceId, helpful).catch(() => undefined);
  }

  if (sent !== null) {
    return <p className="text-[11px] text-muted-foreground">Thanks for the feedback.</p>;
  }
  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] text-muted-foreground">Was this helpful?</span>
      <button
        type="button"
        aria-label="Helpful"
        onClick={() => rate(true)}
        className="rounded p-1 text-muted-foreground hover:bg-surface hover:text-foreground"
      >
        <ThumbsUp className="size-3.5" />
      </button>
      <button
        type="button"
        aria-label="Not helpful"
        onClick={() => rate(false)}
        className="rounded p-1 text-muted-foreground hover:bg-surface hover:text-foreground"
      >
        <ThumbsDown className="size-3.5" />
      </button>
    </div>
  );
}

type ErrorKind = 'no_key' | 'not_enough' | 'generation_failed';

interface AskError {
  kind: ErrorKind;
  message: string;
}

function parseError(err: unknown): AskError {
  const msg = err instanceof Error ? err.message : String(err);
  if (/FREE_LLM_API_KEY|OPENAI_API_KEY|credentials|API key/i.test(msg)) {
    return { kind: 'no_key', message: msg };
  }
  return { kind: 'generation_failed', message: msg };
}

function ErrorBanner({ error }: { error: AskError }) {
  const copy: Record<ErrorKind, { title: string; body: string }> = {
    no_key: {
      title: 'Ask AI is not configured',
      body: 'An AI API key is required. Set FREE_LLM_API_KEY (or OPENAI_API_KEY) in the app environment and restart.',
    },
    not_enough: {
      title: 'Not enough articles yet',
      body: 'Save or finish more articles to ask questions.',
    },
    generation_failed: {
      title: 'Something went wrong',
      body: 'The AI could not generate an answer. Try again in a moment.',
    },
  };
  const { title, body } = copy[error.kind];
  return (
    <div className="mt-6 flex gap-3 rounded-md border border-dashed border-border p-4">
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div>
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="mt-0.5 text-sm text-muted-foreground">{body}</p>
      </div>
    </div>
  );
}

interface Citation {
  id: number;
  title: string;
  url: string;
}

function CitationCard({ citation, index }: { citation: Citation; index: number }) {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => void navigate(`/a/${citation.id}`)}
      className={cn(
        'w-full text-left rounded-md border border-border bg-card p-3',
        'hover:bg-surface transition-colors'
      )}
    >
      <div className="flex items-baseline justify-between gap-2 mb-0.5">
        <span className="text-[10px] text-muted-foreground">[{index + 1}]</span>
        <BookOpen className="size-3 text-muted-foreground shrink-0" />
      </div>
      <div className="text-sm font-medium leading-snug">{citation.title}</div>
      <div className="mt-0.5 text-[11px] text-muted-foreground truncate">{citation.url}</div>
    </button>
  );
}

export function AskPage() {
  const [q, setQ] = useState('');
  const [includeAll, setIncludeAll] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<AskError | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const query = q.trim();
    if (!query || loading) return;
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const res = await askAI(query, includeAll);
      if (res.answer.startsWith('Not enough articles')) {
        setError({ kind: 'not_enough', message: res.answer });
      } else {
        setResult(res);
      }
    } catch (err) {
      setError(parseError(err));
    } finally {
      setLoading(false);
    }
  }

  const noSupportingArticles =
    result !== null && result.sources.length === 0 && result.answer.trim().length > 0;

  return (
    <div className="px-4 md:px-5 pt-4 pb-12 max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles className="size-5 text-accent" />
        <h2 className="text-[22px] font-semibold tracking-tight">Ask AI</h2>
      </div>
      <p className="text-xs text-muted-foreground mb-4">
        Answers over your Starred and Done articles. Today, Skipped, and Archived are excluded by
        default.
      </p>

      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-2">
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="What did I read about Postgres LISTEN/NOTIFY?"
          rows={3}
          maxLength={2000}
          className={cn(
            'w-full p-3 rounded-md border border-border bg-surface text-sm outline-none',
            'focus:border-border-strong focus:bg-background resize-none'
          )}
        />
        <div className="flex items-center justify-between gap-2">
          <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={includeAll}
              onChange={(e) => setIncludeAll(e.target.checked)}
              className="accent-accent"
            />
            Include all non-archived articles
          </label>
          <button
            type="submit"
            disabled={loading || !q.trim()}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-md bg-foreground text-background',
              'px-3 py-1.5 text-sm font-medium disabled:opacity-50'
            )}
          >
            {loading && <Loader2 className="size-3.5 animate-spin" />}
            Ask
          </button>
        </div>
      </form>

      {error && <ErrorBanner error={error} />}

      {result && (
        <div className="mt-6 space-y-4">
          <div className="reader-prose text-[15px] leading-relaxed">{result.answer}</div>

          {result.trace_id && <AnswerFeedback traceId={result.trace_id} />}

          {noSupportingArticles && (
            <p className="text-sm text-muted-foreground italic">
              No specific articles were found to support this answer.
            </p>
          )}

          {result.sources.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-2">
                Citations
              </div>
              <div className="space-y-2">
                {result.sources.map((s, i) => (
                  <CitationCard key={s.id} citation={s} index={i} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
