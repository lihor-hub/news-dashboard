import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import './styles.css';
import {
  askAI,
  fetchArticlesOverTime,
  fetchArticles,
  fetchIngestRunSources,
  fetchIngestRuns,
  fetchSchedulerStatus,
  fetchSourceHealth,
  fetchSources,
  fetchSourcesVolume,
  fetchStatsOverview,
  fetchSummary,
  ingestNow,
  pauseScheduler,
  resumeScheduler,
  searchArticles,
  setSchedulerInterval,
  updateArticleStatus,
  updateSourceEnabled,
} from './api';
import type { SchedulerStatus } from './api';
import type {
  Article,
  ArticleStatus,
  ArticlesOverTimePoint,
  AskResponse,
  Source,
  SourceHealth,
  SourceVolumePoint,
  StatsOverview,
  Summary,
  IngestRun,
  IngestRunSource,
} from './types';

type ActiveTab = 'inbox' | 'saved' | 'read' | 'skipped' | 'archived' | 'sources' | 'scheduler';

const TAB_STATUS: Record<Exclude<ActiveTab, 'sources' | 'scheduler'>, ArticleStatus> = {
  inbox: 'new',
  saved: 'saved',
  read: 'read',
  skipped: 'skipped',
  archived: 'archived',
};

const TABS: { id: ActiveTab; label: string }[] = [
  { id: 'inbox', label: 'Inbox' },
  { id: 'saved', label: 'Saved' },
  { id: 'read', label: 'Read' },
  { id: 'skipped', label: 'Skipped' },
  { id: 'archived', label: 'Archived' },
  { id: 'sources', label: 'Sources' },
  { id: 'scheduler', label: 'Scheduler' },
];

const CATEGORIES = [
  'all',
  'python',
  'ai-llm',
  'agents',
  'cloud-infra',
  'engineering',
  'trending',
  'repositories',
];

const STATUS_NEXT: Record<ArticleStatus, ArticleStatus[]> = {
  new: ['read', 'saved', 'skipped'],
  saved: ['read', 'skipped', 'archived'],
  read: ['saved', 'archived'],
  skipped: ['read', 'archived'],
  archived: ['read'],
};

const ACTION_LABELS: Record<ArticleStatus, string> = {
  new: 'Restore',
  read: 'Read',
  saved: 'Save',
  skipped: 'Skip',
  archived: 'Archive',
};

const ACTION_ICONS: Record<ArticleStatus, string> = {
  new: '↩',
  read: '✓',
  saved: '☆',
  skipped: '×',
  archived: '□',
};

// ===== Helpers =====

function relativeTime(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const ms = Date.now() - date.getTime();
  const h = Math.floor(ms / 3600000);
  if (h < 1) return 'just now';
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  if (d < 30) return `${Math.floor(d / 7)}w ago`;
  return date.toLocaleDateString();
}

function formatDateTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDuration(ms?: number | null): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
}

function parseTags(tags: string): string[] {
  return tags
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

/** Issue #17: estimated read time based on summary word count at 200 wpm */
function readTime(summary: string): number | null {
  if (!summary?.trim()) return null;
  const words = summary.trim().split(/\s+/).length;
  return Math.max(1, Math.round(words / 200));
}

function articleConfidence(article: Article): number {
  const score = Math.max(0, Math.min(100, Number(article.importance_score) || 0));
  if (article.status === 'read') return 100;
  if (article.status === 'saved') return Math.max(score, 90);
  if (article.status === 'skipped') return Math.min(score, 20);
  if (article.status === 'archived') return Math.min(score, 10);
  return score;
}

function confidenceTier(score: number): 'high' | 'medium' | 'low' {
  if (score >= 75) return 'high';
  if (score >= 40) return 'medium';
  return 'low';
}

// Dark mode bootstrap is handled in main.tsx → lib/theme.ts

// ===== ArticleCard =====

interface ArticleCardProps {
  article: Article;
  onStatus: (id: number, status: ArticleStatus) => Promise<void>;
  focused?: boolean;
  cardRef?: React.RefObject<HTMLElement | null>;
  // bulk
  selected?: boolean;
  onToggleSelect?: (id: number) => void;
}

function ArticleCard({
  article,
  onStatus,
  focused,
  cardRef,
  selected,
  onToggleSelect,
}: ArticleCardProps) {
  const [pending, setPending] = useState<ArticleStatus | null>(null);
  const tags = parseTags(article.tags);
  const date = article.published_at ?? article.discovered_at;
  const actions = STATUS_NEXT[article.status] ?? ['read', 'saved', 'skipped'];
  const rt = readTime(article.summary);
  const confidence = articleConfidence(article);
  const confidenceLevel = confidenceTier(confidence);

  async function handle(status: ArticleStatus) {
    setPending(status);
    try {
      await onStatus(article.id, status);
    } finally {
      setPending(null);
    }
  }

  const showReason =
    article.reason &&
    article.reason !== article.summary &&
    !article.reason.startsWith('Tracked under');

  return (
    <article
      className={`article-card${focused ? ' article-card--focused' : ''}${selected ? ' article-card--selected' : ''}`}
      ref={cardRef}
      tabIndex={-1}
    >
      {onToggleSelect && (
        <label className="card-checkbox" aria-label="Select article">
          <input type="checkbox" checked={!!selected} onChange={() => onToggleSelect(article.id)} />
        </label>
      )}
      <div className="card-header">
        <div className="card-badges">
          <span className={`badge cat-${article.category}`}>
            {article.category.replace(/-/g, ' ')}
          </span>
          <span className={`badge status-${article.status}`}>{article.status}</span>
          <span className={`badge confidence-badge confidence-${confidenceLevel}`}>
            confidence {confidence}%
          </span>
        </div>
        <span className="card-date">
          {rt !== null && <span className="card-read-time">~{rt} min</span>}
          {relativeTime(date)}
        </span>
      </div>
      <h3 className="card-title">
        <a href={article.url} target="_blank" rel="noreferrer">
          {article.title}
        </a>
      </h3>
      <p className="card-source">
        {article.source_name}
        {article.also_from && article.also_from.length > 0 && (
          <span className="card-also-from"> · also from: {article.also_from.join(', ')}</span>
        )}
      </p>
      {article.summary ? <p className="card-summary">{article.summary}</p> : null}
      {showReason ? <p className="card-reason">{article.reason}</p> : null}
      {tags.length > 0 && (
        <div className="card-tags">
          {tags.map((tag) => (
            <span key={tag} className="tag">
              #{tag}
            </span>
          ))}
        </div>
      )}
      <div className="card-actions">
        {actions.map((action) => (
          <button
            key={action}
            className={`action-btn action-${action}`}
            onClick={() => void handle(action)}
            disabled={pending !== null}
            title={ACTION_LABELS[action]}
            aria-label={ACTION_LABELS[action]}
          >
            <span className="action-icon" aria-hidden="true">
              {pending === action ? '…' : ACTION_ICONS[action]}
            </span>
            <span>{ACTION_LABELS[action]}</span>
          </button>
        ))}
      </div>
    </article>
  );
}

// ===== SkeletonCard =====

function SkeletonCard() {
  return (
    <div className="skeleton-card" aria-hidden="true">
      <div style={{ display: 'flex', gap: 6 }}>
        <div className="skeleton sk-h" style={{ width: 70 }} />
        <div className="skeleton sk-h" style={{ width: 48 }} />
        <div className="skeleton sk-h" style={{ width: 44, marginLeft: 'auto' }} />
      </div>
      <div className="skeleton sk-h" />
      <div className="skeleton sk-h-sm" />
      <div className="skeleton sk-line" />
      <div className="skeleton sk-line-sm" />
      <div className="skeleton sk-line-xs" />
      <div style={{ display: 'flex', gap: 6 }}>
        <div className="skeleton sk-bar" style={{ flex: 1 }} />
        <div className="skeleton sk-bar" style={{ flex: 1 }} />
        <div className="skeleton sk-bar" style={{ flex: 1 }} />
      </div>
    </div>
  );
}

// ===== SourcesPanel =====

function SourceHealthBadge({ source }: { source: Source }) {
  const hoursSince = (iso?: string | null): number | null => {
    if (!iso) return null;
    // eslint-disable-next-line react-hooks/purity -- display-only "hours ago" label; staleness across renders is acceptable
    const ms = Date.now() - new Date(iso).getTime();
    return Math.floor(ms / 3600000);
  };

  if (source.last_error) {
    return <span className="source-health error">● error</span>;
  }
  const h = hoursSince(source.last_success_at ?? source.last_checked_at);
  if (h === null) return null;
  if (h > 48) return <span className="source-health stale">● stale ({Math.floor(h / 24)}d)</span>;
  return <span className="source-health healthy">● ok</span>;
}

function SourcesContent({
  sources,
  onToggleEnabled,
}: {
  sources: Source[];
  onToggleEnabled: (slug: string, enabled: boolean) => Promise<void>;
}) {
  const grouped = useMemo(() => {
    return sources.reduce<Record<string, Source[]>>((acc, s) => {
      if (!acc[s.category]) acc[s.category] = [];
      acc[s.category].push(s);
      return acc;
    }, {});
  }, [sources]);

  function kindClass(kind: string): string {
    if (kind.startsWith('github')) return 'kind-github';
    if (kind.startsWith('trending')) return 'kind-trending';
    if (kind.startsWith('scraped')) return 'kind-scraped';
    return 'kind-rss';
  }
  function kindLabel(kind: string): string {
    return kind.replace(/_/g, ' ').replace('feed', '').trim() || 'rss';
  }

  return (
    <div className="sources-grid">
      {Object.entries(grouped).map(([cat, items]) => (
        <article className="source-card" key={cat}>
          <h3 className="source-category">{cat.replace(/-/g, ' ')}</h3>
          <ul className="source-list">
            {items.map((source) => (
              <li
                key={source.slug}
                className={`source-item${!source.enabled ? ' source-item--disabled' : ''}`}
              >
                <div className="source-main">
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.name}
                  </a>
                  <span className={`badge ${kindClass(source.kind)}`}>
                    {kindLabel(source.kind)}
                  </span>
                  {/* Issue #20: enable/disable toggle */}
                  <label
                    className="source-toggle"
                    title={source.enabled ? 'Disable source' : 'Enable source'}
                  >
                    <input
                      type="checkbox"
                      role="switch"
                      aria-label={`${source.enabled ? 'Disable' : 'Enable'} ${source.name}`}
                      checked={!!source.enabled}
                      onChange={() => void onToggleEnabled(source.slug, !source.enabled)}
                    />
                    <span className="source-toggle-track" />
                  </label>
                </div>
                <div className="source-meta">
                  {source.last_checked_at && (
                    <span className="source-checked">
                      checked {relativeTime(source.last_checked_at)}
                    </span>
                  )}
                  <SourceHealthBadge source={source} />
                </div>
                {source.last_error && (
                  <p className="source-error-msg" title={source.last_error}>
                    {source.last_error.length > 80
                      ? source.last_error.slice(0, 80) + '…'
                      : source.last_error}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </article>
      ))}
    </div>
  );
}

// ===== Keyboard Shortcut Overlay =====

function ShortcutOverlay({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' || e.key === '?') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="overlay-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div className="overlay-panel" onClick={(e) => e.stopPropagation()}>
        <div className="overlay-header">
          <h2>Keyboard shortcuts</h2>
          <button className="overlay-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <table className="shortcut-table">
          <tbody>
            <tr>
              <td>
                <kbd>j</kbd>
              </td>
              <td>Next article</td>
            </tr>
            <tr>
              <td>
                <kbd>k</kbd>
              </td>
              <td>Previous article</td>
            </tr>
            <tr>
              <td>
                <kbd>Enter</kbd>
              </td>
              <td>Open focused article in new tab</td>
            </tr>
            <tr>
              <td>
                <kbd>r</kbd>
              </td>
              <td>Mark focused article as read</td>
            </tr>
            <tr>
              <td>
                <kbd>s</kbd>
              </td>
              <td>Mark focused article as saved</td>
            </tr>
            <tr>
              <td>
                <kbd>x</kbd>
              </td>
              <td>Mark focused article as skipped</td>
            </tr>
            <tr>
              <td>
                <kbd>a</kbd>
              </td>
              <td>Mark focused article as archived</td>
            </tr>
            <tr>
              <td>
                <kbd>?</kbd>
              </td>
              <td>Toggle this overlay</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ===== Bulk Action Bar =====

interface BulkBarProps {
  count: number;
  onAction: (status: ArticleStatus) => void;
  onClear: () => void;
}

function BulkBar({ count, onAction, onClear }: BulkBarProps) {
  return (
    <div className="bulk-bar" role="toolbar" aria-label="Bulk actions">
      <span className="bulk-count">{count} selected</span>
      <button className="bulk-btn bulk-read" onClick={() => onAction('read')}>
        <span aria-hidden="true">✓</span> Mark read
      </button>
      <button className="bulk-btn bulk-saved" onClick={() => onAction('saved')}>
        <span aria-hidden="true">☆</span> Save
      </button>
      <button className="bulk-btn bulk-skipped" onClick={() => onAction('skipped')}>
        <span aria-hidden="true">×</span> Skip
      </button>
      <button className="bulk-btn bulk-archived" onClick={() => onAction('archived')}>
        <span aria-hidden="true">□</span> Archive
      </button>
      <button className="bulk-clear" onClick={onClear} aria-label="Clear selection">
        Clear
      </button>
    </div>
  );
}

// ===== AskPanel =====

interface AskPanelProps {
  result: AskResponse | null;
  loading: boolean;
}

function AskPanel({ result, loading }: AskPanelProps) {
  if (loading) {
    return (
      <div className="ask-panel">
        <div className="ask-loading">
          <span className="skeleton sk-line" style={{ width: '80%' }} />
          <span className="skeleton sk-line" style={{ width: '60%' }} />
        </div>
      </div>
    );
  }
  if (!result) return null;
  return (
    <div className="ask-panel">
      <p className="ask-answer">{result.answer}</p>
      {result.sources.length > 0 && (
        <div className="ask-sources">
          <p className="ask-sources-label">Sources</p>
          <ol className="ask-sources-list">
            {result.sources.map((s, i) => (
              <li key={s.id}>
                <span className="ask-source-num">[{i + 1}]</span>{' '}
                <a href={s.url} target="_blank" rel="noreferrer">
                  {s.title}
                </a>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

// ===== App =====

// ===== SchedulerTab =====

const INTERVAL_PRESETS = [
  { label: '15m', value: 15 },
  { label: '30m', value: 30 },
  { label: '1h', value: 60 },
  { label: '3h', value: 180 },
  { label: '6h', value: 360 },
];

type StatsRangeId = 'today' | 'last7' | 'last30' | 'last90';

const STATS_RANGE_OPTIONS: { id: StatsRangeId; label: string }[] = [
  { id: 'today', label: 'Today' },
  { id: 'last7', label: 'Last 7 days' },
  { id: 'last30', label: 'Last 30 days' },
  { id: 'last90', label: 'Last 90 days' },
];

function startOfUtcDay(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function statsRange(range: StatsRangeId): { from: string; to: string } {
  const now = new Date();
  const today = startOfUtcDay(now);
  const starts: Record<StatsRangeId, Date> = {
    today,
    last7: addDays(today, -6),
    last30: addDays(today, -29),
    last90: addDays(today, -89),
  };
  return { from: starts[range].toISOString(), to: now.toISOString() };
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat().format(value);
}

function formatTimeBucket(value: string, range: StatsRangeId): string {
  if (range === 'today') {
    return new Date(value).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'UTC',
    });
  }
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function formatRangeDate(value: string): string {
  return new Date(value).toLocaleDateString([], { timeZone: 'UTC' });
}

function formatSourceLabel(value: string): string {
  return value.length > 18 ? `${value.slice(0, 17)}…` : value;
}

function relativeCountdown(isoStr: string | null): string {
  if (!isoStr) return '—';
  const ms = new Date(isoStr).getTime() - Date.now();
  if (ms <= 0) return 'now';
  const totalSecs = Math.floor(ms / 1000);
  const h = Math.floor(totalSecs / 3600);
  const m = Math.floor((totalSecs % 3600) / 60);
  const s = totalSecs % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

const RUN_HISTORY_PER_PAGE = 10;

function RunHistoryTable({ refreshToken }: { refreshToken: number }) {
  const [runs, setRuns] = useState<IngestRun[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);
  const [sourcesByRun, setSourcesByRun] = useState<Record<number, IngestRunSource[]>>({});
  const [loadingSources, setLoadingSources] = useState<number | null>(null);

  async function loadRuns(nextPage = page) {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchIngestRuns(nextPage, RUN_HISTORY_PER_PAGE);
      setRuns(data.items);
      setTotal(data.total);
      setHasMore(data.has_more);
      setPage(data.page);
      setExpandedRunId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load run history');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadRuns(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, refreshToken]);

  async function toggleRun(runId: number) {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      return;
    }
    setExpandedRunId(runId);
    if (sourcesByRun[runId]) return;
    setLoadingSources(runId);
    try {
      const items = await fetchIngestRunSources(runId);
      setSourcesByRun((prev) => ({ ...prev, [runId]: items }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load run details');
    } finally {
      setLoadingSources(null);
    }
  }

  const rangeStart = total === 0 ? 0 : (page - 1) * RUN_HISTORY_PER_PAGE + 1;
  const rangeEnd = Math.min(page * RUN_HISTORY_PER_PAGE, total);

  return (
    <div className="run-history">
      <div className="run-history-header">
        <h3 className="scheduler-card-title">Run History</h3>
        <button
          className="run-history-refresh"
          onClick={() => void loadRuns(page)}
          disabled={loading}
        >
          ↻
        </button>
      </div>

      {error && <div className="run-history-error">{error}</div>}

      {loading ? (
        <div className="run-history-loading">
          <span className="skeleton sk-line" />
          <span className="skeleton sk-line" style={{ width: '72%' }} />
        </div>
      ) : runs.length === 0 ? (
        <div className="run-history-empty">No ingest runs recorded yet.</div>
      ) : (
        <>
          <div className="run-history-table-wrap">
            <table className="run-history-table">
              <thead>
                <tr>
                  <th aria-label="Expand run" />
                  <th>Started at</th>
                  <th>Duration</th>
                  <th>Sources run</th>
                  <th>New articles</th>
                  <th>Errors</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const expanded = expandedRunId === run.id;
                  const sourceRows = sourcesByRun[run.id] ?? [];
                  return (
                    <Fragment key={run.id}>
                      <tr key={run.id} className={expanded ? 'expanded' : undefined}>
                        <td>
                          <button
                            className="run-expand-btn"
                            onClick={() => void toggleRun(run.id)}
                            aria-expanded={expanded}
                            aria-label={`${expanded ? 'Collapse' : 'Expand'} run ${run.id}`}
                          >
                            {expanded ? '⌄' : '›'}
                          </button>
                        </td>
                        <td>
                          <span className="run-started">{formatDateTime(run.started_at)}</span>
                          <span className="run-relative">{relativeTime(run.started_at)}</span>
                        </td>
                        <td>{formatDuration(run.duration_ms)}</td>
                        <td>{run.sources_run}</td>
                        <td>{run.total_new}</td>
                        <td>
                          <span className={run.total_errors > 0 ? 'run-error-count' : undefined}>
                            {run.total_errors}
                          </span>
                        </td>
                      </tr>
                      {expanded && (
                        <tr key={`${run.id}-sources`} className="run-source-row">
                          <td colSpan={6}>
                            {loadingSources === run.id ? (
                              <div className="run-source-loading">Loading source breakdown…</div>
                            ) : sourceRows.length === 0 ? (
                              <div className="run-source-empty">
                                No per-source rows recorded for this run.
                              </div>
                            ) : (
                              <table className="run-source-table">
                                <thead>
                                  <tr>
                                    <th>Source name</th>
                                    <th>Articles found</th>
                                    <th>New</th>
                                    <th>Duplicates</th>
                                    <th>Error message</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {sourceRows.map((source) => (
                                    <tr key={source.id}>
                                      <td>{source.source_name}</td>
                                      <td>{source.articles_found}</td>
                                      <td>{source.articles_new}</td>
                                      <td>{source.duplicates}</td>
                                      <td
                                        className={
                                          source.error_message
                                            ? 'run-source-error'
                                            : 'run-source-muted'
                                        }
                                      >
                                        {source.error_message ?? '—'}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="run-history-pagination">
            <span>
              {rangeStart}-{rangeEnd} of {total}
            </span>
            <div className="run-history-page-buttons">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={loading || page === 1}
              >
                ‹
              </button>
              <button onClick={() => setPage((p) => p + 1)} disabled={loading || !hasMore}>
                ›
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

interface SchedulerTabProps {
  onFetchNow: () => Promise<void>;
  ingesting: boolean;
}

function SourceHealthTable({ items, loading }: { items: SourceHealth[]; loading: boolean }) {
  const sorted = useMemo(() => {
    return [...items].sort((a, b) => {
      if (b.error_streak !== a.error_streak) return b.error_streak - a.error_streak;
      if (a.status !== b.status) return a.status === 'ERROR' ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
  }, [items]);

  if (loading) {
    return (
      <div className="source-health-loading">
        <div className="skeleton sk-line" style={{ width: '70%' }} />
        <div className="skeleton sk-line" style={{ width: '55%' }} />
        <div className="skeleton sk-line" style={{ width: '62%' }} />
      </div>
    );
  }

  if (sorted.length === 0) {
    return <p className="source-health-empty">No sources configured.</p>;
  }

  return (
    <div className="source-health-table-wrap">
      <table className="source-health-table">
        <thead>
          <tr>
            <th>Source name</th>
            <th>Last checked</th>
            <th>Status</th>
            <th>Articles last run</th>
            <th>Error streak</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((source) => (
            <tr
              key={source.slug}
              className={source.status === 'ERROR' ? 'source-health-row-error' : undefined}
            >
              <td>
                <span className="source-health-name">{source.name}</span>
                <span className="source-health-category">{source.category.replace(/-/g, ' ')}</span>
              </td>
              <td>{source.last_checked_at ? relativeTime(source.last_checked_at) : 'Never'}</td>
              <td>
                <span className={`source-health-status ${source.status.toLowerCase()}`}>
                  {source.status}
                </span>
              </td>
              <td>{source.articles_last_run}</td>
              <td>
                <span className="source-health-streak" title={source.last_error ?? undefined}>
                  {source.error_streak}
                </span>
                {source.last_error && (
                  <span className="source-health-last-error" title={source.last_error}>
                    {source.last_error}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IngestTerminal() {
  const [lines, setLines] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const terminalRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    const events = new EventSource('/api/ingest/stream');

    events.onopen = () => setConnected(true);
    events.onerror = () => setConnected(false);
    events.addEventListener('reset', () => setLines([]));
    events.addEventListener('line', (event) => {
      setLines((prev) => [...prev, String(event.data)]);
    });

    return () => events.close();
  }, []);

  useEffect(() => {
    const terminal = terminalRef.current;
    if (terminal) {
      terminal.scrollTop = terminal.scrollHeight;
    }
  }, [lines]);

  return (
    <div className="scheduler-card scheduler-terminal-card">
      <div className="scheduler-terminal-header">
        <h3 className="scheduler-card-title">Ingest Terminal</h3>
        <span className={`scheduler-terminal-status${connected ? ' connected' : ''}`}>
          {connected ? 'Live' : 'Connecting'}
        </span>
      </div>
      <pre className="scheduler-terminal" ref={terminalRef} aria-live="polite">
        {lines.length ? lines.join('\n') : 'Waiting for ingest output...'}
      </pre>
    </div>
  );
}

function SchedulerTab({ onFetchNow, ingesting }: SchedulerTabProps) {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [sourceHealth, setSourceHealth] = useState<SourceHealth[]>([]);
  const [loadingSourceHealth, setLoadingSourceHealth] = useState(true);
  const [customMinutes, setCustomMinutes] = useState('');
  const [actionPending, setActionPending] = useState(false);
  const [tabMessage, setTabMessage] = useState<{ text: string; kind: 'success' | 'error' } | null>(
    null
  );
  const [countdown, setCountdown] = useState<string>('—');
  const [rangeId, setRangeId] = useState<StatsRangeId>('last7');
  const [overview, setOverview] = useState<StatsOverview | null>(null);
  const [articlesSeries, setArticlesSeries] = useState<ArticlesOverTimePoint[]>([]);
  const [sourceVolumes, setSourceVolumes] = useState<SourceVolumePoint[]>([]);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);

  const selectedRange = useMemo(() => statsRange(rangeId), [rangeId]);
  const articlesChartData = useMemo(
    () =>
      articlesSeries.map((row) => ({
        ...row,
        label: formatTimeBucket(row.date, rangeId),
      })),
    [articlesSeries, rangeId]
  );
  const topSourceVolumes = useMemo(() => sourceVolumes.slice(0, 12), [sourceVolumes]);
  const [historyRefresh, setHistoryRefresh] = useState(0);

  async function loadStatus() {
    try {
      const s = await fetchSchedulerStatus();
      setStatus(s);
    } catch (err) {
      setTabMessage({
        text: err instanceof Error ? err.message : 'Failed to load scheduler status',
        kind: 'error',
      });
    } finally {
      setLoadingStatus(false);
    }
  }

  async function loadHealth() {
    setLoadingSourceHealth(true);
    try {
      setSourceHealth(await fetchSourceHealth());
    } catch (err) {
      setTabMessage({
        text: err instanceof Error ? err.message : 'Failed to load source health',
        kind: 'error',
      });
    } finally {
      setLoadingSourceHealth(false);
    }
  }

  async function loadStats() {
    setStatsLoading(true);
    setStatsError(null);
    try {
      const [nextOverview, nextArticlesSeries, nextSourceVolumes] = await Promise.all([
        fetchStatsOverview(selectedRange.from, selectedRange.to),
        fetchArticlesOverTime(selectedRange.from, selectedRange.to),
        fetchSourcesVolume(selectedRange.from, selectedRange.to),
      ]);
      setOverview(nextOverview);
      setArticlesSeries(nextArticlesSeries);
      setSourceVolumes(nextSourceVolumes);
    } catch (err) {
      setStatsError(err instanceof Error ? err.message : 'Failed to load statistics');
    } finally {
      setStatsLoading(false);
    }
  }

  useEffect(() => {
    void loadStatus();
    void loadHealth();
  }, []);

  useEffect(() => {
    void loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loadStats identity changes every render; re-fetch only on range change
  }, [selectedRange.from, selectedRange.to]);

  useEffect(() => {
    if (!status) return;
    if (status.paused) {
      setCountdown('Paused');
      return;
    }
    setCountdown(relativeCountdown(status.next_run_at));
    const timer = setInterval(() => {
      setCountdown(relativeCountdown(status.next_run_at));
    }, 1000);
    return () => clearInterval(timer);
  }, [status]);

  async function handlePreset(minutes: number) {
    setActionPending(true);
    try {
      const res = await setSchedulerInterval(minutes);
      setStatus((prev) =>
        prev ? { ...prev, interval_minutes: minutes, next_run_at: res.next_run_at } : prev
      );
      setTabMessage({ text: `Interval set to ${minutes} minutes.`, kind: 'success' });
    } catch (err) {
      setTabMessage({
        text: err instanceof Error ? err.message : 'Failed to set interval',
        kind: 'error',
      });
    } finally {
      setActionPending(false);
    }
  }

  async function handleCustomSave() {
    const mins = parseInt(customMinutes, 10);
    if (!mins || mins < 1) {
      setTabMessage({ text: 'Enter a valid number of minutes (≥ 1).', kind: 'error' });
      return;
    }
    await handlePreset(mins);
    setCustomMinutes('');
  }

  async function handleTogglePause() {
    if (!status) return;
    setActionPending(true);
    try {
      if (status.paused) {
        const res = await resumeScheduler();
        setStatus((prev) =>
          prev ? { ...prev, paused: false, next_run_at: res.next_run_at ?? prev.next_run_at } : prev
        );
        setTabMessage({ text: 'Scheduler resumed.', kind: 'success' });
      } else {
        await pauseScheduler();
        setStatus((prev) => (prev ? { ...prev, paused: true, next_run_at: null } : prev));
        setTabMessage({ text: 'Scheduler paused.', kind: 'success' });
      }
    } catch (err) {
      setTabMessage({
        text: err instanceof Error ? err.message : 'Failed to toggle pause',
        kind: 'error',
      });
    } finally {
      setActionPending(false);
    }
  }

  async function handleFetchNow() {
    await onFetchNow();
    await loadHealth();
    await loadStats();
    setHistoryRefresh((value) => value + 1);
  }

  if (loadingStatus) {
    return (
      <div className="scheduler-panel">
        <div className="skeleton sk-line" style={{ width: '60%', marginBottom: 12 }} />
        <div className="skeleton sk-line" style={{ width: '40%' }} />
      </div>
    );
  }

  return (
    <div className="scheduler-panel">
      {tabMessage && (
        <div
          className={`message-banner ${tabMessage.kind}`}
          role="status"
          style={{ marginBottom: 16 }}
        >
          <span>{tabMessage.text}</span>
          <button className="dismiss" onClick={() => setTabMessage(null)} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}

      <div className="stats-dashboard">
        <div className="stats-toolbar">
          <div>
            <h3 className="stats-title">Statistics</h3>
            <p className="stats-range-label">
              {formatRangeDate(selectedRange.from)} – {formatRangeDate(selectedRange.to)}
            </p>
          </div>
          <div className="stats-range-picker" role="group" aria-label="Statistics time range">
            {STATS_RANGE_OPTIONS.map((option) => (
              <button
                key={option.id}
                className={`stats-range-btn${rangeId === option.id ? ' active' : ''}`}
                onClick={() => setRangeId(option.id)}
                aria-pressed={rangeId === option.id}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {statsError && (
          <div className="message-banner error stats-error" role="status">
            <span>{statsError}</span>
          </div>
        )}

        <div className="stats-overview-grid">
          {[
            {
              label: 'Total articles',
              value: overview ? formatInteger(overview.total_articles) : '—',
            },
            { label: 'Total new', value: overview ? formatInteger(overview.total_new) : '—' },
            { label: 'Total errors', value: overview ? formatInteger(overview.total_errors) : '—' },
            {
              label: 'Avg run duration',
              value: overview ? formatDuration(overview.avg_duration_ms) : '—',
            },
            {
              label: 'Healthy sources',
              value: overview ? formatInteger(overview.healthy_sources) : '—',
            },
            {
              label: 'Erroring sources',
              value: overview ? formatInteger(overview.erroring_sources) : '—',
            },
          ].map((metric) => (
            <div className="stats-metric-card" key={metric.label}>
              <span className="stats-metric-label">{metric.label}</span>
              <span className="stats-metric-value">{statsLoading ? '…' : metric.value}</span>
            </div>
          ))}
        </div>

        <div className="stats-charts-grid">
          <div className="stats-chart-card">
            <h3 className="stats-chart-title">Articles Ingested Over Time</h3>
            <div className="stats-chart-frame">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={articlesChartData}
                  margin={{ top: 8, right: 8, left: 0, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    width={36}
                  />
                  <Tooltip
                    cursor={{ fill: 'rgba(37, 99, 235, 0.08)' }}
                    formatter={(value) => [formatInteger(Number(value)), 'New articles']}
                    labelFormatter={(_, payload) =>
                      (payload?.[0]?.payload as { date?: string } | undefined)?.date ?? ''
                    }
                  />
                  <Bar
                    dataKey="new_articles"
                    fill="var(--accent)"
                    radius={[4, 4, 0, 0]}
                    minPointSize={2}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="stats-chart-card">
            <h3 className="stats-chart-title">Sources Ranked by Volume</h3>
            <div className="stats-chart-frame">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={topSourceVolumes}
                  layout="vertical"
                  margin={{ top: 8, right: 8, left: 8, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis
                    type="number"
                    allowDecimals={false}
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    dataKey="source_name"
                    type="category"
                    tick={{ fontSize: 11 }}
                    tickFormatter={formatSourceLabel}
                    tickLine={false}
                    axisLine={false}
                    width={118}
                  />
                  <Tooltip
                    cursor={{ fill: 'rgba(37, 99, 235, 0.08)' }}
                    formatter={(value) => [formatInteger(Number(value)), 'New articles']}
                  />
                  <Bar
                    dataKey="total_new"
                    fill="var(--accent-muted)"
                    radius={[0, 4, 4, 0]}
                    minPointSize={2}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      <div className="scheduler-card">
        <h3 className="scheduler-card-title">Status</h3>
        <div className="scheduler-status-row">
          <span className={`scheduler-status-badge${status?.paused ? ' paused' : ' running'}`}>
            {status?.paused ? '⏸ Paused' : '▶ Running'}
          </span>
          <span className="scheduler-status-detail">
            {status?.paused ? 'No runs scheduled' : `Next run in ${countdown}`}
          </span>
        </div>
        <div className="scheduler-status-row">
          <span className="scheduler-label">Interval:</span>
          <span className="scheduler-value">{status?.interval_minutes ?? '—'} minutes</span>
        </div>
        {!status?.paused && status?.next_run_at && (
          <div className="scheduler-status-row">
            <span className="scheduler-label">Next run at:</span>
            <span className="scheduler-value scheduler-value--muted">
              {new Date(status.next_run_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </div>
        )}
      </div>

      <div className="scheduler-card">
        <h3 className="scheduler-card-title">Change Interval</h3>
        <div className="scheduler-presets">
          {INTERVAL_PRESETS.map((p) => (
            <button
              key={p.value}
              className={`scheduler-preset-btn${status?.interval_minutes === p.value ? ' active' : ''}`}
              onClick={() => void handlePreset(p.value)}
              disabled={actionPending}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="scheduler-custom-row">
          <input
            type="number"
            className="scheduler-custom-input"
            min={1}
            placeholder="Custom minutes…"
            value={customMinutes}
            onChange={(e) => setCustomMinutes(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleCustomSave();
            }}
            disabled={actionPending}
            aria-label="Custom interval in minutes"
          />
          <button
            className="scheduler-save-btn"
            onClick={() => void handleCustomSave()}
            disabled={actionPending || !customMinutes}
          >
            Save
          </button>
        </div>
      </div>

      <div className="scheduler-card">
        <h3 className="scheduler-card-title">Controls</h3>
        <div className="scheduler-controls-row">
          <button
            className={`scheduler-toggle-btn${status?.paused ? ' resume' : ' pause'}`}
            onClick={() => void handleTogglePause()}
            disabled={actionPending}
          >
            {status?.paused ? '▶ Resume' : '⏸ Pause'}
          </button>
          <button
            className="scheduler-fetch-btn"
            onClick={() => void handleFetchNow()}
            disabled={ingesting || actionPending}
          >
            {ingesting ? '⟳ Fetching…' : '↻ Fetch now'}
          </button>
        </div>
      </div>

      <div className="scheduler-card scheduler-card--wide">
        <h3 className="scheduler-card-title">Source Health</h3>
        <SourceHealthTable items={sourceHealth} loading={loadingSourceHealth} />
      </div>
      <IngestTerminal />
      <RunHistoryTable refreshToken={historyRefresh} />
    </div>
  );
}

/** #28 — Sources panel: bottom sheet on mobile, sidebar on desktop */
function SourcesPanel({
  sources,
  onToggleEnabled,
}: {
  sources: Source[];
  onToggleEnabled: (slug: string, enabled: boolean) => Promise<void>;
}) {
  const [sheetOpen, setSheetOpen] = useState(false);

  // Prevent body scroll while sheet is open
  useEffect(() => {
    if (sheetOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [sheetOpen]);

  const categories = useMemo(() => {
    return Array.from(new Set(sources.map((s) => s.category)));
  }, [sources]);

  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const filteredSources = activeCategory
    ? sources.filter((s) => s.category === activeCategory)
    : sources;

  return (
    <>
      {/* ── Mobile: toggle button + bottom sheet ── */}
      <button
        className="sources-toggle-btn"
        onClick={() => setSheetOpen(true)}
        aria-expanded={sheetOpen}
        aria-controls="sources-sheet"
      >
        <span aria-hidden="true">☰</span>
        <span>View all {sources.length} sources</span>
        <span style={{ marginLeft: 'auto', fontSize: 18 }} aria-hidden="true">
          ›
        </span>
      </button>

      {/* Overlay */}
      <div
        className={`sources-sheet-overlay${sheetOpen ? ' open' : ''}`}
        onClick={() => setSheetOpen(false)}
        aria-hidden="true"
      />

      {/* Bottom sheet */}
      <div
        id="sources-sheet"
        className={`sources-sheet${sheetOpen ? ' open' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label="News sources"
      >
        <div className="sources-sheet-handle" aria-hidden="true" />
        <div className="sources-sheet-header">
          <span className="sources-sheet-title">News Sources ({sources.length})</span>
          <button
            className="sources-sheet-close"
            onClick={() => setSheetOpen(false)}
            aria-label="Close sources panel"
          >
            ×
          </button>
        </div>
        <div className="sources-sheet-content">
          <SourcesContent sources={sources} onToggleEnabled={onToggleEnabled} />
        </div>
      </div>

      {/* ── Desktop: sidebar + main grid ── */}
      <div className="sources-desktop-layout">
        <aside className="sources-sidebar" aria-label="Filter by category">
          <div className="sources-sidebar-title">Categories</div>
          <button
            className={`sources-sidebar-btn${activeCategory === null ? ' active' : ''}`}
            onClick={() => setActiveCategory(null)}
          >
            All sources
            <span style={{ marginLeft: 'auto', color: 'var(--text-3)', fontSize: 11 }}>
              {sources.length}
            </span>
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              className={`sources-sidebar-btn${activeCategory === cat ? ' active' : ''}`}
              onClick={() => setActiveCategory(cat)}
            >
              {cat.replace(/-/g, ' ')}
              <span style={{ marginLeft: 'auto', color: 'var(--text-3)', fontSize: 11 }}>
                {sources.filter((s) => s.category === cat).length}
              </span>
            </button>
          ))}
        </aside>
        <div className="sources-main">
          <SourcesContent sources={filteredSources} onToggleEnabled={onToggleEnabled} />
        </div>
      </div>
    </>
  );
}

interface AppProps {
  initialTab?: ActiveTab;
  hideLegacyNav?: boolean;
  initialAskMode?: boolean;
}

export default function App({
  initialTab = 'inbox',
  hideLegacyNav = false,
  initialAskMode = false,
}: AppProps) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [summary, setSummary] = useState<Summary>({ byStatus: {}, byCategory: {} });
  const [activeTab, setActiveTab] = useState<ActiveTab>(initialTab);
  const [category, setCategory] = useState('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [ingesting, setIngesting] = useState(false);
  const [message, setMessage] = useState<{
    text: string;
    kind: 'info' | 'success' | 'error';
  } | null>(null);

  // AI Ask mode (issue #23)
  const [askMode, setAskMode] = useState(initialAskMode);
  const [askQuery, setAskQuery] = useState('');
  const [askResult, setAskResult] = useState<AskResponse | null>(null);
  const [askLoading, setAskLoading] = useState(false);

  async function submitAsk() {
    const q = askQuery.trim();
    if (!q || askLoading) return;
    setAskLoading(true);
    setAskResult(null);
    try {
      const result = await askAI(q);
      setAskResult(result);
    } catch (err) {
      setAskResult({
        answer: err instanceof Error ? `Error: ${err.message}` : 'Something went wrong.',
        sources: [],
      });
    } finally {
      setAskLoading(false);
    }
  }

  function switchMode(mode: 'search' | 'ask') {
    setAskMode(mode === 'ask');
    setSearch('');
    setAskQuery('');
    setAskResult(null);
  }

  // Issue #16: dark mode
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const stored = localStorage.getItem('theme');
    if (stored === 'dark' || stored === 'light') return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    localStorage.setItem('theme', next);
    document.documentElement.setAttribute('data-theme', next);
  }

  // Issue #14: keyboard navigation
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const cardRefs = useRef<(HTMLElement | null)[]>([]);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Issue #15: bulk selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Issue #18: pagination
  const PAGE_SIZE = 100;
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const currentStatus: ArticleStatus | undefined =
    activeTab !== 'sources' && activeTab !== 'scheduler' ? TAB_STATUS[activeTab] : undefined;

  async function load(opts: { preserveMessage?: boolean } = {}) {
    setLoading(true);
    setOffset(0);
    setHasMore(false);
    try {
      const [nextArticles, nextSources, nextSummary] = await Promise.all([
        activeTab !== 'sources' && activeTab !== 'scheduler'
          ? fetchArticles(currentStatus, category !== 'all' ? category : undefined, 0, PAGE_SIZE)
          : Promise.resolve<Article[]>([]),
        fetchSources(),
        fetchSummary(),
      ]);
      setArticles(nextArticles);
      setSources(nextSources);
      setSummary(nextSummary);
      setHasMore(
        activeTab !== 'sources' && activeTab !== 'scheduler' && nextArticles.length === PAGE_SIZE
      );
      if (!opts.preserveMessage) setMessage(null);
    } catch (err) {
      setMessage({ text: err instanceof Error ? err.message : 'Failed to load', kind: 'error' });
    } finally {
      setLoading(false);
    }
  }

  async function loadMore() {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    const nextOffset = offset + PAGE_SIZE;
    try {
      const more = await fetchArticles(
        currentStatus,
        category !== 'all' ? category : undefined,
        nextOffset,
        PAGE_SIZE
      );
      setArticles((prev) => [...prev, ...more]);
      setOffset(nextOffset);
      setHasMore(more.length === PAGE_SIZE);
    } catch (err) {
      setMessage({
        text: err instanceof Error ? err.message : 'Failed to load more',
        kind: 'error',
      });
    } finally {
      setLoadingMore(false);
    }
  }

  // Re-load when tab or category changes

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load identity changes every render; re-fetch only on tab/category change
  }, [activeTab, category]);

  // Reset focused index and selection when articles change
  useEffect(() => {
    setFocusedIndex(-1);
    setSelectedIds(new Set());
  }, [activeTab, category, search]);

  // Scroll focused card into view
  useEffect(() => {
    if (focusedIndex >= 0 && cardRefs.current[focusedIndex]) {
      cardRefs.current[focusedIndex]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [focusedIndex]);

  async function runIngest() {
    setIngesting(true);
    setMessage({ text: 'Fetching feeds — this may take a minute.', kind: 'info' });
    try {
      const result = await ingestNow();
      const failed = Object.values(result.results).filter((v) => v < 0).length;
      setMessage({
        text: `Done: ${result.inserted} new article(s).${failed ? ` ${failed} source(s) failed.` : ''}`,
        kind: failed ? 'info' : 'success',
      });
      await load({ preserveMessage: true });
    } catch (err) {
      setMessage({
        text: err instanceof Error ? `Ingest failed: ${err.message}` : 'Ingest failed',
        kind: 'error',
      });
    } finally {
      setIngesting(false);
    }
  }

  async function changeStatus(id: number, next: ArticleStatus) {
    await updateArticleStatus(id, next);
    await load();
  }

  // Issue #20: toggle source enabled (optimistic)
  async function toggleSourceEnabled(slug: string, enabled: boolean) {
    // Optimistic update
    setSources((prev) =>
      prev.map((s) => (s.slug === slug ? { ...s, enabled: enabled ? 1 : 0 } : s))
    );
    try {
      const updated = await updateSourceEnabled(slug, enabled);
      setSources((prev) => prev.map((s) => (s.slug === slug ? updated : s)));
    } catch (err) {
      // Rollback on error
      setSources((prev) =>
        prev.map((s) => (s.slug === slug ? { ...s, enabled: enabled ? 0 : 1 } : s))
      );
      setMessage({
        text: err instanceof Error ? err.message : 'Failed to update source',
        kind: 'error',
      });
    }
  }

  // Client-side search filter
  const filteredArticles = useMemo(() => {
    if (!search.trim()) return articles;
    const q = search.toLowerCase();
    return articles.filter(
      (a) =>
        a.title.toLowerCase().includes(q) ||
        a.summary.toLowerCase().includes(q) ||
        a.source_name.toLowerCase().includes(q) ||
        a.tags.toLowerCase().includes(q)
    );
  }, [articles, search]);

  // Search across all statuses when a search term is typed
  const [searchResults, setSearchResults] = useState<Article[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);

  useEffect(() => {
    if (!search.trim() || activeTab === 'sources' || activeTab === 'scheduler') {
      setSearchResults(null);
      return;
    }
    const timer = setTimeout(() => {
      void (async () => {
        setSearchLoading(true);
        try {
          const results = await searchArticles(search);
          setSearchResults(results);
        } catch {
          setSearchResults(null);
        } finally {
          setSearchLoading(false);
        }
      })();
    }, 350);
    return () => clearTimeout(timer);
  }, [search, activeTab]);

  const displayedArticles = searchResults ?? filteredArticles;
  const isSearchMode = searchResults !== null;

  // Issue #14: keyboard shortcuts handler
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Disable shortcuts when focus is inside a text input
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;

      if (e.key === '?') {
        e.preventDefault();
        setShowShortcuts((v) => !v);
        return;
      }

      if (showShortcuts && e.key === 'Escape') {
        setShowShortcuts(false);
        return;
      }

      if (activeTab === 'sources' || activeTab === 'scheduler') return;

      const len = displayedArticles.length;
      if (len === 0) return;

      if (e.key === 'j') {
        e.preventDefault();
        setFocusedIndex((i) => Math.min(i + 1, len - 1));
      } else if (e.key === 'k') {
        e.preventDefault();
        setFocusedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter' && focusedIndex >= 0) {
        e.preventDefault();
        window.open(displayedArticles[focusedIndex].url, '_blank', 'noreferrer');
      } else if (focusedIndex >= 0) {
        const article = displayedArticles[focusedIndex];
        const actionMap: Record<string, ArticleStatus> = {
          r: 'read',
          s: 'saved',
          x: 'skipped',
          a: 'archived',
        };
        const next = actionMap[e.key];
        if (next) {
          e.preventDefault();
          void changeStatus(article.id, next);
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- changeStatus identity changes every render; the handler reads fresh state via the deps below
    [activeTab, displayedArticles, focusedIndex, showShortcuts]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // Issue #15: bulk selection helpers
  function toggleSelectId(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    if (selectedIds.size === displayedArticles.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(displayedArticles.map((a) => a.id)));
    }
  }

  async function bulkAction(status: ArticleStatus) {
    const ids = [...selectedIds];
    // Optimistic: clear selection immediately
    setSelectedIds(new Set());
    const failures: number[] = [];
    await Promise.all(
      ids.map((id) =>
        updateArticleStatus(id, status).catch(() => {
          failures.push(id);
        })
      )
    );
    if (failures.length > 0) {
      setMessage({ text: `${failures.length} article(s) failed to update.`, kind: 'error' });
      // Roll back: restore failed ids selection so user can retry
      setSelectedIds(new Set(failures));
    }
    await load({ preserveMessage: failures.length > 0 });
  }

  function tabCount(tab: ActiveTab): number {
    if (tab === 'sources') return sources.length;
    if (tab === 'scheduler') return 0;
    const s = TAB_STATUS[tab];
    return summary.byStatus[s] ?? 0;
  }

  const sectionTitle =
    activeTab === 'sources'
      ? 'News Sources'
      : activeTab === 'scheduler'
        ? 'Scheduler'
        : activeTab === 'inbox'
          ? 'Inbox'
          : activeTab.charAt(0).toUpperCase() + activeTab.slice(1);

  // Stable ref-object factory for each card index
  function makeCardRef(i: number): React.RefObject<HTMLElement | null> {
    return {
      get current() {
        return cardRefs.current[i] ?? null;
      },
      set current(el: HTMLElement | null) {
        cardRefs.current[i] = el;
      },
    };
  }

  const allSelected = displayedArticles.length > 0 && selectedIds.size === displayedArticles.length;
  const someSelected = selectedIds.size > 0 && !allSelected;

  return (
    <div className="page">
      {showShortcuts && <ShortcutOverlay onClose={() => setShowShortcuts(false)} />}

      <header className="topbar">
        <div className="topbar-inner">
          <div className="topbar-brand">
            <div className="topbar-title">Ioachim's Inbox</div>
            <div className="topbar-sub">news.lihor.ro · private</div>
          </div>

          {activeTab !== 'sources' && activeTab !== 'scheduler' && (
            <div className="topbar-search">
              <div className="search-mode-toggle" role="group" aria-label="Search mode">
                <button
                  className={`search-mode-btn${!askMode ? ' active' : ''}`}
                  onClick={() => switchMode('search')}
                  aria-pressed={!askMode}
                >
                  Search
                </button>
                <button
                  className={`search-mode-btn${askMode ? ' active' : ''}`}
                  onClick={() => switchMode('ask')}
                  aria-pressed={askMode}
                >
                  Ask
                </button>
              </div>
              {!askMode ? (
                <>
                  <span className="topbar-search-icon" aria-hidden>
                    ⌕
                  </span>
                  <input
                    ref={searchInputRef}
                    type="search"
                    placeholder="Search all articles…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    aria-label="Search articles"
                  />
                </>
              ) : (
                <form
                  className="ask-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void submitAsk();
                  }}
                >
                  <input
                    type="text"
                    placeholder="Ask a question about your saved articles…"
                    value={askQuery}
                    onChange={(e) => setAskQuery(e.target.value)}
                    aria-label="Ask AI"
                    disabled={askLoading}
                  />
                  <button
                    type="submit"
                    className="ask-submit-btn"
                    disabled={!askQuery.trim() || askLoading}
                  >
                    {askLoading ? '…' : '↵'}
                  </button>
                </form>
              )}
            </div>
          )}

          {!hideLegacyNav && (
            <button
              className="theme-toggle"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
            >
              {theme === 'dark' ? '☀' : '☾'}
            </button>
          )}

          <button
            className="fetch-btn"
            onClick={() => void runIngest()}
            disabled={ingesting}
            aria-label="Fetch feeds now"
          >
            <span className="fetch-btn-icon">{ingesting ? '⟳' : '↻'}</span>
            <span className="fetch-btn-label">{ingesting ? 'Fetching…' : 'Fetch now'}</span>
          </button>
        </div>
      </header>

      {!hideLegacyNav && (
        <nav className="tabs-wrap" aria-label="Sections">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={`tab${activeTab === tab.id ? ' active' : ''}`}
              onClick={() => {
                setActiveTab(tab.id);
                setSearch('');
              }}
              aria-current={activeTab === tab.id ? 'page' : undefined}
            >
              {tab.label}
              {tab.id !== 'scheduler' && <span className="tab-count">{tabCount(tab.id)}</span>}
            </button>
          ))}
        </nav>
      )}

      {/* #29: filter bar — responsive, no overflow, safe-area handled in CSS */}
      {activeTab !== 'sources' && activeTab !== 'scheduler' && (
        <div className="filter-bar" role="toolbar" aria-label="Category filter">
          {/* Issue #15: select-all checkbox */}
          <label className="select-all-label" title="Select all on page">
            <input
              type="checkbox"
              checked={allSelected}
              ref={(el) => {
                if (el) el.indeterminate = someSelected;
              }}
              onChange={selectAll}
              aria-label="Select all articles"
            />
          </label>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              className={`filter-pill${category === cat ? ' active' : ''}`}
              onClick={() => setCategory(cat)}
              aria-pressed={category === cat}
            >
              {cat === 'all' ? 'All' : cat.replace(/-/g, ' ')}
            </button>
          ))}
          <span className="filter-meta">
            {loading || searchLoading
              ? 'Loading…'
              : isSearchMode
                ? `${displayedArticles.length} result${displayedArticles.length !== 1 ? 's' : ''} across all tabs`
                : `${filteredArticles.length} article${filteredArticles.length !== 1 ? 's' : ''}`}
          </span>
        </div>
      )}

      {message && (
        <div className={`message-banner ${message.kind}`} role="status">
          <span>{message.text}</span>
          <button className="dismiss" onClick={() => setMessage(null)} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}

      {askMode && <AskPanel result={askResult} loading={askLoading} />}

      <main>
        {activeTab === 'scheduler' ? (
          <>
            <div className="section-header">
              <h2 className="section-title">{sectionTitle}</h2>
            </div>
            <SchedulerTab onFetchNow={runIngest} ingesting={ingesting} />
          </>
        ) : activeTab === 'sources' ? (
          <>
            <div className="section-header">
              <h2 className="section-title">{sectionTitle}</h2>
            </div>
            <SourcesPanel sources={sources} onToggleEnabled={toggleSourceEnabled} />
          </>
        ) : (
          <>
            <div className="section-header">
              <h2 className="section-title">
                {isSearchMode ? `Search: "${search}"` : sectionTitle}
              </h2>
            </div>
            {/* #26: CSS Grid, 1-col mobile / 2-col desktop */}
            <div className="articles-grid">
              {(loading && !isSearchMode) || searchLoading ? (
                Array.from({ length: 6 }, (_, i) => <SkeletonCard key={i} />)
              ) : displayedArticles.length === 0 ? (
                <div className="empty-state">
                  <p>
                    {search
                      ? `No results for "${search}". Try different keywords.`
                      : 'Nothing here yet. Click Fetch now or wait for the cron job.'}
                  </p>
                </div>
              ) : (
                displayedArticles.map((a, i) => (
                  <ArticleCard
                    key={a.id}
                    article={a}
                    onStatus={changeStatus}
                    focused={focusedIndex === i}
                    cardRef={makeCardRef(i)}
                    selected={selectedIds.has(a.id)}
                    onToggleSelect={toggleSelectId}
                  />
                ))
              )}
            </div>
            {/* Issue #18: Load more button */}
            {!isSearchMode && hasMore && (
              <div className="load-more-wrap">
                <button
                  className="load-more-btn"
                  onClick={() => void loadMore()}
                  disabled={loadingMore}
                >
                  {loadingMore ? 'Loading…' : 'Load more'}
                </button>
              </div>
            )}
          </>
        )}
      </main>

      {/* Issue #15: bulk action bar */}
      {selectedIds.size > 0 && (
        <BulkBar
          count={selectedIds.size}
          onAction={(status) => void bulkAction(status)}
          onClear={() => setSelectedIds(new Set())}
        />
      )}
    </div>
  );
}
