import { useEffect, useState } from 'react';
import {
  Sun,
  Moon,
  Monitor,
  RefreshCw,
  Download,
  RotateCcw,
  ExternalLink,
  Sparkles,
} from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';
import { cn } from '@/lib/utils';
import type { Theme } from '@/lib/theme';
import { useUpdateCheck } from '@/hooks/useUpdateCheck';
import { recalculateMyRecommendations } from '@/api';

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
              <span className="text-muted-foreground">Current version</span>
              <span className="tabular-nums font-mono text-xs">{info.currentVersion}</span>
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

          {info && !info.updateAvailable && !loading && (
            <p className="text-xs text-green-600 dark:text-green-400">
              You're on the latest version ({info.latestVersion}).
            </p>
          )}

          {info?.updateAvailable && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Version <span className="font-mono">{info.latestVersion}</span> is available.
              </p>
              {info.apkUrl ? (
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
              ) : (
                <a
                  href={info.releaseUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs text-primary hover:underline"
                >
                  <ExternalLink className="size-3" />
                  View release
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
              href={`https://github.com/${info.releaseUrl.split('github.com/')[1]?.split('/releases')[0] ?? 'ioachim-hub/news-dashboard'}/releases`}
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
  const [state, setState] = useState<RecalcState>({ status: 'idle' });

  const recalculate = async () => {
    setState({ status: 'running' });
    try {
      const { scored } = await recalculateMyRecommendations();
      setState({ status: 'done', scored });
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

      <UpdatesSection />

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
