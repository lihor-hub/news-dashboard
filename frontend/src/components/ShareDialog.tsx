import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Send, Share, Users, Loader2, Search } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchShareableUsers, shareArticle } from '@/api';

export interface ShareTarget {
  id: number;
  title: string;
  url: string;
}

interface ShareDialogProps {
  article: ShareTarget | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type Mode = 'choose' | 'internal';

/**
 * Two-step share flow:
 *   1. Choose between sharing to another platform user (internal) or via the
 *      OS share sheet / clipboard (external).
 *   2. For internal, pick a recipient and optionally add a note.
 */
export function ShareDialog({ article, open, onOpenChange }: ShareDialogProps) {
  const [mode, setMode] = useState<Mode>('choose');
  const [query, setQuery] = useState('');
  const [note, setNote] = useState('');
  const [sendingTo, setSendingTo] = useState<number | null>(null);

  function reset() {
    setMode('choose');
    setQuery('');
    setNote('');
    setSendingTo(null);
  }

  function close() {
    onOpenChange(false);
  }

  const usersQuery = useQuery({
    queryKey: ['shareable-users'],
    queryFn: fetchShareableUsers,
    enabled: open && mode === 'internal',
    staleTime: 60_000,
  });

  async function handleExternal() {
    if (!article) return;
    const shareData = { title: article.title, url: article.url };
    if (navigator.share) {
      try {
        await navigator.share(shareData);
      } catch (err) {
        // User cancelling the share sheet rejects with AbortError — stay quiet.
        if ((err as Error).name !== 'AbortError') {
          toast.error('Could not open the share sheet');
        }
        return;
      }
    } else {
      await navigator.clipboard.writeText(article.url);
      toast('Link copied!');
    }
    close();
  }

  async function handleSendTo(userId: number, username: string) {
    if (!article) return;
    setSendingTo(userId);
    try {
      await shareArticle(article.id, userId, note);
      toast.success(`Sent to ${username}`);
      close();
    } catch {
      toast.error('Could not share the article');
    } finally {
      setSendingTo(null);
    }
  }

  const users = usersQuery.data ?? [];
  const filtered = query
    ? users.filter((u) => u.username.toLowerCase().includes(query.toLowerCase()))
    : users;

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Share article</DialogTitle>
          <DialogDescription className="line-clamp-2">{article?.title}</DialogDescription>
        </DialogHeader>

        {mode === 'choose' ? (
          <div className="mt-1 flex flex-col gap-2">
            <Button
              variant="outline"
              className="h-auto justify-start gap-3 py-3"
              onClick={() => setMode('internal')}
            >
              <Users className="h-5 w-5 shrink-0" />
              <span className="flex flex-col items-start text-left">
                <span className="font-medium">Send inside the platform</span>
                <span className="text-xs text-muted-foreground">
                  Deliver to another user's inbox
                </span>
              </span>
            </Button>
            <Button
              variant="outline"
              className="h-auto justify-start gap-3 py-3"
              onClick={() => void handleExternal()}
            >
              <Share className="h-5 w-5 shrink-0" />
              <span className="flex flex-col items-start text-left">
                <span className="font-medium">Share externally</span>
                <span className="text-xs text-muted-foreground">
                  Open your apps, or copy the link
                </span>
              </span>
            </Button>
          </div>
        ) : (
          <div className="mt-1 flex flex-col gap-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                autoFocus
                placeholder="Search people…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="pl-8"
              />
            </div>
            <Input
              placeholder="Add a note (optional)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
            />
            <div className="max-h-56 overflow-y-auto rounded-md border border-border">
              {usersQuery.isLoading ? (
                <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> Loading people…
                </div>
              ) : filtered.length === 0 ? (
                <div className="py-6 text-center text-sm text-muted-foreground">
                  {users.length === 0 ? 'No other users yet.' : 'No matches.'}
                </div>
              ) : (
                <ul className="divide-y divide-border">
                  {filtered.map((u) => (
                    <li key={u.id}>
                      <button
                        type="button"
                        disabled={sendingTo !== null}
                        onClick={() => void handleSendTo(u.id, u.username)}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm hover:bg-accent disabled:opacity-50"
                      >
                        <span className="flex min-w-0 flex-col">
                          <span className="truncate font-medium">{u.username}</span>
                          {u.email ? (
                            <span className="truncate text-xs text-muted-foreground">
                              {u.email}
                            </span>
                          ) : null}
                        </span>
                        {sendingTo === u.id ? (
                          <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                        ) : (
                          <Send className="h-4 w-4 shrink-0 text-muted-foreground" />
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="self-start"
              onClick={() => setMode('choose')}
            >
              ← Back
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
