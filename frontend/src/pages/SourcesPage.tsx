import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Sparkles,
  Trash2,
  Wand2,
  Plus,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import {
  applySourceCleanup,
  createSource,
  deleteSource,
  fetchSourceCleanupSuggestions,
  fetchSources,
  updateSourceEnabled,
} from '@/api';
import { relativeTime } from '@/lib/format';
import type { Source, SourceCleanupSuggestion } from '@/types';
import { OnboardingWizard } from '@/components/OnboardingWizard';
import { useAuth } from '@/contexts/auth';

type HealthState = 'ok' | 'stale' | 'error';

function isSourceOn(s: Source): boolean {
  return s.owner_user_id == null ? (s.subscribed ?? !!s.enabled) : !!s.enabled;
}

function computeHealth(s: Source): HealthState {
  if (s.last_error) return 'error';
  const ref = s.last_success_at ?? s.last_checked_at;
  if (!ref) return 'stale';
  const hours = (Date.now() - new Date(ref).getTime()) / 3_600_000;
  return hours > 48 ? 'stale' : 'ok';
}

function kindLabel(kind: string): string {
  switch (kind) {
    case 'rss_feed':
      return 'RSS';
    case 'github_release_feed':
      return 'GitHub';
    case 'trending_feed':
      return 'Trending';
    case 'scraped_page':
      return 'Scraped';
    case 'reddit_feed':
      return 'Reddit';
    case 'lobsters_feed':
      return 'Lobsters';
    case 'mastodon_feed':
      return 'Mastodon';
    default:
      return kind;
  }
}

function HealthBadge({ health }: { health: HealthState }) {
  const cfg = {
    ok: { Icon: CheckCircle2, label: 'ok', cls: 'text-[color:var(--ok)]' },
    stale: { Icon: AlertTriangle, label: 'stale', cls: 'text-[color:var(--warn)]' },
    error: { Icon: AlertCircle, label: 'error', cls: 'text-[color:var(--err)]' },
  }[health];
  const { Icon } = cfg;
  return (
    <span className={cn('inline-flex items-center gap-1 text-[11px] font-medium', cfg.cls)}>
      <Icon className="size-3.5" />
      {cfg.label}
    </span>
  );
}

const SOURCES_KEY = 'sources';
const SOURCE_CLEANUP_KEY = 'source-cleanup-suggestions';

function formatSuggestionMeta(suggestion: SourceCleanupSuggestion): string {
  if (suggestion.reason === 'stale') return 'No articles in 30 days';
  return `${Math.round(suggestion.skip_rate * 100)}% skipped · ${suggestion.articles_last_30_days} articles`;
}

interface AddSourceFormState {
  name: string;
  url: string;
  category: string;
  slug: string;
  kind: string;
}

const EMPTY_FORM: AddSourceFormState = {
  name: '',
  url: '',
  category: 'tech',
  slug: '',
  kind: 'rss_feed',
};

function AddSourceDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState<AddSourceFormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createSource({
        name: form.name,
        url: form.url,
        category: form.category || 'tech',
        slug: form.slug || undefined,
        kind: form.kind,
      }),
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setError(null);
      onCreated();
      onClose();
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    mutation.mutate();
  }

  function handleClose() {
    setForm(EMPTY_FORM);
    setError(null);
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add private source</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3 pt-1">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="src-kind">
              Kind
            </label>
            <select
              id="src-kind"
              value={form.kind}
              onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value }))}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-base shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm"
            >
              <option value="rss_feed">RSS Feed</option>
              <option value="reddit_feed">Reddit</option>
              <option value="lobsters_feed">Lobsters</option>
              <option value="mastodon_feed">Mastodon</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="src-name">
              Name
            </label>
            <Input
              id="src-name"
              placeholder="My Blog"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="src-url">
              Feed URL
            </label>
            <Input
              id="src-url"
              type="url"
              placeholder="https://example.com/feed.xml"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="src-category">
                Category
              </label>
              <Input
                id="src-category"
                placeholder="tech"
                value={form.category}
                onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="src-slug">
                Slug (optional)
              </label>
              <Input
                id="src-slug"
                placeholder="my-blog"
                value={form.slug}
                onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
              />
            </div>
          </div>
          {error && <p className="text-xs text-[color:var(--err)]">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" size="sm" onClick={handleClose}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={mutation.isPending}>
              {mutation.isPending ? 'Adding…' : 'Add source'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function SourcesPage() {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const qc = useQueryClient();
  const { user } = useAuth();
  const { data: sources = [], isLoading } = useQuery({
    queryKey: [SOURCES_KEY],
    queryFn: fetchSources,
  });
  const { data: cleanupSuggestions = [] } = useQuery({
    queryKey: [SOURCE_CLEANUP_KEY],
    queryFn: fetchSourceCleanupSuggestions,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ slug, enabled }: { slug: string; enabled: boolean }) =>
      updateSourceEnabled(slug, enabled),
    onMutate: async ({ slug, enabled }) => {
      await qc.cancelQueries({ queryKey: [SOURCES_KEY] });
      const prev = qc.getQueryData<Source[]>([SOURCES_KEY]);
      qc.setQueryData<Source[]>([SOURCES_KEY], (old = []) =>
        old.map((s) => {
          if (s.slug !== slug) return s;
          const isGlobal = s.owner_user_id == null;
          return isGlobal
            ? { ...s, subscribed: enabled, enabled: enabled ? 1 : 0 }
            : { ...s, enabled: enabled ? 1 : 0 };
        })
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData([SOURCES_KEY], ctx.prev);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: [SOURCES_KEY] });
    },
  });
  const cleanupMutation = useMutation({
    mutationFn: (sourceSlug: string) => applySourceCleanup([sourceSlug]),
    onMutate: async (sourceSlug) => {
      await Promise.all([
        qc.cancelQueries({ queryKey: [SOURCES_KEY] }),
        qc.cancelQueries({ queryKey: [SOURCE_CLEANUP_KEY] }),
      ]);
      const prevSources = qc.getQueryData<Source[]>([SOURCES_KEY]);
      const prevSuggestions = qc.getQueryData<SourceCleanupSuggestion[]>([SOURCE_CLEANUP_KEY]);
      qc.setQueryData<Source[]>([SOURCES_KEY], (old = []) =>
        old.map((s) => (s.slug === sourceSlug ? { ...s, enabled: 0, subscribed: false } : s))
      );
      qc.setQueryData<SourceCleanupSuggestion[]>([SOURCE_CLEANUP_KEY], (old = []) =>
        old.filter((s) => s.source_slug !== sourceSlug)
      );
      return { prevSources, prevSuggestions };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prevSources) qc.setQueryData([SOURCES_KEY], ctx.prevSources);
      if (ctx?.prevSuggestions) qc.setQueryData([SOURCE_CLEANUP_KEY], ctx.prevSuggestions);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: [SOURCES_KEY] });
      void qc.invalidateQueries({ queryKey: [SOURCE_CLEANUP_KEY] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (slug: string) => deleteSource(slug),
    onMutate: async (slug) => {
      await qc.cancelQueries({ queryKey: [SOURCES_KEY] });
      const prev = qc.getQueryData<Source[]>([SOURCES_KEY]);
      qc.setQueryData<Source[]>([SOURCES_KEY], (old = []) => old.filter((s) => s.slug !== slug));
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData([SOURCES_KEY], ctx.prev);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: [SOURCES_KEY] });
    },
  });

  if (isLoading) {
    return (
      <div className="px-4 md:px-5 py-6 space-y-2">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="h-9 rounded bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div>
      <section className="border-b border-border px-4 py-3 md:px-5 flex items-center justify-between gap-2">
        <span className="text-sm text-muted-foreground">Manage your feed subscriptions</span>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
            <Plus className="size-4" />
            Add source
          </Button>
          <Button size="sm" variant="outline" onClick={() => setWizardOpen(true)}>
            <Wand2 className="size-4" />
            Personalize
          </Button>
        </div>
      </section>
      <AddSourceDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={() => void qc.invalidateQueries({ queryKey: [SOURCES_KEY] })}
      />
      <OnboardingWizard
        open={wizardOpen}
        onClose={() => {
          setWizardOpen(false);
          void qc.invalidateQueries({ queryKey: [SOURCES_KEY] });
        }}
      />
      {cleanupSuggestions.length > 0 && (
        <section className="border-b border-border bg-muted/25 px-4 py-4 md:px-5">
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Sparkles className="size-4 text-primary" />
              <span>Subscription Optimizer</span>
            </div>
            <div className="grid gap-2 lg:grid-cols-2">
              {cleanupSuggestions.map((suggestion) => (
                <div
                  key={suggestion.source_slug}
                  className="flex flex-col gap-3 rounded-md border border-border bg-background p-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{suggestion.message}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {formatSuggestionMeta(suggestion)}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => cleanupMutation.mutate(suggestion.source_slug)}
                    disabled={cleanupMutation.isPending}
                  >
                    <Trash2 className="size-4" />
                    Apply Cleanup
                  </Button>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border">
              <th className="px-5 py-2 font-medium">Source</th>
              <th className="px-3 py-2 font-medium">Kind</th>
              <th className="px-3 py-2 font-medium">Category</th>
              <th className="px-3 py-2 font-medium">Health</th>
              <th className="px-3 py-2 font-medium">Last checked</th>
              <th className="px-3 py-2 font-medium">Last success</th>
              <th className="px-3 py-2 font-medium text-right">Items (run)</th>
              <th className="px-3 py-2 font-medium text-right">On</th>
              <th className="px-3 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => {
              const isOwned = user != null && s.owner_user_id === user.id;
              return (
                <tr key={s.slug} className="border-b border-border hover:bg-muted/30">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{s.name}</span>
                      {isOwned && (
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                          mine
                        </span>
                      )}
                    </div>
                    {s.last_error && (
                      <div
                        className="text-[11px] text-[color:var(--err)] mt-0.5 max-w-xs truncate"
                        title={s.last_error}
                      >
                        {s.last_error}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3 text-muted-foreground">{kindLabel(s.kind)}</td>
                  <td className="px-3 py-3 text-muted-foreground">{s.category}</td>
                  <td className="px-3 py-3">
                    <HealthBadge health={computeHealth(s)} />
                  </td>
                  <td className="px-3 py-3 text-muted-foreground">
                    {s.last_checked_at ? relativeTime(s.last_checked_at) : '—'}
                  </td>
                  <td className="px-3 py-3 text-muted-foreground">
                    {s.last_success_at ? relativeTime(s.last_success_at) : '—'}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-muted-foreground">
                    {s.last_inserted_count ?? 0}/{s.last_fetched_count ?? 0}
                  </td>
                  <td className="px-3 py-3 text-right">
                    <Switch
                      checked={isSourceOn(s)}
                      onCheckedChange={(checked) =>
                        toggleMutation.mutate({ slug: s.slug, enabled: checked })
                      }
                      aria-label={`Toggle ${s.name}`}
                    />
                  </td>
                  <td className="px-3 py-3 text-right">
                    {isOwned && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-[color:var(--err)] hover:text-[color:var(--err)]"
                        onClick={() => deleteMutation.mutate(s.slug)}
                        disabled={deleteMutation.isPending}
                        aria-label={`Delete ${s.name}`}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* mobile cards */}
      <div className="md:hidden">
        {sources.map((s) => {
          const isOwned = user != null && s.owner_user_id === user.id;
          return (
            <div key={s.slug} className="px-4 py-3 border-b border-border">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium truncate">{s.name}</span>
                    {isOwned && (
                      <span className="text-[10px] font-medium px-1 py-0.5 rounded bg-primary/10 text-primary shrink-0">
                        mine
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">
                    {kindLabel(s.kind)} · {s.category}
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {isOwned && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-[color:var(--err)] hover:text-[color:var(--err)] h-8 w-8 p-0"
                      onClick={() => deleteMutation.mutate(s.slug)}
                      disabled={deleteMutation.isPending}
                      aria-label={`Delete ${s.name}`}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  )}
                  <Switch
                    checked={isSourceOn(s)}
                    onCheckedChange={(checked) =>
                      toggleMutation.mutate({ slug: s.slug, enabled: checked })
                    }
                    aria-label={`Toggle ${s.name}`}
                  />
                </div>
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px]">
                <HealthBadge health={computeHealth(s)} />
                <span className="text-muted-foreground">
                  {s.last_checked_at ? relativeTime(s.last_checked_at) : '—'} ·{' '}
                  {s.last_inserted_count ?? 0}/{s.last_fetched_count ?? 0}
                </span>
              </div>
              {s.last_error && (
                <div
                  className="mt-1 text-[11px] text-[color:var(--err)] truncate"
                  title={s.last_error}
                >
                  {s.last_error}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
