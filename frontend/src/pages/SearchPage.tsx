import { useNavigate, useSearchParams } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { Search as SearchIcon } from 'lucide-react';
import { ArticleRow } from '@/components/article/ArticleRow';
import { EmptyState } from '@/components/EmptyState';
import { useArticleListNav } from '@/hooks/useArticleListNav';
import { useTriageMutations } from '@/hooks/useTriageMutations';
import { useFocusedArticle } from '@/contexts/focusedArticle';
import { setReaderList } from '@/lib/readerList';
import { searchArticlesFiltered } from '@/api/workflowApi';
import { fetchSources } from '@/api';
import type { WorkflowState } from '@/lib/workflowTypes';
import { cn } from '@/lib/utils';

// ─── Constants ───────────────────────────────────────────────────────────────

const WORKFLOW_STATES: { value: WorkflowState; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'later', label: 'Later' },
  { value: 'done', label: 'Done' },
  { value: 'skipped', label: 'Skipped' },
  { value: 'archived', label: 'Archived' },
];

const CATEGORIES = [
  'python',
  'ai-llm',
  'agents',
  'cloud-infra',
  'engineering',
  'trending',
  'repositories',
];

const DATE_OPTIONS: { value: string; label: string }[] = [
  { value: 'all', label: 'Any time' },
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'Past week' },
  { value: 'month', label: 'Past month' },
];

const SEARCH_PAGE_SIZE = 100;

// ─── URL state helpers ────────────────────────────────────────────────────────

function parseList(params: URLSearchParams, key: string): string[] {
  return params.getAll(key).filter(Boolean);
}

function encodedFilters(
  q: string,
  states: string[],
  categories: string[],
  sources: string[],
  starredOnly: boolean,
  includeArchived: boolean,
  dateRange: string
): URLSearchParams {
  const p = new URLSearchParams();
  if (q) p.set('q', q);
  states.forEach((s) => p.append('states', s));
  categories.forEach((c) => p.append('categories', c));
  sources.forEach((s) => p.append('sources', s));
  if (starredOnly) p.set('starred_only', '1');
  if (includeArchived) p.set('include_archived', '1');
  if (dateRange !== 'all') p.set('date_range', dateRange);
  return p;
}

// ─── Page ────────────────────────────────────────────────────────────────────

export function SearchPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const q = searchParams.get('q') ?? '';
  const states = parseList(searchParams, 'states') as WorkflowState[];
  const categories = parseList(searchParams, 'categories');
  const sources = parseList(searchParams, 'sources');
  const starredOnly = searchParams.get('starred_only') === '1';
  const includeArchived = searchParams.get('include_archived') === '1';
  const dateRange = searchParams.get('date_range') ?? 'all';

  const [inputValue, setInputValue] = useState(q);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync input when URL changes externally (e.g., back navigation)
  useEffect(() => {
    setInputValue(q);
  }, [q]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function updateParams(overrides: {
    q?: string;
    states?: string[];
    categories?: string[];
    sources?: string[];
    starredOnly?: boolean;
    includeArchived?: boolean;
    dateRange?: string;
  }) {
    setSearchParams(
      encodedFilters(
        overrides.q ?? q,
        overrides.states ?? states,
        overrides.categories ?? categories,
        overrides.sources ?? sources,
        overrides.starredOnly ?? starredOnly,
        overrides.includeArchived ?? includeArchived,
        overrides.dateRange ?? dateRange
      ),
      { replace: true }
    );
  }

  const hasFilters =
    q ||
    states.length ||
    categories.length ||
    sources.length ||
    starredOnly ||
    includeArchived ||
    dateRange !== 'all';

  const { data: availableSources = [] } = useQuery({
    queryKey: ['sources'],
    queryFn: fetchSources,
    staleTime: 5 * 60_000,
  });

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ['search', q, states, categories, sources, starredOnly, includeArchived, dateRange],
    queryFn: ({ pageParam }) =>
      searchArticlesFiltered({
        q,
        states: states.length ? states : undefined,
        categories: categories.length ? categories : undefined,
        sources: sources.length ? sources : undefined,
        starredOnly,
        includeArchived,
        dateRange: (dateRange || 'all') as 'all' | 'today' | 'week' | 'month',
        limit: SEARCH_PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      if (!lastPage.hasMore) return undefined;
      return lastPage.offset + lastPage.items.length;
    },
    enabled: !!hasFilters,
    staleTime: 30_000,
  });
  const pages = data?.pages ?? [];
  const results = pages.flatMap((page) => page.items);
  const total = pages[0]?.total ?? 0;

  useEffect(() => {
    setReaderList(results.map((a) => a.id));
  }, [results]);

  const mutations = useTriageMutations();
  const { focused } = useArticleListNav(results, (a) => void navigate(`/a/${a.id}`), mutations);
  const { set: setFocused } = useFocusedArticle();
  useEffect(() => {
    setFocused(results[focused] ?? null);
    return () => setFocused(null);
  }, [focused, results, setFocused]);

  // Debounced query update when typing
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  function handleInputChange(value: string) {
    setInputValue(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      updateParams({ q: value });
    }, 300);
  }

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-2">
        <h2 className="text-[22px] font-semibold tracking-tight mb-3">Search</h2>

        {/* Search input */}
        <div className="relative">
          <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <input
            ref={inputRef}
            value={inputValue}
            onChange={(e) => handleInputChange(e.target.value)}
            placeholder="Search titles, summaries, tags, full text…"
            className="w-full h-10 pl-9 pr-3 rounded-md border border-border bg-surface text-sm outline-none focus:border-border-strong focus:bg-background"
          />
        </div>

        {/* Filter chips */}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {/* Starred */}
          <Chip active={starredOnly} onClick={() => updateParams({ starredOnly: !starredOnly })}>
            Starred
          </Chip>

          {/* Include archived */}
          <Chip
            active={includeArchived}
            onClick={() => updateParams({ includeArchived: !includeArchived })}
          >
            Include archived
          </Chip>

          {/* State group */}
          <FilterGroup
            label="State"
            all={WORKFLOW_STATES.map((s) => s.value)}
            selected={states}
            onChange={(next) => updateParams({ states: next })}
            render={(v) => WORKFLOW_STATES.find((s) => s.value === v)?.label ?? v}
          />

          {/* Category group */}
          <FilterGroup
            label="Category"
            all={CATEGORIES}
            selected={categories}
            onChange={(next) => updateParams({ categories: next })}
            render={(v) => v}
          />

          {/* Date group */}
          <FilterGroup
            label="Date"
            all={DATE_OPTIONS.map((d) => d.value)}
            selected={dateRange !== 'all' ? [dateRange] : []}
            onChange={(next) => updateParams({ dateRange: next[next.length - 1] ?? 'all' })}
            render={(v) => DATE_OPTIONS.find((d) => d.value === v)?.label ?? v}
            single
          />

          {/* Source group */}
          {availableSources.length > 0 && (
            <FilterGroup
              label="Source"
              all={availableSources.map((s) => s.slug)}
              selected={sources}
              onChange={(next) => updateParams({ sources: next })}
              render={(slug) => availableSources.find((s) => s.slug === slug)?.name ?? slug}
            />
          )}
        </div>
      </div>

      {/* Result count */}
      {hasFilters && (
        <div className="px-4 md:px-5 py-2 text-[11px] text-muted-foreground border-b border-border">
          {isLoading
            ? '...'
            : `${results.length} of ${total} ${total === 1 ? 'result' : 'results'}`}
        </div>
      )}

      {/* Results */}
      {!hasFilters ? (
        <EmptyState
          icon={SearchIcon}
          title="Start searching"
          subtitle="Type a query or apply filters to find articles."
        />
      ) : isLoading ? (
        <SearchSkeleton />
      ) : results.length === 0 ? (
        <EmptyState
          icon={SearchIcon}
          title="No results"
          subtitle="Try different search terms or filters."
        />
      ) : (
        <div>
          {results.map((a, i) => (
            <ArticleRow key={a.id} article={a} focused={i === focused} />
          ))}
          {hasNextPage && (
            <div className="px-4 md:px-5 py-3 border-t border-border">
              <button
                type="button"
                onClick={() => void fetchNextPage()}
                disabled={isFetchingNextPage}
                className="h-8 px-3 rounded-md border border-border bg-surface text-xs font-medium text-foreground hover:border-border-strong disabled:opacity-60"
              >
                {isFetchingNextPage ? 'Loading...' : 'Load more'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Chip ────────────────────────────────────────────────────────────────────

function Chip({
  active,
  onClick,
  children,
}: {
  active?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'h-7 px-2.5 rounded-full border text-[11px] font-medium transition-colors',
        active
          ? 'bg-foreground text-background border-foreground'
          : 'bg-surface border-border text-muted-foreground hover:text-foreground hover:border-border-strong'
      )}
    >
      {children}
    </button>
  );
}

// ─── FilterGroup ─────────────────────────────────────────────────────────────

function FilterGroup({
  label,
  all,
  selected,
  onChange,
  render,
  single,
}: {
  label: string;
  all: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  render: (v: string) => string;
  single?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const isActive = selected.length > 0;
  const badge =
    single && selected[0]
      ? ` · ${render(selected[0])}`
      : !single && selected.length > 0
        ? ` · ${selected.length}`
        : '';

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'h-7 px-2.5 rounded-full border text-[11px] font-medium transition-colors',
          isActive
            ? 'bg-foreground text-background border-foreground'
            : 'bg-surface border-border text-muted-foreground hover:text-foreground hover:border-border-strong'
        )}
      >
        {label}
        {badge}
      </button>
      {open && (
        <div className="absolute z-20 mt-1 min-w-[160px] max-h-64 overflow-y-auto rounded-md border border-border bg-popover shadow-md p-1">
          {all.map((v) => {
            const on = selected.includes(v);
            return (
              <button
                key={v}
                onClick={() => {
                  if (single) {
                    onChange(on ? [] : [v]);
                    setOpen(false);
                  } else {
                    onChange(on ? selected.filter((x) => x !== v) : [...selected, v]);
                  }
                }}
                className={cn(
                  'flex w-full items-center justify-between gap-2 px-2.5 py-1.5 rounded text-xs hover:bg-surface',
                  on && 'font-medium text-foreground'
                )}
              >
                <span className="truncate text-left">{render(v)}</span>
                {on && <span className="text-accent shrink-0">✓</span>}
              </button>
            );
          })}
          {!single && (
            <div className="border-t border-border mt-1 pt-1 flex justify-end gap-1">
              <button
                onClick={() => onChange([])}
                className="px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
              >
                Clear
              </button>
              <button
                onClick={() => setOpen(false)}
                className="px-2 py-1 text-[11px] text-foreground"
              >
                Done
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Skeleton ────────────────────────────────────────────────────────────────

function SearchSkeleton() {
  return (
    <div className="divide-y divide-border">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="px-4 md:px-5 py-3">
          <div className="h-3 w-32 bg-surface-2 rounded animate-pulse mb-2" />
          <div className="h-4 w-3/4 bg-surface-2 rounded animate-pulse mb-2" />
          <div className="h-3 w-1/2 bg-surface-2 rounded animate-pulse" />
        </div>
      ))}
    </div>
  );
}
