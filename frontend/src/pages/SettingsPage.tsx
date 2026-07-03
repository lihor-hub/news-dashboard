import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sun,
  Moon,
  Monitor,
  RefreshCw,
  Download,
  RotateCcw,
  ExternalLink,
  Sparkles,
  Bell,
  BellOff,
  Brain,
  Pencil,
  Trash2,
} from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTheme } from '@/hooks/useTheme';
import { cn } from '@/lib/utils';
import { Switch } from '@/components/ui/switch';
import type { Theme } from '@/lib/theme';
import { useUpdateCheck } from '@/hooks/useUpdateCheck';
import { useAuth } from '@/contexts/auth';
import { setAnalyticsAllowed, startAnalytics, stopAnalytics } from '@/lib/analytics';
import {
  createWatchlist,
  deleteOwnAccount,
  deleteWatchlist,
  downloadUserExport,
  createAiMemory,
  createMcpToken,
  deactivateAiMemory,
  fetchAiMemories,
  fetchAnalyticsSettings,
  fetchMcpTokens,
  fetchNotificationSettings,
  fetchWatchlists,
  previewWatchlist,
  learnAiMemoriesFromReading,
  recalculateMyRecommendations,
  revokeMcpToken,
  subscribePush,
  unsubscribePush,
  updateAiMemory,
  updateAnalyticsSettings,
  updateNotificationSettings,
  updateWatchlist,
} from '@/api';
import type { AiWatchlist, AiWatchlistMatch } from '@/types';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';
import type { AiMemory, McpToken } from '@/types';

const THEME_OPTS: { v: Theme; label: string; Icon: React.ComponentType<{ className?: string }> }[] =
  [
    { v: 'light', label: 'Light', Icon: Sun },
    { v: 'dark', label: 'Dark', Icon: Moon },
    { v: 'system', label: 'System', Icon: Monitor },
  ];

function UpdatesSection() {
  const {
    platform,
    info,
    loading,
    error,
    check,
    electronStage,
    downloadPercent,
    electronLatestVersion,
    checkElectron,
    downloadElectronUpdate,
    installElectronUpdate,
  } = useUpdateCheck();

  // On Electron: wire IPC and kick off the auto-updater check immediately.
  useEffect(() => {
    if (platform === 'electron') {
      checkElectron();
      return () => window.electronAPI?.removeUpdateListeners();
    }
  }, [platform, checkElectron]);

  const sectionLabel = (
    <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">Updates</div>
  );

  // ── Electron ──────────────────────────────────────────────────────────────
  if (platform === 'electron') {
    const appVersion = window.electronAPI?.appVersion ?? '…';

    return (
      <section>
        {sectionLabel}
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Current version</span>
            <span className="tabular-nums font-mono text-xs">{appVersion}</span>
          </div>

          {electronStage === 'idle' && (
            <p className="text-xs text-muted-foreground">Checking for updates…</p>
          )}

          {electronStage === 'checking' && (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <RefreshCw className="size-3 animate-spin" />
              Checking for updates…
            </p>
          )}

          {electronStage === 'up-to-date' && (
            <p className="text-xs text-green-600 dark:text-green-400">
              You're on the latest version.
            </p>
          )}

          {electronStage === 'available' && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Version <span className="font-mono">{electronLatestVersion}</span> is available.
              </p>
              <button
                onClick={downloadElectronUpdate}
                className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <Download className="size-3" />
                Download update
              </button>
            </div>
          )}

          {electronStage === 'downloading' && (
            <div className="space-y-1.5">
              <p className="text-xs text-muted-foreground">Downloading… {downloadPercent}%</p>
              <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${downloadPercent}%` }}
                />
              </div>
            </div>
          )}

          {electronStage === 'ready' && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">Update downloaded. Restart to apply.</p>
              <button
                onClick={installElectronUpdate}
                className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <RotateCcw className="size-3" />
                Restart and install
              </button>
            </div>
          )}

          {electronStage === 'error' && (
            <div className="space-y-2">
              <p className="text-xs text-destructive">{error ?? 'Update check failed.'}</p>
              <button
                onClick={checkElectron}
                className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Try again
              </button>
            </div>
          )}
        </div>
      </section>
    );
  }

  // ── Android TWA ───────────────────────────────────────────────────────────
  if (platform === 'twa') {
    return (
      <section>
        {sectionLabel}
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          {info && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">App version</span>
              <span className="tabular-nums font-mono text-xs">
                {info.installedVersionKnown ? info.currentVersion : 'Unknown'}
              </span>
            </div>
          )}

          {!info && !loading && (
            <button
              onClick={() => void check()}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
              <RefreshCw className="size-3" />
              Check for updates
            </button>
          )}

          {loading && (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <RefreshCw className="size-3 animate-spin" />
              Checking…
            </p>
          )}

          {error && <p className="text-xs text-destructive">{error}</p>}

          {info && !loading && (
            <div className="space-y-2">
              {info.apkUrl ? (
                <>
                  <p className="text-xs text-muted-foreground">
                    Version <span className="font-mono">{info.latestVersion}</span> is available for
                    download.
                  </p>
                  <div className="space-y-1.5">
                    <a
                      href={info.apkUrl}
                      className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors w-fit"
                    >
                      <Download className="size-3" />
                      Download APK
                    </a>
                    <p className="text-[11px] text-subtle">
                      Android will prompt you to confirm the install — tap Install when it appears.
                    </p>
                  </div>
                </>
              ) : (
                <a
                  href={info.releaseUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs text-primary hover:underline"
                >
                  <ExternalLink className="size-3" />
                  View Android releases
                </a>
              )}
            </div>
          )}

          {info && (
            <button
              onClick={() => void check()}
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Check again
            </button>
          )}
        </div>
      </section>
    );
  }

  // ── Web / PWA ─────────────────────────────────────────────────────────────
  return (
    <section>
      {sectionLabel}
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        {info && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Version</span>
            <span className="tabular-nums font-mono text-xs">{info.currentVersion}</span>
          </div>
        )}

        {!info && !loading && (
          <button
            onClick={() => void check()}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            <RefreshCw className="size-3" />
            Check version
          </button>
        )}

        {loading && (
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            <RefreshCw className="size-3 animate-spin" />
            Loading…
          </p>
        )}

        {error && <p className="text-xs text-destructive">{error}</p>}

        {info && (
          <>
            <p className="text-xs text-muted-foreground">
              The web app is always current — the live site updates automatically on each release.
            </p>
            <a
              href={`https://github.com/${info.releaseUrl.split('github.com/')[1]?.split('/releases')[0] ?? 'lihor-hub/news-dashboard'}/releases`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-primary hover:underline w-fit"
            >
              <ExternalLink className="size-3" />
              Release history
            </a>
          </>
        )}
      </div>
    </section>
  );
}

type RecalcState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'done'; scored: number }
  | { status: 'error' };

function PersonalizationSection() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<RecalcState>({ status: 'idle' });

  const recalculate = async () => {
    setState({ status: 'running' });
    try {
      const { scored } = await recalculateMyRecommendations();
      setState({ status: 'done', scored });
      // Invalidate cached article data so recommendation scores refresh on next render.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: [ARTICLES_KEY] }),
        queryClient.invalidateQueries({ queryKey: ['article'] }),
      ]);
    } catch {
      setState({ status: 'error' });
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Personalization
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <p className="text-xs text-muted-foreground">
          Recommendations are learned from articles you star, read, or skip. Refresh to recompute
          your personalized scores now.
        </p>
        <button
          onClick={() => void recalculate()}
          disabled={state.status === 'running'}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
        >
          {state.status === 'running' ? (
            <RefreshCw className="size-3 animate-spin" />
          ) : (
            <Sparkles className="size-3" />
          )}
          {state.status === 'running' ? 'Refreshing…' : 'Refresh recommendations'}
        </button>

        {state.status === 'done' && state.scored > 0 && (
          <p className="text-xs text-green-600 dark:text-green-400">
            Personalized {state.scored} {state.scored === 1 ? 'article' : 'articles'}. Your feed is
            up to date.
          </p>
        )}
        {state.status === 'done' && state.scored === 0 && (
          <p className="text-xs text-muted-foreground">
            Nothing to personalize yet — star, read, or skip a few articles first, then refresh.
          </p>
        )}
        {state.status === 'error' && (
          <p className="text-xs text-destructive">Couldn't refresh recommendations. Try again.</p>
        )}
      </div>
    </section>
  );
}

function WatchlistsSection() {
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

type MemoryState = 'idle' | 'loading' | 'saving' | 'learning' | 'error';

function AiMemorySection() {
  const [memories, setMemories] = useState<AiMemory[]>([]);
  const [newContent, setNewContent] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [state, setState] = useState<MemoryState>('loading');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setState('loading');
      try {
        const loaded = await fetchAiMemories();
        if (!cancelled) {
          setMemories(loaded);
          setState('idle');
        }
      } catch {
        if (!cancelled) setState('error');
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const activeMemories = memories.filter((memory) => memory.active);

  const create = async () => {
    const content = newContent.trim();
    if (!content) return;
    setState('saving');
    try {
      const memory = await createAiMemory(content);
      setMemories((current) => [memory, ...current]);
      setNewContent('');
      setState('idle');
    } catch {
      setState('error');
    }
  };

  const learn = async () => {
    setState('learning');
    try {
      const learned = await learnAiMemoriesFromReading();
      setMemories((current) => [...learned, ...current]);
      setState('idle');
    } catch {
      setState('error');
    }
  };

  const saveEdit = async (memoryId: number) => {
    const content = editingContent.trim();
    if (!content) return;
    setState('saving');
    try {
      const updated = await updateAiMemory(memoryId, { content });
      setMemories((current) =>
        current.map((memory) => (memory.id === memoryId ? updated : memory))
      );
      setEditingId(null);
      setEditingContent('');
      setState('idle');
    } catch {
      setState('error');
    }
  };

  const deactivate = async (memoryId: number) => {
    setState('saving');
    try {
      const updated = await deactivateAiMemory(memoryId);
      setMemories((current) =>
        current.map((memory) => (memory.id === memoryId ? updated : memory))
      );
      setState('idle');
    } catch {
      setState('error');
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        AI Memory
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <div className="flex gap-2">
          <input
            value={newContent}
            onChange={(event) => setNewContent(event.target.value)}
            placeholder="Remember a preference or goal"
            aria-label="New AI memory"
            className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <button
            onClick={() => void create()}
            disabled={state === 'saving' || !newContent.trim()}
            className="flex shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
          >
            {state === 'saving' ? (
              <RefreshCw className="size-3 animate-spin" />
            ) : (
              <Brain className="size-3" />
            )}
            Add
          </button>
        </div>

        <button
          onClick={() => void learn()}
          disabled={state === 'learning'}
          className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-surface transition-colors disabled:opacity-60"
        >
          {state === 'learning' ? (
            <RefreshCw className="size-3 animate-spin" />
          ) : (
            <Sparkles className="size-3" />
          )}
          Learn from recent reading
        </button>

        {state === 'loading' && (
          <p className="text-xs text-muted-foreground">Loading memories...</p>
        )}
        {state === 'error' && (
          <p className="text-xs text-destructive" role="alert">
            Could not update AI memory.
          </p>
        )}

        <div className="space-y-2">
          {activeMemories.map((memory) => (
            <div key={memory.id} className="rounded-md border border-border bg-surface p-3">
              {editingId === memory.id ? (
                <div className="space-y-2">
                  <textarea
                    value={editingContent}
                    onChange={(event) => setEditingContent(event.target.value)}
                    aria-label="AI memory content"
                    className="min-h-20 w-full rounded-md border border-border bg-card px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => void saveEdit(memory.id)}
                      className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <p className="break-words text-sm text-foreground">{memory.content}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {memory.memory_type} / {memory.source} / {Math.round(memory.confidence * 100)}
                      %
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      onClick={() => {
                        setEditingId(memory.id);
                        setEditingContent(memory.content);
                      }}
                      aria-label="Edit AI memory"
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-card hover:text-foreground"
                    >
                      <Pencil className="size-3.5" />
                    </button>
                    <button
                      onClick={() => void deactivate(memory.id)}
                      aria-label="Deactivate AI memory"
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-card hover:text-destructive"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
          {state !== 'loading' && activeMemories.length === 0 && (
            <p className="text-xs text-muted-foreground">No active memories yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}

function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return new Uint8Array([...raw].map((c) => c.charCodeAt(0)));
}

function arrayBufferToBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const standard = btoa(String.fromCharCode(...bytes));
  return standard.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

type PushState = 'idle' | 'requesting' | 'subscribed' | 'denied' | 'unavailable' | 'error';
type TimezoneSaveState = 'idle' | 'saving' | 'saved' | 'error';

const FALLBACK_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Bucharest',
  'Asia/Tokyo',
  'Australia/Sydney',
];

function getSupportedTimezones(): string[] {
  const intlWithSupportedValues = Intl as typeof Intl & {
    supportedValuesOf?: (key: 'timeZone') => string[];
  };
  return intlWithSupportedValues.supportedValuesOf?.('timeZone') ?? FALLBACK_TIMEZONES;
}

function DailyBriefSection() {
  const [briefingTime, setBriefingTime] = useState('09:00');
  const [briefingTimezone, setBriefingTimezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone
  );
  const [savedBriefingTimezone, setSavedBriefingTimezone] = useState(briefingTimezone);
  const [timezoneSaveState, setTimezoneSaveState] = useState<TimezoneSaveState>('idle');
  const [timezoneError, setTimezoneError] = useState<string | null>(null);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [vapidKey, setVapidKey] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [timeSaving, setTimeSaving] = useState(false);
  const [pushState, setPushState] = useState<PushState>('idle');
  const [supportedTimezones] = useState(getSupportedTimezones);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await fetchNotificationSettings();
        if (!cancelled) {
          setBriefingTime(s.briefing_time);
          const loadedTimezone =
            s.briefing_timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
          setBriefingTimezone(loadedTimezone);
          setSavedBriefingTimezone(loadedTimezone);
          setPushEnabled(s.push_enabled);
          setVapidKey(s.vapid_public_key);
          if (s.push_enabled) setPushState('subscribed');
        }
      } catch {
        // keep defaults if settings fail to load
      } finally {
        if (!cancelled) setLoaded(true);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleTimeBlur = async (t: string) => {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(t)) return;
    setTimeSaving(true);
    try {
      await updateNotificationSettings({ briefing_time: t });
    } catch {
      // non-critical — time preference will resync on next load
    } finally {
      setTimeSaving(false);
    }
  };

  const handleTimezoneBlur = async (tz: string) => {
    const normalizedTimezone = tz.trim();
    if (!normalizedTimezone) return;
    if (normalizedTimezone === savedBriefingTimezone) {
      setTimezoneSaveState('idle');
      setTimezoneError(null);
      return;
    }
    setBriefingTimezone(normalizedTimezone);
    setTimezoneSaveState('saving');
    setTimezoneError(null);
    try {
      await updateNotificationSettings({ briefing_timezone: normalizedTimezone });
      setSavedBriefingTimezone(normalizedTimezone);
      setTimezoneSaveState('saved');
    } catch {
      setTimezoneSaveState('error');
      setTimezoneError('Unknown timezone. Choose a valid IANA timezone.');
    }
  };

  const enablePush = async () => {
    if (window.electronAPI) {
      try {
        await updateNotificationSettings({ push_enabled: true });
      } catch {
        // best-effort
      }
      setPushEnabled(true);
      setPushState('subscribed');
      return;
    }

    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      setPushState('unavailable');
      return;
    }

    setPushState('requesting');
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setPushState('denied');
        return;
      }

      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey ?? ''),
      });

      const rawKey = sub.getKey('p256dh');
      const rawAuth = sub.getKey('auth');
      if (!rawKey || !rawAuth) throw new Error('missing push keys');

      await subscribePush({
        endpoint: sub.endpoint,
        p256dh: arrayBufferToBase64Url(rawKey),
        auth: arrayBufferToBase64Url(rawAuth),
      });
      await updateNotificationSettings({ push_enabled: true });
      setPushEnabled(true);
      setPushState('subscribed');
    } catch {
      setPushState('error');
    }
  };

  const disablePush = async () => {
    let subscription: PushSubscription | null = null;
    try {
      if (!window.electronAPI && 'serviceWorker' in navigator && 'PushManager' in window) {
        const reg = await navigator.serviceWorker.ready;
        subscription = await reg.pushManager.getSubscription();
      }
      await unsubscribePush(subscription?.endpoint);
      await subscription?.unsubscribe();
    } catch {
      // best-effort
    }
    try {
      await updateNotificationSettings({ push_enabled: false });
    } catch {
      // best-effort
    }
    setPushEnabled(false);
    setPushState('idle');
  };

  const canEnablePush =
    !pushEnabled &&
    (!!window.electronAPI ||
      (!!vapidKey && 'serviceWorker' in navigator && 'PushManager' in window));
  const timezoneDescriptionIds =
    timezoneSaveState === 'saved' || timezoneError
      ? 'briefing-timezone-help briefing-timezone-status'
      : 'briefing-timezone-help';

  if (!loaded) return null;

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Daily Brief
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-foreground" htmlFor="briefing-time">
            Generation time
          </label>
          <div className="flex items-center gap-2">
            <input
              id="briefing-time"
              type="time"
              value={briefingTime}
              onChange={(e) => setBriefingTime(e.target.value)}
              onBlur={(e) => void handleTimeBlur(e.target.value)}
              className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
            />
            {timeSaving && <RefreshCw className="size-3 animate-spin text-muted-foreground" />}
          </div>
          <p className="text-[11px] text-muted-foreground">
            Your brief will be generated automatically at this local time each day.
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-foreground" htmlFor="briefing-timezone">
            Timezone
          </label>
          <div className="flex items-center gap-2">
            <input
              id="briefing-timezone"
              type="text"
              list="briefing-timezone-options"
              value={briefingTimezone}
              onChange={(e) => {
                setBriefingTimezone(e.target.value);
                setTimezoneSaveState('idle');
                setTimezoneError(null);
              }}
              onBlur={(e) => void handleTimezoneBlur(e.target.value)}
              placeholder="e.g. Europe/Bucharest"
              aria-describedby={timezoneDescriptionIds}
              aria-invalid={timezoneSaveState === 'error'}
              className={cn(
                'w-full rounded-md border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring',
                timezoneSaveState === 'error' ? 'border-destructive' : 'border-border'
              )}
            />
            {timezoneSaveState === 'saving' && (
              <RefreshCw className="size-3 shrink-0 animate-spin text-muted-foreground" />
            )}
            {timezoneSaveState === 'saved' && (
              <span
                id="briefing-timezone-status"
                className="text-xs text-green-600 dark:text-green-400"
              >
                Saved
              </span>
            )}
          </div>
          <datalist id="briefing-timezone-options">
            {supportedTimezones.map((timezone) => (
              <option key={timezone} value={timezone} />
            ))}
          </datalist>
          <p id="briefing-timezone-help" className="text-[11px] text-muted-foreground">
            IANA timezone name (e.g. America/New_York). DST is applied automatically.
          </p>
          {timezoneError && (
            <p id="briefing-timezone-status" className="text-xs text-destructive" role="alert">
              {timezoneError}
            </p>
          )}
        </div>

        <div className="space-y-2">
          <div className="text-xs font-medium text-foreground">Push notifications</div>
          {pushEnabled ? (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
                <Bell className="size-3" />
                Enabled
              </div>
              <button
                onClick={() => void disablePush()}
                className="flex items-center gap-1 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                <BellOff className="size-3" />
                Disable
              </button>
            </div>
          ) : canEnablePush ? (
            <button
              onClick={() => void enablePush()}
              disabled={pushState === 'requesting'}
              className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
            >
              {pushState === 'requesting' ? (
                <RefreshCw className="size-3 animate-spin" />
              ) : (
                <Bell className="size-3" />
              )}
              {pushState === 'requesting' ? 'Requesting…' : 'Enable push notifications'}
            </button>
          ) : !window.electronAPI &&
            (!('serviceWorker' in navigator) || !('PushManager' in window)) ? (
            <p className="text-xs text-muted-foreground">
              Push notifications are not supported in this environment.
            </p>
          ) : null}

          {pushState === 'denied' && (
            <p className="text-xs text-destructive">
              Permission denied. Allow notifications in your browser settings and try again.
            </p>
          )}
          {pushState === 'error' && (
            <p className="text-xs text-destructive">
              Could not set up push notifications. Please try again.
            </p>
          )}
          {!vapidKey && !window.electronAPI && (
            <p className="text-[11px] text-muted-foreground">
              Push notifications require server configuration (VAPID keys).
            </p>
          )}
          <p className="text-[11px] text-muted-foreground">
            You'll receive a notification when your daily brief is ready.
          </p>
        </div>
      </div>
    </section>
  );
}

const RECAP_DAYS: { value: string; label: string }[] = [
  { value: 'mon', label: 'Monday' },
  { value: 'tue', label: 'Tuesday' },
  { value: 'wed', label: 'Wednesday' },
  { value: 'thu', label: 'Thursday' },
  { value: 'fri', label: 'Friday' },
  { value: 'sat', label: 'Saturday' },
  { value: 'sun', label: 'Sunday' },
];

function WeeklyRecapSection() {
  const [recapEnabled, setRecapEnabled] = useState(true);
  const [recapDay, setRecapDay] = useState('mon');
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await fetchNotificationSettings();
        if (!cancelled) {
          setRecapEnabled(s.recap_enabled);
          setRecapDay(s.recap_day);
        }
      } catch {
        // keep defaults if settings fail to load
      } finally {
        if (!cancelled) setLoaded(true);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleEnabled = async () => {
    const next = !recapEnabled;
    setRecapEnabled(next);
    setSaving(true);
    try {
      await updateNotificationSettings({ recap_enabled: next });
    } catch {
      setRecapEnabled(!next);
    } finally {
      setSaving(false);
    }
  };

  const handleDayChange = async (day: string) => {
    setRecapDay(day);
    setSaving(true);
    try {
      await updateNotificationSettings({ recap_day: day });
    } catch {
      // non-critical — cadence preference will resync on next load
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) return null;

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Weekly Recap
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <div className="text-xs font-medium text-foreground">Send weekly recap</div>
            <p className="text-[11px] text-muted-foreground">
              A summary of your reading week, delivered via push.
            </p>
          </div>
          <Switch
            checked={recapEnabled}
            onCheckedChange={() => void toggleEnabled()}
            disabled={saving}
            aria-label="Send weekly recap"
          />
        </div>

        {recapEnabled && (
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground" htmlFor="recap-day">
              Delivery day
            </label>
            <select
              id="recap-day"
              value={recapDay}
              onChange={(e) => void handleDayChange(e.target.value)}
              className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {RECAP_DAYS.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-muted-foreground">
              Delivered at your daily brief time, in your briefing timezone.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function PrivacySection() {
  const [enabled, setEnabled] = useState(true);
  const [globalEnabled, setGlobalEnabled] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await fetchAnalyticsSettings();
        if (!cancelled) {
          setEnabled(s.enabled);
          setGlobalEnabled(s.global_enabled);
        }
      } catch {
        // keep defaults if settings fail to load
      } finally {
        if (!cancelled) setLoaded(true);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleEnabled = async () => {
    const next = !enabled;
    setEnabled(next);
    setSaving(true);
    try {
      await updateAnalyticsSettings({ enabled: next });
      setAnalyticsAllowed(next && globalEnabled);
      if (next && globalEnabled) {
        startAnalytics();
      } else {
        stopAnalytics();
      }
    } catch {
      setEnabled(!next);
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) return null;

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Privacy
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <div className="text-xs font-medium text-foreground">Usage analytics</div>
            <p className="text-[11px] text-muted-foreground">
              Lets Radar track route views, time-on-app, and article dwell time to improve your
              recommendations and reading insights.
            </p>
          </div>
          <Switch
            checked={enabled && globalEnabled}
            onCheckedChange={() => void toggleEnabled()}
            disabled={saving || !globalEnabled}
            aria-label="Usage analytics"
          />
        </div>
        {!globalEnabled && (
          <p className="text-[11px] text-muted-foreground">
            Analytics have been disabled instance-wide by the administrator.
          </p>
        )}
      </div>
    </section>
  );
}

type ExportState = 'idle' | 'running' | 'done' | 'error';

function DataExportSection() {
  const [state, setState] = useState<ExportState>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleExport = async () => {
    setState('running');
    setErrorMsg(null);
    try {
      await downloadUserExport();
      setState('done');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Export failed.');
      setState('error');
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Data Export
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <p className="text-xs text-muted-foreground">
          Download a personal archive of your reading history, starred articles, workflow state, and
          daily briefings as a JSON file.
        </p>
        <button
          onClick={() => void handleExport()}
          disabled={state === 'running'}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
        >
          {state === 'running' ? (
            <RefreshCw className="size-3 animate-spin" />
          ) : (
            <Download className="size-3" />
          )}
          {state === 'running' ? 'Preparing…' : 'Download archive'}
        </button>

        {state === 'done' && (
          <p className="text-xs text-green-600 dark:text-green-400">Archive downloaded.</p>
        )}
        {state === 'error' && (
          <p className="text-xs text-destructive">
            {errorMsg ?? 'Export failed. Please try again.'}
          </p>
        )}
      </div>
    </section>
  );
}

type McpTokenState = 'idle' | 'loading' | 'creating' | 'error';

function McpTokensSection() {
  const [tokens, setTokens] = useState<McpToken[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [newName, setNewName] = useState('');
  const [mintedToken, setMintedToken] = useState<string | null>(null);
  const [state, setState] = useState<McpTokenState>('loading');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await fetchMcpTokens();
        if (!cancelled) {
          setTokens(data.items);
          setEnabled(data.enabled);
          setState('idle');
        }
      } catch {
        if (!cancelled) setState('error');
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const create = async () => {
    const name = newName.trim();
    if (!name) return;
    setState('creating');
    try {
      const token = await createMcpToken(name);
      setTokens((current) => [token, ...current]);
      setMintedToken(token.token ?? null);
      setNewName('');
      setState('idle');
    } catch {
      setState('error');
    }
  };

  const revoke = async (tokenId: number) => {
    setState('creating');
    try {
      const updated = await revokeMcpToken(tokenId);
      setTokens((current) => current.map((t) => (t.id === tokenId ? updated : t)));
      setState('idle');
    } catch {
      setState('error');
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        MCP Client Access
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <p className="text-xs text-muted-foreground">
          Create a scoped token to let an external MCP client (e.g. Claude Desktop) search and read
          articles visible to you. Tokens are read-only and disabled by default; ask an admin to
          enable the MCP server on this instance.
        </p>

        {!enabled && state !== 'loading' && (
          <p className="text-xs text-destructive" role="alert">
            The MCP server is not enabled on this instance.
          </p>
        )}

        {mintedToken && (
          <div className="rounded-md border border-border bg-surface p-3 space-y-1">
            <p className="text-xs font-medium text-foreground">
              Copy this token now — it will not be shown again:
            </p>
            <code className="block break-all text-xs text-foreground">{mintedToken}</code>
            <button
              onClick={() => setMintedToken(null)}
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Dismiss
            </button>
          </div>
        )}

        <div className="flex gap-2">
          <input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder="Token name (e.g. Claude Desktop)"
            aria-label="New MCP token name"
            className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <button
            onClick={() => void create()}
            disabled={state === 'creating' || !newName.trim() || !enabled}
            className="flex shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
          >
            {state === 'creating' ? <RefreshCw className="size-3 animate-spin" /> : null}
            Create token
          </button>
        </div>

        {state === 'error' && (
          <p className="text-xs text-destructive" role="alert">
            Could not update MCP tokens.
          </p>
        )}

        <div className="space-y-2">
          {tokens.map((token) => (
            <div
              key={token.id}
              className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface p-3"
            >
              <div className="min-w-0 space-y-1">
                <p className="truncate text-sm text-foreground">{token.name}</p>
                <p className="text-[11px] text-muted-foreground">
                  {token.token_prefix}… · scopes: {token.scopes.join(', ')}
                  {token.revoked_at ? ' · revoked' : ''}
                  {token.last_used_at ? ` · last used ${token.last_used_at}` : ' · never used'}
                </p>
              </div>
              {!token.revoked_at && (
                <button
                  onClick={() => void revoke(token.id)}
                  aria-label="Revoke MCP token"
                  className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-card hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </button>
              )}
            </div>
          ))}
          {state !== 'loading' && tokens.length === 0 && (
            <p className="text-xs text-muted-foreground">No MCP tokens yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}

type DeleteAccountState = 'idle' | 'confirming' | 'deleting' | 'error';

function DeleteAccountSection() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<DeleteAccountState>('idle');
  const [confirmation, setConfirmation] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!user) return null;

  const canDelete = confirmation === user.username;

  const handleDelete = async () => {
    if (!canDelete) return;
    setState('deleting');
    setErrorMsg(null);
    try {
      await deleteOwnAccount(confirmation);
      setUser(null);
      void navigate('/login', { replace: true });
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Could not delete account.');
      setState('error');
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        Danger Zone
      </div>
      <div className="rounded-lg border border-destructive/40 bg-card p-4 space-y-3">
        <p className="text-xs text-muted-foreground">
          Permanently delete your account and all associated data — reading history, starred
          articles, highlights, shares, and preferences. This cannot be undone.
        </p>

        {state === 'idle' && (
          <button
            onClick={() => setState('confirming')}
            className="flex items-center gap-1.5 rounded-md border border-destructive px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors"
          >
            <Trash2 className="size-3" />
            Delete my account
          </button>
        )}

        {(state === 'confirming' || state === 'deleting' || state === 'error') && (
          <div className="space-y-2">
            <label
              className="text-xs font-medium text-foreground"
              htmlFor="delete-account-confirmation"
            >
              Type <span className="font-mono">{user.username}</span> to confirm
            </label>
            <input
              id="delete-account-confirmation"
              type="text"
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
              disabled={state === 'deleting'}
              className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              autoComplete="off"
            />
            <div className="flex items-center gap-2">
              <button
                onClick={() => void handleDelete()}
                disabled={!canDelete || state === 'deleting'}
                className="flex items-center gap-1.5 rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-60"
              >
                {state === 'deleting' ? (
                  <RefreshCw className="size-3 animate-spin" />
                ) : (
                  <Trash2 className="size-3" />
                )}
                {state === 'deleting' ? 'Deleting…' : 'Permanently delete account'}
              </button>
              <button
                onClick={() => {
                  setState('idle');
                  setConfirmation('');
                  setErrorMsg(null);
                }}
                disabled={state === 'deleting'}
                className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-60"
              >
                Cancel
              </button>
            </div>
            {state === 'error' && (
              <p className="text-xs text-destructive" role="alert">
                {errorMsg ?? 'Could not delete account. Please try again.'}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

export function SettingsPage() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="p-4 md:p-5 max-w-2xl space-y-6">
      <div>
        <h2 className="text-[22px] font-semibold tracking-tight">Settings</h2>
      </div>

      <section>
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
          Theme
        </div>
        <div className="grid grid-cols-3 gap-2">
          {THEME_OPTS.map(({ v, label, Icon }) => {
            const active = theme === v;
            return (
              <button
                key={v}
                onClick={() => setTheme(v)}
                className={cn(
                  'flex flex-col items-center gap-1.5 rounded-md border p-3 text-xs font-medium transition-colors',
                  active
                    ? 'border-foreground bg-surface-2'
                    : 'border-border bg-card hover:bg-surface'
                )}
              >
                <Icon className="size-5" />
                {label}
              </button>
            );
          })}
        </div>
      </section>

      <PersonalizationSection />

      <WatchlistsSection />

      <AiMemorySection />

      <McpTokensSection />

      <DataExportSection />

      <DailyBriefSection />

      <WeeklyRecapSection />

      <PrivacySection />

      <UpdatesSection />

      <DeleteAccountSection />

      <section className="text-xs text-muted-foreground space-y-2">
        <div className="text-[10px] uppercase tracking-wider text-subtle font-medium">About</div>
        <p>Radar is a private technical news triage tool. State is stored on the server.</p>
        <p>
          Press{' '}
          <kbd className="font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
            ?
          </kbd>{' '}
          anywhere for keyboard shortcuts.
        </p>
      </section>
    </div>
  );
}
