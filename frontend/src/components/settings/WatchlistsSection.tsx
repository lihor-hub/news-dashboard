import { useEffect, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import {
  createWatchlist,
  deleteWatchlist,
  fetchWatchlists,
  previewWatchlist,
  updateWatchlist,
} from '@/api';
import type { AiWatchlist, AiWatchlistMatch } from '@/types';

export function WatchlistsSection() {
  const [watchlists, setWatchlists] = useState<AiWatchlist[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [label, setLabel] = useState('');
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<AiWatchlistMatch[] | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const load = async () => {
    try {
      setWatchlists(await fetchWatchlists());
    } catch {
      // keep whatever we had; the section stays usable
    } finally {
      setLoaded(true);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handlePreview = async () => {
    if (!query.trim()) return;
    setPreviewLoading(true);
    setError(null);
    try {
      setPreview(await previewWatchlist(query.trim()));
    } catch {
      setError("Couldn't preview matches. Try again.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!label.trim() || !query.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await createWatchlist({ label: label.trim(), query: query.trim() });
      setLabel('');
      setQuery('');
      setPreview(null);
      await load();
    } catch {
      setError("Couldn't create watchlist. Try again.");
    } finally {
      setCreating(false);
    }
  };

  const handleToggle = async (watchlist: AiWatchlist) => {
    setWatchlists((prev) =>
      prev.map((w) => (w.id === watchlist.id ? { ...w, enabled: !w.enabled } : w))
    );
    try {
      await updateWatchlist(watchlist.id, { enabled: !watchlist.enabled });
    } catch {
      await load(); // resync on failure
    }
  };

  const handleDelete = async (watchlistId: number) => {
    setWatchlists((prev) => prev.filter((w) => w.id !== watchlistId));
    try {
      await deleteWatchlist(watchlistId);
    } catch {
      await load(); // resync on failure
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        AI Watchlists
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <p className="text-xs text-muted-foreground">
          Describe a topic or goal and get notified when a new article matches it. Matching runs in
          the background — it never stars or archives articles for you.
        </p>

        {loaded && watchlists.length > 0 && (
          <ul className="space-y-2">
            {watchlists.map((w) => (
              <li
                key={w.id}
                className="flex items-center justify-between gap-2 rounded-md border border-border bg-surface px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate">{w.label}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{w.query}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Switch checked={w.enabled} onCheckedChange={() => void handleToggle(w)} />
                  <button
                    onClick={() => void handleDelete(w.id)}
                    aria-label={`Delete watchlist ${w.label}`}
                    className="text-muted-foreground hover:text-destructive transition-colors"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="space-y-2 pt-1">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label, e.g. AI safety"
            maxLength={120}
            className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs"
          />
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="What should this watch for? e.g. artificial intelligence safety research"
            maxLength={500}
            rows={2}
            className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs resize-none"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={() => void handlePreview()}
              disabled={previewLoading || !query.trim()}
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-medium hover:bg-surface-2 transition-colors disabled:opacity-60"
            >
              {previewLoading ? 'Previewing…' : 'Preview matches'}
            </button>
            <button
              onClick={() => void handleCreate()}
              disabled={creating || !label.trim() || !query.trim()}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
            >
              {creating ? 'Adding…' : 'Add watchlist'}
            </button>
          </div>
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        {preview && (
          <div className="space-y-1.5 pt-1">
            <div className="text-[11px] text-muted-foreground">
              {preview.length === 0
                ? 'No recent articles match yet.'
                : `${preview.length} recent match${preview.length === 1 ? '' : 'es'}:`}
            </div>
            {preview.map((m) => (
              <div key={m.article.id} className="text-xs rounded-md bg-surface px-2.5 py-1.5">
                <div className="font-medium truncate">{m.article.title}</div>
                <div className="text-[11px] text-muted-foreground truncate">{m.explanation}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
