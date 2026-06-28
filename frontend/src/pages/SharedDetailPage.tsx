import { useState, useRef, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ExternalLink, Sparkles, MessageSquare, Highlighter, Send } from 'lucide-react';
import { fetchShareDetail, postShareMessage } from '@/api';
import { relativeTime } from '@/lib/format';
import { useAuth } from '@/contexts/auth';

function BackLink() {
  return (
    <Link
      to="/shared"
      className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
    >
      <ArrowLeft className="size-3.5" />
      Shared with me
    </Link>
  );
}

export function SharedDetailPage() {
  const { shareId } = useParams<{ shareId: string }>();
  const id = shareId ? parseInt(shareId, 10) : NaN;
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [draft, setDraft] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    data: share,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['share', id],
    queryFn: () => fetchShareDetail(id),
    enabled: !isNaN(id),
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: (message: string) => postShareMessage(id, message),
    onSuccess: () => {
      setDraft('');
      void queryClient.invalidateQueries({ queryKey: ['share', id] });
    },
  });

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const msg = draft.trim();
    if (!msg || mutation.isPending) return;
    mutation.mutate(msg);
  }

  if (isNaN(id)) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <BackLink />
        <p className="mt-4 text-sm text-destructive">Invalid share link.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <BackLink />
        <div className="mt-6 space-y-3">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-5 animate-pulse rounded bg-surface-2" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !share) {
    const msg = error instanceof Error ? error.message : 'Share not found.';
    return (
      <div className="mx-auto max-w-2xl px-4 py-6">
        <BackLink />
        <p className="mt-4 text-sm text-destructive">{msg}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6 space-y-5">
      <BackLink />

      {/* Article header */}
      <div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
          <span className="font-medium text-foreground">{share.from_username}</span>
          <span>shared · {relativeTime(share.created_at)}</span>
        </div>
        <h1 className="text-lg font-semibold text-foreground leading-snug">
          {share.article_title}
        </h1>
        <p className="mt-0.5 text-xs text-muted-foreground">{share.article_source_name}</p>

        <div className="mt-3 flex items-center gap-4 text-xs">
          <Link to={`/a/${share.article_id}`} className="text-accent-foreground hover:underline">
            Read article
          </Link>
          <a
            href={share.article_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
          >
            Original <ExternalLink className="size-3" />
          </a>
        </div>
      </div>

      {/* Sender note */}
      {share.note ? (
        <div className="rounded-md border border-border bg-surface-2 px-3 py-2.5 text-sm text-foreground">
          <p className="mb-0.5 text-xs font-medium text-muted-foreground">
            Note from {share.from_username}
          </p>
          <p>"{share.note}"</p>
        </div>
      ) : null}

      {/* AI context summary */}
      {share.context_summary ? (
        <div className="rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-foreground">
          <div className="flex items-center gap-1.5 mb-1 text-xs font-medium text-muted-foreground">
            <Sparkles className="size-3.5" />
            Why this is relevant to you
          </div>
          <p>{share.context_summary}</p>
        </div>
      ) : null}

      {/* Annotations */}
      {share.annotations && share.annotations.length > 0 ? (
        <div>
          <div className="flex items-center gap-1.5 mb-2 text-xs font-medium text-muted-foreground">
            <Highlighter className="size-3.5" />
            Highlights
          </div>
          <ul className="space-y-2">
            {share.annotations.map((ann) => (
              <li key={ann.id} className="rounded-md border border-border bg-surface px-3 py-2">
                <p className="text-sm text-foreground border-l-2 border-accent-foreground pl-2">
                  "{ann.highlighted_text}"
                </p>
                {ann.note ? <p className="mt-1 text-xs text-muted-foreground">{ann.note}</p> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Message thread */}
      <div>
        <div className="flex items-center gap-1.5 mb-2 text-xs font-medium text-muted-foreground">
          <MessageSquare className="size-3.5" />
          Discussion
        </div>

        {share.messages && share.messages.length > 0 ? (
          <ul className="space-y-2 mb-3">
            {share.messages.map((msg) => {
              const isMe = user?.username === msg.username;
              return (
                <li
                  key={msg.id}
                  className={`rounded-md border border-border px-3 py-2 text-sm ${isMe ? 'bg-surface-2' : 'bg-surface'}`}
                >
                  <div className="flex items-center gap-1.5 mb-0.5 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">{msg.username}</span>
                    <span>· {relativeTime(msg.created_at)}</span>
                  </div>
                  <p className="text-foreground">{msg.message}</p>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground mb-3">
            No messages yet. Start the conversation.
          </p>
        )}

        {/* Compose */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-2">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a message…"
            rows={2}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-1 focus:ring-ring"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                handleSubmit(e);
              }
            }}
          />
          <div className="flex items-center justify-between">
            {mutation.isError ? (
              <p className="text-xs text-destructive">
                {mutation.error instanceof Error
                  ? mutation.error.message
                  : 'Failed to send message.'}
              </p>
            ) : (
              <span className="text-xs text-muted-foreground">⌘↵ to send</span>
            )}
            <button
              type="submit"
              disabled={!draft.trim() || mutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity disabled:opacity-50"
            >
              <Send className="size-3" />
              {mutation.isPending ? 'Sending…' : 'Send'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
