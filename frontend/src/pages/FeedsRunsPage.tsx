import { useState, useEffect, Fragment } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { fetchIngestRuns, fetchIngestRunSources } from '../api';
import type { IngestRun, IngestRunSource } from '../types';
import { formatDateTime, formatDuration } from '../lib/format';
import { relativeTime } from '../lib/format';

const PER_PAGE = 10;

export function FeedsRunsPage() {
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
      const data = await fetchIngestRuns(nextPage, PER_PAGE);
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
  }, [page]);

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

  const rangeStart = total === 0 ? 0 : (page - 1) * PER_PAGE + 1;
  const rangeEnd = Math.min(page * PER_PAGE, total);

  return (
    <div className="p-4 md:p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-[22px] font-semibold tracking-tight">Run History</h2>
        <Button variant="outline" size="sm" onClick={() => void loadRuns(page)} disabled={loading}>
          ↻ Refresh
        </Button>
      </div>

      {error && <p className="text-sm text-destructive mb-3">{error}</p>}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full rounded" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <p className="text-sm text-muted-foreground">No ingest runs recorded yet.</p>
      ) : (
        <>
          <div className="rounded-lg border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Started at</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Sources</TableHead>
                  <TableHead>New articles</TableHead>
                  <TableHead>Errors</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => {
                  const expanded = expandedRunId === run.id;
                  const sourceRows = sourcesByRun[run.id] ?? [];
                  return (
                    <Fragment key={run.id}>
                      <TableRow>
                        <TableCell>
                          <button
                            className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                            onClick={() => void toggleRun(run.id)}
                            aria-expanded={expanded}
                            aria-label={`${expanded ? 'Collapse' : 'Expand'} run ${run.id}`}
                          >
                            {expanded ? '⌄' : '›'}
                          </button>
                        </TableCell>
                        <TableCell>
                          <span className="font-medium text-sm">
                            {formatDateTime(run.started_at)}
                          </span>
                          <span className="block text-xs text-muted-foreground">
                            {relativeTime(run.started_at)}
                          </span>
                        </TableCell>
                        <TableCell className="text-sm">{formatDuration(run.duration_ms)}</TableCell>
                        <TableCell className="text-sm">{run.sources_run}</TableCell>
                        <TableCell className="text-sm">{run.total_new}</TableCell>
                        <TableCell className="text-sm">
                          {run.total_errors > 0 ? (
                            <span className="text-destructive font-semibold">
                              {run.total_errors}
                            </span>
                          ) : (
                            run.total_errors
                          )}
                        </TableCell>
                      </TableRow>
                      {expanded && (
                        <TableRow className="bg-muted/30">
                          <TableCell colSpan={6} className="p-0">
                            {loadingSources === run.id ? (
                              <p className="px-4 py-3 text-sm text-muted-foreground">
                                Loading source breakdown…
                              </p>
                            ) : sourceRows.length === 0 ? (
                              <p className="px-4 py-3 text-sm text-muted-foreground">
                                No per-source rows recorded for this run.
                              </p>
                            ) : (
                              <Table>
                                <TableHeader>
                                  <TableRow>
                                    <TableHead className="pl-8">Source name</TableHead>
                                    <TableHead>Found</TableHead>
                                    <TableHead>New</TableHead>
                                    <TableHead>Duplicates</TableHead>
                                    <TableHead>Error</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {sourceRows.map((source) => (
                                    <TableRow key={source.id}>
                                      <TableCell className="pl-8 text-sm font-medium">
                                        {source.source_name}
                                      </TableCell>
                                      <TableCell className="text-sm">
                                        {source.articles_found}
                                      </TableCell>
                                      <TableCell className="text-sm">
                                        {source.articles_new}
                                      </TableCell>
                                      <TableCell className="text-sm">{source.duplicates}</TableCell>
                                      <TableCell className="text-sm">
                                        {source.error_message ? (
                                          <span className="text-destructive">
                                            {source.error_message}
                                          </span>
                                        ) : (
                                          <span className="text-muted-foreground">—</span>
                                        )}
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            )}
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between mt-3 text-sm text-muted-foreground">
            <span>
              {rangeStart}–{rangeEnd} of {total}
            </span>
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={loading || page === 1}
              >
                ‹
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => p + 1)}
                disabled={loading || !hasMore}
              >
                ›
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
