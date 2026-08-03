import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { useInfiniteQuery } from '@tanstack/react-query';
import { AlertCircle, ExternalLink, GraduationCap, Loader2, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { EmptyState } from '@/components/EmptyState';
import { listLessons, type Lesson, type LessonReadWorthiness, type LessonSummary } from '@/api';

const LESSON_PAGE_SIZE = 20;

const STATUS_FILTERS: { value: Lesson['generation_status'] | 'all'; label: string }[] = [
  { value: 'all', label: 'All statuses' },
  { value: 'complete', label: 'Complete' },
  { value: 'pending', label: 'Generating' },
  { value: 'failed', label: 'Failed' },
];

const VERDICT_FILTERS: { value: LessonReadWorthiness['verdict'] | 'all'; label: string }[] = [
  { value: 'all', label: 'All verdicts' },
  { value: 'study', label: 'Study' },
  { value: 'read', label: 'Read' },
  { value: 'skim', label: 'Skim' },
  { value: 'skip', label: 'Skip' },
];

function statusBadgeVariant(
  status: Lesson['generation_status']
): 'default' | 'secondary' | 'destructive' {
  if (status === 'complete') return 'default';
  if (status === 'failed') return 'destructive';
  return 'secondary';
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function LessonCard({ lesson }: { lesson: LessonSummary }) {
  const verdict = lesson.lesson_detail?.read_worthiness.verdict;
  const isFailed = lesson.generation_status === 'failed';
  const isPending = lesson.generation_status === 'pending';

  return (
    <Link
      to={`/learn/${lesson.id}`}
      className="block rounded-lg border border-border bg-background p-4 transition-colors hover:bg-surface"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="truncate text-sm font-semibold text-foreground">
            {lesson.title ?? lesson.original_url}
          </h3>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {lesson.source_name ? <span>{lesson.source_name}</span> : null}
            <span>{formatDate(lesson.created_at)}</span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {verdict ? <Badge variant="outline">{verdict}</Badge> : null}
          <Badge variant={statusBadgeVariant(lesson.generation_status)}>
            {isPending ? (
              <span className="inline-flex items-center gap-1">
                <Loader2 className="size-3 animate-spin" />
                Generating
              </span>
            ) : isFailed ? (
              'Failed'
            ) : (
              'Complete'
            )}
          </Badge>
        </div>
      </div>

      {isFailed && lesson.generation_error ? (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-destructive">
          <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
          <span>{lesson.generation_error}</span>
        </p>
      ) : lesson.lesson_detail ? (
        <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
          {lesson.lesson_detail.gist}
        </p>
      ) : null}

      <div className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
        <ExternalLink className="size-3" />
        <span className="truncate">{lesson.original_url}</span>
      </div>
    </Link>
  );
}

export function LessonLibraryPage() {
  const { t } = useTranslation();
  const [searchInput, setSearchInput] = useState('');
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<Lesson['generation_status'] | 'all'>('all');
  const [verdict, setVerdict] = useState<LessonReadWorthiness['verdict'] | 'all'>('all');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setQ(searchInput), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchInput]);

  const { data, isLoading, isError, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: ['lessons', q, status, verdict],
      initialPageParam: 0,
      queryFn: ({ pageParam }) =>
        listLessons({
          q: q || undefined,
          status: status === 'all' ? undefined : status,
          verdict: verdict === 'all' ? undefined : verdict,
          limit: LESSON_PAGE_SIZE,
          offset: pageParam,
        }),
      getNextPageParam: (lastPage) => lastPage.next_offset ?? undefined,
    });

  const lessons = data?.pages.flatMap((page) => page.lessons) ?? [];

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="mt-0.5 rounded-md border border-border p-2 text-muted-foreground">
          <GraduationCap className="size-5" />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-foreground">
            {t('learn.library.title', 'Lesson Library')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t(
              'learn.library.description',
              'Browse, search, and revisit lessons you generated from articles.'
            )}
          </p>
        </div>
      </div>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label={t('learn.library.search_label', 'Search lessons')}
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder={t(
              'learn.library.search_placeholder',
              'Search by title, URL, source, or concept'
            )}
            className="pl-9"
          />
        </div>
        <select
          aria-label={t('learn.library.status_filter_label', 'Filter by status')}
          value={status}
          onChange={(event) => setStatus(event.target.value as Lesson['generation_status'] | 'all')}
          className="h-9 rounded-md border border-border bg-surface px-2 text-sm outline-none focus:border-border-strong"
        >
          {STATUS_FILTERS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          aria-label={t('learn.library.verdict_filter_label', 'Filter by read-worthiness')}
          value={verdict}
          onChange={(event) =>
            setVerdict(event.target.value as LessonReadWorthiness['verdict'] | 'all')
          }
          className="h-9 rounded-md border border-border bg-surface px-2 text-sm outline-none focus:border-border-strong"
        >
          {VERDICT_FILTERS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      ) : isError ? (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div className="text-sm text-foreground">
            {t('learn.library.load_error', 'Failed to load your lesson library.')}
          </div>
        </div>
      ) : lessons.length === 0 ? (
        <EmptyState
          icon={GraduationCap}
          title={
            q || status !== 'all' || verdict !== 'all'
              ? t('learn.library.no_matches', 'No lessons match your filters.')
              : t('learn.library.empty', 'No lessons yet. Paste a link on the Learn page.')
          }
        />
      ) : (
        <div className="space-y-3">
          {lessons.map((lesson) => (
            <LessonCard key={lesson.id} lesson={lesson} />
          ))}
          {hasNextPage ? (
            <div className="flex justify-center pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => void fetchNextPage()}
                disabled={isFetchingNextPage}
              >
                {isFetchingNextPage ? (
                  <span className="inline-flex items-center gap-2">
                    <Loader2 className="size-4 animate-spin" />
                    {t('learn.library.loading_more', 'Loading more')}
                  </span>
                ) : (
                  t('learn.library.load_more', 'Load more lessons')
                )}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
