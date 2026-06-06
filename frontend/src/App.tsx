import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './styles.css'
import { askAI, fetchArticles, fetchSources, fetchSummary, ingestNow, searchArticles, updateArticleStatus, updateSourceEnabled } from './api'
import type { Article, ArticleStatus, AskResponse, Source, Summary } from './types'

type ActiveTab = 'inbox' | 'saved' | 'read' | 'skipped' | 'archived' | 'sources'

const TAB_STATUS: Record<Exclude<ActiveTab, 'sources'>, ArticleStatus> = {
  inbox: 'new',
  saved: 'saved',
  read: 'read',
  skipped: 'skipped',
  archived: 'archived',
}

const TABS: { id: ActiveTab; label: string }[] = [
  { id: 'inbox',    label: 'Inbox'    },
  { id: 'saved',    label: 'Saved'    },
  { id: 'read',     label: 'Read'     },
  { id: 'skipped',  label: 'Skipped'  },
  { id: 'archived', label: 'Archived' },
  { id: 'sources',  label: 'Sources'  },
]

const CATEGORIES = [
  'all', 'python', 'ai-llm', 'agents', 'cloud-infra', 'engineering', 'trending', 'repositories',
]

const STATUS_NEXT: Record<ArticleStatus, ArticleStatus[]> = {
  new:      ['read', 'saved', 'skipped'],
  saved:    ['read', 'skipped', 'archived'],
  read:     ['saved', 'archived'],
  skipped:  ['read', 'archived'],
  archived: ['read'],
}

const ACTION_LABELS: Record<ArticleStatus, string> = {
  new:      'Restore',
  read:     'Read',
  saved:    'Save',
  skipped:  'Skip',
  archived: 'Archive',
}

const ACTION_ICONS: Record<ArticleStatus, string> = {
  new:      '↩',
  read:     '✓',
  saved:    '☆',
  skipped:  '×',
  archived: '□',
}

// ===== Helpers =====

function relativeTime(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const ms = Date.now() - date.getTime()
  const h = Math.floor(ms / 3600000)
  if (h < 1) return 'just now'
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d}d ago`
  if (d < 30) return `${Math.floor(d / 7)}w ago`
  return date.toLocaleDateString()
}

function parseTags(tags: string): string[] {
  return tags.split(',').map((t) => t.trim()).filter(Boolean)
}

/** Issue #17: estimated read time based on summary word count at 200 wpm */
function readTime(summary: string): number | null {
  if (!summary || !summary.trim()) return null
  const words = summary.trim().split(/\s+/).length
  return Math.max(1, Math.round(words / 200))
}

// ===== Dark mode bootstrap (runs before React renders) =====
function initTheme() {
  const stored = localStorage.getItem('theme')
  if (stored === 'dark' || stored === 'light') {
    document.documentElement.setAttribute('data-theme', stored)
  } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.documentElement.setAttribute('data-theme', 'dark')
  }
}
initTheme()

// ===== ArticleCard =====

interface ArticleCardProps {
  article: Article
  onStatus: (id: number, status: ArticleStatus) => Promise<void>
  focused?: boolean
  cardRef?: React.RefObject<HTMLElement | null>
  // bulk
  selected?: boolean
  onToggleSelect?: (id: number) => void
}

function ArticleCard({ article, onStatus, focused, cardRef, selected, onToggleSelect }: ArticleCardProps) {
  const [pending, setPending] = useState<ArticleStatus | null>(null)
  const tags = parseTags(article.tags)
  const date = article.published_at ?? article.discovered_at
  const actions = STATUS_NEXT[article.status] ?? ['read', 'saved', 'skipped']
  const rt = readTime(article.summary)

  async function handle(status: ArticleStatus) {
    setPending(status)
    try {
      await onStatus(article.id, status)
    } finally {
      setPending(null)
    }
  }

  const showReason = article.reason
    && article.reason !== article.summary
    && !article.reason.startsWith('Tracked under')

  return (
    <article
      className={`article-card${focused ? ' article-card--focused' : ''}${selected ? ' article-card--selected' : ''}`}
      ref={cardRef as React.RefObject<HTMLElement>}
      tabIndex={-1}
    >
      {onToggleSelect && (
        <label className="card-checkbox" aria-label="Select article">
          <input
            type="checkbox"
            checked={!!selected}
            onChange={() => onToggleSelect(article.id)}
          />
        </label>
      )}
      <div className="card-header">
        <div className="card-badges">
          <span className={`badge cat-${article.category}`}>
            {article.category.replace(/-/g, ' ')}
          </span>
          <span className={`badge status-${article.status}`}>{article.status}</span>
        </div>
        <span className="card-date">
          {rt !== null && <span className="card-read-time">~{rt} min</span>}
          {relativeTime(date)}
        </span>
      </div>
      <h3 className="card-title">
        <a href={article.url} target="_blank" rel="noreferrer">{article.title}</a>
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
          {tags.map((tag) => <span key={tag} className="tag">#{tag}</span>)}
        </div>
      )}
      <div className="card-actions">
        {actions.map((action) => (
          <button
            key={action}
            className={`action-btn action-${action}`}
            onClick={() => handle(action)}
            disabled={pending !== null}
            title={ACTION_LABELS[action]}
            aria-label={ACTION_LABELS[action]}
          >
            <span className="action-icon" aria-hidden="true">{pending === action ? '…' : ACTION_ICONS[action]}</span>
            <span>{ACTION_LABELS[action]}</span>
          </button>
        ))}
      </div>
    </article>
  )
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
  )
}

// ===== SourcesPanel =====

function SourceHealthBadge({ source }: { source: Source }) {
  const hoursSince = (iso?: string | null): number | null => {
    if (!iso) return null
    const ms = Date.now() - new Date(iso).getTime()
    return Math.floor(ms / 3600000)
  }

  if (source.last_error) {
    return <span className="source-health error">● error</span>
  }
  const h = hoursSince(source.last_success_at ?? source.last_checked_at)
  if (h === null) return null
  if (h > 48) return <span className="source-health stale">● stale ({Math.floor(h / 24)}d)</span>
  return <span className="source-health healthy">● ok</span>
}

function SourcesContent({ sources, onToggleEnabled }: { sources: Source[]; onToggleEnabled: (slug: string, enabled: boolean) => Promise<void> }) {
  const grouped = useMemo(() => {
    return sources.reduce<Record<string, Source[]>>((acc, s) => {
      if (!acc[s.category]) acc[s.category] = []
      acc[s.category].push(s)
      return acc
    }, {})
  }, [sources])

  function kindClass(kind: string): string {
    if (kind.startsWith('github')) return 'kind-github'
    if (kind.startsWith('trending')) return 'kind-trending'
    if (kind.startsWith('scraped')) return 'kind-scraped'
    return 'kind-rss'
  }
  function kindLabel(kind: string): string {
    return kind.replace(/_/g, ' ').replace('feed', '').trim() || 'rss'
  }

  return (
    <div className="sources-grid">
      {Object.entries(grouped).map(([cat, items]) => (
        <article className="source-card" key={cat}>
          <h3 className="source-category">{cat.replace(/-/g, ' ')}</h3>
          <ul className="source-list">
            {items.map((source) => (
              <li key={source.slug} className={`source-item${!source.enabled ? ' source-item--disabled' : ''}`}>
                <div className="source-main">
                  <a href={source.url} target="_blank" rel="noreferrer">{source.name}</a>
                  <span className={`badge ${kindClass(source.kind)}`}>{kindLabel(source.kind)}</span>
                  {/* Issue #20: enable/disable toggle */}
                  <label className="source-toggle" title={source.enabled ? 'Disable source' : 'Enable source'}>
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
                    <span className="source-checked">checked {relativeTime(source.last_checked_at)}</span>
                  )}
                  <SourceHealthBadge source={source} />
                </div>
                {source.last_error && (
                  <p className="source-error-msg" title={source.last_error}>
                    {source.last_error.length > 80 ? source.last_error.slice(0, 80) + '…' : source.last_error}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </article>
      ))}
    </div>
  )
}

// ===== Keyboard Shortcut Overlay =====

function ShortcutOverlay({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' || e.key === '?') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="overlay-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
      <div className="overlay-panel" onClick={(e) => e.stopPropagation()}>
        <div className="overlay-header">
          <h2>Keyboard shortcuts</h2>
          <button className="overlay-close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <table className="shortcut-table">
          <tbody>
            <tr><td><kbd>j</kbd></td><td>Next article</td></tr>
            <tr><td><kbd>k</kbd></td><td>Previous article</td></tr>
            <tr><td><kbd>Enter</kbd></td><td>Open focused article in new tab</td></tr>
            <tr><td><kbd>r</kbd></td><td>Mark focused article as read</td></tr>
            <tr><td><kbd>s</kbd></td><td>Mark focused article as saved</td></tr>
            <tr><td><kbd>x</kbd></td><td>Mark focused article as skipped</td></tr>
            <tr><td><kbd>a</kbd></td><td>Mark focused article as archived</td></tr>
            <tr><td><kbd>?</kbd></td><td>Toggle this overlay</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ===== Bulk Action Bar =====

interface BulkBarProps {
  count: number
  onAction: (status: ArticleStatus) => void
  onClear: () => void
}

function BulkBar({ count, onAction, onClear }: BulkBarProps) {
  return (
    <div className="bulk-bar" role="toolbar" aria-label="Bulk actions">
      <span className="bulk-count">{count} selected</span>
      <button className="bulk-btn bulk-read"     onClick={() => onAction('read')}><span aria-hidden="true">✓</span> Mark read</button>
      <button className="bulk-btn bulk-saved"    onClick={() => onAction('saved')}><span aria-hidden="true">☆</span> Save</button>
      <button className="bulk-btn bulk-skipped"  onClick={() => onAction('skipped')}><span aria-hidden="true">×</span> Skip</button>
      <button className="bulk-btn bulk-archived" onClick={() => onAction('archived')}><span aria-hidden="true">□</span> Archive</button>
      <button className="bulk-clear" onClick={onClear} aria-label="Clear selection">Clear</button>
    </div>
  )
}


// ===== AskPanel =====

interface AskPanelProps {
  result: AskResponse | null
  loading: boolean
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
    )
  }
  if (!result) return null
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
                <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}

// ===== App =====

/** #28 — Sources panel: bottom sheet on mobile, sidebar on desktop */
function SourcesPanel({ sources, onToggleEnabled }: { sources: Source[]; onToggleEnabled: (slug: string, enabled: boolean) => Promise<void> }) {
  const [sheetOpen, setSheetOpen] = useState(false)

  // Prevent body scroll while sheet is open
  useEffect(() => {
    if (sheetOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [sheetOpen])

  const categories = useMemo(() => {
    return Array.from(new Set(sources.map((s) => s.category)))
  }, [sources])

  const [activeCategory, setActiveCategory] = useState<string | null>(null)

  const filteredSources = activeCategory
    ? sources.filter((s) => s.category === activeCategory)
    : sources

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
        <span style={{ marginLeft: 'auto', fontSize: 18 }} aria-hidden="true">›</span>
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
            <span style={{ marginLeft: 'auto', color: 'var(--text-3)', fontSize: 11 }}>{sources.length}</span>
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
  )
}

export default function App() {
  const [articles, setArticles] = useState<Article[]>([])
  const [sources, setSources] = useState<Source[]>([])
  const [summary, setSummary] = useState<Summary>({ byStatus: {}, byCategory: {} })
  const [activeTab, setActiveTab] = useState<ActiveTab>('inbox')
  const [category, setCategory] = useState('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [ingesting, setIngesting] = useState(false)
  const [message, setMessage] = useState<{ text: string; kind: 'info' | 'success' | 'error' } | null>(null)

  // AI Ask mode (issue #23)
  const [askMode, setAskMode] = useState(false)
  const [askQuery, setAskQuery] = useState('')
  const [askResult, setAskResult] = useState<AskResponse | null>(null)
  const [askLoading, setAskLoading] = useState(false)

  async function submitAsk() {
    const q = askQuery.trim()
    if (!q || askLoading) return
    setAskLoading(true)
    setAskResult(null)
    try {
      const result = await askAI(q)
      setAskResult(result)
    } catch (err) {
      setAskResult({
        answer: err instanceof Error ? `Error: ${err.message}` : 'Something went wrong.',
        sources: [],
      })
    } finally {
      setAskLoading(false)
    }
  }

  function switchMode(mode: 'search' | 'ask') {
    setAskMode(mode === 'ask')
    setSearch('')
    setAskQuery('')
    setAskResult(null)
  }

  // Issue #16: dark mode
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const stored = localStorage.getItem('theme')
    if (stored === 'dark' || stored === 'light') return stored
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    localStorage.setItem('theme', next)
    document.documentElement.setAttribute('data-theme', next)
  }

  // Issue #14: keyboard navigation
  const [focusedIndex, setFocusedIndex] = useState<number>(-1)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const cardRefs = useRef<(HTMLElement | null)[]>([])
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Issue #15: bulk selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  // Issue #18: pagination
  const PAGE_SIZE = 100
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  const currentStatus: ArticleStatus | undefined =
    activeTab !== 'sources' ? TAB_STATUS[activeTab] : undefined

  async function load(opts: { preserveMessage?: boolean } = {}) {
    setLoading(true)
    setOffset(0)
    setHasMore(false)
    try {
      const [nextArticles, nextSources, nextSummary] = await Promise.all([
        activeTab !== 'sources'
          ? fetchArticles(currentStatus, category !== 'all' ? category : undefined, 0, PAGE_SIZE)
          : Promise.resolve<Article[]>([]),
        fetchSources(),
        fetchSummary(),
      ])
      setArticles(nextArticles)
      setSources(nextSources)
      setSummary(nextSummary)
      setHasMore(activeTab !== 'sources' && nextArticles.length === PAGE_SIZE)
      if (!opts.preserveMessage) setMessage(null)
    } catch (err) {
      setMessage({ text: err instanceof Error ? err.message : 'Failed to load', kind: 'error' })
    } finally {
      setLoading(false)
    }
  }

  async function loadMore() {
    if (loadingMore || !hasMore) return
    setLoadingMore(true)
    const nextOffset = offset + PAGE_SIZE
    try {
      const more = await fetchArticles(
        currentStatus,
        category !== 'all' ? category : undefined,
        nextOffset,
        PAGE_SIZE,
      )
      setArticles((prev) => [...prev, ...more])
      setOffset(nextOffset)
      setHasMore(more.length === PAGE_SIZE)
    } catch (err) {
      setMessage({ text: err instanceof Error ? err.message : 'Failed to load more', kind: 'error' })
    } finally {
      setLoadingMore(false)
    }
  }

  // Re-load when tab or category changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load() }, [activeTab, category])

  // Reset focused index and selection when articles change
  useEffect(() => {
    setFocusedIndex(-1)
    setSelectedIds(new Set())
  }, [activeTab, category, search])

  // Scroll focused card into view
  useEffect(() => {
    if (focusedIndex >= 0 && cardRefs.current[focusedIndex]) {
      cardRefs.current[focusedIndex]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [focusedIndex])

  async function runIngest() {
    setIngesting(true)
    setMessage({ text: 'Fetching feeds — this may take a minute.', kind: 'info' })
    try {
      const result = await ingestNow()
      const failed = Object.values(result.results).filter((v) => v < 0).length
      setMessage({
        text: `Done: ${result.inserted} new article(s).${failed ? ` ${failed} source(s) failed.` : ''}`,
        kind: failed ? 'info' : 'success',
      })
      await load({ preserveMessage: true })
    } catch (err) {
      setMessage({ text: err instanceof Error ? `Ingest failed: ${err.message}` : 'Ingest failed', kind: 'error' })
    } finally {
      setIngesting(false)
    }
  }

  async function changeStatus(id: number, next: ArticleStatus) {
    await updateArticleStatus(id, next)
    await load()
  }

  // Issue #20: toggle source enabled (optimistic)
  async function toggleSourceEnabled(slug: string, enabled: boolean) {
    // Optimistic update
    setSources((prev) => prev.map((s) => s.slug === slug ? { ...s, enabled: enabled ? 1 : 0 } : s))
    try {
      const updated = await updateSourceEnabled(slug, enabled)
      setSources((prev) => prev.map((s) => s.slug === slug ? updated : s))
    } catch (err) {
      // Rollback on error
      setSources((prev) => prev.map((s) => s.slug === slug ? { ...s, enabled: enabled ? 0 : 1 } : s))
      setMessage({ text: err instanceof Error ? err.message : 'Failed to update source', kind: 'error' })
    }
  }

  // Client-side search filter
  const filteredArticles = useMemo(() => {
    if (!search.trim()) return articles
    const q = search.toLowerCase()
    return articles.filter(
      (a) =>
        a.title.toLowerCase().includes(q) ||
        a.summary.toLowerCase().includes(q) ||
        a.source_name.toLowerCase().includes(q) ||
        a.tags.toLowerCase().includes(q),
    )
  }, [articles, search])

  // Search across all statuses when a search term is typed
  const [searchResults, setSearchResults] = useState<Article[] | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)

  useEffect(() => {
    if (!search.trim() || activeTab === 'sources') {
      setSearchResults(null)
      return
    }
    const timer = setTimeout(async () => {
      setSearchLoading(true)
      try {
        const results = await searchArticles(search)
        setSearchResults(results)
      } catch {
        setSearchResults(null)
      } finally {
        setSearchLoading(false)
      }
    }, 350)
    return () => clearTimeout(timer)
  }, [search, activeTab])

  const displayedArticles = searchResults !== null ? searchResults : filteredArticles
  const isSearchMode = searchResults !== null

  // Issue #14: keyboard shortcuts handler
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Disable shortcuts when focus is inside a text input
    const target = e.target as HTMLElement
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return

    if (e.key === '?') {
      e.preventDefault()
      setShowShortcuts((v) => !v)
      return
    }

    if (showShortcuts && e.key === 'Escape') {
      setShowShortcuts(false)
      return
    }

    if (activeTab === 'sources') return

    const len = displayedArticles.length
    if (len === 0) return

    if (e.key === 'j') {
      e.preventDefault()
      setFocusedIndex((i) => Math.min(i + 1, len - 1))
    } else if (e.key === 'k') {
      e.preventDefault()
      setFocusedIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && focusedIndex >= 0) {
      e.preventDefault()
      window.open(displayedArticles[focusedIndex].url, '_blank', 'noreferrer')
    } else if (focusedIndex >= 0) {
      const article = displayedArticles[focusedIndex]
      const actionMap: Record<string, ArticleStatus> = { r: 'read', s: 'saved', x: 'skipped', a: 'archived' }
      const next = actionMap[e.key]
      if (next) {
        e.preventDefault()
        void changeStatus(article.id, next)
      }
    }
  }, [activeTab, displayedArticles, focusedIndex, showShortcuts])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  // Issue #15: bulk selection helpers
  function toggleSelectId(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function selectAll() {
    if (selectedIds.size === displayedArticles.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(displayedArticles.map((a) => a.id)))
    }
  }

  async function bulkAction(status: ArticleStatus) {
    const ids = [...selectedIds]
    // Optimistic: clear selection immediately
    setSelectedIds(new Set())
    const failures: number[] = []
    await Promise.all(
      ids.map((id) =>
        updateArticleStatus(id, status).catch(() => { failures.push(id) })
      )
    )
    if (failures.length > 0) {
      setMessage({ text: `${failures.length} article(s) failed to update.`, kind: 'error' })
      // Roll back: restore failed ids selection so user can retry
      setSelectedIds(new Set(failures))
    }
    await load({ preserveMessage: failures.length > 0 })
  }

  function tabCount(tab: ActiveTab): number {
    if (tab === 'sources') return sources.length
    const s = TAB_STATUS[tab as Exclude<ActiveTab, 'sources'>]
    return (summary.byStatus as Record<string, number>)[s] ?? 0
  }

  const sectionTitle = activeTab === 'sources'
    ? 'News Sources'
    : activeTab === 'inbox'
    ? 'Inbox'
    : activeTab.charAt(0).toUpperCase() + activeTab.slice(1)

  // Stable ref-object factory for each card index
  function makeCardRef(i: number): React.RefObject<HTMLElement | null> {
    return {
      get current() { return cardRefs.current[i] ?? null },
      set current(el: HTMLElement | null) { cardRefs.current[i] = el },
    }
  }

  const allSelected = displayedArticles.length > 0 && selectedIds.size === displayedArticles.length
  const someSelected = selectedIds.size > 0 && !allSelected

  return (
    <div className="page">
      {showShortcuts && <ShortcutOverlay onClose={() => setShowShortcuts(false)} />}

      <header className="topbar">
        <div className="topbar-inner">
          <div className="topbar-brand">
            <div className="topbar-title">Ioachim's Inbox</div>
            <div className="topbar-sub">news.lihor.ro · private</div>
          </div>

          {activeTab !== 'sources' && (
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
                  <span className="topbar-search-icon" aria-hidden>⌕</span>
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
                  onSubmit={(e) => { e.preventDefault(); void submitAsk() }}
                >
                  <input
                    type="text"
                    placeholder="Ask a question about your saved articles…"
                    value={askQuery}
                    onChange={(e) => setAskQuery(e.target.value)}
                    aria-label="Ask AI"
                    disabled={askLoading}
                  />
                  <button type="submit" className="ask-submit-btn" disabled={!askQuery.trim() || askLoading}>
                    {askLoading ? '…' : '↵'}
                  </button>
                </form>
              )}
            </div>
          )}

          <button
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>

          <button className="fetch-btn" onClick={runIngest} disabled={ingesting} aria-label="Fetch feeds now">
            <span className="fetch-btn-icon">{ingesting ? '⟳' : '↻'}</span>
            <span className="fetch-btn-label">{ingesting ? 'Fetching…' : 'Fetch now'}</span>
          </button>
        </div>
      </header>

      <nav className="tabs-wrap" aria-label="Sections">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`tab${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => { setActiveTab(tab.id); setSearch('') }}
            aria-current={activeTab === tab.id ? 'page' : undefined}
          >
            {tab.label}
            <span className="tab-count">{tabCount(tab.id)}</span>
          </button>
        ))}
      </nav>

      {/* #29: filter bar — responsive, no overflow, safe-area handled in CSS */}
      {activeTab !== 'sources' && (
        <div className="filter-bar" role="toolbar" aria-label="Category filter">
          {/* Issue #15: select-all checkbox */}
          <label className="select-all-label" title="Select all on page">
            <input
              type="checkbox"
              checked={allSelected}
              ref={(el) => { if (el) el.indeterminate = someSelected }}
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
          <button className="dismiss" onClick={() => setMessage(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      {askMode && (
        <AskPanel result={askResult} loading={askLoading} />
      )}

      <main>
        {activeTab === 'sources' ? (
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
                  onClick={loadMore}
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
          onAction={bulkAction}
          onClear={() => setSelectedIds(new Set())}
        />
      )}
    </div>
  )
}
